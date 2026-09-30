# Agent Collab — Design

Date: 2026-09-30
Status: Draft, awaiting review

## Purpose

A local tool where two coding agents (Claude + Codex, Claude + Claude, or Codex + Codex) **talk to each other directly** to solve one task: they split or share the work, exchange findings, argue over disagreements, agree on a conclusion, and hand off to a third session that applies it. The user watches the whole conversation live in a web dashboard and can join it.

The tool is task-agnostic: the task is whatever the user writes when starting a run. There are no per-task presets or prompts.

Example: both agents get an eval report for the user's agent, work out prompt changes together, and an executor session edits the prompts.

## Core idea: a shared room, not an orchestrator

There is no controller deciding who speaks when. Each agent is a single long-running CLI session with a set of **room tools** (via MCP). They message each other, wait for replies, and maintain a shared findings board on their own initiative.

How they behave is governed by a **collaboration prompt** (the "working agreement"), not by code. The app is infrastructure: it carries messages, shows everything, enforces a budget, and gates the two actions that need the user's approval.

```
            ┌──────────── app (Node + TS) ────────────┐
 browser ◄──┤ dashboard (SSE)   room state   run store│
            └──────▲─────────────────▲────────────────┘
                   │ MCP (room tools)│
            Claude session      Codex session      (+ executor session later)
            (in working dir)     (in working dir)
```

## Success criteria

- One command starts the app; the user launches a run from the browser.
- The two agents exchange messages directly, with no scripted turn order.
- The dashboard shows the conversation as a chat, each agent's own reasoning and tool calls, and the shared findings board, all live.
- The user can post into the room mid-run, and both agents see it.
- A run ends only when both agents sign off on the same conclusion, or when the budget runs out (open items are then marked unresolved).
- A `conclusion.md` is written for every run; the executor applies approved changes without committing.
- Every run can be replayed from disk.
- Collaboration behavior can be changed by editing prompt files, with no code changes.

## Non-goals (v1)

- More than two collaborators (the room supports N; the UI and prompts assume 2).
- Agents spawning helper sessions other than the executor.
- Remote or multi-user access. Localhost only.
- Auto-commit or opening PRs.
- Resuming a run after the app restarts.

## Room tools (MCP)

Every agent in a run gets the same tools. The agent's identity comes from its MCP connection.

| Tool | Purpose |
|---|---|
| `send_message(text)` | Post to the room. |
| `wait_for_messages()` | Block ~40s for new messages from partner or user. Returns them, or "no new messages yet" (agent calls again). Keeps the call under both CLIs' MCP tool timeouts. |
| `read_room(since?)` | Re-read history (e.g. after context compaction). |
| `post_finding({cases, issue, evidence, proposedChange, confidence})` | Add a finding to the shared board. Returns an id (`claude-3`). |
| `respond_to_finding(id, {stance: agree\|disagree\|partial, reasoning, amendedChange?})` | Record a stance on a partner's finding. |
| `update_finding(id, patch)` | Author revises their own finding (e.g. after conceding). |
| `propose_plan({mode: independent\|split, slices?})` | Propose how to divide the work. Becomes a **user checkpoint** once both agents endorse it. |
| `propose_conclusion({changes[], unresolved[]})` | Propose the final outcome. |
| `agree_to_conclusion(proposalId)` / `reject_conclusion(proposalId, reason)` | Sign off, or push back. |
| `request_executor(proposalId)` | Only valid after both have agreed. Goes to the apply gate (user checkpoint unless auto-apply). |

Finding status is derived from stances: **agreed** (partner agrees), **contested** (disagree/partial not yet settled), **resolved** (author updated the finding and partner agreed), **unresolved** (still contested at the end).

## Collaboration prompt

One file, `prompts/collaboration.md`: the working agreement for every run, whatever the task. It covers:
   - who you are, who your partner is, how the room tools work
   - do your own independent pass and `post_finding` before reading your partner's findings (anti-anchoring)
   - back every claim with evidence (file:line, trace excerpt, case id)
   - disagree when the evidence says so; don't concede just to be agreeable; concede explicitly when shown wrong
   - keep messages short and specific; one topic per message
   - always `wait_for_messages` after sending; never end your turn while the partner is mid-discussion
   - how to finish: propose conclusion → both agree → request executor
   - treat user messages in the room as highest priority

The launcher fills it with `{{var}}` substitution (agent name, partner name, working directory, attached paths, default mode, budget), appends the user's task text as-is, and passes the result as the session's initial prompt.

The first version of this prompt is part of this project. They're expected to be iterated on after real runs.

## Agent sessions

### Launch

- **Claude:** `claude -p --output-format stream-json --verbose --mcp-config <room> --strict-mcp-config --allowedTools <room tools + read tools> --permission-mode default`, cwd = working directory, `MCP_TOOL_TIMEOUT` raised.
- **Codex:** `codex exec --json -C <working dir> -s read-only -c mcp_servers.room.* -c mcp_servers.room.default_tools_approval_mode="approve" -c mcp_servers.room.tool_timeout_sec=120`. Without the approval override, `codex exec` cancels MCP calls ("requires approval, but approval policy is never").
- Reviewers are read-only in the working directory but otherwise run like normal sessions with their usual read tools. Only the executor can write (`acceptEdits` / `-s workspace-write`).

### Keep-alive

A headless session ends when the model ends its turn. If an agent's process exits while the run is still open (no agreed conclusion, budget left), the launcher **resumes** that session (`claude -p --resume <id>` / `codex exec resume <id>`) with a nudge: "The collaboration is still open. Check the room." Repeated early exits (3 in a row with no room activity) mark the agent stalled and surface it in the dashboard.

### Stream capture

Each adapter parses its CLI's JSON event stream into normalized events (`text`, `tool_call`, `tool_result`, `error`, `session_started`, `exited`) so the dashboard shows each agent's private work, not just its room messages.

### Adapter interface

```ts
interface AgentAdapter {
  kind: "claude" | "codex";
  start(opts: { prompt: string; cwd: string; mcp: RoomConnection; mode: "review" | "execute" },
        onEvent: (e: AgentEvent) => void): AgentProcess;
  resume(sessionId: string, prompt: string, ...same): AgentProcess;
}
interface AgentProcess { sessionId: Promise<string>; exited: Promise<number>; kill(): void }
```

## Room server

- Room state (messages, findings, stances, proposals, checkpoints) lives in the app process, which is the single source of truth.
- Each agent's MCP server is a small stdio bridge spawned by its CLI. It forwards tool calls over localhost HTTP to the app, tagged with run id and agent name. This works with both CLIs' stdio MCP support and keeps all state in one place for the dashboard.
- Every room mutation is appended to `events.jsonl` and pushed to the dashboard over SSE.

## Run lifecycle

1. **Start.** The user fills the form: task text, working directory (the repo both agents run in), optional attached file paths (e.g. an eval report), agent A kind, agent B kind, executor kind (default Claude), default mode (`independent`/`split`), auto-apply (default off), budget (max messages, max wall time).
2. **Launch.** The app creates the room and starts both sessions with the filled prompts.
3. **Collaborate (agent-driven).** The agents talk, post findings, respond, debate. Typical shape, set by the prompt rather than code: agree on plan → independent pass → exchange findings → debate contested items → propose conclusion.
4. **Plan checkpoint.** When both endorse a `split` plan, the dashboard shows Approve / Reject. The agents' `wait_for_messages` returns the decision as a system message. An `independent` plan matching the default doesn't need approval.
5. **User messages.** At any time the user can post into the room.
6. **Conclusion.** Once both `agree_to_conclusion` on the same proposal, the app writes `conclusion.md`.
7. **Apply gate.** On `request_executor`: if auto-apply is off, the user sees the change list, can untick items, add a note, then Approve or Stop.
8. **Executor.** A fresh session in execute mode that also joins the room (it can ask the reviewers questions). It gets the approved changes and note, edits the working directory, doesn't commit, and posts a summary. The app records `git diff --stat` if the working directory is a git repo.
9. **End.** All sessions are stopped and the run is marked `completed`.

### Budget and failure handling

- **Budget:** at 80% of max messages or time, the app posts a system message telling the agents to wrap up and propose a conclusion. At 100%, it posts "budget exhausted", gives them one final turn to propose/agree, then writes `conclusion.md` with every contested finding marked unresolved.
- **Crash:** a non-zero exit gets one resume attempt. If that fails, the agent is marked failed, its partner is told via a system message, and the user can Stop or let the remaining agent conclude.
- **Stop:** the user can stop at any time; child processes are killed and artifacts kept.

## Dashboard

- **Runs list:** past runs with status; open any to replay.
- **Start form:** fields from step 1.
- **Run view:**
  - Center: the **room chat** (Claude / Codex / You / system messages), with a composer so the user can post.
  - Side panels: each agent's **private activity stream** (reasoning text, collapsible tool calls, file reads).
  - **Findings board:** each finding with author, both stances, status, and its linked discussion.
  - Checkpoint panels (plan approval, apply gate) appear inline when the run is waiting.
  - Budget meter and each agent's status (working / waiting / stalled / done).
  - Conclusion rendered at the end; the executor gets its own activity panel.
- Vite + React, built to static files served by the app. SSE for live events, JSON POSTs for actions.

## Storage

```
runs/<runId>/
  run.json          inputs, status, timestamps, agent session ids
  events.jsonl      every room + agent event, timestamped (source of truth for replay)
  prompts/          the exact filled prompts each agent received
  findings.json     final board snapshot
  conclusion.md
  executor.md       executor summary + diff stat
```

Replay feeds `events.jsonl` through the same UI reducer used for live runs.

## Configuration

`collab.config.json`: port, CLI binary paths, permission mapping, default models per agent kind, default budget.

## Testing

- **Room:** unit tests for tools and state rules (finding status derivation, conclusion needs both signatures, `request_executor` rejected before agreement, budget transitions).
- **MCP bridge:** protocol tests over stdio (initialize, tools/list, tools/call, forwarding).
- **Adapters:** parse recorded CLI stream fixtures; opt-in smoke test per CLI.
- **Launcher:** keep-alive and resume logic with a fake adapter (early exit → resume, stalled detection, crash path).
- **Scripted collaboration:** two fake agents driving the room tools through a full run (plan checkpoint, debate, conclusion, apply gate).
- **Manual end to end:** a small sample task + toy repo in `examples/`, run with Claude + Codex.

## Validation spike

A throwaway spike (outside the repo) checks the riskiest assumption before planning: a real Claude session and a real Codex session, each with a stdio MCP room server sharing state, exchange messages in headless mode using `wait_for_messages` polling. Results are recorded below.

Results (2026-09-30, Claude Code 2.1.285, codex-cli 0.159.2):

- **Works.** Claude and Codex exchanged 5 messages through the room, critiqued each other's proposals with reasons, converged, and both exited cleanly. Total ~100s, Claude cost ~$0.19.
- **Polling holds up.** In the first attempt Claude sat in `wait_for_messages` → timeout → call again for ~9 minutes without giving up, so 40s polling under the MCP timeout keeps a headless session alive.
- **Codex needs `default_tools_approval_mode="approve"`** on the room server (valid values: `auto`, `prompt`, `writes`, `approve`). Without it, `codex exec` cancels every MCP call.
- **Claude needs the room tools in `--allowedTools`.**
- **Still to verify in implementation:** keep-alive resume after an early exit, since neither agent exited early in the spike.
