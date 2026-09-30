# collab

Two coding agents (Claude + Codex, Claude + Claude, or Codex + Codex) talk to each other **directly** to work through a task you give them. They agree on a plan, review independently, argue about disagreements with evidence, and sign off on a shared conclusion. Then a third session can apply the result. You watch everything live in a local dashboard and can join the conversation.

There is no orchestrator deciding who speaks. Each agent is a normal headless `claude` / `codex` session with a set of **room tools** (an MCP server): `send_message`, `wait_for_messages`, a shared findings board, plans and conclusions. How they collaborate is set by one prompt: [`prompts/collaboration.md`](prompts/collaboration.md).

## Setup

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+, and the `claude` and/or `codex` CLIs logged in.

```bash
uv sync
cd web && npm install && npm run build && cd ..
uv run python -m collab        # → http://127.0.0.1:4747
```

## Using it

1. **New run:** write the task, set the working directory both agents run in, and attach any files (for example an eval report). Pick the two agents and the executor.
2. **Watch:**
   - the room chat is in the middle
   - each agent's own reasoning and tool calls are on the sides
   - the findings board below shows every finding with both agents' stances
3. **Join in:** anything you type in the composer reaches both agents.
4. **Checkpoints:**
   - If the agents agree to *split* the work, you approve the split.
   - When they request the executor, you pick which agreed changes to apply and can add a note. With **auto-apply** on, this step is skipped.
5. **Result:**
   - The executor edits files in the working directory and never commits.
   - `runs/<id>/` holds `events.jsonl` (the full replayable history), `conclusion.md`, `executor.md` (summary + `git diff --stat`) and the exact prompts each agent got.

A run ends when both reviewers agree on a conclusion. It also ends when the budget runs out: at 80% the agents are told to wrap up, and at 100% any findings still contested are recorded as unresolved. Agents that end their turn early are resumed. An agent is marked stalled after 3 idle exits in a row, and failed after 2 crashes in a row.

## Example

[`examples/toy/`](examples/toy) holds a deliberately flawed helpdesk agent prompt and an eval report with 8 failing cases. Copy it somewhere, `git init` it, and start a run with that folder as the working directory, `eval-report.md` attached, and a task like *"Figure out prompt changes to system_prompt.md that would fix the failing evals."*

## Configuration

`collab.config.json`, optionally overridden by a gitignored `collab.config.local.json`:

| Key | Default | |
|---|---|---|
| `port` | `4747` | localhost only |
| `bin` | `{"claude": "claude", "codex": "codex"}` | CLI paths |
| `models` | `null` | model per agent kind (`null` = CLI default) |
| `budget` | `80` messages / `30` min | per-run default, overridable in the form |
| `wait_timeout_s` | `40` | how long `wait_for_messages` blocks (stays under the CLIs' 120s MCP timeout) |
| `claude_env` | `{}` | env vars for Claude agent sessions only |
| `claude_strict_mcp` | `true` | `false` = Claude agents also load your own MCP servers |
| `claude_extra_allowed_tools` | `[]` | extra tools Claude agents may call |

**Permissions:**
- Reviewers are read-only: Claude runs with `--permission-mode default` and only room + read tools allowed, and Codex runs with `-s read-only`.
- The executor can edit: Claude with `acceptEdits`, Codex with `-s workspace-write`.
- Codex's room server is set to `default_tools_approval_mode="approve"`. Without it, `codex exec` cancels every MCP call.
- Claude agents run with hooks and tool search turned off, so the room tools are loaded up front.

**If you route Claude through a context-compressing proxy** (`ANTHROPIC_BASE_URL` pointing at something like headroom), agents can fail with `API Error: 400 Tool reference '…' not found`. The proxy replaces content with references to a retrieval tool that agent sessions don't have. To send agent sessions straight to the API, add this to `collab.config.local.json`:

```json
{ "claude_env": { "ANTHROPIC_BASE_URL": "https://api.anthropic.com" } }
```

## Development

```bash
uv run pytest                 # backend
cd web && npx vitest run      # dashboard reducer
cd web && npm run dev         # dashboard with hot reload, proxies /api to :4747
```

Design and plan: [`docs/superpowers/`](docs/superpowers).
