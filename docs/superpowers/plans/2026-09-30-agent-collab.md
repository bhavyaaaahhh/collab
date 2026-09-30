# Agent Collab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local app where two CLI agents (Claude/Codex) talk to each other directly through a shared MCP chat room, with a live web dashboard, user checkpoints, and an executor session.

**Architecture:** One Node + TypeScript process holds all room state, serves an HTTP API + SSE stream + static dashboard, and spawns agent CLIs. Each CLI gets a small stdio MCP bridge that forwards room tool calls to the app over localhost HTTP. Collaboration behavior lives in `prompts/collaboration.md`, not code.

**Tech Stack:** Node 25, TypeScript (run via `tsx`), Express, Vitest, Vite + React for the dashboard.

**Spec:** `docs/superpowers/specs/2026-09-30-agent-collab-design.md`

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

1. Agent exits early while run is open → must be resumed, and marked stalled after 3 exits with no room activity (Task 7 test).
2. `request_executor` before both agents agreed on the same proposal → rejected with an explanatory error the agent can read (Task 3 test).
3. Budget exhausted while agents keep talking → wrap-up at 80%, forced conclusion with contested findings marked unresolved at 100% (Task 7 test).
4. User clicks Stop mid-run → all child processes killed, run status `stopped`, artifacts kept (Task 7 test).
5. Malformed/unknown lines in CLI JSON streams (hooks, rate-limit events) → ignored, never crash the parser (Task 5 test).

---

## File Structure

```
package.json, tsconfig.json, vitest.config.ts, collab.config.json
prompts/collaboration.md            working agreement (the collaboration prompt)
src/room/types.ts                   Message, Finding, Stance, Proposal, Checkpoint, RoomEvent
src/room/room.ts                    Room class: state + rules, emits RoomEvent
src/room/tools.ts                   MCP tool definitions + dispatch(room, agent, name, args)
src/bridge/mcp-bridge.ts            stdio MCP server; forwards tools/call to app HTTP
src/agents/types.ts                 AgentEvent, AgentAdapter, AgentProcess
src/agents/claude.ts                build args + parse stream-json
src/agents/codex.ts                 build args + parse --json
src/agents/spawn.ts                 spawn CLI, split stdout lines, feed parser
src/runs/store.ts                   runs/<id>/ files: run.json, events.jsonl, artifacts
src/runs/prompt.ts                  fill collaboration.md
src/runs/run.ts                     Run: room + agents + keep-alive + budget + checkpoints
src/server/app.ts                   Express routes + SSE
src/main.ts                         load config, start server
web/                                Vite React dashboard
tests/**                            vitest
examples/toy/                       small sample task repo for manual E2E
```

---

### Task 1: Scaffold

**Files:** Create `package.json`, `tsconfig.json`, `vitest.config.ts`, `collab.config.json`, `.gitignore`

- [ ] **Step 1: Create files**

`package.json`:
```json
{
  "name": "agent-collab",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "npm run build:web && tsx src/main.ts",
    "dev": "tsx watch src/main.ts",
    "build:web": "vite build web",
    "dev:web": "vite web",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  }
}
```
Then: `npm i express @modelcontextprotocol/sdk zod && npm i -D typescript tsx vitest @types/express @types/node vite @vitejs/plugin-react react react-dom @types/react @types/react-dom`

`tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2023", "module": "NodeNext", "moduleResolution": "NodeNext",
    "strict": true, "esModuleInterop": true, "skipLibCheck": true,
    "jsx": "react-jsx", "noEmit": true
  },
  "include": ["src", "tests", "web/src"]
}
```

`collab.config.json`:
```json
{
  "port": 4747,
  "bin": { "claude": "claude", "codex": "codex" },
  "models": { "claude": null, "codex": null },
  "budget": { "maxMessages": 80, "maxMinutes": 30 },
  "waitTimeoutMs": 40000
}
```

`.gitignore`: `node_modules/`, `runs/`, `web/dist/`

- [ ] **Step 2:** `npx vitest run` → "No test files found" (exit ok with `--passWithNoTests` is fine). `npx tsc --noEmit` → no errors.
- [ ] **Step 3: Commit** `chore: scaffold project`

---

### Task 2: Room types and state rules

**Files:** Create `src/room/types.ts`, `src/room/room.ts`; Test `tests/room/room.test.ts`

**Interfaces — Produces:**
```ts
export type AgentName = string;                 // "claude", "codex", "claude-2", "executor"
export type Author = AgentName | "user" | "system";
export interface Message { seq: number; from: Author; text: string; at: number }
export type StanceKind = "agree" | "disagree" | "partial";
export interface Stance { by: AgentName; stance: StanceKind; reasoning: string; amendedChange?: string; at: number }
export interface Finding {
  id: string; author: AgentName; cases: string[]; issue: string; evidence: string;
  proposedChange: string; confidence: "high" | "medium" | "low";
  stances: Stance[]; revision: number;
}
export type FindingStatus = "open" | "agreed" | "contested" | "resolved";
export interface Plan { id: string; by: AgentName; mode: "independent" | "split"; slices?: Record<AgentName, string>; endorsedBy: AgentName[] }
export interface Conclusion { id: string; by: AgentName; changes: string[]; unresolved: string[]; agreedBy: AgentName[]; rejectedBy: { by: AgentName; reason: string }[] }
export type Checkpoint =
  | { id: string; kind: "plan"; planId: string; status: "pending" | "approved" | "rejected" }
  | { id: string; kind: "apply"; conclusionId: string; status: "pending" | "approved" | "rejected"; selected?: number[]; note?: string };
export type RoomEvent =
  | { type: "message"; message: Message }
  | { type: "finding"; finding: Finding; status: FindingStatus }
  | { type: "plan"; plan: Plan }
  | { type: "conclusion"; conclusion: Conclusion }
  | { type: "checkpoint"; checkpoint: Checkpoint }
  | { type: "executor_requested"; conclusionId: string };
export class RoomError extends Error {}
```

`Room` (in `room.ts`), constructed `new Room(participants: AgentName[], defaultMode: "independent" | "split")`, extends `EventEmitter` emitting `"event"` with `RoomEvent`:
- `post(from, text): Message`
- `messagesFor(agent, afterSeq): Message[]` — messages with seq > afterSeq and `from !== agent`
- `waitFor(agent, afterSeq, timeoutMs, signal?): Promise<Message[]>` — resolves as soon as `messagesFor` is non-empty, else `[]` after timeout
- `postFinding(author, f): Finding` — id `${author}-${n}`
- `respond(by, findingId, stance, reasoning, amendedChange?)` — throws `RoomError` if `by === author` or finding missing
- `updateFinding(by, id, patch)` — only author; bumps `revision`; clears nothing (stances stay, history kept)
- `findingStatus(f): FindingStatus`:
  - no stance from a non-author → `open`
  - latest non-author stance `agree` and `revision === 0` → `agreed`
  - latest non-author stance `agree` and `revision > 0` → `resolved`
  - otherwise → `contested`
- `proposePlan(by, mode, slices?)` → Plan endorsed by `by`; `endorsePlan(by, planId)`. When all participants endorse: if `mode === defaultMode && mode === "independent"` post system message "Plan accepted." Else create a `plan` checkpoint.
- `proposeConclusion(by, changes, unresolved)` → Conclusion agreed by `by`; `agreeConclusion(by, id)`; `rejectConclusion(by, id, reason)` (posts reason to room as that agent).
- `isConcluded(): Conclusion | undefined` — a conclusion agreed by all participants.
- `requestExecutor(by, conclusionId)` — throws `RoomError("Both participants must agree_to_conclusion on this proposal first.")` unless that conclusion is agreed by all; emits `executor_requested`.
- `resolveCheckpoint(id, status, extra?)` — updates, emits, posts system message (e.g. "User approved the split plan." / "User rejected the split plan; do a full independent review.").
- `snapshot()` — plain object of all state (for store + dashboard initial load).

- [ ] **Step 1: Write failing tests**

```ts
import { describe, it, expect } from "vitest";
import { Room, RoomError } from "../../src/room/room.js";

const room = () => new Room(["claude", "codex"], "independent");
const f = { cases: ["14"], issue: "i", evidence: "e", proposedChange: "c", confidence: "high" as const };

describe("Room", () => {
  it("delivers only other agents' messages after a seq", () => {
    const r = room();
    r.post("claude", "hi"); r.post("codex", "yo"); r.post("user", "focus");
    expect(r.messagesFor("claude", 0).map(m => m.text)).toEqual(["yo", "focus"]);
    expect(r.messagesFor("claude", 2).map(m => m.text)).toEqual(["focus"]);
  });

  it("waitFor resolves when a message arrives and [] on timeout", async () => {
    const r = room();
    const p = r.waitFor("claude", 0, 1000);
    setTimeout(() => r.post("codex", "late"), 20);
    expect((await p).map(m => m.text)).toEqual(["late"]);
    expect(await r.waitFor("claude", 1, 30)).toEqual([]);
  });

  it("derives finding status", () => {
    const r = room();
    const a = r.postFinding("claude", f);
    expect(a.id).toBe("claude-1");
    expect(r.findingStatus(a)).toBe("open");
    r.respond("codex", a.id, "disagree", "no");
    expect(r.findingStatus(a)).toBe("contested");
    r.updateFinding("claude", a.id, { proposedChange: "c2" });
    r.respond("codex", a.id, "agree", "ok now");
    expect(r.findingStatus(a)).toBe("resolved");
    const b = r.postFinding("codex", f);
    r.respond("claude", b.id, "agree", "yes");
    expect(r.findingStatus(b)).toBe("agreed");
  });

  it("rejects self-stance and non-author updates", () => {
    const r = room();
    const a = r.postFinding("claude", f);
    expect(() => r.respond("claude", a.id, "agree", "")).toThrow(RoomError);
    expect(() => r.updateFinding("codex", a.id, {})).toThrow(RoomError);
  });

  it("split plan needs a user checkpoint once both endorse", () => {
    const r = room(); const events: any[] = [];
    r.on("event", e => events.push(e));
    const p = r.proposePlan("claude", "split", { claude: "1-18", codex: "19-40" });
    expect(events.some(e => e.type === "checkpoint")).toBe(false);
    r.endorsePlan("codex", p.id);
    expect(events.find(e => e.type === "checkpoint")?.checkpoint.kind).toBe("plan");
  });

  it("independent plan matching default needs no checkpoint", () => {
    const r = room(); const events: any[] = [];
    r.on("event", e => events.push(e));
    const p = r.proposePlan("claude", "independent");
    r.endorsePlan("codex", p.id);
    expect(events.some(e => e.type === "checkpoint")).toBe(false);
  });

  it("request_executor requires both agents on the same conclusion", () => {
    const r = room();
    const c = r.proposeConclusion("claude", ["x"], []);
    expect(() => r.requestExecutor("claude", c.id)).toThrow(/Both participants/);
    r.agreeConclusion("codex", c.id);
    expect(r.isConcluded()?.id).toBe(c.id);
    expect(() => r.requestExecutor("claude", c.id)).not.toThrow();
  });
});
```

- [ ] **Step 2:** `npx vitest run tests/room` → FAIL (module not found)
- [ ] **Step 3:** Implement `types.ts` and `room.ts` per the interface above. `waitFor` implementation: check `messagesFor`; if empty, subscribe to `"event"` for `type === "message"` and resolve on first matching message; `setTimeout` resolves `[]`; clean up listener in both paths; honor `signal.abort`.
- [ ] **Step 4:** `npx vitest run tests/room` → PASS
- [ ] **Step 5: Commit** `feat(room): room state and collaboration rules`

---

### Task 3: Room tools (definitions + dispatch)

**Files:** Create `src/room/tools.ts`; Test `tests/room/tools.test.ts`

**Interfaces:**
- Consumes: `Room` from Task 2.
- Produces:
```ts
export interface ToolDef { name: string; description: string; inputSchema: object }
export const TOOL_DEFS: ToolDef[];
export const TOOL_NAMES: string[];            // for --allowedTools as mcp__room__<name>
export interface AgentCursor { lastSeq: number }
export async function dispatch(room: Room, agent: string, cursor: AgentCursor,
  name: string, args: any, opts: { waitTimeoutMs: number; signal?: AbortSignal }): Promise<string>;
```
Tools: `send_message{text}`, `wait_for_messages{}`, `read_room{since?}`, `post_finding{cases,issue,evidence,proposedChange,confidence}`, `respond_to_finding{id,stance,reasoning,amendedChange?}`, `update_finding{id,patch}`, `propose_plan{mode,slices?}`, `endorse_plan{planId}`, `propose_conclusion{changes,unresolved}`, `agree_to_conclusion{proposalId}`, `reject_conclusion{proposalId,reason}`, `request_executor{proposalId}`, `list_findings{}`.

Return values are plain text the model reads. `wait_for_messages` formats `[from] text` blocks joined by blank lines, advances `cursor.lastSeq`, and on timeout returns `"No new messages yet. Call wait_for_messages again."`. `RoomError` is caught and returned as `"Error: <message>"` (not thrown), so the agent can recover.

- [ ] **Step 1: Write failing tests**

```ts
import { describe, it, expect } from "vitest";
import { Room } from "../../src/room/room.js";
import { dispatch, TOOL_DEFS } from "../../src/room/tools.js";

const opts = { waitTimeoutMs: 30 };

describe("room tools", () => {
  it("defines every tool with a schema", () => {
    expect(TOOL_DEFS.map(t => t.name)).toContain("wait_for_messages");
    for (const t of TOOL_DEFS) expect(t.inputSchema).toHaveProperty("type", "object");
  });

  it("send + wait round trip advances the cursor", async () => {
    const r = new Room(["claude", "codex"], "independent");
    const cc = { lastSeq: 0 }, xc = { lastSeq: 0 };
    await dispatch(r, "claude", cc, "send_message", { text: "hello" }, opts);
    expect(await dispatch(r, "codex", xc, "wait_for_messages", {}, opts)).toContain("[claude] hello");
    expect(await dispatch(r, "codex", xc, "wait_for_messages", {}, opts)).toMatch(/No new messages/);
  });

  it("returns room errors as text", async () => {
    const r = new Room(["claude", "codex"], "independent");
    const out = await dispatch(r, "claude", { lastSeq: 0 }, "request_executor", { proposalId: "nope" }, opts);
    expect(out).toMatch(/^Error:/);
  });

  it("post_finding returns the new id", async () => {
    const r = new Room(["claude", "codex"], "independent");
    const out = await dispatch(r, "claude", { lastSeq: 0 }, "post_finding",
      { cases: ["1"], issue: "i", evidence: "e", proposedChange: "c", confidence: "low" }, opts);
    expect(out).toContain("claude-1");
  });
});
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** Implement. Unknown tool → `"Error: unknown tool <name>"`.
- [ ] **Step 4:** run → PASS
- [ ] **Step 5: Commit** `feat(room): MCP tool definitions and dispatch`

---

### Task 4: stdio MCP bridge

**Files:** Create `src/bridge/mcp-bridge.ts`; Test `tests/bridge/bridge.test.ts`

**Interfaces:**
- Consumes: `TOOL_DEFS`; app endpoint `POST /api/runs/:runId/tool` body `{agent, name, args}` → `{text}` (Task 8).
- Produces: a script run as `tsx <abs>/src/bridge/mcp-bridge.ts` with env `COLLAB_URL`, `COLLAB_RUN`, `COLLAB_AGENT`. Uses `@modelcontextprotocol/sdk` `Server` + `StdioServerTransport`; `ListTools` returns `TOOL_DEFS`; `CallTool` POSTs and returns `{content:[{type:"text",text}]}`. HTTP failure → text `"Error: collab app unreachable (<msg>)"`.

- [ ] **Step 1: Write failing test** — start a tiny `http.createServer` fake on a random port that echoes `{text: \`${agent}:${name}\`}`, spawn the bridge via `Client` + `StdioClientTransport` from the SDK, and assert:

```ts
const { tools } = await client.listTools();
expect(tools.map(t => t.name)).toContain("send_message");
const res = await client.callTool({ name: "send_message", arguments: { text: "x" } });
expect((res.content as any)[0].text).toBe("claude:send_message");
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** Implement bridge (~40 lines).
- [ ] **Step 4:** run → PASS
- [ ] **Step 5: Commit** `feat(bridge): stdio MCP bridge to collab app`

---

### Task 5: Agent adapters (args + stream parsing)

**Files:** Create `src/agents/types.ts`, `src/agents/claude.ts`, `src/agents/codex.ts`; Tests `tests/agents/claude.test.ts`, `tests/agents/codex.test.ts`; Fixtures `tests/fixtures/claude.jsonl`, `tests/fixtures/codex.jsonl` (trimmed copies of real spike output, one line per event shape listed below)

**Interfaces — Produces:**
```ts
export type AgentKind = "claude" | "codex";
export type Mode = "review" | "execute";
export type AgentEvent =
  | { type: "session"; sessionId: string }
  | { type: "text"; text: string }
  | { type: "tool_call"; id: string; name: string; input: unknown }
  | { type: "tool_result"; id: string; summary: string; isError: boolean }
  | { type: "turn_end"; costUsd?: number }
  | { type: "error"; message: string };
export interface LaunchOpts {
  prompt: string; cwd: string; mode: Mode; resumeSessionId?: string;
  bridge: { command: string; args: string[]; env: Record<string, string> };
  model?: string | null; bin: string; mcpConfigPath: string; // claude only uses mcpConfigPath
}
export interface AgentAdapter {
  kind: AgentKind;
  buildCommand(o: LaunchOpts): { bin: string; args: string[]; env: Record<string, string>; files?: Record<string, string> };
  parseLine(line: string): AgentEvent[];     // never throws
}
```

Claude `buildCommand`:
- args: `-p <prompt> --output-format stream-json --verbose --mcp-config <mcpConfigPath> --strict-mcp-config --allowedTools <list>` + `--resume <id>` if resuming + `--model` if set.
- review: `--permission-mode default`, allowedTools = `mcp__room__*` names + `Read,Grep,Glob,LS`.
- execute: `--permission-mode acceptEdits`, allowedTools also `Edit,Write,MultiEdit,Bash`.
- `files`: `{ [mcpConfigPath]: JSON.stringify({ mcpServers: { room: bridge } }) }`.
- env: `MCP_TOOL_TIMEOUT=120000`.

Claude `parseLine` mapping (from spike output):
- `system/init` → `session`
- `assistant` content `text` → `text`; `tool_use` → `tool_call`; `thinking` → ignore
- `user` content `tool_result` → `tool_result` (summary = first 200 chars of text content)
- `result` → `turn_end` with `total_cost_usd`; if `is_error` also `error`
- anything else / invalid JSON → `[]`

Codex `buildCommand`:
- new: `exec --json --skip-git-repo-check -C <cwd> -s <read-only|workspace-write> <cfg...> <prompt>`
- resume: `exec resume <id> --json --skip-git-repo-check <cfg...> <prompt>` (resume takes no `-C`/`-s`; set sandbox via `-c sandbox_mode="..."` in cfg for both cases)
- cfg: `-c mcp_servers.room.command="<cmd>"`, `-c mcp_servers.room.args=[...]`, `-c mcp_servers.room.env={K="v",...}`, `-c mcp_servers.room.tool_timeout_sec=120`, `-c mcp_servers.room.default_tools_approval_mode="approve"`, plus `-m` if model set. Values are TOML: quote strings with `JSON.stringify`.

Codex `parseLine` mapping:
- `thread.started` → `session` (`thread_id`)
- `item.completed` `agent_message` → `text`
- `item.started` `mcp_tool_call` → `tool_call` (name = `tool`, input = `arguments`)
- `item.completed` `mcp_tool_call` → `tool_result` (summary from `result`/`error`, isError = `!!error`)
- `item.completed` `command_execution` → `tool_call` + `tool_result` (name `shell`)
- `turn.completed` → `turn_end`; `turn.failed`/`error` → `error`
- else → `[]`

- [ ] **Step 1: Write failing tests** (Claude shown; Codex mirrors with its fixture and mappings):

```ts
import { readFileSync } from "node:fs";
import { claude } from "../../src/agents/claude.js";

const lines = readFileSync("tests/fixtures/claude.jsonl", "utf8").split("\n");
const events = lines.flatMap(l => claude.parseLine(l));

it("extracts session, text, tool calls, results, turn end", () => {
  expect(events.find(e => e.type === "session")).toMatchObject({ sessionId: expect.any(String) });
  expect(events.some(e => e.type === "text")).toBe(true);
  expect(events.some(e => e.type === "tool_call" && e.name.startsWith("mcp__room__"))).toBe(true);
  expect(events.some(e => e.type === "tool_result")).toBe(true);
  expect(events.at(-1)).toMatchObject({ type: "turn_end" });
});

it("ignores junk and unknown events", () => {
  expect(claude.parseLine("not json")).toEqual([]);
  expect(claude.parseLine('{"type":"rate_limit_event"}')).toEqual([]);
  expect(claude.parseLine("")).toEqual([]);
});

it("review mode is read-only and resumes by id", () => {
  const c = claude.buildCommand({ prompt: "p", cwd: "/w", mode: "review", resumeSessionId: "s1",
    bridge: { command: "tsx", args: ["b.ts"], env: {} }, bin: "claude", mcpConfigPath: "/r/m.json" });
  expect(c.args).toContain("--resume");
  expect(c.args.join(" ")).toContain("--permission-mode default");
  expect(c.args.join(" ")).not.toMatch(/\bEdit\b/);
});
```

Codex extra test: resume args start with `["exec","resume","s1"]` and contain `default_tools_approval_mode="approve"`.

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** Build fixtures by copying one line of each shape from the spike output files, then implement adapters.
- [ ] **Step 4:** run → PASS
- [ ] **Step 5: Commit** `feat(agents): claude and codex adapters`

---

### Task 6: Spawner, store, prompt filling

**Files:** Create `src/agents/spawn.ts`, `src/runs/store.ts`, `src/runs/prompt.ts`, `prompts/collaboration.md`; Tests `tests/runs/store.test.ts`, `tests/runs/prompt.test.ts`, `tests/agents/spawn.test.ts`

**Interfaces — Produces:**
```ts
// spawn.ts
export interface AgentProcess { exited: Promise<number>; kill(): void }
export function spawnAgent(adapter: AgentAdapter, o: LaunchOpts, onEvent: (e: AgentEvent) => void): AgentProcess;
// writes cmd.files, spawns cmd.bin with cmd.args (cwd = o.cwd, env = process.env + cmd.env),
// splits stdout by "\n", parseLine each, stderr lines → { type:"error" } only if the process exits non-zero.

// store.ts
export class RunStore {
  constructor(root: string);                    // default "runs"
  create(input: RunInput): string;              // returns runId (timestamp + 4 random chars), writes run.json
  append(runId: string, event: StoredEvent): void;  // events.jsonl
  writeArtifact(runId: string, name: string, content: string): void;
  updateRun(runId: string, patch: Partial<RunRecord>): void;
  list(): RunRecord[];
  events(runId: string): StoredEvent[];
}
export interface RunInput {
  task: string; cwd: string; attachments: string[];
  agents: [AgentKind, AgentKind]; executor: AgentKind;
  defaultMode: "independent" | "split"; autoApply: boolean;
  budget: { maxMessages: number; maxMinutes: number };
}
export interface RunRecord extends RunInput {
  id: string; status: "running" | "waiting" | "completed" | "stopped" | "failed" | "interrupted";
  createdAt: number; sessions: Record<string, string>;
}
export type StoredEvent = { at: number } & (
  | { kind: "room"; event: RoomEvent }
  | { kind: "agent"; agent: string; event: AgentEvent }
  | { kind: "status"; agent: string; status: "working" | "waiting" | "stalled" | "done" | "failed" }
  | { kind: "run"; status: RunRecord["status"] });

// prompt.ts
export function agentNames(kinds: [AgentKind, AgentKind]): [string, string]; // ["claude","codex"] or ["claude-1","claude-2"]
export function buildPrompt(template: string, v: { me: string; partner: string; cwd: string;
  attachments: string[]; defaultMode: string; budget: RunInput["budget"]; task: string; role: "reviewer" | "executor" }): string;
```

`buildPrompt` replaces `{{me}}`, `{{partner}}`, `{{cwd}}`, `{{attachments}}` (bullet list or "none"), `{{defaultMode}}`, `{{maxMessages}}`, `{{maxMinutes}}`, `{{role}}`, then appends `\n\n## Task from the user\n\n${task}`. Unknown `{{x}}` left as is.

`prompts/collaboration.md` (first version):

```markdown
# How you work in this session

You are **{{me}}**, a {{role}} in a two-agent collaboration. Your partner is **{{partner}}**, another AI agent working in the same directory (`{{cwd}}`). The user is watching everything live and may post messages in the room.

You talk to your partner only through the room tools (`send_message`, `wait_for_messages`, and the findings/plan/conclusion tools). Your partner cannot see your private reasoning or tool output — if it matters, say it in the room.

Attached files: {{attachments}}

## Working agreement

1. **Agree on a plan first.** One of you proposes with `propose_plan` (default mode: `{{defaultMode}}`), the other endorses or counter-proposes. `independent` = both of you cover everything. `split` = you divide the work; the user must approve a split before you proceed.
2. **Do your own pass before reading theirs.** Investigate yourself and `post_finding` for each issue before you look at your partner's findings. This is what makes two opinions worth more than one.
3. **Evidence or it didn't happen.** Every finding and every argument cites something concrete: file:line, a quote, a trace excerpt, a case id.
4. **Review every partner finding.** Use `respond_to_finding` with agree / disagree / partial and a reason. Also flag anything they missed.
5. **Disagree honestly.** Don't concede to be polite. Concede explicitly — and `update_finding` — when the evidence shows you were wrong. Prefer a concrete compromise over a stalemate.
6. **Keep messages short and specific.** One topic per message. Reference finding ids.
7. **Stay in the conversation.** After sending, always call `wait_for_messages`. If it says no new messages, call it again. Never end your turn while the collaboration is open.
8. **User messages come first.** If the user posts, address it before anything else.
9. **Finish together.** When nothing is left to debate, one of you calls `propose_conclusion` (list of concrete changes + anything still unresolved). The other reviews it and calls `agree_to_conclusion` or `reject_conclusion` with a reason. Once both agreed, call `request_executor` if the task involves changing files. Then end your turn.

## Budget

About {{maxMessages}} room messages and {{maxMinutes}} minutes. If the room tells you to wrap up, move straight to a conclusion and list open disagreements as unresolved.
```

Executor role uses the same template with `role: "executor"` plus appended section (in `run.ts`, Task 7): "Apply exactly these approved changes: … User note: … Do not commit. When done, `send_message` a summary of what you changed and end your turn."

- [ ] **Step 1: Write failing tests**

```ts
// prompt.test.ts
it("fills variables and appends task", () => {
  const p = buildPrompt("I am {{me}}, partner {{partner}}, {{attachments}}, {{unknown}}",
    { me: "claude", partner: "codex", cwd: "/w", attachments: ["/r.json"], defaultMode: "independent",
      budget: { maxMessages: 80, maxMinutes: 30 }, task: "fix evals", role: "reviewer" });
  expect(p).toContain("I am claude, partner codex, - /r.json, {{unknown}}");
  expect(p.endsWith("fix evals")).toBe(true);
});
it("names same-kind agents distinctly", () => {
  expect(agentNames(["claude", "claude"])).toEqual(["claude-1", "claude-2"]);
  expect(agentNames(["claude", "codex"])).toEqual(["claude", "codex"]);
});

// store.test.ts (tmp dir via fs.mkdtempSync)
it("creates, appends, lists and replays", () => {
  const s = new RunStore(tmp);
  const id = s.create(input);
  s.append(id, { at: 1, kind: "run", status: "running" });
  expect(s.events(id)).toHaveLength(1);
  expect(s.list()[0].id).toBe(id);
});

// spawn.test.ts — fake adapter whose buildCommand returns node -e printing two JSON lines
it("feeds parsed stdout lines to onEvent and resolves exit code", async () => {
  const seen: any[] = [];
  const p = spawnAgent(fakeAdapter, opts, e => seen.push(e));
  expect(await p.exited).toBe(0);
  expect(seen.map(e => e.type)).toEqual(["session", "text"]);
});
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** Implement the three modules and write `prompts/collaboration.md`.
- [ ] **Step 4:** run → PASS
- [ ] **Step 5: Commit** `feat(runs): spawner, run store, collaboration prompt`

---

### Task 7: Run — keep-alive, budget, checkpoints, executor, stop

**Files:** Create `src/runs/run.ts`; Test `tests/runs/run.test.ts`

**Interfaces:**
- Consumes: `Room`, `dispatch`, `spawnAgent`, adapters, `RunStore`, `buildPrompt`, `agentNames`.
- Produces:
```ts
export interface RunDeps {
  store: RunStore; adapters: Record<AgentKind, AgentAdapter>;
  spawn: typeof spawnAgent; template: string; config: Config; bridgeFor(runId: string, agent: string): LaunchOpts["bridge"];
  now?: () => number;
}
export class Run extends EventEmitter {              // emits "event" (StoredEvent)
  readonly id: string; readonly room: Room;
  constructor(input: RunInput, deps: RunDeps);
  start(): void;
  callTool(agent: string, name: string, args: unknown): Promise<string>;   // used by HTTP bridge endpoint
  userMessage(text: string): void;
  resolveCheckpoint(id: string, decision: "approved" | "rejected", extra?: { selected?: number[]; note?: string }): void;
  stop(): void;
  snapshot(): object;                                 // record + room snapshot + agent statuses
}
```

Behavior:
- `start`: create room with `agentNames(input.agents)`; for each, build prompt and spawn in `review` mode; record session ids from `session` events into `run.json`.
- **Keep-alive:** when an agent process exits and the run is still open (not concluded, not stopped), resume with prompt `"The collaboration is still open. Call wait_for_messages and continue."`. Track `exitsWithoutActivity` per agent (reset whenever that agent calls any room tool). At 3 → status `stalled`, post system message to room, stop resuming. Non-zero exit counts too; if resume itself exits non-zero immediately twice → `failed` + system message to partner.
- An agent that exits after `room.isConcluded()` → status `done`.
- **Budget:** count room messages from agents; also a timer. At 80% post system "Budget nearly used: wrap up now — propose_conclusion, list open disagreements as unresolved." At 100% post "Budget exhausted: agree on a conclusion now." and stop resuming. When all agents are done/stalled/failed without a conclusion, write `conclusion.md` from findings: agreed/resolved as changes, contested/open as unresolved.
- **Checkpoints:** `plan` and `apply` checkpoints set run status `waiting`; resolving sets back to `running`. Room posts the result so waiting agents see it.
- **Executor:** on `executor_requested`: write `conclusion.md`; if `autoApply` → start executor directly with all changes; else create `apply` checkpoint. On approval: spawn executor (kind `input.executor`, name `"executor"`, mode `execute`, participant added to room so it can talk) with selected changes + note. When executor exits: if `cwd` is a git repo, run `git diff --stat` and write `executor.md`; run `completed`; kill remaining agents.
- **Stop:** kill all processes, status `stopped`.
- Every room event and agent event → `store.append` and `emit("event")`.

- [ ] **Step 1: Write failing tests** with a fake spawn: each fake agent is scripted as an async function receiving `callTool` and exit control.

```ts
function fakeSpawn(scripts: Record<string, (ctx: Ctx) => Promise<number>>) { /* returns spawn fn: looks up
  script by the COLLAB_AGENT env in o.bridge.env, runs it with ctx = { tool: (n,a)=>run.callTool(agent,n,a),
  attempt }, resolves exited with its return code, records calls */ }

it("resumes an agent that exits early, and it can finish", async () => { /* claude script: attempt 1
  exits 0 without tools; attempt 2 proposes conclusion. codex agrees. assert spawn called twice for claude,
  resumeSessionId set on 2nd, room.isConcluded() true */ });

it("marks stalled after 3 idle exits", async () => { /* script always exits 0 without tools →
  3 resumes then status "stalled" and a system message */ });

it("posts wrap-up at 80% budget and marks contested findings unresolved at 100%", async () => {
  /* maxMessages 5; agents ping-pong send_message; assert system wrap-up message after 4th,
     conclusion.md contains "Unresolved" with the contested finding id */ });

it("apply gate: request_executor creates checkpoint; approval spawns executor in execute mode", async () => {});

it("autoApply skips the checkpoint", async () => {});

it("split plan waits for user approval and agents see the decision", async () => {});

it("stop kills all processes", async () => { /* assert kill called on every live process, status stopped */ });
```

Write each test body in full while implementing — fake scripts are short (3–8 lines each).

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** Implement `run.ts`.
- [ ] **Step 4:** run → PASS
- [ ] **Step 5: Commit** `feat(runs): run lifecycle with keep-alive, budget, checkpoints, executor`

---

### Task 8: HTTP server + SSE + main

**Files:** Create `src/server/app.ts`, `src/main.ts`, `src/config.ts`; Test `tests/server/app.test.ts`

**Interfaces — Produces (HTTP):**
- `GET /api/runs` → `RunRecord[]`
- `POST /api/runs` body `RunInput` → `{ id }` (validated with zod; 400 on bad input; cwd must exist)
- `GET /api/runs/:id` → snapshot (live run) or `{ record, events }` from store (past run)
- `GET /api/runs/:id/stream` → SSE; sends `event: snapshot` first, then each `StoredEvent` as `data:`
- `POST /api/runs/:id/tool` body `{agent, name, args}` → `{ text }` (bridge endpoint; 404 unknown run)
- `POST /api/runs/:id/message` `{text}`; `POST /api/runs/:id/checkpoints/:cid` `{decision, selected?, note?}`; `POST /api/runs/:id/stop`
- Static `web/dist` at `/`.
- `createApp(deps): { app: Express; runs: Map<string, Run> }`; `main.ts` loads `collab.config.json`, marks store runs with status `running|waiting` as `interrupted`, listens on `127.0.0.1:<port>`, logs URL.
- `bridgeFor(runId, agent)` → `{ command: process.execPath, args: ["--import", "tsx", <abs path to mcp-bridge.ts>], env: { COLLAB_URL, COLLAB_RUN: runId, COLLAB_AGENT: agent } }`.

- [ ] **Step 1: Write failing tests** using `app.listen(0)` + `fetch`, with `Run` built from fake spawn (reuse helper from Task 7 — move it to `tests/helpers/fakeSpawn.ts`):

```ts
it("creates a run, relays a tool call, streams events", async () => {
  const { id } = await post("/api/runs", validInput);
  const events = collectSSE(`/api/runs/${id}/stream`);
  const r = await post(`/api/runs/${id}/tool`, { agent: "claude", name: "send_message", args: { text: "hi" } });
  expect(r.text).toBe("sent");
  await expect.poll(() => events.some(e => e.kind === "room" && e.event.message?.text === "hi")).toBe(true);
});
it("rejects bad input with 400", async () => { expect((await rawPost("/api/runs", {})).status).toBe(400); });
it("user message reaches the room", async () => {});
it("stop marks the run stopped", async () => {});
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** run → PASS; `npx tsc --noEmit` clean
- [ ] **Step 5: Commit** `feat(server): HTTP API, SSE, bridge endpoint`

---

### Task 9: Dashboard

**Files:** Create `web/index.html`, `web/vite.config.ts`, `web/src/main.tsx`, `web/src/api.ts`, `web/src/reducer.ts`, `web/src/App.tsx`, `web/src/views/RunsList.tsx`, `web/src/views/StartForm.tsx`, `web/src/views/RunView.tsx`, `web/src/components/{Chat,ActivityPanel,FindingsBoard,CheckpointPanel,StatusBar}.tsx`, `web/src/styles.css`; Test `tests/web/reducer.test.ts`

**Interfaces:**
- Consumes: HTTP API from Task 8, `StoredEvent` types (import from `src/`).
- `reducer(state: RunViewState, e: StoredEvent): RunViewState` — the single place that turns events into UI state, used for both live SSE and replay. State: `messages`, `findings` (by id, with status), `plans`, `conclusions`, `checkpoints`, `activity[agent]` (text/tool_call/tool_result list), `agentStatus[agent]`, `runStatus`.
- `vite.config.ts`: `root: "web"`, react plugin, dev proxy `/api` → `http://127.0.0.1:4747`.

UI:
- `#/` runs list + "New run" button. `#/new` start form (task textarea, cwd, attachments one per line, agent A/B selects, executor select, mode, auto-apply checkbox, budget). `#/run/:id` run view.
- Run view layout: top status bar (run status, budget meter = agent messages / max, each agent's status chip); left activity panel agent A; center chat (color per author, system messages grey, composer at bottom posting to `/message`); right activity panel agent B; below chat a findings board table (id, author, issue, change, stances, status badge); checkpoint panel pinned above the composer when pending (plan: slices + Approve/Reject; apply: checklist of changes + note + Approve/Stop); executor activity panel appears when executor exists; Stop button in status bar.
- Tool calls in activity panels collapsed to one line (`▸ mcp__room__wait_for_messages`), click to expand input/result.

- [ ] **Step 1: Write failing reducer test**

```ts
it("builds chat, findings and activity from events", () => {
  let s = initialState();
  s = reducer(s, { at: 1, kind: "room", event: { type: "message", message: { seq: 1, from: "claude", text: "hi", at: 1 } } });
  s = reducer(s, { at: 2, kind: "agent", agent: "codex", event: { type: "tool_call", id: "t", name: "Read", input: {} } });
  s = reducer(s, { at: 3, kind: "room", event: { type: "finding", finding: { id: "claude-1" } as any, status: "contested" } });
  expect(s.messages).toHaveLength(1);
  expect(s.activity.codex[0]).toMatchObject({ type: "tool_call", name: "Read" });
  expect(s.findings["claude-1"].status).toBe("contested");
});
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** Implement reducer, then components. Keep CSS plain (grid layout, system font, dark/light via `prefers-color-scheme`).
- [ ] **Step 4:** reducer test PASS; `npm run build:web` succeeds.
- [ ] **Step 5: Commit** `feat(web): live dashboard`

---

### Task 10: Example + real end-to-end run

**Files:** Create `examples/toy/` (a git repo-shaped folder: `system_prompt.md` with a deliberately flawed agent prompt, `eval-report.md` with ~8 failing cases whose causes trace to the prompt), `README.md`

- [ ] **Step 1:** Write the example files and `README.md` (install, `npm start`, open URL, what each panel shows, config keys, permission notes).
- [ ] **Step 2:** `npm test` all PASS, `npm run typecheck` clean.
- [ ] **Step 3: Real run.** `npm start`, start a run: cwd `examples/toy`, attachment `examples/toy/eval-report.md`, task "Figure out prompt changes that would fix the failing evals", Claude + Codex, auto-apply off. Verify manually:
  - both agents post in the chat and reference each other's findings
  - findings board fills with stances
  - apply gate appears; approve with one item unticked
  - executor edits `system_prompt.md` (and not the unticked change); nothing committed
  - `runs/<id>/` contains `events.jsonl`, `conclusion.md`, `executor.md`
  - reopening the run from the runs list replays it
- [ ] **Step 4:** Record anything that failed; fix via systematic debugging before claiming done. Restore `examples/toy/system_prompt.md` afterward (`git checkout examples/toy`).
- [ ] **Step 5: Commit** `docs: README and toy example`
