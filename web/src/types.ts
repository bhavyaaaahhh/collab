// Mirrors collab/room/models.py, collab/runs/store.py and the events written by collab/runs/run.py.

export type AgentKind = "claude" | "codex";
export type RunStatus = "running" | "waiting" | "completed" | "stopped" | "failed" | "interrupted";
export type AgentStatus = "starting" | "working" | "waiting" | "stalled" | "done" | "failed";
export type FindingStatus = "open" | "agreed" | "contested" | "resolved";

export interface Budget { max_messages: number; max_minutes: number }

export interface RunInput {
  task: string;
  cwd: string;
  attachments: string[];
  agents: [AgentKind, AgentKind];
  executor: AgentKind;
  default_mode: "independent" | "split";
  auto_apply: boolean;
  budget: Budget | null;
}

export interface RunRecord extends RunInput {
  id: string;
  status: RunStatus;
  created_at: number;
  sessions: Record<string, string>;
}

export interface Message { seq: number; sender: string; text: string; at: number }
export interface Stance { by: string; stance: "agree" | "disagree" | "partial"; reasoning: string; amended_change: string | null; at: number }
export interface Finding {
  id: string; author: string; cases: string[]; issue: string; evidence: string;
  proposed_change: string; confidence: "high" | "medium" | "low"; stances: Stance[]; revision: number;
}
export interface Plan { id: string; by: string; mode: "independent" | "split"; slices: Record<string, string> | null; endorsed_by: string[] }
export interface Conclusion { id: string; by: string; changes: string[]; unresolved: string[]; agreed_by: string[]; rejected_by: { by: string; reason: string }[] }
export interface Checkpoint { id: string; kind: "plan" | "apply"; ref_id: string; status: "pending" | "approved" | "rejected"; selected: number[] | null; note: string | null }

export type RoomEvent =
  | { type: "message"; data: Message }
  | { type: "finding"; data: { finding: Finding; status: FindingStatus } }
  | { type: "plan"; data: Plan }
  | { type: "conclusion"; data: Conclusion }
  | { type: "checkpoint"; data: Checkpoint }
  | { type: "executor_requested"; data: { conclusion_id: string; by: string } };

export type AgentEvent =
  | { type: "session"; data: { session_id: string } }
  | { type: "text"; data: { text: string } }
  | { type: "tool_call"; data: { id: string; name: string; input: unknown } }
  | { type: "tool_result"; data: { id: string; summary: string; is_error: boolean } }
  | { type: "turn_end"; data: { cost_usd: number | null } }
  | { type: "error"; data: { message: string } };

export type StoredEvent = { n: number; at: number } & (
  | { kind: "room"; event: RoomEvent }
  | { kind: "agent"; agent: string; event: AgentEvent }
  | { kind: "status"; agent: string; status: AgentStatus }
  | { kind: "run"; status: RunStatus }
);
