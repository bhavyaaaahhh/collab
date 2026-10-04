import sys

from collab.agents.base import AgentEvent, Bridge, Command, LaunchOpts
from collab.agents.spawn import spawn_agent


class FakeAdapter:
    kind = "claude"

    def __init__(self, script: str):
        self.script = script

    def build_command(self, o):
        return Command(argv=[sys.executable, "-c", self.script], env={"FAKE": "1"},
                       files={o.work_dir / "cfg.json": "{}"})

    def parse_line(self, line):
        return [AgentEvent(line.strip(), {})] if line.strip() else []


def opts(tmp_path):
    return LaunchOpts(prompt="p", cwd=tmp_path, mode="review", bin="x", work_dir=tmp_path / "agent",
                      bridge=Bridge("x", [], {}))


async def test_parses_stdout_and_writes_files(tmp_path):
    seen = []
    script = "import os; print('session'); print('text' if os.environ['FAKE'] == '1' else 'bad')"
    p = await spawn_agent(FakeAdapter(script), opts(tmp_path), seen.append)
    assert await p.wait() == 0
    assert [e.type for e in seen] == ["session", "text"]
    assert (tmp_path / "agent" / "cfg.json").read_text() == "{}"


async def test_nonzero_exit_reports_stderr(tmp_path):
    seen = []
    p = await spawn_agent(FakeAdapter("import sys; sys.stderr.write('kaboom\\n'); sys.exit(3)"), opts(tmp_path), seen.append)
    assert await p.wait() == 3
    assert seen[-1].type == "error" and "kaboom" in seen[-1].data["message"]


async def test_kill(tmp_path):
    p = await spawn_agent(FakeAdapter("import time; time.sleep(30)"), opts(tmp_path), lambda e: None)
    p.kill()
    assert await p.wait() != 0
