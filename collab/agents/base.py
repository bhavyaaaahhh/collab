import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

AgentKind = Literal["claude", "codex"]
Mode = Literal["review", "execute"]
EventType = Literal["session", "text", "tool_call", "tool_result", "turn_end", "error"]


@dataclass
class AgentEvent:
    type: EventType
    data: dict[str, Any]


@dataclass
class Bridge:
    """How the CLI should launch the room MCP server."""

    command: str
    args: list[str]
    env: dict[str, str]


@dataclass
class LaunchOpts:
    prompt: str
    cwd: Path
    mode: Mode
    bridge: Bridge
    bin: str
    work_dir: Path  # where per-agent files (e.g. mcp config) are written
    resume_session_id: str | None = None
    model: str | None = None
    extra_allowed_tools: list[str] = field(default_factory=list)
    strict_mcp: bool = True
    env: dict[str, str] = field(default_factory=dict)  # agent-only env, applied over user settings


@dataclass
class Command:
    argv: list[str]
    env: dict[str, str]
    files: dict[Path, str] = field(default_factory=dict)


class AgentAdapter(Protocol):
    kind: AgentKind

    def build_command(self, o: LaunchOpts) -> Command: ...

    def parse_line(self, line: str) -> list[AgentEvent]: ...


def load_json_line(line: str) -> dict | None:
    """Parse one JSONL line into a dict, or None for blank, invalid or non-object lines."""
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def summarize(value: Any, limit: int = 200) -> str:
    """Short text preview of a tool result for the dashboard."""
    if isinstance(value, list):
        value = " ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in value)
    elif not isinstance(value, str):
        value = json.dumps(value, default=str)
    return value[:limit]
