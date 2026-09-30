# Agent Collab — Design

Date: 2026-09-30
Status: Draft, awaiting review

## Purpose

A local tool that lets two coding agents (Claude + Codex, Claude + Claude, or Codex + Codex) collaborate on one task: analyze independently, compare, debate disagreements, reach a conclusion, and optionally hand off to a third session that applies the result. The user watches everything live in a web dashboard and can intervene at checkpoints.

First use case: **eval triage**. Both agents read an eval report for the user's agent, propose prompt changes, reconcile their findings, and an executor session edits the prompts.

## Success criteria

- One command starts a local server; the user launches a run from the browser.
- Both agents' activity (messages, tool calls) streams live, side by side.
- Findings from both agents are compared into an agree / disagree / partial table.
- Disagreements are debated for at most N rounds; unresolved items are surfaced, never forced.
- A final `conclusion.md` is produced for every run.
- Executor applies approved changes to the target repo without committing.
- Every run is fully replayable from disk.

## Non-goals (v1)

- Re-running eval cases to verify hypotheses.
- More than two reviewers.
- Remote / multi-user access. Localhost only.
- Auto-committing or opening PRs.

## Architecture

Single Node + TypeScript process:

```
browser (dashboard)  <--SSE / HTTP-->  server  -->  orchestrator  -->  agent adapters  -->  claude / codex CLIs
                                                          |
                                                    runs/<id>/ (events.jsonl, artifacts)
```

### Units

| Unit | Responsibility | Depends on |
|---|---|---|
| `adapters/` | Spawn a CLI headless, stream normalized events, resume a session, return structured final output | CLI binaries |
| `orchestrator/` | Phase state machine; builds prompts from the preset; merges findings; waits on checkpoints | adapters, store, preset |
| `store/` | Append events to `events.jsonl`, write artifacts, list/replay runs | filesystem |
| `presets/` | Per-phase prompt templates + JSON schemas for a workflow (v1: `eval-triage`) | none |
| `server/` | HTTP API (start run, approve checkpoint, list runs) + SSE event stream + static dashboard | orchestrator, store |
| `web/` | Dashboard UI | server API |

### Agent adapter interface

```ts
interface AgentAdapter {
  kind: "claude" | "codex";
  // Runs one turn. First call starts a session; later calls resume it.
  turn(input: {
    prompt: string;
    cwd: string;
    schema?: object;          // JSON schema for the final message
    sessionId?: string;       // resume if present
    mode: "review" | "execute";
  }, onEvent: (e: AgentEvent) => void): Promise<{ sessionId: string; output: unknown; raw: string }>;
}

type AgentEvent =
  | { type: "text"; text: string }
  | { type: "tool_call"; name: string; input: unknown }
  | { type: "tool_result"; name: string; summary: string }
  | { type: "error"; message: string };
```

**Claude adapter:** `claude -p --output-format stream-json --verbose --json-schema <schema> [--resume <id>] --permission-mode <mode>`, run with `cwd` set to the target repo. Session id comes from the stream's init / result event.

**Codex adapter:** `codex exec --json --output-schema <file> -C <cwd> -s <sandbox> [--skip-git-repo-check]`; later turns use `codex exec resume <sessionId>`. The session id comes from the JSONL stream.

Permission mapping (configured once in `collab.config.json`):

| mode | Claude | Codex |
|---|---|---|
| review | `--permission-mode default`, write tools disallowed | `-s read-only` |
| execute | `--permission-mode acceptEdits` | `-s workspace-write` |

Reviewers run normally in the target repo with their usual read tools. Only the executor can write.

## Run lifecycle

Run inputs (from the start form): task description, eval report path, target repo path, agent A kind, agent B kind, executor kind (default Claude), split mode default (`independent` | `split`), auto-apply (default off), max debate rounds (default 3).

1. **Plan.** Both agents skim the task/report and each returns `{ recommendedMode, splitProposal? }`. If the configured mode is `independent` and neither agent proposes a split, continue. If a split is proposed, the run pauses at a **checkpoint**: the dashboard shows the proposal with Approve / Reject (reject = full independent review).
2. **Independent analysis.** Both agents run in parallel with no access to each other's output. Each returns a findings list:
   ```json
   { "findings": [ {
       "id": "A-1",
       "cases": ["eval case ids"],
       "issue": "what goes wrong",
       "evidence": "quotes from report / prompt file + line",
       "proposedChange": { "file": "path", "description": "...", "patchHint": "..." },
       "confidence": "high|medium|low"
   } ] }
   ```
3. **Cross-review.** Each agent (resumed session) is given the other's findings and returns a verdict per item: `agree | disagree | partial` + reasoning + (for partial) amended change. The orchestrator builds the agreement table:
   - agreed: both sides agree (either direction)
   - contested: at least one `disagree` or `partial`
4. **Debate.** Only contested items. Each round, both agents see the other's latest argument and return per item: `hold | concede | compromise` + argument (+ amended change for compromise). An item resolves when both agents land on the same position/change. Stops when all items resolve or max rounds hit; leftovers are marked `unresolved` with both final arguments.
5. **Conclusion.** Orchestrator writes `conclusion.md`: agreed changes, resolved items with how they were settled, unresolved items with both sides.
6. **Apply gate.** If auto-apply is off, run pauses at a checkpoint: user can untick changes, add a free-text note, then Approve (or Stop). If on, continue directly.
7. **Executor.** Fresh session in execute mode, given the approved change list + note. Edits files in the target repo; does not commit. Its final output summarizes what changed; the orchestrator records `git diff --stat` of the target repo if it is a git repo.

Split mode differs only in step 2 (each agent gets its assigned slice) and step 3 (cross-review checks the other's slice for mistakes and missed issues rather than overlap).

### Failure handling

- Adapter process exits non-zero or output fails schema validation: retry the turn once with the error appended; on second failure the run moves to `failed` with the error shown in the dashboard. Partial artifacts stay on disk.
- User can Stop a run at any time; child processes are killed.
- A checkpoint waits indefinitely; the server restarting marks in-progress runs `interrupted` (no resume in v1).

## Dashboard

- **Runs list:** past runs with status, open any to replay from `events.jsonl`.
- **Start form:** fields listed in Run lifecycle.
- **Run view:**
  - Phase timeline across the top (Plan → Analysis → Cross-review → Debate → Conclusion → Apply → Execute) with current phase highlighted.
  - Two columns, Agent A and Agent B, streaming text and collapsible tool calls. A third column appears for the executor.
  - Agreement table: item, A's position, B's position, status (agreed / contested / resolved / unresolved), expandable debate history.
  - Checkpoint panel appears in place when the run is waiting on the user.
  - Conclusion rendered as markdown at the end.

Transport: Server-Sent Events for the live stream, plain JSON POSTs for actions. Frontend is a small Vite + React app built into static files served by the same process.

## Storage

```
runs/<runId>/
  run.json            inputs, status, timestamps, agent session ids
  events.jsonl        every orchestrator + agent event, timestamped
  plan.json
  findings-A.json
  findings-B.json
  review-A.json
  review-B.json
  debate.json         per item, per round positions
  conclusion.md
  executor.md         executor summary + diff stat
```

Replay = read `events.jsonl` and feed it through the same UI reducer used for live events.

## Presets

A preset is a folder:

```
presets/eval-triage/
  plan.md  analysis.md  cross-review.md  debate.md  executor.md   (prompt templates)
  schemas/*.json                                                   (output schemas per phase)
```

Templates use simple `{{var}}` substitution (task, reportPath, repoPath, otherFindings, slice, etc.). The orchestrator is preset-agnostic; adding a "code review" preset later means adding a folder.

## Configuration

`collab.config.json` at project root: port, CLI binary paths, permission mapping, default models per agent kind, default max rounds.

## Testing

- **Adapters:** unit tests against recorded CLI stream fixtures (parse events, extract session id, extract final structured output). One opt-in smoke test per adapter that calls the real CLI with a trivial prompt.
- **Orchestrator:** tested with a fake adapter that returns scripted outputs, covering: all-agree path, debate that resolves, debate that hits max rounds, split proposal approve/reject, schema failure + retry, stop mid-run.
- **Store:** write + replay round trip.
- **End to end (manual):** a small sample eval report + toy prompt repo checked into `examples/`, run with Claude + Codex.
