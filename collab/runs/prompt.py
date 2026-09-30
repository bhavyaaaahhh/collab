import re
from typing import Literal

from collab.config import Budget


def agent_names(kinds: tuple[str, str]) -> tuple[str, str]:
    a, b = kinds
    return (f"{a}-1", f"{b}-2") if a == b else (a, b)


def build_prompt(
    template: str,
    *,
    me: str,
    partner: str,
    cwd: str,
    attachments: list[str],
    default_mode: str,
    budget: Budget,
    task: str,
    role: Literal["reviewer", "executor"],
) -> str:
    values = {
        "me": me,
        "partner": partner,
        "cwd": cwd,
        "attachments": "".join(f"\n- {a}" for a in attachments) if attachments else "none",
        "default_mode": default_mode,
        "max_messages": str(budget.max_messages),
        "max_minutes": str(budget.max_minutes),
        "role": role,
    }
    filled = re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), template)
    return f"{filled.rstrip()}\n\n## Task from the user\n\n{task}"
