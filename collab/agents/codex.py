import json

from collab.agents.base import AgentEvent, Command, LaunchOpts, load_json_line, summarize


def _toml(value) -> str:
    """Render a -c override value as TOML (strings, string lists, string tables, ints)."""
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}={_toml(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_toml(v) for v in value) + "]"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value)


class CodexAdapter:
    kind = "codex"

    def build_command(self, o: LaunchOpts) -> Command:
        overrides = {
            "mcp_servers.room.command": o.bridge.command,
            "mcp_servers.room.args": o.bridge.args,
            "mcp_servers.room.env": o.bridge.env,
            "mcp_servers.room.tool_timeout_sec": 120,
            # Without this, codex exec cancels every MCP call ("approval policy is never").
            "mcp_servers.room.default_tools_approval_mode": "approve",
            "sandbox_mode": "workspace-write" if o.mode == "execute" else "read-only",
        }
        cfg = [arg for key, value in overrides.items() for arg in ("-c", f"{key}={_toml(value)}")]
        if o.model:
            cfg += ["-m", o.model]
        if o.resume_session_id:
            argv = [o.bin, "exec", "resume", o.resume_session_id, "--json", "--skip-git-repo-check", *cfg, o.prompt]
        else:
            argv = [o.bin, "exec", "--json", "--skip-git-repo-check", "-C", str(o.cwd), *cfg, o.prompt]
        return Command(argv=argv, env={})

    def parse_line(self, line: str) -> list[AgentEvent]:
        j = load_json_line(line)
        if j is None:
            return []
        item = j.get("item") or {}
        match j.get("type"), item.get("type"):
            case "thread.started", _:
                return [AgentEvent("session", {"session_id": j.get("thread_id")})]
            case "item.completed", "agent_message":
                return [AgentEvent("text", {"text": item.get("text", "")})]
            case "item.started", "mcp_tool_call":
                return [AgentEvent("tool_call", {"id": item.get("id"), "name": _mcp_name(item),
                                                 "input": item.get("arguments")})]
            case "item.completed", "mcp_tool_call":
                error = item.get("error")
                result = error.get("message") if isinstance(error, dict) else _mcp_text(item.get("result"))
                return [AgentEvent("tool_result", {"id": item.get("id"), "summary": summarize(result or ""),
                                                   "is_error": error is not None})]
            case "item.completed", "command_execution":
                return [
                    AgentEvent("tool_call", {"id": item.get("id"), "name": "shell", "input": item.get("command")}),
                    AgentEvent("tool_result", {"id": item.get("id"),
                                               "summary": summarize(item.get("aggregated_output", "")),
                                               "is_error": item.get("exit_code") not in (0, None)}),
                ]
            case "turn.completed", _:
                return [AgentEvent("turn_end", {"cost_usd": None})]
            case ("turn.failed" | "error"), _:
                error = j.get("error")
                message = error.get("message") if isinstance(error, dict) else j.get("message", "unknown error")
                return [AgentEvent("error", {"message": str(message)})]
        return []


def _mcp_name(item: dict) -> str:
    # Match Claude's naming so the dashboard shows room tools the same way for both agents.
    return f"mcp__{item.get('server')}__{item.get('tool')}"


def _mcp_text(result) -> str:
    if isinstance(result, dict):
        return summarize(result.get("content", result))
    return summarize(result or "")


codex = CodexAdapter()
