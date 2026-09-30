import { describe, expect, it } from "vitest";
import { agreedConclusion, conclusionStatus, executorOutcome, initialState, progress, reducer, reviewerMessageCount, reviewerNames, withRecord } from "./reducer";
import type { RunRecord, StoredEvent } from "./types";

const record = {
  id: "r", status: "running", created_at: 0, sessions: {}, task: "t", cwd: "/w", attachments: [],
  agents: ["claude", "codex"], executor: "claude", default_mode: "independent", auto_apply: false, budget: null,
} as RunRecord;

const finding = {
  id: "claude-1", author: "claude", cases: ["1"], issue: "i", evidence: "e", proposed_change: "c",
  confidence: "high" as const, stances: [], revision: 0,
};

function fold(events: StoredEvent[]) {
  return events.reduce(reducer, withRecord(initialState(), record));
}

describe("reducer", () => {
  it("builds chat, findings and activity from events", () => {
    const s = fold([
      { n: 1, at: 1, kind: "room", event: { type: "message", data: { seq: 1, sender: "claude", text: "hi", at: 1 } } },
      { n: 2, at: 2, kind: "agent", agent: "codex", event: { type: "tool_call", data: { id: "t", name: "Read", input: {} } } },
      { n: 3, at: 3, kind: "agent", agent: "codex", event: { type: "tool_result", data: { id: "t", summary: "ok", is_error: false } } },
      { n: 4, at: 4, kind: "room", event: { type: "finding", data: { finding, status: "contested" } } },
      { n: 5, at: 5, kind: "status", agent: "codex", status: "waiting" },
    ]);
    expect(s.messages).toHaveLength(1);
    expect(s.activity.codex[0]).toMatchObject({ type: "tool_call", name: "Read", result: "ok" });
    expect(s.findings["claude-1"].status).toBe("contested");
    expect(s.agentStatus.codex).toBe("waiting");
    expect(reviewerMessageCount(s)).toBe(1);
  });

  it("ignores replayed events", () => {
    const e: StoredEvent = { n: 1, at: 1, kind: "room", event: { type: "message", data: { seq: 1, sender: "user", text: "x", at: 1 } } };
    expect(fold([e, e]).messages).toHaveLength(1);
  });

  it("finds the conclusion both reviewers agreed to", () => {
    const c = { id: "conclusion-1", by: "claude", changes: ["a"], unresolved: [], rejected_by: [] };
    const s = fold([
      { n: 1, at: 1, kind: "room", event: { type: "conclusion", data: { ...c, agreed_by: ["claude"] } } },
    ]);
    expect(agreedConclusion(s)).toBeUndefined();
    const s2 = reducer(s, { n: 2, at: 2, kind: "room", event: { type: "conclusion", data: { ...c, agreed_by: ["claude", "codex"] } } });
    expect(agreedConclusion(s2)?.id).toBe("conclusion-1");
  });

  it("sums turn costs and names same-kind reviewers", () => {
    const s = fold([
      { n: 1, at: 1, kind: "agent", agent: "claude", event: { type: "turn_end", data: { cost_usd: 0.1 } } },
      { n: 2, at: 2, kind: "agent", agent: "claude", event: { type: "turn_end", data: { cost_usd: 0.2 } } },
    ]);
    expect(s.costUsd.claude).toBeCloseTo(0.3);
    expect(reviewerNames({ ...record, agents: ["codex", "codex"] })).toEqual(["codex-1", "codex-2"]);
  });
});

describe("progress", () => {
  it("moves through phases as the room fills up", () => {
    const msg = (n: number, sender: string, text: string): StoredEvent =>
      ({ n, at: n, kind: "room", event: { type: "message", data: { seq: n, sender, text, at: n } } });
    let s = fold([msg(1, "claude", "hi")]);
    expect(progress(s)).toEqual({ current: 0, complete: false });
    s = reducer(s, msg(2, "system", "Plan accepted."));
    expect(progress(s).current).toBe(1);
    s = reducer(s, { n: 3, at: 3, kind: "room", event: { type: "finding", data: {
      finding: { ...finding, stances: [{ by: "codex", stance: "agree", reasoning: "", amended_change: null, at: 3 }] },
      status: "agreed" } } });
    expect(progress(s).current).toBe(2);
    const c = { id: "conclusion-1", by: "claude", changes: ["a"], unresolved: [], agreed_by: ["claude", "codex"], rejected_by: [] };
    s = reducer(s, { n: 4, at: 4, kind: "room", event: { type: "conclusion", data: c } });
    expect(conclusionStatus(s, c)).toBe("agreed");
    s = reducer(s, { n: 5, at: 5, kind: "run", status: "completed" });
    expect(progress(s)).toEqual({ current: 3, complete: true });
    s = reducer(s, { n: 6, at: 6, kind: "status", agent: "executor", status: "done" });
    expect(progress(s)).toEqual({ current: 4, complete: true });
  });

  it("treats an executor that errored as failed, even if marked done", () => {
    const s = fold([
      { n: 1, at: 1, kind: "agent", agent: "executor", event: { type: "error", data: { message: "API Error: 400" } } },
      { n: 2, at: 2, kind: "status", agent: "executor", status: "done" },
    ]);
    expect(executorOutcome(s)).toBe("failed");
    expect(progress(s).complete).toBe(false);
  });

  it("marks rejected conclusions", () => {
    const c = { id: "conclusion-1", by: "claude", changes: [], unresolved: [], agreed_by: ["claude"], rejected_by: [{ by: "codex", reason: "x" }] };
    expect(conclusionStatus(fold([]), c)).toBe("rejected");
  });
});
