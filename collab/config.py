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


def load_config(path: Path = Path("collab.config.json")) -> Config:
    if not path.exists():
        return Config()
    return Config.model_validate(json.loads(path.read_text()))
