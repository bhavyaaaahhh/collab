# Related projects — 2026-10-01

First research pass (no earlier report). Compared against collab as of branch `task-10-example-e2e`.

## Summary

- **Nobody else combines collab's pieces.** Close projects either relay messages between interactive sessions (agents-council, crew, CCB) or run a fixed pipeline with one agent in charge (team-loop, pal-mcp). None pair a structured findings board, both agents signing off on a conclusion, and a separate executor. The peer-to-peer design is a real point of difference.
- **The biggest gap is after execution.** team-loop captures the full diff, including untracked files, and has the reviewer check the implementation before finishing. collab stops once the executor exits and records only `git diff --stat`, which leaves out new files.
- **Messages should reach agents mid-turn.** crew delivers mail "after its next tool call" rather than waiting for the agent to poll. collab only surfaces user and partner messages when an agent calls `wait_for_messages`, even though the prompt says "User messages come first."
- **The research's main risk is that agents agree too readily.** MAD and pal-mcp (`challenge`, blinded consensus) both add structural pressure against agreeing too quickly. collab asks for honest disagreement in the prompt, but the code doesn't enforce any of it.
- **Budgets could include cost.** AutoGen has composable `TokenUsageTermination` / `TimeoutTermination` / `MaxMessageTermination`. collab budgets only messages and minutes, and discards the token usage Codex reports.

## Projects

### SeemSeam/claude_codex_bridge (CCB): ★3.5k, updated 2026-09
- **What it is:** a TUI workspace that runs Claude, Codex, Gemini and other CLIs in visible tmux panes, with a message layer between them. Read: README only.
- **Overlap with collab:** cross-provider agent-to-agent messaging, and a human who can see everything and take over.
- **How it differs:** agents are interactive terminals, not headless. Routing is an explicit graph (`A -> B -> C`, `A,B -> C`), not a room. It has no findings, conclusions or executor.
- **Worth borrowing:**
  - A background daemon keeps project state alive when the UI closes (README "Why CCB?"). collab instead marks open runs `interrupted` on restart (`collab/__main__.py`).
  - A per-target FIFO queue, so "later replies cannot interrupt an earlier reply's processing turn" (README "Agent / agent queue mode").

### BeehiveInnovations/pal-mcp-server (formerly zen-mcp): ★11.8k, updated 2025-12
- **What it is:** an MCP server that gives Claude Code, Codex or Gemini CLI tools for consulting other models, including `consensus`, `challenge`, `codereview` and `clink` (launch another CLI as a subagent).
- **Overlap with collab:** multi-model review, driving `claude` / `codex` without a UI, and parsing `codex exec --json`.
- **How it differs:** one agent calls the others as tools, so it's hub-and-spoke rather than peer-to-peer. The calling agent combines the opinions itself.
- **Worth borrowing:**
  - `consensus` assigns stances (for/against/neutral) and supports a *blinded* first round (`docs/tools/consensus.md`, "How It Works" and "Watch In Action").
  - `challenge` wraps pushback in instructions against reflexive "You're absolutely right!" (`docs/tools/challenge.md`).
  - Its Codex parser keeps `turn.completed.usage` (`clink/parsers/codex.py`). collab's Codex adapter drops it and emits `cost_usd: None` (`collab/agents/codex.py:64`).
  - `CodexAgent._recover_from_error` still parses stdout when Codex exits non-zero (`clink/agents/codex.py`).

### MrLesk/agents-council: ★69, updated 2026-02
- **What it is:** an MCP "council" that already-running Claude, Codex or Gemini sessions join to trade feedback, plus a desktop "Council Hall" where humans can watch and post.
- **Overlap with collab:** the closest match. An MCP room, cursor-based polling (`get_current_session_data`), a human in the chat, read-only summoned agents (Read/Glob/Grep plus council tools), and `close_council` with a conclusion (README "MCP Tools", "Summon Claude").
- **How it differs:** it's built around *your existing sessions* joining. It has no findings or stances, no rule that both sides sign off, no executor and no keep-alive. A summoned Codex "returns a single response."
- **Worth borrowing:**
  - Joining a council from a session you already set up. For collab this would mean an "attach my current Claude session as a reviewer" mode.
  - Its roadmap item "Agents can summon user (Telegram/Slack)" is the same idea as remote approvals (see foreman).

### 0xmmo/crew: ★27, updated 2026-09
- **What it is:** hooks that inject what your other running Claude, Codex or OpenCode sessions are doing, plus `crew send` mail between them.
- **Overlap with collab:** agents messaging each other, and a human view of every session's status and transcript tail.
- **How it differs:** ambient coordination across unrelated sessions, not a structured task.
- **Worth borrowing:**
  - Delivery timing depends on the target's state. Busy targets get mail "after its next tool call"; a turn that's ending gets it "at turn end, and the agent acts on it before going idle" (README "Messaging between agents").
  - `--kickstart` turns a message into a directive.
  - `crew doctor` explains setup failures that look healthy from outside.

### aluarius/team-loop: ★0, updated 2026-05
- **What it is:** Claude Code slash commands for a 12-phase spec → plan → implement loop. Claude orchestrates and reviews; Codex audits and implements.
- **Overlap with collab:** a Claude and Codex pair, Codex with `read-only` or `workspace-write` sandboxes, and human gates.
- **How it differs:** Claude is explicitly the orchestrator, and the phases are fixed. Both conflict with collab's peer-to-peer, task-agnostic design.
- **Worth borrowing:**
  - Phase 11 "captures the full diff (including untracked files)."
  - Phase 12 is a review of the implementation with `finish / iterate / abort`.
  - Gate decisions are recorded in `state.json`.
  - Bootstrap branches off first (README "The 12-phase flow").

### smtg-ai/claude-squad: ★8.6k, updated 2026-08
- **What it is:** a TUI that runs many Claude, Codex, Aider or Gemini sessions in tmux.
- **Overlap with collab:** managing several coding-agent CLIs, and reviewing changes before applying them.
- **How it differs:** there's no communication between agents.
- **Worth borrowing:** "Each task gets its own isolated git workspace", i.e. worktrees, plus "Review changes before applying them" (README "Highlights"). That points to a safer executor.

### tuzlu07x/foreman: ★9, updated 2026-09
- **What it is:** a gateway that sits between agents and their tools. It filters every tool call by policy and risk, asks for human approval when needed, and logs everything.
- **Overlap with collab:** human approval while agents run, plus a live TUI dashboard and an inbox.
- **How it differs:** it's a security layer, not a way for agents to collaborate.
- **Worth borrowing:**
  - Approvals from your phone (Telegram, Slack or Discord buttons).
  - "Denied if nobody answers in time": a timeout on approvals (README "Quick start").

### Skytliang/Multi-Agents-Debate (MAD): ★613, updated 2025-12
- **What it is:** research code for the Multi-Agent Debate paper: an affirmative agent, a negative agent and a moderator.
- **Overlap with collab:** two agents disagreeing on purpose to avoid "degeneration of thoughts."
- **How it differs:** Q&A only. A moderator ends the debate each round, and a separate judge decides if rounds run out.
- **Worth borrowing:**
  - The negative side is told outright: "You disagree with my answer. Provide your answer and reasons" (`code/utils/config4all.json`, `negative_prompt`).
  - After `max_round`, a judge lists the candidate answers and then picks one (`interactive.py`, around L194–214).

### microsoft/autogen (AgentChat): ★61k, updated 2026-04
- **What it is:** a general multi-agent framework with round-robin and selector group chats.
- **Overlap with collab:** multi-agent conversations with end conditions.
- **How it differs:** an orchestrator picks who speaks, which collab deliberately avoids.
- **Worth borrowing:** end conditions you can combine: `MaxMessageTermination`, `TimeoutTermination`, `TokenUsageTermination`, `ExternalTermination`, `FunctionCallTermination`… (`python/packages/autogen-agentchat/src/autogen_agentchat/conditions/_terminations.py`).

## Improvement ideas for collab

Ranked by value vs effort.

1. **Notify agents of unread messages in every tool result.**
   - *Idea:* when an agent calls any room tool while it has unread user or partner messages, append a line to the result, e.g. `📨 2 unread messages (1 from user) — call wait_for_messages.` Rule 8 of the prompt ("User messages come first") then holds even mid-investigation.
   - *Source:* crew (delivery after the next tool call).
   - *Files:* `collab/room/tools.py` (`dispatch`), maybe `collab/room/room.py` (unread count per cursor).
   - *Effort:* S.
   - *Risks:* noise if repeated on every call. Only mention it once per new message.
   - Only room tools can carry it. Read or Grep results can't.

2. **Include untracked files in the executor summary.** This is a bug.
   - *Idea:* `_git_diff_stat` runs `git diff --stat` (`collab/runs/run.py:357`), which leaves out new files and staged changes. Add `git status --porcelain`, or diff against `HEAD` using intent-to-add. Save the full patch as `runs/<id>/executor.diff`.
   - *Source:* team-loop (Phase 11).
   - *Files:* `collab/runs/run.py`.
   - *Effort:* S.
   - *Risks:* none significant.

3. **Reviewers check the executor's work.**
   - *Idea:* after the executor finishes, give the diff to both reviewers, still in the room. They each post `verify_execution` (pass or fail, with findings). Failures loop back to the executor at most N times, and the user sees `finish / iterate`. Today the run completes as soon as the executor exits (`_finish_executor`).
   - *Source:* team-loop (Phase 12 and its iterate gate), claude-squad ("review changes before applying").
   - *Files:* `collab/runs/run.py`, `collab/room/room.py` and `tools.py` (new tool and checkpoint kind), `prompts/collaboration.md`, `web/src` (checkpoint UI).
   - *Effort:* M.
   - *Risks:* longer runs and more cost, which needs budget handling. It stays peer-to-peer, since the reviewers decide together.

4. **Enforce the blind first pass.**
   - *Idea:* until an agent has posted at least one finding (or called `done_first_pass`), `list_findings` hides the partner's findings. Today the prompt asks for this (rule 2), but `list_findings` returns the whole board (`collab/room/tools.py:98`).
   - *Source:* pal-mcp (blinded consensus), MAD (independent opening answers).
   - *Files:* `collab/room/room.py`, `collab/room/tools.py`, `prompts/collaboration.md`.
   - *Effort:* S.
   - *Risks:* chat messages can still leak findings, so this only closes the board. Split plans need per-slice handling.

5. **Budget cost as well as messages and time.**
   - *Idea:* add `max_cost_usd`. Claude already reports `total_cost_usd` per turn. Parse `turn.completed.usage` for Codex and record tokens even though there's no price. Feed this into the existing 80% / 100% wrap-up logic.
   - *Source:* AutoGen `TokenUsageTermination`, pal-mcp Codex parser.
   - *Files:* `collab/agents/codex.py`, `collab/config.py`, `collab/runs/run.py` (`_check_budget`), `web/src/components/StatusBar.tsx`.
   - *Effort:* S–M.
   - *Risks:* Codex tokens have no dollar value, so it would need a separate token budget.

6. **Push back when agreement comes too fast.**
   - *Idea:* if a reviewer agrees with most of the partner's findings within a short window and without citing evidence, the room posts a system nudge (MAD-style) asking it to argue the strongest case against at least one. Also consider a prompt rule: "an `agree` stance must add evidence of its own."
   - *Source:* MAD `negative_prompt`, pal-mcp `challenge`.
   - *Files:* `collab/room/room.py` (`respond`), `prompts/collaboration.md`.
   - *Effort:* S.
   - *Risks:* the thresholds are guesses. Getting them wrong makes agents argue for its own sake. Test it on the toy example first.

7. **Run the executor in a worktree or branch.**
   - *Idea:* the executor edits a `collab/<run-id>` worktree. The user merges from the dashboard, or with auto-apply it lands in `cwd`.
   - *Source:* claude-squad (isolated workspaces), team-loop (bootstrap branch).
   - *Files:* `collab/runs/run.py`, `collab/server.py`, `web/src`.
   - *Effort:* M.
   - *Risks:* fails for folders that aren't git repos (fall back to the current behavior). Uncommitted changes in `cwd` aren't in the worktree.

8. **Resume interrupted runs.**
   - *Idea:* rebuild the `Room` from `events.jsonl` and restart agents with `--resume <session>`. Session ids are already saved in `run.json`, so a restart doesn't have to end the run.
   - *Source:* CCB (background daemon keeps state).
   - *Files:* `collab/__main__.py`, `collab/runs/run.py`, `collab/room/room.py` (replay).
   - *Effort:* L.
   - *Risks:* the rebuilt state could differ from the original, and agents lose any tool calls that were in flight.

9. **Tiebreak contested findings with a judge.** ⚠️ This partly conflicts with "peer-to-peer, no orchestrator".
   - *Idea:* when the budget runs out with contested findings, an optional third session reads both sides and writes a recommendation for each finding into `conclusion.md`. It doesn't decide anything; the user still does.
   - *Source:* MAD judge.
   - *Files:* `collab/runs/run.py`, `prompts/`.
   - *Effort:* M.
   - *Risks:* adds a hierarchy, and weakens the "record it as unresolved" honesty. Keep it off by default, if built at all.

10. **Remote approvals and approval timeouts.**
    - *Idea:* send checkpoints to Slack or Telegram, with optional auto-reject after X minutes.
    - *Source:* foreman, agents-council roadmap.
    - *Files:* `collab/server.py`, `collab/runs/run.py`, config.
    - *Effort:* M.
    - *Risks:* credentials, and exposing more of the app to the network. Collab is localhost-only on purpose.

**Not recommended:** fixed phase pipelines (team-loop) and orchestrator-selected speakers (AutoGen `SelectorGroupChat`). Both contradict collab's core design. Attaching existing interactive sessions (agents-council) is interesting, but it's a different product shape (L).

## Searched but skipped

- `router-for-me/CLIProxyAPI`, `BenedictKing/ccx`: API proxies, not collaboration.
- `UditAkhourii/adhd`: a tree-of-thought skill for a single agent.
- `thunlp/ChatEval`: a multi-agent judge for comparing texts. Its idea (roles debating one-by-one) is already covered by MAD.
- `YerbaPage/SWE-Debate`: research code for locating faults with a code graph plus MCTS. Too tied to its pipeline to borrow from.
- `skyhi69/claudex`: README returns 404.
- `ytj0604/agent-bridge`, `modulastack/modula-relay`, `dhruvyad/openroom`: tiny relays (≤14★) that CCB and crew cover better.
- `camel-ai/camel`, `Pickle-Pixel/HydraMCP`, `magnus919/hermes-council`: general frameworks or model voting via APIs, not CLI agents. Not studied in depth.
- Agent-to-agent MCP demos (`yai333/Agent-to-Agent-MCP` and similar): tutorials.
