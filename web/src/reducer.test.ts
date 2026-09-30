import { describe, expect, it } from "vitest";
import { agreedConclusion, initialState, reducer, reviewerMessageCount, reviewerNames, withRecord } from "./reducer";
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
