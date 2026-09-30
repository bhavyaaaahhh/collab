import json

from collab.agents.base import AgentEvent, Command, LaunchOpts, load_json_line, summarize
from collab.room.tools import TOOL_NAMES

READ_TOOLS = ["Read", "Grep", "Glob", "LS"]
WRITE_TOOLS = ["Edit", "Write", "MultiEdit", "Bash"]


class ClaudeAdapter:
    kind = "claude"

    def build_command(self, o: LaunchOpts) -> Command:
        mcp_path = o.work_dir / "mcp.json"
        mcp = {"mcpServers": {"room": {"command": o.bridge.command, "args": o.bridge.args, "env": o.bridge.env}}}
        tools = [f"mcp__room__{name}" for name in TOOL_NAMES] + READ_TOOLS
        if o.mode == "execute":
            tools += WRITE_TOOLS
        argv = [
            o.bin, "-p", o.prompt,
            "--output-format", "stream-json", "--verbose",
            "--mcp-config", str(mcp_path), "--strict-mcp-config",
            "--allowedTools", ",".join(tools),
            "--permission-mode", "acceptEdits" if o.mode == "execute" else "default",
        ]
        if o.resume_session_id:
            argv += ["--resume", o.resume_session_id]
        if o.model:
            argv += ["--model", o.model]
        return Command(argv=argv, env={"MCP_TOOL_TIMEOUT": "120000"}, files={mcp_path: json.dumps(mcp)})

    def parse_line(self, line: str) -> list[AgentEvent]:
        j = load_json_line(line)
        if j is None:
            return []
        match j.get("type"):
            case "system" if j.get("subtype") == "init":
                return [AgentEvent("session", {"session_id": j.get("session_id")})]
            case "assistant":
                return [e for block in _content(j) if (e := _assistant_block(block))]
            case "user":
                return [
                    AgentEvent("tool_result", {"id": b.get("tool_use_id"), "summary": summarize(b.get("content", "")),
                                               "is_error": bool(b.get("is_error"))})
                    for b in _content(j) if b.get("type") == "tool_result"
                ]
            case "result":
                events = [AgentEvent("error", {"message": summarize(j.get("result", ""))})] if j.get("is_error") else []
                return events + [AgentEvent("turn_end", {"cost_usd": j.get("total_cost_usd")})]
        return []


def _content(j: dict) -> list[dict]:
    content = (j.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _assistant_block(b: dict) -> AgentEvent | None:
    match b.get("type"):
        case "text" if b.get("text"):
            return AgentEvent("text", {"text": b["text"]})
        case "tool_use":
            return AgentEvent("tool_call", {"id": b.get("id"), "name": b.get("name"), "input": b.get("input")})
    return None


claude = ClaudeAdapter()
