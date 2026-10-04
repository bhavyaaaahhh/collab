import json
from pathlib import Path

from pydantic import BaseModel


class Budget(BaseModel):
    max_messages: int = 80
    max_minutes: int = 30


class Config(BaseModel):
    port: int = 4747
    bin: dict[str, str] = {"claude": "claude", "codex": "codex"}
    models: dict[str, str | None] = {"claude": None, "codex": None}
    budget: Budget = Budget()
    wait_timeout_s: float = 40
    # Extra tools Claude agents may use, e.g. an MCP tool your API proxy relies on.
    claude_extra_allowed_tools: list[str] = []
    # Env vars for Claude agent sessions only, applied over ~/.claude/settings.json. E.g. set ANTHROPIC_BASE_URL to
    # https://api.anthropic.com to skip a context-compressing proxy that agents can't retrieve from.
    claude_env: dict[str, str] = {}
    # False = Claude agents also load your own MCP servers (their tools still need claude_extra_allowed_tools).
    claude_strict_mcp: bool = True


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def load_config(path: Path = Path("collab.config.json")) -> Config:
    """Reads the config, then layers `<name>.local.json` (gitignored, for personal setup) on top."""
    data: dict = {}
    for p in (path, path.with_suffix(".local.json")):
        if p.exists():
            data = _merge(data, json.loads(p.read_text()))
    return Config.model_validate(data)
