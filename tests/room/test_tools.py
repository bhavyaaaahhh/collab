from collab.room.room import Room
from collab.room.tools import TOOL_DEFS, TOOL_NAMES, Cursor, dispatch

FINDING = {"cases": ["1"], "issue": "i", "evidence": "e", "proposed_change": "c", "confidence": "low"}


def room():
    return Room(["claude", "codex"], "independent")


def test_every_tool_has_object_schema():
    assert "wait_for_messages" in TOOL_NAMES
    assert all(t["inputSchema"]["type"] == "object" for t in TOOL_DEFS)
    assert len(set(TOOL_NAMES)) == len(TOOL_NAMES)


async def test_send_wait_round_trip():
    r = room()
    cc, xc = Cursor(), Cursor()
    await dispatch(r, "claude", cc, "send_message", {"text": "hello"}, 0.03)
    assert "[claude] hello" in await dispatch(r, "codex", xc, "wait_for_messages", {}, 0.03)
    assert "No new messages" in await dispatch(r, "codex", xc, "wait_for_messages", {}, 0.03)


async def test_errors_are_text():
    r = room()
    out = await dispatch(r, "claude", Cursor(), "request_executor", {"proposal_id": "nope"}, 0.03)
    assert out.startswith("Error:")
    assert (await dispatch(r, "claude", Cursor(), "post_finding", {"cases": 1}, 0.03)).startswith("Error:")
    assert (await dispatch(r, "claude", Cursor(), "fly", {}, 0.03)).startswith("Error: unknown tool")


async def test_post_finding_returns_id():
    out = await dispatch(room(), "claude", Cursor(), "post_finding", FINDING, 0.03)
    assert "claude-1" in out


async def test_debate_flow_through_tools():
    r = room()
    await dispatch(r, "claude", Cursor(), "post_finding", FINDING, 0.03)
    out = await dispatch(
        r, "codex", Cursor(), "respond_to_finding", {"id": "claude-1", "stance": "disagree", "reasoning": "no"}, 0.03
    )
    assert "contested" in out
    board = await dispatch(r, "codex", Cursor(), "list_findings", {}, 0.03)
    assert "claude-1" in board and "contested" in board
    out = await dispatch(r, "claude", Cursor(), "propose_conclusion", {"changes": ["x"], "unresolved": []}, 0.03)
    assert "conclusion-1" in out
    await dispatch(r, "codex", Cursor(), "agree_to_conclusion", {"proposal_id": "conclusion-1"}, 0.03)
    out = await dispatch(r, "claude", Cursor(), "request_executor", {"proposal_id": "conclusion-1"}, 0.03)
    assert not out.startswith("Error")


async def test_read_room_since():
    r = room()
    r.post("claude", "a")
    r.post("codex", "b")
    out = await dispatch(r, "claude", Cursor(), "read_room", {"since": 1}, 0.03)
    assert "[codex] b" in out and "[claude] a" not in out
