import asyncio
import os
from collections import deque
from collections.abc import Callable

from collab.agents.base import AgentAdapter, AgentEvent, LaunchOpts

STDERR_TAIL = 20
# stream-json lines (e.g. a tool result with a whole file) can be far above asyncio's 64 KiB default.
LINE_LIMIT = 32 * 1024 * 1024


class AgentProcess:
    def __init__(self, proc: asyncio.subprocess.Process, pump: asyncio.Task):
        self._proc = proc
        self._pump = pump

    async def wait(self) -> int:
        code = await self._proc.wait()
        await self._pump
        return code

    def kill(self) -> None:
        if self._proc.returncode is None:
            self._proc.kill()


async def spawn_agent(adapter: AgentAdapter, o: LaunchOpts, on_event: Callable[[AgentEvent], None]) -> AgentProcess:
    cmd = adapter.build_command(o)
    o.work_dir.mkdir(parents=True, exist_ok=True)
    for path, content in cmd.files.items():
        path.write_text(content)
    proc = await asyncio.create_subprocess_exec(
        *cmd.argv,
        cwd=o.cwd,
        env={**os.environ, **cmd.env},
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=LINE_LIMIT,
    )

    async def pump() -> None:
        stderr: deque[str] = deque(maxlen=STDERR_TAIL)

        async def read_stdout():
            async for raw in proc.stdout:
                for event in adapter.parse_line(raw.decode(errors="replace")):
                    on_event(event)

        async def read_stderr():
            async for raw in proc.stderr:
                stderr.append(raw.decode(errors="replace").rstrip())

        await asyncio.gather(read_stdout(), read_stderr())
        code = await proc.wait()
        if code != 0 and stderr:
            on_event(AgentEvent("error", {"message": f"exit {code}: " + "\n".join(stderr)}))

    return AgentProcess(proc, asyncio.create_task(pump()))
