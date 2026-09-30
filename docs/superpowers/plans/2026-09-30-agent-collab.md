# Agent Collab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local app where two CLI agents (Claude/Codex) talk to each other directly through a shared MCP chat room, with a live web dashboard, user checkpoints, and an executor session.

**Architecture:** One Python asyncio process holds all room state, serves an HTTP API + SSE stream + static dashboard, and spawns agent CLIs as subprocesses. Each CLI gets a small stdio MCP bridge that forwards room tool calls to the app over localhost HTTP. Collaboration behavior lives in `prompts/collaboration.md`, not code.

**Tech Stack:** Python 3.14, uv, FastAPI + uvicorn, pydantic v2, `mcp` (official Python SDK), httpx, pytest + pytest-asyncio. Dashboard: Vite + React (TypeScript) in `web/`, built to static files served by FastAPI.

**Spec:** `docs/superpowers/specs/2026-09-30-agent-collab-design.md`

**Execution:** native, one task at a time; stop after each task for user review.

## Global Constraints

- Localhost only; server binds `127.0.0.1`.
- Task-agnostic: no presets. The only prompt file is `prompts/collaboration.md`; the user's task text is appended as-is.
- Reviewers are read-only (Claude `--permission-mode default` with only room + read tools allowed; Codex `-s read-only`). Only the executor writes (`acceptEdits` / `-s workspace-write`).
- Codex room server must set `default_tools_approval_mode="approve"` and `tool_timeout_sec=120`.
- Claude must list room tools in `--allowedTools` and run with `MCP_TOOL_TIMEOUT=120000`.
- `wait_for_messages` blocks at most 40s.
- The executor never commits.
- Every room/agent event is appended to `runs/<id>/events.jsonl`.

## Review Focus

1. Agent exits early while run is open → resumed; marked stalled after 3 exits with no room activity (Task 7 test).
2. `request_executor` before both agents agreed on the same proposal → rejected with an error the agent can read (Task 3 test).
3. Budget exhausted while agents keep talking → wrap-up at 80%; at 100% conclusion written with contested findings unresolved (Task 7 test).
4. User clicks Stop mid-run → all child processes killed, status `stopped`, artifacts kept (Task 7 test).
5. Malformed/unknown lines in CLI JSON streams (hooks, rate-limit events) → ignored, parser never raises (Task 5 test).

---

## File Structure

```
pyproject.toml, collab.config.json, .gitignore
prompts/collaboration.md            working agreement (the collaboration prompt)
collab/__init__.py
collab/config.py                    load collab.config.json
collab/room/models.py               Message, Finding, Stance, Plan, Conclusion, Checkpoint, RoomEvent (pydantic)
collab/room/room.py                 Room: state + rules, event subscribers
collab/room/tools.py                MCP tool definitions + dispatch()
collab/bridge.py                    stdio MCP server; forwards tool calls to app HTTP
collab/agents/base.py               AgentEvent, LaunchOpts, Command, AgentAdapter protocol
collab/agents/claude.py             build command + parse stream-json
collab/agents/codex.py              build command + parse --json
collab/agents/spawn.py              spawn CLI subprocess, parse stdout lines
collab/runs/store.py                runs/<id>/: run.json, events.jsonl, artifacts
collab/runs/prompt.py               fill collaboration.md
collab/runs/run.py                  Run: room + agents + keep-alive + budget + checkpoints + executor
collab/server.py                    FastAPI routes + SSE + static
collab/__main__.py                  `uv run python -m collab`
tests/...                           pytest
web/                                Vite React dashboard
examples/toy/                       sample task for manual E2E
```

---

### Task 1: Scaffold

**Files:** Create `pyproject.toml`, `collab.config.json`, `.gitignore`, `collab/__init__.py`, `collab/config.py`, `tests/test_config.py`

**Interfaces — Produces:**
```python
class Budget(BaseModel): max_messages: int = 80; max_minutes: int = 30
class Config(BaseModel):
    port: int = 4747
    bin: dict[str, str] = {"claude": "claude", "codex": "codex"}
    models: dict[str, str | None] = {"claude": None, "codex": None}
    budget: Budget = Budget()
    wait_timeout_s: float = 40
def load_config(path: Path = Path("collab.config.json")) -> Config  # missing file → defaults
```

- [ ] **Step 1:** `uv init --lib`-style layout by hand; `pyproject.toml` with deps `fastapi uvicorn[standard] pydantic httpx mcp`, dev deps `pytest pytest-asyncio`, `[tool.pytest.ini_options] asyncio_mode = "auto"`. `uv sync`.
- [ ] **Step 2: Failing test**
```python
def test_defaults_when_missing(tmp_path):
    c = load_config(tmp_path / "nope.json")
    assert c.port == 4747 and c.budget.max_messages == 80

def test_overrides(tmp_path):
    p = tmp_path / "c.json"; p.write_text('{"port": 5000, "budget": {"max_minutes": 5}}')
    c = load_config(p)
    assert c.port == 5000 and c.budget.max_minutes == 5 and c.budget.max_messages == 80
```
- [ ] **Step 3:** `uv run pytest` → FAIL; implement `config.py`; → PASS.
- [ ] **Step 4: Commit** `chore: scaffold project`

---

### Task 2: Room models and state rules

**Files:** Create `collab/room/__init__.py`, `collab/room/models.py`, `collab/room/room.py`; Test `tests/room/test_room.py`

**Interfaces — Produces** (`models.py`, pydantic):
```python
Author = str                                   # agent name | "user" | "system"
class Message: seq: int; sender: str; text: str; at: float
StanceKind = Literal["agree", "disagree", "partial"]
class Stance: by: str; stance: StanceKind; reasoning: str; amended_change: str | None; at: float
class FindingIn: cases: list[str]; issue: str; evidence: str; proposed_change: str; confidence: Literal["high","medium","low"]
class Finding(FindingIn): id: str; author: str; stances: list[Stance] = []; revision: int = 0
FindingStatus = Literal["open", "agreed", "contested", "resolved"]
class Plan: id: str; by: str; mode: Literal["independent","split"]; slices: dict[str,str] | None; endorsed_by: list[str]
class Conclusion: id: str; by: str; changes: list[str]; unresolved: list[str]; agreed_by: list[str]; rejected_by: list[dict]
class Checkpoint: id: str; kind: Literal["plan","apply"]; ref_id: str; status: Literal["pending","approved","rejected"]; selected: list[int] | None = None; note: str | None = None
class RoomEvent: type: Literal["message","finding","plan","conclusion","checkpoint","executor_requested"]; data: dict
class RoomError(Exception)
```

`Room(participants: list[str], default_mode: str)`:
- `subscribe(fn: Callable[[RoomEvent], None])`
- `add_participant(name)` (for the executor)
- `post(sender, text) -> Message`
- `messages_for(agent, after_seq) -> list[Message]` — seq > after_seq and sender != agent
- `async wait_for(agent, after_seq, timeout_s) -> list[Message]` — returns as soon as non-empty, `[]` on timeout (uses an `asyncio.Condition`)
- `post_finding(author, FindingIn) -> Finding` — id `f"{author}-{n}"`
- `respond(by, finding_id, stance, reasoning, amended_change=None)` — RoomError if self or missing
- `update_finding(by, finding_id, patch: dict)` — author only; `revision += 1`
- `finding_status(f)`: no non-author stance → open; latest non-author `agree` & revision 0 → agreed; latest `agree` & revision > 0 → resolved; else contested
- `propose_plan(by, mode, slices=None) -> Plan`, `endorse_plan(by, plan_id)`: when all participants endorsed → if mode == "independent" == default_mode post system "Plan accepted." else create `plan` checkpoint
- `propose_conclusion(by, changes, unresolved) -> Conclusion`, `agree_conclusion(by, id)`, `reject_conclusion(by, id, reason)` (also posts reason as `by`)
- `concluded() -> Conclusion | None` — agreed by all *reviewers* (participants at construction)
- `request_executor(by, conclusion_id)` — RoomError("Both participants must agree_to_conclusion on this proposal first.") unless concluded on that id; emits `executor_requested`
- `resolve_checkpoint(id, status, selected=None, note=None)` — updates, emits, posts system message ("User approved the split plan." / "User rejected the split plan; do a full independent review." / "User approved the changes; executor starting." / "User stopped before applying changes.")
- `snapshot() -> dict`

- [ ] **Step 1: Failing tests**
```python
F = FindingIn(cases=["14"], issue="i", evidence="e", proposed_change="c", confidence="high")
def room(): return Room(["claude", "codex"], "independent")

def test_messages_for_excludes_own_and_old():
    r = room(); r.post("claude", "hi"); r.post("codex", "yo"); r.post("user", "focus")
    assert [m.text for m in r.messages_for("claude", 0)] == ["yo", "focus"]
    assert [m.text for m in r.messages_for("claude", 2)] == ["focus"]

async def test_wait_for_wakes_and_times_out():
    r = room()
    async def later(): await asyncio.sleep(0.02); r.post("codex", "late")
    asyncio.create_task(later())
    assert [m.text for m in await r.wait_for("claude", 0, 1)] == ["late"]
    assert await r.wait_for("claude", 1, 0.03) == []

def test_finding_status():
    r = room(); a = r.post_finding("claude", F)
    assert a.id == "claude-1" and r.finding_status(a) == "open"
    r.respond("codex", a.id, "disagree", "no"); assert r.finding_status(a) == "contested"
    r.update_finding("claude", a.id, {"proposed_change": "c2"})
    r.respond("codex", a.id, "agree", "ok"); assert r.finding_status(a) == "resolved"
    b = r.post_finding("codex", F); r.respond("claude", b.id, "agree", "y")
    assert r.finding_status(b) == "agreed"

def test_rejects_self_stance_and_foreign_update():
    r = room(); a = r.post_finding("claude", F)
    with pytest.raises(RoomError): r.respond("claude", a.id, "agree", "")
    with pytest.raises(RoomError): r.update_finding("codex", a.id, {})

def test_split_plan_creates_checkpoint_after_both_endorse():
    r = room(); ev = []; r.subscribe(ev.append)
    p = r.propose_plan("claude", "split", {"claude": "1-18", "codex": "19-40"})
    assert not any(e.type == "checkpoint" for e in ev)
    r.endorse_plan("codex", p.id)
    assert [e for e in ev if e.type == "checkpoint"][0].data["kind"] == "plan"

def test_independent_plan_needs_no_checkpoint():
    r = room(); ev = []; r.subscribe(ev.append)
    p = r.propose_plan("claude", "independent"); r.endorse_plan("codex", p.id)
    assert not any(e.type == "checkpoint" for e in ev)

def test_request_executor_requires_agreement():
    r = room(); c = r.propose_conclusion("claude", ["x"], [])
    with pytest.raises(RoomError, match="Both participants"): r.request_executor("claude", c.id)
    r.agree_conclusion("codex", c.id)
    assert r.concluded().id == c.id
    r.request_executor("claude", c.id)
```
- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat(room): room state and collaboration rules`

---

### Task 3: Room tools

**Files:** Create `collab/room/tools.py`; Test `tests/room/test_tools.py`

**Interfaces — Produces:**
```python
TOOL_DEFS: list[dict]        # {"name", "description", "inputSchema"} — JSON Schema objects
TOOL_NAMES: list[str]
@dataclass class Cursor: last_seq: int = 0
async def dispatch(room: Room, agent: str, cursor: Cursor, name: str, args: dict, wait_timeout_s: float) -> str
```
Tools: `send_message{text}`, `wait_for_messages{}`, `read_room{since?}`, `list_findings{}`, `post_finding{cases,issue,evidence,proposed_change,confidence}`, `respond_to_finding{id,stance,reasoning,amended_change?}`, `update_finding{id,patch}`, `propose_plan{mode,slices?}`, `endorse_plan{plan_id}`, `propose_conclusion{changes,unresolved}`, `agree_to_conclusion{proposal_id}`, `reject_conclusion{proposal_id,reason}`, `request_executor{proposal_id}`.

`wait_for_messages` returns `[sender] text` blocks joined by blank lines and advances the cursor; on timeout `"No new messages yet. Call wait_for_messages again."`. `RoomError`, pydantic `ValidationError`, unknown tool → returned as `"Error: ..."`, never raised.

- [ ] **Step 1: Failing tests**
```python
def test_every_tool_has_object_schema():
    assert "wait_for_messages" in TOOL_NAMES
    assert all(t["inputSchema"]["type"] == "object" for t in TOOL_DEFS)

async def test_send_wait_round_trip():
    r = Room(["claude", "codex"], "independent"); cc, xc = Cursor(), Cursor()
    await dispatch(r, "claude", cc, "send_message", {"text": "hello"}, 0.03)
    assert "[claude] hello" in await dispatch(r, "codex", xc, "wait_for_messages", {}, 0.03)
    assert "No new messages" in await dispatch(r, "codex", xc, "wait_for_messages", {}, 0.03)

async def test_errors_are_text():
    r = Room(["claude", "codex"], "independent")
    out = await dispatch(r, "claude", Cursor(), "request_executor", {"proposal_id": "nope"}, 0.03)
    assert out.startswith("Error:")
    assert (await dispatch(r, "claude", Cursor(), "post_finding", {"cases": 1}, 0.03)).startswith("Error:")

async def test_post_finding_returns_id():
    r = Room(["claude", "codex"], "independent")
    out = await dispatch(r, "claude", Cursor(), "post_finding",
        {"cases": ["1"], "issue": "i", "evidence": "e", "proposed_change": "c", "confidence": "low"}, 0.03)
    assert "claude-1" in out
```
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(room): MCP tool definitions and dispatch`

---

### Task 4: stdio MCP bridge

**Files:** Create `collab/bridge.py`; Test `tests/test_bridge.py`

**Interfaces:**
- Consumes: `TOOL_DEFS`; app endpoint `POST /api/runs/{run_id}/tool` body `{"agent","name","args"}` → `{"text"}` (Task 8).
- Produces: `python -m collab.bridge` with env `COLLAB_URL`, `COLLAB_RUN`, `COLLAB_AGENT`. Uses `mcp.server.lowlevel.Server` + `mcp.server.stdio.stdio_server`; `list_tools` returns `TOOL_DEFS` as `mcp.types.Tool`; `call_tool` POSTs via httpx (timeout 120s) and returns `[TextContent(text=...)]`. HTTP failure → `"Error: collab app unreachable (...)"`.

- [ ] **Step 1: Failing test** — run a tiny `http.server` in a thread on a free port echoing `{"text": f"{agent}:{name}"}`; connect with `mcp.client.stdio.stdio_client(StdioServerParameters(command=sys.executable, args=["-m","collab.bridge"], env={...}))` + `ClientSession`:
```python
tools = (await session.list_tools()).tools
assert "send_message" in [t.name for t in tools]
res = await session.call_tool("send_message", {"text": "x"})
assert res.content[0].text == "claude:send_message"
```
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(bridge): stdio MCP bridge to collab app`

---

### Task 5: Agent adapters

**Files:** Create `collab/agents/__init__.py`, `base.py`, `claude.py`, `codex.py`; Tests `tests/agents/test_claude.py`, `tests/agents/test_codex.py`; Fixtures `tests/fixtures/claude.jsonl`, `tests/fixtures/codex.jsonl` (one line per event shape, copied from real spike output)

**Interfaces — Produces** (`base.py`):
```python
AgentKind = Literal["claude", "codex"]; Mode = Literal["review", "execute"]
@dataclass class AgentEvent: type: Literal["session","text","tool_call","tool_result","turn_end","error"]; data: dict
@dataclass class Bridge: command: str; args: list[str]; env: dict[str, str]
@dataclass class LaunchOpts:
    prompt: str; cwd: Path; mode: Mode; bridge: Bridge; bin: str; work_dir: Path
    resume_session_id: str | None = None; model: str | None = None
@dataclass class Command: argv: list[str]; env: dict[str, str]; files: dict[Path, str] = field(default_factory=dict)
class AgentAdapter(Protocol):
    kind: AgentKind
    def build_command(self, o: LaunchOpts) -> Command: ...
    def parse_line(self, line: str) -> list[AgentEvent]: ...   # never raises
```
`claude.py` exports `claude = ClaudeAdapter()`, `codex.py` exports `codex = CodexAdapter()`.

Claude `build_command`:
- writes `files[work_dir/"mcp.json"] = {"mcpServers": {"room": {command,args,env}}}`
- argv: `[bin, "-p", prompt, "--output-format", "stream-json", "--verbose", "--mcp-config", <path>, "--strict-mcp-config", "--allowedTools", ",".join(tools)]` + `["--resume", id]` + `["--model", m]`
- review: `--permission-mode default`, tools = `mcp__room__<name>` for all `TOOL_NAMES` + `Read,Grep,Glob,LS`
- execute: `--permission-mode acceptEdits`, tools also `Edit,Write,MultiEdit,Bash`
- env `{"MCP_TOOL_TIMEOUT": "120000"}`

Claude `parse_line`: `system/init` → session(`session_id`); `assistant` content `text` → text, `tool_use` → tool_call(id,name,input), `thinking` ignored; `user` content `tool_result` → tool_result(id, summary = first 200 chars, is_error); `result` → turn_end(cost_usd = `total_cost_usd`) plus error if `is_error`; anything else / bad JSON → `[]`.

Codex `build_command`:
- cfg = `-c` pairs: `mcp_servers.room.command=<toml str>`, `mcp_servers.room.args=[...]`, `mcp_servers.room.env={K="v"}`, `mcp_servers.room.tool_timeout_sec=120`, `mcp_servers.room.default_tools_approval_mode="approve"`, `sandbox_mode="read-only"|"workspace-write"`; TOML strings via `json.dumps`
- new: `[bin, "exec", "--json", "--skip-git-repo-check", "-C", cwd, *cfg, prompt]`
- resume: `[bin, "exec", "resume", id, "--json", "--skip-git-repo-check", *cfg, prompt]` (subprocess cwd = cwd)
- `-m model` if set

Codex `parse_line`: `thread.started` → session(`thread_id`); `item.completed/agent_message` → text; `item.started/mcp_tool_call` → tool_call(name=`tool`, input=`arguments`); `item.completed/mcp_tool_call` → tool_result(is_error = error is not None); `item.completed/command_execution` → tool_call + tool_result (name `shell`); `turn.completed` → turn_end; `turn.failed`/`error` → error; else `[]`.

- [ ] **Step 1: Failing tests** (Claude; Codex mirrors)
```python
LINES = Path("tests/fixtures/claude.jsonl").read_text().splitlines()
EVENTS = [e for l in LINES for e in claude.parse_line(l)]

def test_extracts_stream():
    types = [e.type for e in EVENTS]
    assert "session" in types and "text" in types and "tool_result" in types
    assert any(e.type == "tool_call" and e.data["name"].startswith("mcp__room__") for e in EVENTS)
    assert EVENTS[-1].type == "turn_end"

@pytest.mark.parametrize("line", ["", "not json", '{"type":"rate_limit_event"}', '{"type":"assistant"}'])
def test_ignores_junk(line):
    assert claude.parse_line(line) == []

def test_review_is_read_only_and_resumes(tmp_path):
    c = claude.build_command(LaunchOpts(prompt="p", cwd=tmp_path, mode="review", bin="claude",
        bridge=Bridge("py", ["-m", "collab.bridge"], {}), work_dir=tmp_path, resume_session_id="s1"))
    s = " ".join(c.argv)
    assert "--resume s1" in s and "--permission-mode default" in s and "Edit" not in s
```
Codex extras: resume argv starts `["codex","exec","resume","s1"]`; contains `mcp_servers.room.default_tools_approval_mode="approve"`; execute mode has `sandbox_mode="workspace-write"`.
- [ ] **Step 2–4:** build fixtures from the spike output, FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(agents): claude and codex adapters`

---

### Task 6: Spawner, store, prompt

**Files:** Create `collab/agents/spawn.py`, `collab/runs/__init__.py`, `collab/runs/store.py`, `collab/runs/prompt.py`, `prompts/collaboration.md`; Tests `tests/agents/test_spawn.py`, `tests/runs/test_store.py`, `tests/runs/test_prompt.py`

**Interfaces — Produces:**
```python
# spawn.py
class AgentProcess(Protocol):
    async def wait(self) -> int: ...
    def kill(self) -> None: ...
async def spawn_agent(adapter, o: LaunchOpts, on_event: Callable[[AgentEvent], None]) -> AgentProcess
# writes cmd.files, asyncio.create_subprocess_exec(cwd=o.cwd, env=os.environ|cmd.env, stdin=DEVNULL),
# reads stdout lines → parse_line → on_event; keeps last 20 stderr lines, emitted as one error event if exit != 0

# store.py
class RunInput(BaseModel):
    task: str; cwd: str; attachments: list[str] = []
    agents: tuple[AgentKind, AgentKind] = ("claude", "codex"); executor: AgentKind = "claude"
    default_mode: Literal["independent","split"] = "independent"; auto_apply: bool = False
    budget: Budget | None = None
RunStatus = Literal["running","waiting","completed","stopped","failed","interrupted"]
class RunRecord(RunInput): id: str; status: RunStatus; created_at: float; sessions: dict[str, str] = {}
class RunStore:
    def __init__(self, root: Path = Path("runs"))
    def create(self, inp: RunInput) -> RunRecord          # id = "%Y%m%d-%H%M%S-" + 4 hex
    def update(self, run_id: str, **patch) -> RunRecord
    def append(self, run_id: str, event: dict) -> None    # event has "at" and "kind": room|agent|status|run
    def write_artifact(self, run_id: str, name: str, content: str) -> None
    def list(self) -> list[RunRecord]                     # newest first
    def get(self, run_id: str) -> RunRecord | None
    def events(self, run_id: str) -> list[dict]
    def dir(self, run_id: str) -> Path

# prompt.py
def agent_names(kinds: tuple[str, str]) -> tuple[str, str]   # ("claude","codex") or ("claude-1","claude-2")
def build_prompt(template: str, *, me, partner, cwd, attachments: list[str], default_mode,
                 budget: Budget, task: str, role: Literal["reviewer","executor"]) -> str
```
`build_prompt` replaces `{{me}} {{partner}} {{cwd}} {{attachments}}` (bullet list or "none") `{{default_mode}} {{max_messages}} {{max_minutes}} {{role}}`, leaves unknown `{{x}}`, appends `"\n\n## Task from the user\n\n" + task`.

`prompts/collaboration.md` (first version):
```markdown
# How you work in this session

You are **{{me}}**, a {{role}} in a two-agent collaboration. Your partner is **{{partner}}**, another AI agent working in the same directory (`{{cwd}}`). The user is watching everything live and may post messages in the room.

You talk to your partner only through the room tools (`send_message`, `wait_for_messages`, and the findings/plan/conclusion tools). Your partner cannot see your private reasoning or tool output — if it matters, say it in the room.

Attached files: {{attachments}}

## Working agreement

1. **Agree on a plan first.** One of you proposes with `propose_plan` (default mode: `{{default_mode}}`), the other endorses with `endorse_plan` or counter-proposes. `independent` = both of you cover everything. `split` = you divide the work; the user must approve a split before you proceed.
2. **Do your own pass before reading theirs.** Investigate yourself and `post_finding` for each issue before you look at your partner's findings. That is what makes two opinions worth more than one.
3. **Evidence or it didn't happen.** Every finding and argument cites something concrete: file:line, a quote, a trace excerpt, a case id.
4. **Review every partner finding.** Use `respond_to_finding` with agree / disagree / partial and a reason. Also flag anything they missed.
5. **Disagree honestly.** Don't concede to be polite. Concede explicitly — and `update_finding` — when the evidence shows you were wrong. Prefer a concrete compromise over a stalemate.
6. **Keep messages short and specific.** One topic per message. Reference finding ids.
7. **Stay in the conversation.** After sending, always call `wait_for_messages`. If it says no new messages, call it again. Never end your turn while the collaboration is open.
8. **User messages come first.** If the user posts, address it before anything else.
9. **Finish together.** When nothing is left to debate, one of you calls `propose_conclusion` (concrete changes + anything still unresolved). The other calls `agree_to_conclusion` or `reject_conclusion` with a reason. Once both agree, call `request_executor` if the task involves changing files. Then end your turn.

## Budget

About {{max_messages}} room messages and {{max_minutes}} minutes. If the room tells you to wrap up, go straight to a conclusion and list open disagreements as unresolved.
```

- [ ] **Step 1: Failing tests**
```python
def test_build_prompt():
    p = build_prompt("I am {{me}}, partner {{partner}}, {{attachments}}, {{unknown}}", me="claude",
        partner="codex", cwd="/w", attachments=["/r.json"], default_mode="independent",
        budget=Budget(), task="fix evals", role="reviewer")
    assert "I am claude, partner codex, - /r.json, {{unknown}}" in p and p.endswith("fix evals")

def test_agent_names():
    assert agent_names(("claude", "claude")) == ("claude-1", "claude-2")
    assert agent_names(("claude", "codex")) == ("claude", "codex")

def test_store_round_trip(tmp_path):
    s = RunStore(tmp_path); r = s.create(RunInput(task="t", cwd="/w"))
    s.append(r.id, {"at": 1, "kind": "run", "status": "running"})
    assert len(s.events(r.id)) == 1 and s.list()[0].id == r.id
    assert s.update(r.id, status="stopped").status == "stopped"

async def test_spawn_parses_stdout(tmp_path):
    # fake adapter: argv = [sys.executable, "-c", "print('{\"t\":\"session\"}'); print('{\"t\":\"text\"}')"]
    seen = []
    p = await spawn_agent(FakeAdapter(), opts(tmp_path), seen.append)
    assert await p.wait() == 0 and [e.type for e in seen] == ["session", "text"]
```
- [ ] **Step 2–4:** FAIL → implement (+ write `prompts/collaboration.md`) → PASS.
- [ ] **Step 5: Commit** `feat(runs): spawner, run store, collaboration prompt`

---

### Task 7: Run lifecycle

**Files:** Create `collab/runs/run.py`, `tests/helpers.py` (fake spawn); Test `tests/runs/test_run.py`

**Interfaces — Produces:**
```python
@dataclass class RunDeps:
    store: RunStore; adapters: dict[str, AgentAdapter]; spawn: Callable  # same signature as spawn_agent
    template: str; config: Config; bridge_for: Callable[[str, str], Bridge]
class Run:
    id: str; room: Room; record: RunRecord
    def __init__(self, record: RunRecord, deps: RunDeps)
    def subscribe(self, fn: Callable[[dict], None])     # stored-event dicts, same shape as events.jsonl
    async def start(self) -> None
    async def call_tool(self, agent: str, name: str, args: dict) -> str
    def user_message(self, text: str) -> None
    async def resolve_checkpoint(self, cid: str, decision: Literal["approved","rejected"], selected=None, note=None)
    async def stop(self) -> None
    async def done(self) -> None                        # awaits run end (tests)
    def snapshot(self) -> dict                          # record + room snapshot + agent statuses
```

Behavior:
- `start`: room with `agent_names(record.agents)`; spawn each in `review` mode with filled prompt; store session ids from `session` events in `run.json`; one supervisor task per agent.
- **Keep-alive** (supervisor): on process exit while the run is open (not concluded, not stopped, budget not exhausted) → resume with `"The collaboration is still open. Call wait_for_messages and continue."`. `idle_exits[agent]` resets on any room tool call; at 3 → status `stalled`, system message, stop resuming. Two consecutive non-zero exits → `failed`, system message to partner. Exit after conclusion → `done`.
- **Budget:** count agent-sent room messages + wall clock. At 80% system "Budget nearly used: wrap up now — propose_conclusion and list open disagreements as unresolved." At 100% system "Budget exhausted: agree on a conclusion now." and no more resumes. When every reviewer is done/stalled/failed with no conclusion → write `conclusion.md` from findings (agreed/resolved → changes, contested/open → unresolved), status `completed`.
- **Checkpoints:** pending → run status `waiting`; resolved → `running`.
- **Executor:** on `executor_requested` → write `conclusion.md`; `auto_apply` → start executor with all changes, else `apply` checkpoint. On approval → `room.add_participant("executor")`, spawn `record.executor` in `execute` mode with prompt role `executor` plus "Apply exactly these approved changes:\n- …\nUser note: …\nDo not commit. When done, send_message a summary of what you changed and end your turn." On exit → `git diff --stat` in cwd if git repo → `executor.md`; kill reviewers; status `completed`. Rejected apply → status `completed` without executor.
- **Stop:** kill all, status `stopped`.
- Every room event, agent event, status change → `store.append` + subscribers.

- [ ] **Step 1: Failing tests** — `tests/helpers.py`:
```python
class FakeSpawn:
    """Each agent is a script: async def script(tool, attempt) -> exit_code.
    `tool(name, args)` calls run.call_tool as that agent."""
    def __init__(self, scripts): self.scripts, self.calls, self.killed = scripts, [], []
    def bind(self, run): self.run = run
    async def __call__(self, adapter, o, on_event):
        agent = o.bridge.env["COLLAB_AGENT"]
        attempt = sum(1 for c in self.calls if c[0] == agent) + 1
        self.calls.append((agent, o.mode, o.resume_session_id))
        on_event(AgentEvent("session", {"session_id": f"{agent}-s"}))
        tool = lambda n, a={}: self.run.call_tool(agent, n, a)
        task = asyncio.create_task(self.scripts[agent](tool, attempt))
        fake = self
        class P:
            async def wait(self): return await task
            def kill(self): fake.killed.append(agent); task.cancel()
        return P()
```
Tests (full bodies written during implementation; each script 3–8 lines):
```python
async def test_resumes_agent_that_exits_early(): ...   # claude attempt 1 exits 0 silently, attempt 2 proposes; codex agrees
                                                        # → claude spawned twice, 2nd with resume id "claude-s"; concluded
async def test_stalls_after_three_idle_exits(): ...     # codex always exits silently → 1 start + 3 resumes... status stalled + system msg
async def test_budget_wrap_up_and_unresolved(): ...     # max_messages=5, ping-pong; wrap-up msg; conclusion.md lists contested id under Unresolved
async def test_apply_gate_then_executor(): ...          # request_executor → apply checkpoint, status waiting; approve selected=[0] → executor spawned mode execute
async def test_auto_apply_skips_gate(): ...
async def test_split_plan_waits_for_user(): ...         # agents see "User approved the split plan." via wait_for_messages
async def test_stop_kills_everything(): ...             # killed contains both agents; status stopped; events.jsonl exists
```
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(runs): run lifecycle with keep-alive, budget, checkpoints, executor`

---

### Task 8: HTTP server + SSE + entrypoint

**Files:** Create `collab/server.py`, `collab/__main__.py`; Test `tests/test_server.py`

**Interfaces — Produces:**
- `create_app(store: RunStore, config: Config, spawn=spawn_agent, template_path=Path("prompts/collaboration.md")) -> FastAPI`; live runs in `app.state.runs: dict[str, Run]`.
- `GET /api/runs` → list of `RunRecord`
- `POST /api/runs` body `RunInput` → `{"id"}`; 400 if `cwd` does not exist; budget defaults from config
- `GET /api/runs/{id}` → live `run.snapshot()` or `{"record", "events"}` from store; 404 unknown
- `GET /api/runs/{id}/stream` → `text/event-stream`: first `event: snapshot`, then each stored event as `data: <json>`; for finished runs, replays stored events then closes
- `POST /api/runs/{id}/tool` `{"agent","name","args"}` → `{"text"}` (bridge endpoint)
- `POST /api/runs/{id}/message` `{"text"}`; `POST /api/runs/{id}/checkpoints/{cid}` `{"decision","selected"?,"note"?}`; `POST /api/runs/{id}/stop`
- `/` serves `web/dist` if present.
- `bridge_for(run_id, agent)` → `Bridge(sys.executable, ["-m", "collab.bridge"], {"COLLAB_URL": f"http://127.0.0.1:{port}", "COLLAB_RUN": run_id, "COLLAB_AGENT": agent, "PYTHONPATH": <project root>})`
- `__main__`: load config, mark store runs `running|waiting` as `interrupted`, `uvicorn.run(app, host="127.0.0.1", port=config.port)`, print URL.

- [ ] **Step 1: Failing tests** with `httpx.AsyncClient(transport=ASGITransport(app))` and `FakeSpawn` whose scripts just `await asyncio.sleep(10)`:
```python
async def test_create_relay_tool_and_stream(client, tmp_path): ...  # POST run; POST tool send_message → "sent"; GET snapshot shows message
async def test_bad_cwd_is_400(client): ...
async def test_user_message_reaches_room(client, tmp_path): ...
async def test_stop(client, tmp_path): ...                           # status stopped in GET /api/runs
async def test_unknown_run_404(client): ...
```
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(server): HTTP API, SSE, bridge endpoint`

---

### Task 9: Dashboard

**Files:** Create `web/package.json`, `web/index.html`, `web/vite.config.ts`, `web/tsconfig.json`, `web/src/main.tsx`, `web/src/api.ts`, `web/src/types.ts`, `web/src/reducer.ts`, `web/src/reducer.test.ts`, `web/src/App.tsx`, `web/src/views/{RunsList,StartForm,RunView}.tsx`, `web/src/components/{Chat,ActivityPanel,FindingsBoard,CheckpointPanel,StatusBar}.tsx`, `web/src/styles.css`

**Interfaces:**
- Consumes: HTTP API (Task 8); stored-event shape from Task 7 mirrored in `types.ts`.
- `reducer(state, event) -> state` — single place turning events into UI state, used for live SSE and replay. State: `messages`, `findings` (by id + status), `plans`, `conclusions`, `checkpoints`, `activity[agent]`, `agentStatus[agent]`, `runStatus`.
- `vite.config.ts`: react plugin, `build.outDir: "dist"`, dev proxy `/api` → `http://127.0.0.1:4747`. Tests with vitest.

UI:
- `#/` runs list + "New run". `#/new` start form (task, cwd, attachments one per line, agent A/B, executor, mode, auto-apply, budget). `#/run/:id` run view.
- Run view: status bar (run status, budget meter, agent status chips, Stop); left = agent A activity; center = chat (color per author, system grey, composer); right = agent B activity; findings board below chat (id, author, issue, change, stances, status badge); checkpoint panel above composer when pending (plan: slices + Approve/Reject; apply: checklist + note + Approve/Stop); executor panel when present.
- Tool calls collapsed to one line, click to expand.

- [ ] **Step 1: Failing reducer test**
```ts
it("builds chat, findings and activity from events", () => {
  let s = initialState();
  s = reducer(s, { at: 1, kind: "room", event: { type: "message", data: { seq: 1, sender: "claude", text: "hi", at: 1 } } });
  s = reducer(s, { at: 2, kind: "agent", agent: "codex", event: { type: "tool_call", data: { id: "t", name: "Read", input: {} } } });
  s = reducer(s, { at: 3, kind: "room", event: { type: "finding", data: { finding: { id: "claude-1" }, status: "contested" } } });
  expect(s.messages).toHaveLength(1);
  expect(s.activity.codex[0]).toMatchObject({ type: "tool_call" });
  expect(s.findings["claude-1"].status).toBe("contested");
});
```
- [ ] **Step 2–4:** `cd web && npm i && npx vitest run` FAIL → implement → PASS; `npm run build` succeeds; `uv run python -m collab` serves it.
- [ ] **Step 5: Commit** `feat(web): live dashboard`

---

### Task 10: Example + real end-to-end run

**Files:** Create `examples/toy/system_prompt.md` (deliberately flawed agent prompt), `examples/toy/eval-report.md` (~8 failing cases traceable to the prompt), `README.md`

- [ ] **Step 1:** Write example + README (install with `uv sync` and `cd web && npm i && npm run build`, start with `uv run python -m collab`, what each panel shows, config keys, permission notes).
- [ ] **Step 2:** `uv run pytest` all PASS; `cd web && npx vitest run` PASS.
- [ ] **Step 3: Real run.** Start: cwd `examples/toy`, attachment `examples/toy/eval-report.md`, task "Figure out prompt changes that would fix the failing evals", Claude + Codex, auto-apply off. Verify:
  - both agents post and reference each other's findings
  - findings board fills with stances
  - apply gate appears; approve with one item unticked
  - executor edits `system_prompt.md`, skips the unticked change, commits nothing
  - `runs/<id>/` has `events.jsonl`, `conclusion.md`, `executor.md`
  - reopening from the runs list replays it
- [ ] **Step 4:** Fix failures via systematic debugging; restore `examples/toy` afterward.
- [ ] **Step 5: Commit** `docs: README and toy example`
