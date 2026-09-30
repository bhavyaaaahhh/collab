from typing import Any, Literal

from pydantic import BaseModel

Mode = Literal["independent", "split"]
StanceKind = Literal["agree", "disagree", "partial"]
FindingStatus = Literal["open", "agreed", "contested", "resolved"]


class RoomError(Exception):
    """A rule violation the agent should read and recover from."""


class Message(BaseModel):
    seq: int
    sender: str  # agent name, "user" or "system"
    text: str
    at: float


class Stance(BaseModel):
    by: str
    stance: StanceKind
    reasoning: str
    amended_change: str | None = None
    at: float


class FindingIn(BaseModel):
    cases: list[str]
    issue: str
    evidence: str
    proposed_change: str
    confidence: Literal["high", "medium", "low"]


class Finding(FindingIn):
    id: str
    author: str
    stances: list[Stance] = []
    revision: int = 0


class Plan(BaseModel):
    id: str
    by: str
    mode: Mode
    slices: dict[str, str] | None = None
    endorsed_by: list[str]


class Rejection(BaseModel):
    by: str
    reason: str


class Conclusion(BaseModel):
    id: str
    by: str
    changes: list[str]
    unresolved: list[str]
    agreed_by: list[str]
    rejected_by: list[Rejection] = []


class Checkpoint(BaseModel):
    id: str
    kind: Literal["plan", "apply"]
    ref_id: str  # plan id or conclusion id
    status: Literal["pending", "approved", "rejected"] = "pending"
    selected: list[int] | None = None
    note: str | None = None


class RoomEvent(BaseModel):
    type: Literal["message", "finding", "plan", "conclusion", "checkpoint", "executor_requested"]
    data: dict[str, Any]
