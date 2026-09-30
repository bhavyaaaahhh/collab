from pathlib import Path

from collab.config import Budget
from collab.runs.prompt import agent_names, build_prompt


def fill(template, **kw):
    base = dict(me="claude", partner="codex", cwd="/w", attachments=["/r.json"], default_mode="independent",
                budget=Budget(), task="fix evals", role="reviewer")
    return build_prompt(template, **{**base, **kw})


def test_build_prompt():
    p = fill("I am {{me}}, partner {{partner}}, {{attachments}}, {{unknown}}")
    assert "I am claude, partner codex, \n- /r.json, {{unknown}}" in p
    assert p.endswith("## Task from the user\n\nfix evals")


def test_no_attachments():
    assert "files: none" in fill("files: {{attachments}}", attachments=[])


def test_real_template_has_no_leftover_vars():
    p = fill(Path("prompts/collaboration.md").read_text())
    assert "{{" not in p and "claude" in p and "80" in p


def test_agent_names():
    assert agent_names(("claude", "claude")) == ("claude-1", "claude-2")
    assert agent_names(("claude", "codex")) == ("claude", "codex")
