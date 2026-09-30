import asyncio

import pytest

from collab.room.models import FindingIn, RoomError
from collab.room.room import Room

F = FindingIn(cases=["14"], issue="i", evidence="e", proposed_change="c", confidence="high")


def room():
    return Room(["claude", "codex"], "independent")


def test_messages_for_excludes_own_and_old():
    r = room()
    r.post("claude", "hi")
    r.post("codex", "yo")
    r.post("user", "focus")
    assert [m.text for m in r.messages_for("claude", 0)] == ["yo", "focus"]
    assert [m.text for m in r.messages_for("claude", 2)] == ["focus"]


async def test_wait_for_wakes_and_times_out():
    r = room()

    async def later():
        await asyncio.sleep(0.02)
        r.post("codex", "late")

    asyncio.create_task(later())
    assert [m.text for m in await r.wait_for("claude", 0, 1)] == ["late"]
    assert await r.wait_for("claude", 1, 0.03) == []


def test_finding_status():
    r = room()
    a = r.post_finding("claude", F)
    assert a.id == "claude-1"
    assert r.finding_status(a) == "open"
    r.respond("codex", a.id, "disagree", "no")
    assert r.finding_status(a) == "contested"
    r.update_finding("claude", a.id, {"proposed_change": "c2"})
    r.respond("codex", a.id, "agree", "ok")
    assert r.finding_status(a) == "resolved"
    b = r.post_finding("codex", F)
    r.respond("claude", b.id, "agree", "y")
    assert r.finding_status(b) == "agreed"


def test_rejects_self_stance_and_foreign_update():
    r = room()
    a = r.post_finding("claude", F)
    with pytest.raises(RoomError):
        r.respond("claude", a.id, "agree", "")
    with pytest.raises(RoomError):
        r.update_finding("codex", a.id, {})
    with pytest.raises(RoomError):
        r.respond("codex", "missing-9", "agree", "")


def test_update_finding_rejects_unknown_fields():
    r = room()
    a = r.post_finding("claude", F)
    with pytest.raises(RoomError):
        r.update_finding("claude", a.id, {"author": "codex"})


def test_split_plan_creates_checkpoint_after_both_endorse():
    r = room()
    ev = []
    r.subscribe(ev.append)
    p = r.propose_plan("claude", "split", {"claude": "1-18", "codex": "19-40"})
    assert not any(e.type == "checkpoint" for e in ev)
    r.endorse_plan("codex", p.id)
    cps = [e for e in ev if e.type == "checkpoint"]
    assert cps[0].data["kind"] == "plan"
    r.resolve_checkpoint(cps[0].data["id"], "approved")
    assert r.messages_for("claude", 0)[-1].text == "User approved the split plan."


def test_independent_plan_needs_no_checkpoint():
    r = room()
    ev = []
    r.subscribe(ev.append)
    p = r.propose_plan("claude", "independent")
    r.endorse_plan("codex", p.id)
    assert not any(e.type == "checkpoint" for e in ev)
    assert r.messages_for("claude", 0)[-1].text == "Plan accepted."


def test_request_executor_requires_agreement():
    r = room()
    c = r.propose_conclusion("claude", ["x"], [])
    with pytest.raises(RoomError, match="Both participants"):
        r.request_executor("claude", c.id)
    r.agree_conclusion("codex", c.id)
    assert r.concluded().id == c.id
    ev = []
    r.subscribe(ev.append)
    r.request_executor("claude", c.id)
    assert ev[-1].type == "executor_requested"


def test_reject_conclusion_posts_reason():
    r = room()
    c = r.propose_conclusion("claude", ["x"], [])
    r.reject_conclusion("codex", c.id, "missing case 22")
    assert r.concluded() is None
    assert "missing case 22" in r.messages_for("claude", 0)[-1].text


def test_executor_does_not_count_toward_conclusion():
    r = room()
    r.add_participant("executor")
    c = r.propose_conclusion("claude", ["x"], [])
    r.agree_conclusion("codex", c.id)
    assert r.concluded().id == c.id
