import asyncio
import json

import httpx
import pytest

from collab.config import Budget, Config
from collab.runs.store import RunStore
from collab.server import create_app, event_stream
from tests.helpers import FakeSpawn, idle


@pytest.fixture
def setup(tmp_path):
    fake = FakeSpawn({"claude": idle, "codex": idle})
    config = Config(wait_timeout_s=0.05, budget=Budget(max_messages=10, max_minutes=5))
    template = tmp_path / "t.md"
    template.write_text("You are {{me}}.")
    app = create_app(RunStore(tmp_path / "runs"), config, spawn=fake, template_path=template,
                     adapters={"claude": object(), "codex": object()})
    fake.run = None
    return app, fake, tmp_path


@pytest.fixture
async def client(setup):
    app = setup[0]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c
    for run in app.state.runs.values():
        await run.stop()


async def start(client, setup, **extra):
    app, fake, tmp_path = setup
    res = await client.post("/api/runs", json={"task": "t", "cwd": str(tmp_path), **extra})
    assert res.status_code == 200, res.text
    run_id = res.json()["id"]
    fake.run = app.state.runs[run_id]
    return run_id


async def test_create_relay_tool_and_snapshot(client, setup):
    run_id = await start(client, setup)
    res = await client.post(f"/api/runs/{run_id}/tool", json={"agent": "claude", "name": "send_message",
                                                              "args": {"text": "hi"}})
    assert res.json() == {"text": "sent"}
    snap = (await client.get(f"/api/runs/{run_id}")).json()
    assert snap["room"]["messages"][0]["text"] == "hi"
    assert snap["record"]["budget"]["max_messages"] == 10  # config default applied
    assert (await client.get("/api/runs")).json()[0]["id"] == run_id


async def test_bad_input_is_rejected(client, tmp_path):
    assert (await client.post("/api/runs", json={"task": "t", "cwd": str(tmp_path / "nope")})).status_code == 400
    assert (await client.post("/api/runs", json={"cwd": str(tmp_path)})).status_code == 422
    assert (await client.post("/api/runs", json={"task": " ", "cwd": str(tmp_path)})).status_code == 400


async def test_user_message_and_checkpoint_errors(client, setup):
    run_id = await start(client, setup)
    assert (await client.post(f"/api/runs/{run_id}/message", json={"text": "focus"})).status_code == 200
    snap = (await client.get(f"/api/runs/{run_id}")).json()
    assert snap["room"]["messages"][-1] == {**snap["room"]["messages"][-1], "sender": "user", "text": "focus"}
    res = await client.post(f"/api/runs/{run_id}/checkpoints/nope", json={"decision": "approved"})
    assert res.status_code == 409


async def test_stop_and_past_run(client, setup):
    app = setup[0]
    run_id = await start(client, setup)
    assert (await client.post(f"/api/runs/{run_id}/stop")).status_code == 200
    assert (await client.get("/api/runs")).json()[0]["status"] == "stopped"
    del app.state.runs[run_id]  # as after a restart
    past = (await client.get(f"/api/runs/{run_id}")).json()
    assert past["record"]["status"] == "stopped" and past["events"]
    events = await client.get(f"/api/runs/{run_id}/stream")
    assert "event: record" in events.text and '"kind": "run"' in events.text


async def test_stream_of_finished_live_run_closes(client, setup):
    run_id = await start(client, setup)
    await client.post(f"/api/runs/{run_id}/stop")
    res = await asyncio.wait_for(client.get(f"/api/runs/{run_id}/stream"), 3)
    assert '"status": "stopped"' in res.text


async def test_unknown_run_404(client):
    assert (await client.get("/api/runs/nope")).status_code == 404
    assert (await client.post("/api/runs/nope/tool", json={"agent": "a", "name": "b", "args": {}})).status_code == 404


async def test_live_stream_replays_then_follows(client, setup):
    app = setup[0]
    run_id = await start(client, setup)
    run = app.state.runs[run_id]
    run.user_message("before")
    stream = event_stream(app, run_id)
    chunks = [await anext(stream)]
    while "before" not in chunks[-1]:
        chunks.append(await anext(stream))
    run.user_message("after")
    nxt = await asyncio.wait_for(anext(stream), 2)
    while "after" not in nxt:
        nxt = await asyncio.wait_for(anext(stream), 2)
    ns = [json.loads(c.split("data: ", 1)[1])["n"] for c in chunks[1:] + [nxt]]
    assert ns == sorted(set(ns))  # no duplicates, in order
    await stream.aclose()
