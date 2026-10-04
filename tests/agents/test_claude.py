import json
from pathlib import Path

import pytest

from collab.agents.base import Bridge, LaunchOpts
from collab.agents.claude import claude

LINES = Path("tests/fixtures/claude.jsonl").read_text().splitlines()
EVENTS = [e for line in LINES for e in claude.parse_line(line)]


def opts(tmp_path, **kw):
    base = dict(prompt="p", cwd=tmp_path, mode="review", bin="claude", work_dir=tmp_path,
                bridge=Bridge("py", ["-m", "collab.bridge"], {"COLLAB_AGENT": "claude"}))
    return LaunchOpts(**{**base, **kw})


def test_extracts_stream():
    types = [e.type for e in EVENTS]
    assert types[0] == "session" and EVENTS[0].data["session_id"]
    assert "text" in types and "tool_result" in types
    assert any(e.type == "tool_call" and e.data["name"] == "mcp__room__send_message" for e in EVENTS)
    assert EVENTS[-1].type == "turn_end" and EVENTS[-1].data["cost_usd"] > 0


@pytest.mark.parametrize("line", ["", "not json", "[1]", '{"type":"rate_limit_event"}', '{"type":"assistant"}',
                                  '{"type":"assistant","message":{"content":"oops"}}'])
def test_ignores_junk(line):
    assert claude.parse_line(line) == []


def test_error_result():
    out = claude.parse_line('{"type":"result","is_error":true,"result":"boom","total_cost_usd":0}')
    assert [e.type for e in out] == ["error", "turn_end"]


def test_review_is_read_only_and_resumes(tmp_path):
    c = claude.build_command(opts(tmp_path, resume_session_id="s1", model="claude-sonnet-5-5"))
    s = " ".join(c.argv)
    assert "--resume s1" in s and "--permission-mode default" in s and "--model claude-sonnet-5-5" in s
    tools = c.argv[c.argv.index("--allowedTools") + 1].split(",")
    assert "mcp__room__wait_for_messages" in tools and "Read" in tools and "Edit" not in tools
    assert c.env["MCP_TOOL_TIMEOUT"] == "120000"
    settings = json.loads(c.argv[c.argv.index("--settings") + 1])
    assert settings == {"disableAllHooks": True, "env": {"ENABLE_TOOL_SEARCH": "false"}}
    mcp = json.loads(c.files[tmp_path / "mcp.json"])
    assert mcp["mcpServers"]["room"]["env"]["COLLAB_AGENT"] == "claude"


def test_mcp_isolation_and_extra_tools(tmp_path):
    assert "--strict-mcp-config" in claude.build_command(opts(tmp_path)).argv
    loose = claude.build_command(opts(tmp_path, strict_mcp=False, extra_allowed_tools=["mcp__headroom__headroom_retrieve"]))
    assert "--strict-mcp-config" not in loose.argv
    assert "mcp__headroom__headroom_retrieve" in loose.argv[loose.argv.index("--allowedTools") + 1]
    assert "--strict-mcp-config" in claude.build_command(opts(tmp_path, strict_mcp=True)).argv


def test_agent_env_goes_into_settings(tmp_path):
    c = claude.build_command(opts(tmp_path, env={"ANTHROPIC_BASE_URL": "https://api.anthropic.com"}))
    env = json.loads(c.argv[c.argv.index("--settings") + 1])["env"]
    assert env == {"ENABLE_TOOL_SEARCH": "false", "ANTHROPIC_BASE_URL": "https://api.anthropic.com"}


def test_execute_can_edit(tmp_path):
    c = claude.build_command(opts(tmp_path, mode="execute"))
    s = " ".join(c.argv)
    assert "--permission-mode acceptEdits" in s and "Edit" in s and "--resume" not in s
