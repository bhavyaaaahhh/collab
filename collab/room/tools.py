import json
from dataclasses import dataclass

from pydantic import ValidationError

from collab.room.models import FindingIn, Message, RoomError
from collab.room.room import Room

_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": _STR}


def _tool(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties or {}, "required": required or []},
    }


TOOL_DEFS: list[dict] = [
    _tool("send_message", "Post a message to the shared room. Your partner and the user see it.",
          {"text": _STR}, ["text"]),
    _tool("wait_for_messages",
          "Block up to ~40s for new messages from your partner, the user or the system. "
          "If it returns 'No new messages yet', call it again."),
    _tool("read_room", "Re-read room history, e.g. after losing context. `since` is a message seq number.",
          {"since": {"type": "integer"}}),
    _tool("list_findings", "Show the shared findings board with every finding, its stances and status."),
    _tool("post_finding", "Add one finding to the shared board. Returns its id.",
          {"cases": _STR_LIST, "issue": _STR, "evidence": _STR, "proposed_change": _STR,
           "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
          ["cases", "issue", "evidence", "proposed_change", "confidence"]),
    _tool("respond_to_finding", "Record your stance on your partner's finding.",
          {"id": _STR, "stance": {"type": "string", "enum": ["agree", "disagree", "partial"]},
           "reasoning": _STR, "amended_change": _STR},
          ["id", "stance", "reasoning"]),
    _tool("update_finding",
          "Revise one of your own findings (e.g. after conceding). `patch` holds any of: "
          "cases, issue, evidence, proposed_change, confidence.",
          {"id": _STR, "patch": {"type": "object"}}, ["id", "patch"]),
    _tool("propose_plan", "Propose how to divide the work. `slices` maps each agent to its part (split mode only).",
          {"mode": {"type": "string", "enum": ["independent", "split"]},
           "slices": {"type": "object", "additionalProperties": _STR}},
          ["mode"]),
    _tool("endorse_plan", "Endorse your partner's plan proposal.", {"plan_id": _STR}, ["plan_id"]),
    _tool("propose_conclusion", "Propose the final outcome: concrete changes, plus anything still unresolved.",
          {"changes": _STR_LIST, "unresolved": _STR_LIST}, ["changes", "unresolved"]),
    _tool("agree_to_conclusion", "Sign off on a conclusion proposal.", {"proposal_id": _STR}, ["proposal_id"]),
    _tool("reject_conclusion", "Reject a conclusion proposal with a reason.",
          {"proposal_id": _STR, "reason": _STR}, ["proposal_id", "reason"]),
    _tool("request_executor",
          "After both of you agreed on a conclusion, ask for an executor session to apply its changes.",
          {"proposal_id": _STR}, ["proposal_id"]),
]

TOOL_NAMES: list[str] = [t["name"] for t in TOOL_DEFS]


@dataclass
class Cursor:
    last_seq: int = 0


def _format(messages: list[Message]) -> str:
    return "\n\n".join(f"[{m.sender}] {m.text}" for m in messages)


def _board(room: Room) -> str:
    if not room.findings:
        return "No findings yet."
    lines = []
    for f in room.findings.values():
        lines.append(f"{f.id} by {f.author} [{room.finding_status(f)}] cases={','.join(f.cases)} "
                     f"confidence={f.confidence} rev={f.revision}")
        lines.append(f"  issue: {f.issue}")
        lines.append(f"  evidence: {f.evidence}")
        lines.append(f"  change: {f.proposed_change}")
        for s in f.stances:
            extra = f" | amended: {s.amended_change}" if s.amended_change else ""
            lines.append(f"  - {s.by}: {s.stance} — {s.reasoning}{extra}")
    return "\n".join(lines)


async def _call(room: Room, agent: str, cursor: Cursor, name: str, args: dict, wait_timeout_s: float) -> str:
    match name:
        case "send_message":
            room.post(agent, args["text"])
            return "sent"
        case "wait_for_messages":
            fresh = await room.wait_for(agent, cursor.last_seq, wait_timeout_s)
            cursor.last_seq = len(room.messages)
            return _format(fresh) if fresh else "No new messages yet. Call wait_for_messages again."
        case "read_room":
            history = room.messages[args.get("since", 0):]
            cursor.last_seq = len(room.messages)
            return _format(history) or "The room is empty."
        case "list_findings":
            return _board(room)
        case "post_finding":
            f = room.post_finding(agent, FindingIn.model_validate(args))
            return f"Posted {f.id}."
        case "respond_to_finding":
            f = room.respond(agent, args["id"], args["stance"], args["reasoning"], args.get("amended_change"))
            return f"Recorded. {f.id} is now {room.finding_status(f)}."
        case "update_finding":
            f = room.update_finding(agent, args["id"], args["patch"])
            return f"Updated {f.id} (revision {f.revision}). Ask your partner to re-review it."
        case "propose_plan":
            p = room.propose_plan(agent, args["mode"], args.get("slices"))
            return f"Proposed {p.id}. Your partner must endorse_plan it."
        case "endorse_plan":
            p = room.endorse_plan(agent, args["plan_id"])
            return f"Endorsed {p.id}."
        case "propose_conclusion":
            c = room.propose_conclusion(agent, args["changes"], args["unresolved"])
            return f"Proposed {c.id}. Your partner must agree_to_conclusion or reject_conclusion."
        case "agree_to_conclusion":
            c = room.agree_conclusion(agent, args["proposal_id"])
            done = room.concluded() is not None and room.concluded().id == c.id
            return f"Agreed to {c.id}." + (" Both agreed; the collaboration is concluded." if done else "")
        case "reject_conclusion":
            c = room.reject_conclusion(agent, args["proposal_id"], args["reason"])
            return f"Rejected {c.id}."
        case "request_executor":
            c = room.request_executor(agent, args["proposal_id"])
            return f"Executor requested for {c.id}. The user may need to approve first. You can end your turn."
    raise RoomError(f"unknown tool {name}")


async def dispatch(room: Room, agent: str, cursor: Cursor, name: str, args: dict, wait_timeout_s: float) -> str:
    """Run one room tool. Rule violations and bad arguments come back as text the agent can act on."""
    try:
        return await _call(room, agent, cursor, name, args or {}, wait_timeout_s)
    except RoomError as e:
        return f"Error: {e}"
    except ValidationError as e:
        return f"Error: invalid arguments: {json.dumps(e.errors(include_url=False), default=str)}"
    except (KeyError, TypeError) as e:
        return f"Error: missing or invalid argument {e}"
