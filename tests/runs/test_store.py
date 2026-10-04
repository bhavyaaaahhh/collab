from collab.runs.store import RunInput, RunStore


def test_round_trip(tmp_path):
    s = RunStore(tmp_path)
    r = s.create(RunInput(task="t", cwd="/w"))
    assert r.status == "running" and r.agents == ("claude", "codex")
    s.append(r.id, {"at": 1, "kind": "run", "status": "running"})
    s.append(r.id, {"at": 2, "kind": "run", "status": "stopped"})
    assert [e["status"] for e in s.events(r.id)] == ["running", "stopped"]
    assert s.update(r.id, status="stopped").status == "stopped"
    assert s.get(r.id).status == "stopped"
    s.write_artifact(r.id, "conclusion.md", "# done")
    assert (s.dir(r.id) / "conclusion.md").read_text() == "# done"


def test_list_newest_first_and_missing(tmp_path):
    s = RunStore(tmp_path)
    a = s.create(RunInput(task="a", cwd="/w"))
    b = s.create(RunInput(task="b", cwd="/w"))
    assert [r.id for r in s.list()] == [b.id, a.id]
    assert s.get("nope") is None and s.events("nope") == []


def test_tolerates_truncated_event_line(tmp_path):
    s = RunStore(tmp_path)
    r = s.create(RunInput(task="t", cwd="/w"))
    s.append(r.id, {"at": 1, "kind": "run", "status": "running"})
    with open(s.dir(r.id) / "events.jsonl", "a") as f:
        f.write('{"at": 2, "kin')
    assert len(s.events(r.id)) == 1


def test_summary_from_events(tmp_path):
    s = RunStore(tmp_path)
    r = s.create(RunInput(task="t", cwd="/w"))
    msg = lambda sender: {"kind": "room", "event": {"type": "message", "data": {"sender": sender, "text": "x"}}}
    finding = {"kind": "room", "event": {"type": "finding", "data": {"finding": {"id": "claude-1"}, "status": "open"}}}
    for i, e in enumerate([
        msg("claude"), msg("system"), msg("codex"), msg("user"), finding, finding,
        {"kind": "agent", "agent": "claude", "event": {"type": "turn_end", "data": {"cost_usd": 0.25}}},
        {"kind": "agent", "agent": "codex", "event": {"type": "turn_end", "data": {"cost_usd": None}}},
        {"kind": "room", "event": {"type": "conclusion", "data": {"agreed_by": ["claude"], "changes": ["a"]}}},
        {"kind": "room", "event": {"type": "conclusion", "data": {"agreed_by": ["claude", "codex"], "changes": ["a", "b"]}}},
        {"kind": "agent", "agent": "executor", "event": {"type": "text", "data": {"text": "done"}}},
        {"kind": "status", "agent": "executor", "status": "done"},
    ]):
        s.append(r.id, {"n": i + 1, "at": r.created_at + 60 + i, **e})
    assert s.summary(r) == {"messages": 2, "findings": 1, "cost_usd": 0.25, "ended_at": r.created_at + 71,
                            "agreed_changes": 2, "executor": "done"}
    s.append(r.id, {"n": 99, "at": 0, "kind": "agent", "agent": "executor",
                    "event": {"type": "error", "data": {"message": "API Error: 400"}}})
    assert s.summary(r)["executor"] == "failed"


def test_summary_of_empty_run(tmp_path):
    s = RunStore(tmp_path)
    r = s.create(RunInput(task="t", cwd="/w"))
    assert s.summary(r)["agreed_changes"] is None and s.summary(r)["messages"] == 0
