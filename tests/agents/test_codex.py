from pathlib import Path

import pytest

from collab.agents.base import Bridge, LaunchOpts
from collab.agents.codex import codex

LINES = Path("tests/fixtures/codex.jsonl").read_text().splitlines()
EVENTS = [e for line in LINES for e in codex.parse_line(line)]


def opts(tmp_path, **kw):
    base = dict(prompt="p", cwd=tmp_path, mode="review", bin="codex", work_dir=tmp_path,
                bridge=Bridge("py", ["-m", "collab.bridge"], {"COLLAB_AGENT": "codex"}))
    return LaunchOpts(**{**base, **kw})


def test_extracts_stream():
    types = [e.type for e in EVENTS]
    assert types[0] == "session" and EVENTS[0].data["session_id"]
    assert "text" in types and "tool_result" in types
    assert any(e.type == "tool_call" and e.data["name"] == "mcp__room__wait_for_messages" for e in EVENTS)
    assert EVENTS[-1].type == "turn_end"


@pytest.mark.parametrize("line", ["", "garbage", '{"type":"turn.started"}', '{"type":"item.completed"}'])
def test_ignores_junk(line):
    assert codex.parse_line(line) == []


def test_command_execution_and_failure():
    item = '{"type":"item.completed","item":{"id":"i","type":"command_execution","command":"ls","aggregated_output":"a","exit_code":0}}'
    assert [e.type for e in codex.parse_line(item)] == ["tool_call", "tool_result"]
    assert codex.parse_line('{"type":"turn.failed","error":{"message":"x"}}')[0].type == "error"


def test_new_session_args(tmp_path):
    c = codex.build_command(opts(tmp_path))
    assert c.argv[:4] == ["codex", "exec", "--json", "--skip-git-repo-check"]
    s = " ".join(c.argv)
    assert f"-C {tmp_path}" in s
    assert 'mcp_servers.room.default_tools_approval_mode="approve"' in s
    assert "mcp_servers.room.tool_timeout_sec=120" in s
    assert 'sandbox_mode="read-only"' in s
    assert 'mcp_servers.room.env={COLLAB_AGENT="codex"}' in s
    assert c.argv[-1] == "p"


def test_resume_execute_args(tmp_path):
    c = codex.build_command(opts(tmp_path, mode="execute", resume_session_id="s1", model="gpt-6"))
    assert c.argv[:4] == ["codex", "exec", "resume", "s1"]
    s = " ".join(c.argv)
    assert 'sandbox_mode="workspace-write"' in s and "-m gpt-6" in s and "-C" not in c.argv
