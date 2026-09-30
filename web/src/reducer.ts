import type {
  AgentStatus, Checkpoint, Conclusion, Finding, FindingStatus, Message, Plan, RunRecord, RunStatus, StoredEvent,
} from "./types";

export type Activity =
  | { type: "text"; at: number; text: string }
  | { type: "tool_call"; at: number; id: string; name: string; input: unknown; result?: string; isError?: boolean }
  | { type: "error"; at: number; message: string }
  | { type: "turn_end"; at: number; costUsd: number | null };

export interface RunViewState {
  lastN: number;
  record: RunRecord | null;
  runStatus: RunStatus | null;
  messages: Message[];
  findings: Record<string, { finding: Finding; status: FindingStatus }>;
  plans: Record<string, Plan>;
  conclusions: Record<string, Conclusion>;
  checkpoints: Record<string, Checkpoint>;
  activity: Record<string, Activity[]>;
  agentStatus: Record<string, AgentStatus>;
  costUsd: Record<string, number>;
}

export function initialState(): RunViewState {
  return {
    lastN: 0, record: null, runStatus: null, messages: [], findings: {}, plans: {}, conclusions: {},
    checkpoints: {}, activity: {}, agentStatus: {}, costUsd: {},
  };
}

export function reviewerNames(record: RunRecord | null): string[] {
  if (!record) return [];
  const [a, b] = record.agents;
  return a === b ? [`${a}-1`, `${b}-2`] : [a, b];
}

export function withRecord(state: RunViewState, record: RunRecord): RunViewState {
  return { ...state, record, runStatus: state.runStatus ?? record.status };
}

function pushActivity(state: RunViewState, agent: string, item: Activity): RunViewState {
  return { ...state, activity: { ...state.activity, [agent]: [...(state.activity[agent] ?? []), item] } };
}

/** Folds one stored event into view state. Used for both live SSE and replay; events at or below lastN are ignored. */
export function reducer(state: RunViewState, e: StoredEvent): RunViewState {
  if (e.n <= state.lastN) return state;
  const s = { ...state, lastN: e.n };
  switch (e.kind) {
    case "run":
      return { ...s, runStatus: e.status };
    case "status":
      return { ...s, agentStatus: { ...s.agentStatus, [e.agent]: e.status } };
    case "room": {
      const ev = e.event;
      switch (ev.type) {
        case "message":
          return { ...s, messages: [...s.messages, ev.data] };
        case "finding":
          return { ...s, findings: { ...s.findings, [ev.data.finding.id]: ev.data } };
        case "plan":
          return { ...s, plans: { ...s.plans, [ev.data.id]: ev.data } };
        case "conclusion":
          return { ...s, conclusions: { ...s.conclusions, [ev.data.id]: ev.data } };
        case "checkpoint":
          return { ...s, checkpoints: { ...s.checkpoints, [ev.data.id]: ev.data } };
        default:
          return s;
      }
    }
    case "agent": {
      const ev = e.event;
      switch (ev.type) {
        case "text":
          return pushActivity(s, e.agent, { type: "text", at: e.at, text: ev.data.text });
        case "tool_call":
          return pushActivity(s, e.agent, { type: "tool_call", at: e.at, id: ev.data.id, name: ev.data.name, input: ev.data.input });
        case "tool_result": {
          const items = s.activity[e.agent] ?? [];
          const i = items.findLastIndex((a) => a.type === "tool_call" && a.id === ev.data.id);
          if (i < 0) return s;
          const updated = [...items];
          updated[i] = { ...(items[i] as Extract<Activity, { type: "tool_call" }>), result: ev.data.summary, isError: ev.data.is_error };
          return { ...s, activity: { ...s.activity, [e.agent]: updated } };
        }
        case "error":
          return pushActivity(s, e.agent, { type: "error", at: e.at, message: ev.data.message });
        case "turn_end": {
          const next = pushActivity(s, e.agent, { type: "turn_end", at: e.at, costUsd: ev.data.cost_usd });
          const cost = ev.data.cost_usd ?? 0;
          return { ...next, costUsd: { ...next.costUsd, [e.agent]: (next.costUsd[e.agent] ?? 0) + cost } };
        }
        default:
          return s;
      }
    }
  }
}

export function agreedConclusion(state: RunViewState): Conclusion | undefined {
  const reviewers = reviewerNames(state.record);
  return Object.values(state.conclusions).find((c) => reviewers.every((r) => c.agreed_by.includes(r)));
}

export function reviewerMessageCount(state: RunViewState): number {
  const reviewers = reviewerNames(state.record);
  return state.messages.filter((m) => reviewers.includes(m.sender)).length;
}
