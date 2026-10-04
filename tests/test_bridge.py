import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]


class Echo(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Echo.paths.append(self.path)
        out = json.dumps({"text": f"{body['agent']}:{body['name']}:{json.dumps(body['args'])}"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


@pytest.fixture
def app_url():
    Echo.paths = []
    server = HTTPServer(("127.0.0.1", 0), Echo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def params(url: str) -> StdioServerParameters:
    env = {**os.environ, "COLLAB_URL": url, "COLLAB_RUN": "run-1", "COLLAB_AGENT": "claude", "PYTHONPATH": str(ROOT)}
    return StdioServerParameters(command=sys.executable, args=["-m", "collab.bridge"], env=env)


async def test_lists_tools_and_forwards_calls(app_url):
    async with stdio_client(params(app_url)) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = (await session.list_tools()).tools
        assert "send_message" in [t.name for t in tools]
        res = await session.call_tool("send_message", {"text": "x"})
        assert res.content[0].text == 'claude:send_message:{"text": "x"}'
    assert Echo.paths == ["/api/runs/run-1/tool"]


async def test_unreachable_app_is_text_error():
    async with stdio_client(params("http://127.0.0.1:9")) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        res = await session.call_tool("send_message", {"text": "x"})
        assert res.content[0].text.startswith("Error: collab app unreachable")
