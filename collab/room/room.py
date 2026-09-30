import asyncio
import time
from collections.abc import Callable

from collab.room.models import (
    Checkpoint,
    Conclusion,
    Finding,
    FindingIn,
    FindingStatus,
    Message,
    Mode,
    Plan,
    Rejection,
    RoomError,
    RoomEvent,
    Stance,
    StanceKind,
)

CHECKPOINT_MESSAGES = {
    ("plan", "approved"): "User approved the split plan.",
    ("plan", "rejected"): "User rejected the split plan; do a full independent review.",
    ("apply", "approved"): "User approved the changes; executor starting.",
    ("apply", "rejected"): "User stopped before applying changes.",
}


class Room:
    """Shared state for one run. All rules live here; tools and the run only call these methods."""

    def __init__(self, participants: list[str], default_mode: Mode):
        self.reviewers = list(participants)
        self.participants = list(participants)
        self.default_mode = default_mode
        self.messages: list[Message] = []
        self.findings: dict[str, Finding] = {}
        self.plans: dict[str, Plan] = {}
        self.conclusions: dict[str, Conclusion] = {}
        self.checkpoints: dict[str, Checkpoint] = {}
        self._subscribers: list[Callable[[RoomEvent], None]] = []
        self._changed = asyncio.Event()
        self._counters: dict[str, int] = {}

    # --- plumbing ---

    def subscribe(self, fn: Callable[[RoomEvent], None]) -> None:
        self._subscribers.append(fn)

    def add_participant(self, name: str) -> None:
        if name not in self.participants:
            self.participants.append(name)

    def _emit(self, type_: str, data: dict) -> None:
        event = RoomEvent(type=type_, data=data)
        for fn in self._subscribers:
            fn(event)

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}-{self._counters[prefix]}"

    # --- messages ---

    def post(self, sender: str, text: str) -> Message:
        msg = Message(seq=len(self.messages) + 1, sender=sender, text=text, at=time.time())
        self.messages.append(msg)
        self._emit("message", msg.model_dump())
        # Wake every waiter, then arm a fresh event for the next message.
        self._changed.set()
        self._changed = asyncio.Event()
        return msg

    def messages_for(self, agent: str, after_seq: int) -> list[Message]:
        return [m for m in self.messages[after_seq:] if m.sender != agent]

    async def wait_for(self, agent: str, after_seq: int, timeout_s: float) -> list[Message]:
        deadline = asyncio.get_running_loop().time() + timeout_s
        while not (fresh := self.messages_for(agent, after_seq)):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return []
            try:
                await asyncio.wait_for(self._changed.wait(), remaining)
            except TimeoutError:
                return []
        return fresh

    # --- findings ---

    def _finding(self, finding_id: str) -> Finding:
        if finding_id not in self.findings:
            raise RoomError(f"No finding with id {finding_id}.")
        return self.findings[finding_id]

    def _emit_finding(self, f: Finding) -> None:
        self._emit("finding", {"finding": f.model_dump(), "status": self.finding_status(f)})

    def post_finding(self, author: str, f: FindingIn) -> Finding:
        finding = Finding(**f.model_dump(), id=self._next_id(author), author=author)
        self.findings[finding.id] = finding
        self._emit_finding(finding)
        return finding

    def respond(
        self, by: str, finding_id: str, stance: StanceKind, reasoning: str, amended_change: str | None = None
    ) -> Finding:
        f = self._finding(finding_id)
        if f.author == by:
            raise RoomError("You can't take a stance on your own finding; use update_finding to revise it.")
        f.stances.append(Stance(by=by, stance=stance, reasoning=reasoning, amended_change=amended_change, at=time.time()))
        self._emit_finding(f)
        return f

    def update_finding(self, by: str, finding_id: str, patch: dict) -> Finding:
        f = self._finding(finding_id)
        if f.author != by:
            raise RoomError(f"Only {f.author} can update {finding_id}; respond_to_finding instead.")
        unknown = set(patch) - set(FindingIn.model_fields)
        if unknown:
            raise RoomError(f"Can't update fields: {', '.join(sorted(unknown))}.")
        updated = FindingIn.model_validate({**f.model_dump(include=set(FindingIn.model_fields)), **patch})
        for key, value in updated.model_dump().items():
            setattr(f, key, value)
        f.revision += 1
        self._emit_finding(f)
        return f

    def finding_status(self, f: Finding) -> FindingStatus:
        others = [s for s in f.stances if s.by != f.author]
        if not others:
            return "open"
        if others[-1].stance == "agree":
            return "resolved" if f.revision > 0 else "agreed"
        return "contested"

    # --- plans ---

    def propose_plan(self, by: str, mode: Mode, slices: dict[str, str] | None = None) -> Plan:
        plan = Plan(id=self._next_id("plan"), by=by, mode=mode, slices=slices, endorsed_by=[by])
        self.plans[plan.id] = plan
        self._emit("plan", plan.model_dump())
        return plan

    def endorse_plan(self, by: str, plan_id: str) -> Plan:
        if plan_id not in self.plans:
            raise RoomError(f"No plan with id {plan_id}.")
        plan = self.plans[plan_id]
        if by not in plan.endorsed_by:
            plan.endorsed_by.append(by)
        self._emit("plan", plan.model_dump())
        if all(r in plan.endorsed_by for r in self.reviewers):
            if plan.mode == "independent" and self.default_mode == "independent":
                self.post("system", "Plan accepted.")
            else:
                self._open_checkpoint("plan", plan.id)
        return plan

    # --- conclusions ---

    def _conclusion(self, conclusion_id: str) -> Conclusion:
        if conclusion_id not in self.conclusions:
            raise RoomError(f"No conclusion proposal with id {conclusion_id}.")
        return self.conclusions[conclusion_id]

    def propose_conclusion(self, by: str, changes: list[str], unresolved: list[str]) -> Conclusion:
        c = Conclusion(id=self._next_id("conclusion"), by=by, changes=changes, unresolved=unresolved, agreed_by=[by])
        self.conclusions[c.id] = c
        self._emit("conclusion", c.model_dump())
        return c

    def agree_conclusion(self, by: str, conclusion_id: str) -> Conclusion:
        c = self._conclusion(conclusion_id)
        if by not in c.agreed_by:
            c.agreed_by.append(by)
        self._emit("conclusion", c.model_dump())
        return c

    def reject_conclusion(self, by: str, conclusion_id: str, reason: str) -> Conclusion:
        c = self._conclusion(conclusion_id)
        c.rejected_by.append(Rejection(by=by, reason=reason))
        self._emit("conclusion", c.model_dump())
        self.post(by, f"Rejected {conclusion_id}: {reason}")
        return c

    def concluded(self) -> Conclusion | None:
        for c in self.conclusions.values():
            if all(r in c.agreed_by for r in self.reviewers):
                return c
        return None

    def request_executor(self, by: str, conclusion_id: str) -> Conclusion:
        c = self._conclusion(conclusion_id)
        if not all(r in c.agreed_by for r in self.reviewers):
            raise RoomError("Both participants must agree_to_conclusion on this proposal first.")
        self._emit("executor_requested", {"conclusion_id": c.id, "by": by})
        return c

    # --- checkpoints ---

    def _open_checkpoint(self, kind: str, ref_id: str) -> Checkpoint:
        cp = Checkpoint(id=self._next_id("checkpoint"), kind=kind, ref_id=ref_id)
        self.checkpoints[cp.id] = cp
        self._emit("checkpoint", cp.model_dump())
        return cp

    def open_apply_checkpoint(self, conclusion_id: str) -> Checkpoint:
        return self._open_checkpoint("apply", conclusion_id)

    def resolve_checkpoint(
        self, checkpoint_id: str, status: str, selected: list[int] | None = None, note: str | None = None
    ) -> Checkpoint:
        if checkpoint_id not in self.checkpoints:
            raise RoomError(f"No checkpoint with id {checkpoint_id}.")
        cp = self.checkpoints[checkpoint_id]
        if cp.status != "pending":
            raise RoomError(f"Checkpoint {checkpoint_id} was already {cp.status}.")
        cp.status, cp.selected, cp.note = status, selected, note
        self._emit("checkpoint", cp.model_dump())
        self.post("system", CHECKPOINT_MESSAGES[(cp.kind, status)])
        return cp

    def snapshot(self) -> dict:
        return {
            "participants": self.participants,
            "messages": [m.model_dump() for m in self.messages],
            "findings": [{"finding": f.model_dump(), "status": self.finding_status(f)} for f in self.findings.values()],
            "plans": [p.model_dump() for p in self.plans.values()],
            "conclusions": [c.model_dump() for c in self.conclusions.values()],
            "checkpoints": [c.model_dump() for c in self.checkpoints.values()],
        }
