import asyncio
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from collab.agents.base import Bridge
from collab.agents.claude import claude
from collab.agents.codex import codex
from collab.agents.spawn import spawn_agent
from collab.config import Config
from collab.room.models import RoomError
from collab.runs.run import Run, RunDeps
from collab.runs.store import RunInput, RunStore

ROOT = Path(__file__).resolve().parents[1]
WEB_DIST = ROOT / "web" / "dist"
PUBLIC_ARTIFACTS = {"conclusion.md", "executor.md"}


class ToolCall(BaseModel):
    agent: str
    name: str
    args: dict = {}


class UserMessage(BaseModel):
    text: str


class Decision(BaseModel):
    decision: Literal["approved", "rejected"]
    selected: list[int] | None = None
    note: str | None = None


def create_app(
    store: RunStore,
    config: Config,
    spawn=spawn_agent,
    template_path: Path = ROOT / "prompts" / "collaboration.md",
    adapters: dict | None = None,
) -> FastAPI:
    app = FastAPI(title="collab")
    app.state.runs = {}
    app.state.store = store

    def bridge_for(run_id: str, agent: str) -> Bridge:
        env = {"COLLAB_URL": f"http://127.0.0.1:{config.port}", "COLLAB_RUN": run_id, "COLLAB_AGENT": agent}
        return Bridge(sys.executable, ["-m", "collab.bridge"], env)

    def live(run_id: str) -> Run:
        if run_id not in app.state.runs:
            raise HTTPException(404, f"No live run {run_id}.")
        return app.state.runs[run_id]

    @app.get("/api/runs")
    def list_runs():
        return [{**r.model_dump(), "summary": store.summary(r)} for r in store.list()]

    @app.post("/api/runs")
    async def create_run(inp: RunInput):
        if not inp.task.strip():
            raise HTTPException(400, "Task is empty.")
        if not Path(inp.cwd).is_dir():
            raise HTTPException(400, f"Working directory does not exist: {inp.cwd}")
        missing = [a for a in inp.attachments if not Path(a).exists()]
        if missing:
            raise HTTPException(400, f"Attached files not found: {', '.join(missing)}")
        if inp.budget is None:
            inp = inp.model_copy(update={"budget": config.budget})
        deps = RunDeps(store=store, adapters=adapters or {"claude": claude, "codex": codex}, spawn=spawn,
                       template=template_path.read_text(), config=config, bridge_for=bridge_for)
        run = Run(store.create(inp), deps)
        app.state.runs[run.id] = run
        await run.start()
        return {"id": run.id}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        if run_id in app.state.runs:
            return app.state.runs[run_id].snapshot()
        record = store.get(run_id)
        if record is None:
            raise HTTPException(404, f"No run {run_id}.")
        return {"record": record.model_dump(), "events": store.events(run_id)}

    @app.get("/api/runs/{run_id}/stream")
    def stream(run_id: str):
        if run_id not in app.state.runs and store.get(run_id) is None:
            raise HTTPException(404, f"No run {run_id}.")
        return StreamingResponse(event_stream(app, run_id), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @app.get("/api/runs/{run_id}/artifacts/{name}", response_class=PlainTextResponse)
    def artifact(run_id: str, name: str):
        path = store.dir(run_id) / name
        if name not in PUBLIC_ARTIFACTS or not path.is_file():
            raise HTTPException(404, f"No {name} for run {run_id}.")
        return path.read_text()

    @app.post("/api/runs/{run_id}/tool")
    async def tool(run_id: str, call: ToolCall):
        return {"text": await live(run_id).call_tool(call.agent, call.name, call.args)}

    @app.post("/api/runs/{run_id}/message")
    def message(run_id: str, msg: UserMessage):
        if not msg.text.strip():
            raise HTTPException(400, "Message is empty.")
        live(run_id).user_message(msg.text)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/checkpoints/{checkpoint_id}")
    async def checkpoint(run_id: str, checkpoint_id: str, d: Decision):
        try:
            await live(run_id).resolve_checkpoint(checkpoint_id, d.decision, d.selected, d.note)
        except RoomError as e:
            raise HTTPException(409, str(e))
        return {"ok": True}

    @app.post("/api/runs/{run_id}/stop")
    async def stop(run_id: str):
        await live(run_id).stop()
        return {"ok": True}

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    return app


def _sse(data: dict, event: str | None = None) -> str:
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data, default=str)}\n\n"


async def event_stream(app: FastAPI, run_id: str) -> AsyncIterator[str]:
    """Replay events.jsonl, then follow the live run (if any). Events carry `n`, so nothing is sent twice."""
    store: RunStore = app.state.store
    run: Run | None = app.state.runs.get(run_id)
    queue: asyncio.Queue[dict] = asyncio.Queue()
    if run:
        run.subscribe(queue.put_nowait)  # before reading the file, so no event falls in between
    try:
        record = run.record if run else store.get(run_id)
        yield _sse(record.model_dump(), "record")
        last = 0
        for event in store.events(run_id):
            last = event.get("n", last)
            yield _sse(event)
        while run and not (run.finished and queue.empty()):
            try:
                event = await asyncio.wait_for(queue.get(), 15)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event["n"] > last:
                last = event["n"]
                yield _sse(event)
    finally:
        if run:
            run.unsubscribe(queue.put_nowait)
