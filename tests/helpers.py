import asyncio
from pathlib import Path

from collab.agents.base import AgentEvent, Bridge
from collab.config import Budget, Config
from collab.runs.run import Run, RunDeps
from collab.runs.store import RunInput, RunStore

TEMPLATE = "You are {{me}} ({{role}}), partner {{partner}}."


class FakeSpawn:
    """Each agent is a script: `async def script(tool, attempt, opts) -> exit_code`.
    `tool(name, args)` calls run.call_tool as that agent."""

    def __init__(self, scripts):
        self.scripts = scripts
        self.calls = []  # (agent, mode, resume_session_id, prompt)
        self.killed = []
        self.run = None

    async def __call__(self, adapter, o, on_event):
        agent = o.bridge.env["COLLAB_AGENT"]
        attempt = sum(1 for c in self.calls if c[0] == agent) + 1
        self.calls.append((agent, o.mode, o.resume_session_id, o.prompt))
        on_event(AgentEvent("session", {"session_id": f"{agent}-s"}))

        def tool(name, args=None):
            return self.run.call_tool(agent, name, args or {})

        task = asyncio.create_task(self.scripts[agent](tool, attempt, o))
        fake = self

        class Proc:
            async def wait(self):
                try:
                    return await task
                except asyncio.CancelledError:
                    return -9

            def kill(self):
                fake.killed.append(agent)
                task.cancel()

        return Proc()

    def spawned(self, agent):
        return [c for c in self.calls if c[0] == agent]


def make_run(tmp_path: Path, scripts, **inp) -> tuple[Run, FakeSpawn]:
    fake = FakeSpawn(scripts)
    config = Config(wait_timeout_s=0.05, budget=Budget(max_messages=80, max_minutes=30))
    deps = RunDeps(
        store=RunStore(tmp_path / "runs"),
        adapters={"claude": object(), "codex": object()},
        spawn=fake,
        template=TEMPLATE,
        config=config,
        bridge_for=lambda run_id, agent: Bridge("x", [], {"COLLAB_AGENT": agent}),
    )
    record = deps.store.create(RunInput(task="do it", cwd=str(tmp_path), **inp))
    run = Run(record, deps)
    fake.run = run
    return run, fake


async def until(cond, timeout=3.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        if loop.time() > end:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


async def idle(tool, attempt, o):
    """An agent that stays in the conversation until killed."""
    while True:
        await tool("wait_for_messages")


FINDING = {"cases": ["1"], "issue": "i", "evidence": "e", "proposed_change": "fix prompt", "confidence": "high"}
