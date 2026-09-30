from __future__ import annotations  # RunStore.list shadows the builtin inside the class body

import json
import secrets
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from collab.agents.base import AgentKind
from collab.config import Budget

RunStatus = Literal["running", "waiting", "completed", "stopped", "failed", "interrupted"]


class RunInput(BaseModel):
    task: str
    cwd: str
    attachments: list[str] = []
    agents: tuple[AgentKind, AgentKind] = ("claude", "codex")
    executor: AgentKind = "claude"
    default_mode: Literal["independent", "split"] = "independent"
    auto_apply: bool = False
    budget: Budget | None = None  # None → config default


class RunRecord(RunInput):
    id: str
    status: RunStatus = "running"
    created_at: float
    sessions: dict[str, str] = {}


class RunStore:
    """One folder per run: run.json, events.jsonl and artifacts (conclusion.md, executor.md, prompts)."""

    def __init__(self, root: Path = Path("runs")):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def dir(self, run_id: str) -> Path:
        return self.root / run_id

    def create(self, inp: RunInput) -> RunRecord:
        run_id = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        record = RunRecord(**inp.model_dump(), id=run_id, created_at=time.time())
        self.dir(run_id).mkdir(parents=True)
        self._save(record)
        return record

    def _save(self, record: RunRecord) -> None:
        (self.dir(record.id) / "run.json").write_text(record.model_dump_json(indent=2))

    def get(self, run_id: str) -> RunRecord | None:
        path = self.dir(run_id) / "run.json"
        return RunRecord.model_validate_json(path.read_text()) if path.exists() else None

    def update(self, run_id: str, **patch) -> RunRecord:
        record = self.get(run_id).model_copy(update=patch)
        self._save(record)
        return record

    def list(self) -> list[RunRecord]:
        records = [r for p in self.root.iterdir() if p.is_dir() and (r := self.get(p.name))]
        return sorted(records, key=lambda r: (r.created_at, r.id), reverse=True)

    def append(self, run_id: str, event: dict) -> None:
        with open(self.dir(run_id) / "events.jsonl", "a") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def events(self, run_id: str) -> list[dict]:
        path = self.dir(run_id) / "events.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue  # partial last line from a crash
        return events

    def write_artifact(self, run_id: str, name: str, content: str) -> None:
        path = self.dir(run_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
