import asyncio

import pytest

from collab.room.models import RoomError
from tests.helpers import FINDING, idle, make_run, until


async def test_resumes_agent_that_exits_early(tmp_path):
    async def claude(tool, attempt, o):
        if attempt == 1:
            return 0  # exits without touching the room
        await tool("propose_conclusion", {"changes": ["x"], "unresolved": []})
        while not run.room.concluded():
            await tool("wait_for_messages")
        return 0

    async def codex(tool, attempt, o):
        while not run.room.conclusions:
            await tool("wait_for_messages")
        await tool("agree_to_conclusion", {"proposal_id": "conclusion-1"})
        return 0

    run, fake = make_run(tmp_path, {"claude": claude, "codex": codex})
    await run.start()
    await asyncio.wait_for(run.done(), 3)
    calls = fake.spawned("claude")
    assert len(calls) == 2
    assert calls[1][2] == "claude-s" and "still open" in calls[1][3]
    assert run.room.concluded() is not None
    assert run.record.status == "completed"
    assert "conclusion.md" in {p.name for p in run.dir.iterdir()}


async def test_stalls_after_three_idle_exits(tmp_path):
    async def silent(tool, attempt, o):
        return 0

    run, fake = make_run(tmp_path, {"claude": idle, "codex": silent})
    await run.start()
    await until(lambda: run.agent_status("codex") == "stalled")
    assert len(fake.spawned("codex")) == 3  # 3 exits in a row without using the room
    assert any("codex" in m.text and "stalled" in m.text for m in run.room.messages if m.sender == "system")
    await run.stop()


async def test_failed_after_two_crashes(tmp_path):
    async def crash(tool, attempt, o):
        return 1

    run, fake = make_run(tmp_path, {"claude": idle, "codex": crash})
    await run.start()
    await until(lambda: run.agent_status("codex") == "failed")
    assert len(fake.spawned("codex")) == 2
    await run.stop()


async def test_budget_wrap_up_and_unresolved(tmp_path):
    async def claude(tool, attempt, o):
        await tool("post_finding", FINDING)
        for i in range(3):
            await tool("send_message", {"text": f"c{i}"})
        return 0

    async def codex(tool, attempt, o):
        while not run.room.findings:
            await tool("wait_for_messages")
        await tool("respond_to_finding", {"id": "claude-1", "stance": "disagree", "reasoning": "no"})
        for i in range(3):
            await tool("send_message", {"text": f"x{i}"})
        return 0

    run, fake = make_run(tmp_path, {"claude": claude, "codex": codex}, budget={"max_messages": 5, "max_minutes": 30})
    await run.start()
    await asyncio.wait_for(run.done(), 3)
    system = [m.text for m in run.room.messages if m.sender == "system"]
    assert any("wrap up" in t for t in system) and any("Budget exhausted" in t for t in system)
    assert len(fake.spawned("claude")) == 1 and len(fake.spawned("codex")) == 1  # no resumes after budget
    conclusion = (run.dir / "conclusion.md").read_text()
    assert "Unresolved" in conclusion and "claude-1" in conclusion.split("Unresolved")[1]
    assert run.record.status == "completed"


def _concluding_pair(run_ref, request=True):
    async def claude(tool, attempt, o):
        await tool("propose_conclusion", {"changes": ["change A", "change B"], "unresolved": []})
        while not run_ref[0].room.concluded():
            await tool("wait_for_messages")
        if request:
            await tool("request_executor", {"proposal_id": "conclusion-1"})
        return 0

    async def codex(tool, attempt, o):
        while not run_ref[0].room.conclusions:
            await tool("wait_for_messages")
        await tool("agree_to_conclusion", {"proposal_id": "conclusion-1"})
        return 0

    async def executor(tool, attempt, o):
        await tool("send_message", {"text": "applied"})
        return 0

    return {"claude": claude, "codex": codex, "executor": executor}


async def test_apply_gate_then_executor(tmp_path):
    ref = [None]
    run, fake = make_run(tmp_path, _concluding_pair(ref))
    ref[0] = run
    await run.start()
    await until(lambda: run.record.status == "waiting")
    cp = next(c for c in run.room.checkpoints.values() if c.kind == "apply")
    assert fake.spawned("executor") == []
    await run.resolve_checkpoint(cp.id, "approved", selected=[1], note="be careful")
    with pytest.raises(RoomError, match="already approved"):
        await run.resolve_checkpoint(cp.id, "approved")
    await asyncio.wait_for(run.done(), 3)
    (agent, mode, _, prompt), = fake.spawned("executor")
    assert mode == "execute"
    assert "change B" in prompt and "change A" not in prompt and "be careful" in prompt
    assert run.record.status == "completed"
    assert (run.dir / "executor.md").exists()


async def test_apply_rejected_completes_without_executor(tmp_path):
    ref = [None]
    run, fake = make_run(tmp_path, _concluding_pair(ref))
    ref[0] = run
    await run.start()
    await until(lambda: run.record.status == "waiting")
    cp = next(iter(run.room.checkpoints.values()))
    await run.resolve_checkpoint(cp.id, "rejected")
    await asyncio.wait_for(run.done(), 3)
    assert fake.spawned("executor") == [] and run.record.status == "completed"


async def test_auto_apply_skips_gate(tmp_path):
    ref = [None]
    run, fake = make_run(tmp_path, _concluding_pair(ref), auto_apply=True)
    ref[0] = run
    await run.start()
    await asyncio.wait_for(run.done(), 3)
    assert not run.room.checkpoints
    assert len(fake.spawned("executor")) == 1


async def test_conclusion_without_executor_request_completes(tmp_path):
    ref = [None]
    run, fake = make_run(tmp_path, _concluding_pair(ref, request=False))
    ref[0] = run
    await run.start()
    await asyncio.wait_for(run.done(), 3)
    assert run.record.status == "completed" and fake.spawned("executor") == []
    assert "change A" in (run.dir / "conclusion.md").read_text()


async def test_split_plan_waits_for_user(tmp_path):
    seen = []

    async def claude(tool, attempt, o):
        await tool("propose_plan", {"mode": "split", "slices": {"claude": "1-4", "codex": "5-8"}})
        while True:
            out = await tool("wait_for_messages")
            if "approved the split" in out:
                seen.append(out)
                return 0

    async def codex(tool, attempt, o):
        while not run.room.plans:
            await tool("wait_for_messages")
        await tool("endorse_plan", {"plan_id": "plan-1"})
        await idle(tool, attempt, o)

    run, fake = make_run(tmp_path, {"claude": claude, "codex": codex})
    await run.start()
    await until(lambda: run.record.status == "waiting")
    cp = next(iter(run.room.checkpoints.values()))
    await run.resolve_checkpoint(cp.id, "approved")
    await until(lambda: seen)
    assert run.record.status == "running"
    await run.stop()


async def test_user_message_reaches_agents(tmp_path):
    got = []

    async def listener(tool, attempt, o):
        while True:
            out = await tool("wait_for_messages")
            if "[user]" in out:
                got.append(out)
                await idle(tool, attempt, o)

    run, fake = make_run(tmp_path, {"claude": listener, "codex": idle})
    await run.start()
    run.user_message("focus on case 3")
    await until(lambda: got)
    assert "focus on case 3" in got[0]
    await run.stop()


async def test_stop_kills_everything(tmp_path):
    run, fake = make_run(tmp_path, {"claude": idle, "codex": idle})
    await run.start()
    await until(lambda: len(fake.calls) == 2)
    await run.stop()
    await asyncio.wait_for(run.done(), 3)
    assert sorted(fake.killed) == ["claude", "codex"]
    assert run.record.status == "stopped"
    assert run.deps.store.get(run.id).status == "stopped"
    assert run.agent_status("claude") == run.agent_status("codex") == "done"
    kinds = {e["kind"] for e in run.deps.store.events(run.id)}
    assert {"agent", "status", "run"} <= kinds
    assert len(fake.calls) == 2  # nothing resumed after stop


async def test_same_kind_agents_get_distinct_names(tmp_path):
    run, fake = make_run(tmp_path, {"claude-1": idle, "claude-2": idle}, agents=("claude", "claude"))
    await run.start()
    await until(lambda: len(fake.calls) == 2)
    assert {c[0] for c in fake.calls} == {"claude-1", "claude-2"}
    assert "partner claude-2" in fake.spawned("claude-1")[0][3]
    await run.stop()
