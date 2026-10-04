---
name: research-related-projects
description: Use when the user wants to find GitHub projects similar to collab (multi-agent collaboration, agent-to-agent chat over MCP, Claude/Codex pairing, debate/review loops) and turn them into concrete improvement ideas for this repo. Produces a dated report in docs/research/.
---

# Research related projects

Find open-source projects that overlap with collab, study how they solve the same problems, and write down what collab could borrow. The output is a report the user reviews — not code changes.

## Ground rules

- **Read-only on GitHub.** Use `gh search`, `gh repo view` and `gh api` GET calls only. Never star, fork, open issues/PRs or comment.
- **Search terms are public queries.** Don't put private paths, the user's email or unreleased details in them.
- **Evidence over vibes.** Every claim about another project cites a file, README section or URL. If you only read the README, say so.
- **Short updates.** Tell the user in one line what you're about to search before each phase; don't go quiet.

## 1. Re-read collab first

So comparisons are against the real design, not a memory of it. Skim:

- `README.md` and `prompts/collaboration.md` — the collaboration contract
- `collab/room/tools.py` and `collab/room/room.py` — room tools and rules (findings, stances, plans, conclusions, checkpoints)
- `collab/runs/run.py` — keep-alive/resume, budget, executor hand-off
- `collab/agents/` — how Claude and Codex CLIs are launched and parsed
- the latest file in `docs/research/`, if any — don't repeat old findings; note what changed

Write down collab's key traits to compare against: peer-to-peer (no orchestrator), headless CLI agents, MCP room bridge, structured findings board, human checkpoints, separate executor, replayable event log, live dashboard.

## 2. Search

Run several searches and merge the results. Starting points (adapt and add your own):

```bash
gh search repos "multi-agent collaboration claude codex" --sort stars --limit 20 --json fullName,description,stargazersCount,updatedAt,url
gh search repos "agent to agent mcp" --sort stars --limit 20 --json fullName,description,stargazersCount,updatedAt,url
gh search repos "llm debate agents" --sort stars --limit 20 --json fullName,description,stargazersCount,updatedAt,url
gh search repos "claude code codex together" --limit 20 --json fullName,description,stargazersCount,updatedAt,url
gh search repos topic:multi-agent-systems --sort stars --limit 20 --json fullName,description,stargazersCount,updatedAt,url
gh search code "wait_for_messages" --language python --limit 20 --json repository,path
gh search code "codex exec --json" --limit 20 --json repository,path
```

Code search is noisy (message queues, IoT SDKs); skim paths and keep only agent-related hits.

Angles worth covering:
- agents talking directly (shared chat room, message bus, A2A protocol)
- multi-agent frameworks with debate / critique / consensus (AutoGen, CAMEL, CrewAI, LangGraph, MetaGPT-style)
- tools that drive `claude` / `codex` / other coding-agent CLIs headlessly
- human-in-the-loop review dashboards for agent runs
- eval-triage / prompt-improvement loops (collab's first use case)

Use web search for well-known projects or papers that repo search misses.

Shortlist **6–10** repos. Prefer active (updated in the last year) and relevant over popular. Drop tutorials, empty repos and forks.

## 3. Study each shortlisted repo

For each, read the README and the 1–3 files that implement the part that overlaps with collab:

```bash
gh repo view OWNER/REPO
gh api repos/OWNER/REPO/contents/PATH --jq .content | base64 -d
gh api "repos/OWNER/REPO/git/trees/HEAD?recursive=1" --jq '.tree[].path' | head -200
```

Capture: what it does, how turn-taking/coordination works, how agents are launched, how disagreement and termination are handled, how humans intervene, persistence/replay, and anything collab lacks.

## 4. Write the report

Save to `docs/research/YYYY-MM-DD-related-projects.md` (today's date):

```markdown
# Related projects — YYYY-MM-DD

## Summary
3–5 bullets: the most useful takeaways.

## Projects
### owner/repo — ★N, updated YYYY-MM
- **What it is:** one line
- **Overlap with collab:** …
- **How it differs:** …
- **Worth borrowing:** … (cite file/section)

## Improvement ideas for collab
Ranked by value vs effort. For each: the idea, which project(s) it comes from, which collab files it would touch, rough effort (S/M/L), and risks. Flag any idea that conflicts with collab's core decisions (peer-to-peer, no orchestrator, task-agnostic, no per-task presets) instead of silently dropping it.

## Searched but skipped
Repos looked at and why they weren't relevant.
```

## 5. Report back

Give the user the summary and the top 3 ideas in chat, with the report path. Stop there — don't start implementing ideas until the user picks one.
