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
