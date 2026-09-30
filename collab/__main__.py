import uvicorn

from collab.config import load_config
from collab.runs.store import RunStore
from collab.server import ROOT, create_app


def main() -> None:
    config = load_config(ROOT / "collab.config.json")
    store = RunStore(ROOT / "runs")
    # Agent processes die with the app, so anything left open from a previous session can't continue.
    for record in store.list():
        if record.status in ("running", "waiting"):
            store.update(record.id, status="interrupted")
    app = create_app(store, config)
    print(f"collab running at http://127.0.0.1:{config.port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=config.port, log_level="warning")


if __name__ == "__main__":
    main()
