import asyncio
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from collab.agents.base import AgentAdapter, AgentEvent, AgentKind, Bridge, LaunchOpts
from collab.config import Budget, Config
from collab.room.models import Conclusion, RoomEvent
from collab.room.room import Room
from collab.room.tools import Cursor, dispatch
from collab.runs.prompt import agent_names, build_prompt
from collab.runs.store import RunRecord, RunStatus, RunStore

AgentStatus = Literal["starting", "working", "waiting", "stalled", "done", "failed"]

NUDGE = "The collaboration is still open. Call wait_for_messages and continue."
MAX_IDLE_EXITS = 3
MAX_CRASHES = 2
WRAP_UP_AT = 0.8
WRAP_UP = "Budget nearly used: wrap up now — propose_conclusion and list open disagreements as unresolved."
EXHAUSTED = "Budget exhausted: agree on a conclusion now. You won't be restarted after this turn."
EXECUTOR = "executor"


@dataclass
class RunDeps:
    store: RunStore
    adapters: dict[str, AgentAdapter]
    spawn: Callable  # same signature as collab.agents.spawn.spawn_agent
    template: str
    config: Config
    bridge_for: Callable[[str, str], Bridge]


@dataclass
class Agent:
    name: str
    kind: AgentKind
    role: Literal["reviewer", "executor"]
    prompt: str
    cursor: Cursor = field(default_factory=Cursor)
    status: AgentStatus = "starting"
    session_id: str | None = None
    process: object | None = None
    active: bool = False  # called a room tool since the last (re)start
    idle_exits: int = 0
    crashes: int = 0
    last_text: str = ""


class Run:
    """One collaboration: the room, the agent processes that talk in it, and the rules around them
    (keep-alive, budget, checkpoints, executor hand-off)."""

    def __init__(self, record: RunRecord, deps: RunDeps):
        self.record = record
        self.deps = deps
        self.id = record.id
        self.dir: Path = deps.store.dir(record.id)
        self.budget: Budget = record.budget or deps.config.budget
        self.reviewers = agent_names(record.agents)
        self.room = Room(list(self.reviewers), record.default_mode)
        self.room.subscribe(self._on_room_event)
        self.agents: dict[str, Agent] = {}
        self.messages_sent = 0
        self.wrap_up_sent = False
        self.exhausted = False
        self.started_at = 0.0
        self._subscribers: list[Callable[[dict], None]] = []
        self._tasks: set[asyncio.Task] = set()
        self._finished = asyncio.Event()
        self._executor_requested = False
        self._n = 0

    # --- events ---

    def subscribe(self, fn: Callable[[dict], None]) -> None:
        self._subscribers.append(fn)

    def unsubscribe(self, fn: Callable[[dict], None]) -> None:
        if fn in self._subscribers:
            self._subscribers.remove(fn)

    def _record(self, event: dict) -> None:
        # n orders events so a stream can replay events.jsonl and then follow live without duplicates.
        self._n += 1
        event = {"n": self._n, "at": time.time(), **event}
        self.deps.store.append(self.id, event)
        for fn in self._subscribers:
            fn(event)

    def _on_room_event(self, e: RoomEvent) -> None:
        self._record({"kind": "room", "event": e.model_dump()})
        if e.type == "checkpoint":
            self._set_run_status("waiting" if e.data["status"] == "pending" else "running")
        elif e.type == "executor_requested" and not self._executor_requested:
            self._executor_requested = True
            self._spawn_task(self._on_executor_requested(e.data["conclusion_id"]))

    def _set_run_status(self, status: RunStatus) -> None:
        if self.record.status == status or self._closed:
            return
        self.record = self.deps.store.update(self.id, status=status)
        self._record({"kind": "run", "status": status})

    def _set_agent_status(self, agent: Agent, status: AgentStatus) -> None:
        if agent.status != status:
            agent.status = status
            self._record({"kind": "status", "agent": agent.name, "status": status})

    def agent_status(self, name: str) -> AgentStatus | None:
        return self.agents[name].status if name in self.agents else None

    @property
    def finished(self) -> bool:
        return self._closed

    @property
    def _closed(self) -> bool:
        return self.record.status in ("completed", "stopped", "failed")

    def _spawn_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # --- lifecycle ---

    async def start(self) -> None:
        self.started_at = time.time()
        self._record({"kind": "run", "status": "running"})
        for me, partner in (self.reviewers, self.reviewers[::-1]):
            kind = self.record.agents[self.reviewers.index(me)]
            self._add_agent(me, kind, "reviewer", self._prompt(me, partner, "reviewer"))
        self._spawn_task(self._budget_clock())

    def _prompt(self, me: str, partner: str, role: Literal["reviewer", "executor"], extra: str = "") -> str:
        prompt = build_prompt(
            self.deps.template, me=me, partner=partner, cwd=self.record.cwd, attachments=self.record.attachments,
            default_mode=self.record.default_mode, budget=self.budget, task=self.record.task, role=role,
        ) + extra
        self.deps.store.write_artifact(self.id, f"prompts/{me}.md", prompt)
        return prompt

    def _add_agent(self, name: str, kind: AgentKind, role: Literal["reviewer", "executor"], prompt: str) -> None:
        agent = Agent(name=name, kind=kind, role=role, prompt=prompt)
        self.agents[name] = agent
        self._spawn_task(self._supervise(agent))

    async def _launch(self, agent: Agent, prompt: str) -> int:
        opts = LaunchOpts(
            prompt=prompt,
            cwd=Path(self.record.cwd),
            mode="execute" if agent.role == "executor" else "review",
            bridge=self.deps.bridge_for(self.id, agent.name),
            bin=self.deps.config.bin.get(agent.kind, agent.kind),
            work_dir=self.dir / "agents" / agent.name,
            resume_session_id=agent.session_id,
            model=self.deps.config.models.get(agent.kind),
            extra_allowed_tools=self.deps.config.claude_extra_allowed_tools,
            strict_mcp=self.deps.config.claude_strict_mcp,
            env=self.deps.config.claude_env if agent.kind == "claude" else {},
        )
        agent.active = False
        self._set_agent_status(agent, "working")
        try:
            agent.process = await self.deps.spawn(self.deps.adapters[agent.kind], opts, lambda e: self._on_agent(agent, e))
        except OSError as e:
            self._on_agent(agent, AgentEvent("error", {"message": f"could not start {opts.bin}: {e}"}))
            return 127
        return await agent.process.wait()

    def _on_agent(self, agent: Agent, e: AgentEvent) -> None:
        if e.type == "session" and e.data.get("session_id") and agent.session_id != e.data["session_id"]:
            agent.session_id = e.data["session_id"]
            self.record.sessions[agent.name] = agent.session_id
            self.record = self.deps.store.update(self.id, sessions=self.record.sessions)
        if e.type == "text":
            agent.last_text = e.data.get("text", "")
        self._record({"kind": "agent", "agent": agent.name, "event": {"type": e.type, "data": e.data}})

    async def _supervise(self, agent: Agent) -> None:
        prompt = agent.prompt
        while True:
            code = await self._launch(agent, prompt)
            if self._closed:
                return
            if agent.role == "executor":
                await self._finish_executor(agent)
                return
            outcome = self._after_exit(agent, code)
            if outcome is not None:
                self._set_agent_status(agent, outcome)
                self._maybe_finish()
                return
            # Resuming keeps the agent's memory; without a session id we can only start over.
            prompt = NUDGE if agent.session_id else agent.prompt

    def _after_exit(self, agent: Agent, code: int) -> AgentStatus | None:
        """Decide what an exited reviewer becomes. None means: resume it."""
        if self.room.concluded() or self.exhausted:
            return "done"
        agent.crashes = agent.crashes + 1 if code != 0 else 0
        if agent.crashes >= MAX_CRASHES:
            self.room.post("system", f"{agent.name} failed (exit {code}) and won't be restarted.")
            return "failed"
        agent.idle_exits = 0 if agent.active else agent.idle_exits + 1
        if agent.idle_exits >= MAX_IDLE_EXITS:
            self.room.post("system", f"{agent.name} stalled: it keeps ending its turn without using the room.")
            return "stalled"
        return None

    def _maybe_finish(self) -> None:
        """Called when a reviewer stops for good. Completes the run unless an executor hand-off is in flight."""
        reviewers = [self.agents[n] for n in self.reviewers]
        if self._closed or self._executor_requested or any(a.status not in ("done", "stalled", "failed") for a in reviewers):
            return
        self._write_conclusion(self.room.concluded())
        self._complete()

    def _complete(self, status: RunStatus = "completed") -> None:
        if self._closed:
            return
        self._set_run_status(status)
        for agent in self.agents.values():
            if agent.process:
                agent.process.kill()
            if agent.status in ("starting", "working", "waiting"):
                agent.status = "done"
                self._record({"kind": "status", "agent": agent.name, "status": "done"})
        for task in self._tasks:
            if task is not asyncio.current_task():
                task.cancel()
        self._finished.set()

    async def stop(self) -> None:
        self._complete("stopped")

    async def done(self) -> None:
        await self._finished.wait()

    # --- tools ---

    async def call_tool(self, agent_name: str, name: str, args: dict) -> str:
        agent = self.agents.get(agent_name)
        if agent is None:
            return f"Error: {agent_name} is not part of this run."
        agent.active = True
        agent.idle_exits = 0
        waiting = name == "wait_for_messages"
        self._set_agent_status(agent, "waiting" if waiting else "working")
        out = await dispatch(self.room, agent_name, agent.cursor, name, args, self.deps.config.wait_timeout_s)
        if waiting and not self._closed:
            self._set_agent_status(agent, "working")
        if name == "send_message" and agent.role == "reviewer" and not out.startswith("Error"):
            self.messages_sent += 1
            self._check_budget()
        return out

    def user_message(self, text: str) -> None:
        self.room.post("user", text)

    # --- budget ---

    def _check_budget(self) -> None:
        used = max(self.messages_sent / self.budget.max_messages,
                   (time.time() - self.started_at) / (self.budget.max_minutes * 60))
        if used >= WRAP_UP_AT and not self.wrap_up_sent:
            self.wrap_up_sent = True
            self.room.post("system", WRAP_UP)
        if used >= 1 and not self.exhausted:
            self.exhausted = True
            self.room.post("system", EXHAUSTED)

    async def _budget_clock(self) -> None:
        total = self.budget.max_minutes * 60
        await asyncio.sleep(total * WRAP_UP_AT)
        self._check_budget()
        await asyncio.sleep(total * (1 - WRAP_UP_AT))
        self._check_budget()

    # --- checkpoints + executor ---

    async def resolve_checkpoint(self, checkpoint_id: str, decision: Literal["approved", "rejected"],
                                 selected: list[int] | None = None, note: str | None = None) -> None:
        cp = self.room.resolve_checkpoint(checkpoint_id, decision, selected, note)
        if cp.kind != "apply":
            return
        if decision == "approved":
            self._start_executor(self.room.conclusions[cp.ref_id], selected, note)
        else:
            self._complete()

    async def _on_executor_requested(self, conclusion_id: str) -> None:
        conclusion = self.room.conclusions[conclusion_id]
        self._write_conclusion(conclusion)
        if self.record.auto_apply:
            self._start_executor(conclusion, None, None)
        else:
            self.room.open_apply_checkpoint(conclusion_id)

    def _start_executor(self, conclusion: Conclusion, selected: list[int] | None, note: str | None) -> None:
        changes = [c for i, c in enumerate(conclusion.changes) if selected is None or i in selected]
        extra = "\n\n## Your job\n\nApply exactly these approved changes:\n" + "".join(f"\n- {c}" for c in changes)
        if note:
            extra += f"\n\nUser note: {note}"
        extra += ("\n\nDo not commit. The reviewers are still in the room if you need to ask something. "
                  "When done, send_message a summary of what you changed and end your turn.")
        self.room.add_participant(EXECUTOR)
        prompt = self._prompt(EXECUTOR, " and ".join(self.reviewers), "executor", extra)
        self._add_agent(EXECUTOR, self.record.executor, "executor", prompt)

    async def _finish_executor(self, agent: Agent) -> None:
        self._set_agent_status(agent, "done")
        diff = await asyncio.to_thread(_git_diff_stat, Path(self.record.cwd))
        said = [m.text for m in self.room.messages if m.sender == agent.name]
        body = f"# Executor summary\n\n{(said[-1] if said else agent.last_text) or '(no summary)'}\n"
        if diff is not None:
            body += f"\n## git diff --stat\n\n```\n{diff or '(no changes)'}\n```\n"
        self.deps.store.write_artifact(self.id, "executor.md", body)
        self._complete()

    def _write_conclusion(self, conclusion: Conclusion | None) -> None:
        by_status: dict[str, list[str]] = {"agreed": [], "resolved": [], "contested": [], "open": []}
        for f in self.room.findings.values():
            by_status[self.room.finding_status(f)].append(f"{f.id} ({f.author}): {f.issue} → {f.proposed_change}")
        lines = [f"# Conclusion — run {self.id}", ""]
        if conclusion:
            lines += [f"Agreed by {', '.join(conclusion.agreed_by)} ({conclusion.id}).", "", "## Changes", ""]
            lines += [f"{i + 1}. {c}" for i, c in enumerate(conclusion.changes)] or ["(none)"]
            unresolved = conclusion.unresolved + [f"{x} (still contested)" for x in by_status["contested"]]
        else:
            lines += ["The agents did not agree on a conclusion. Built from the findings board.", "", "## Changes", ""]
            lines += [f"- {x}" for x in by_status["agreed"] + by_status["resolved"]] or ["(none)"]
            unresolved = by_status["contested"] + [f"{x} (never reviewed)" for x in by_status["open"]]
        lines += ["", "## Unresolved", ""] + ([f"- {x}" for x in unresolved] or ["(none)"])
        self.deps.store.write_artifact(self.id, "conclusion.md", "\n".join(lines) + "\n")

    def snapshot(self) -> dict:
        return {
            "record": self.record.model_dump(),
            "room": self.room.snapshot(),
            "agents": {a.name: {"kind": a.kind, "role": a.role, "status": a.status} for a in self.agents.values()},
            "budget": {**self.budget.model_dump(), "messages_sent": self.messages_sent, "started_at": self.started_at},
        }


def _git_diff_stat(cwd: Path) -> str | None:
    try:
        inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=cwd, capture_output=True, text=True)
        if inside.returncode != 0:
            return None
        return subprocess.run(["git", "diff", "--stat"], cwd=cwd, capture_output=True, text=True).stdout.strip()
    except OSError:
        return None
