import { displayName, money, type Tone } from "../format";
import type { Activity } from "../reducer";
import type { AgentStatus } from "../types";
import { AgentStatusDot, Avatar, Markdown } from "./Primitives";

// Room plumbing that only duplicates what the chat already shows.
const HIDDEN = new Set(["wait_for_messages", "list_findings", "read_room", "send_message"]);

type ToolCall = Extract<Activity, { type: "tool_call" }>;

function roomTool(name: string): string | null {
  const m = name.match(/^mcp__room__(.+)$/);
  return m ? m[1] : null;
}

function basename(path: unknown): string {
  return typeof path === "string" ? path.split("/").pop() ?? path : "";
}

/** One human sentence per tool call. */
function describe(call: ToolCall): { icon: string; text: string } {
  const input = (call.input ?? {}) as Record<string, unknown>;
  const room = roomTool(call.name);
  if (room) {
    switch (room) {
      case "post_finding": return { icon: "✦", text: `Posted a finding: ${String(input.issue ?? "")}` };
      case "respond_to_finding": return { icon: "↳", text: `${capitalize(String(input.stance ?? "responded"))} with ${input.id}` };
      case "update_finding": return { icon: "✎", text: `Revised ${input.id}` };
      case "propose_plan": return { icon: "◇", text: `Proposed a ${input.mode} plan` };
      case "endorse_plan": return { icon: "◆", text: `Endorsed ${input.plan_id}` };
      case "propose_conclusion": return { icon: "◎", text: "Proposed a conclusion" };
      case "agree_to_conclusion": return { icon: "✓", text: `Agreed to ${input.proposal_id}` };
      case "reject_conclusion": return { icon: "✕", text: `Rejected ${input.proposal_id}` };
      case "request_executor": return { icon: "▶", text: "Asked for the executor" };
      default: return { icon: "·", text: room.replace(/_/g, " ") };
    }
  }
  switch (call.name) {
    case "Read": return { icon: "▤", text: `Read ${basename(input.file_path)}` };
    case "Grep": return { icon: "⌕", text: `Searched for “${String(input.pattern ?? "")}”` };
    case "Glob": return { icon: "⌕", text: `Listed ${String(input.pattern ?? "files")}` };
    case "Edit": case "MultiEdit": return { icon: "✎", text: `Edited ${basename(input.file_path)}` };
    case "Write": return { icon: "✎", text: `Wrote ${basename(input.file_path)}` };
    case "shell": case "Bash": {
      const cmd = typeof call.input === "string" ? call.input : String(input.command ?? "");
      return { icon: "›", text: cmd.length > 70 ? `${cmd.slice(0, 70)}…` : cmd };
    }
    default: return { icon: "·", text: call.name };
  }
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function ActivityPanel({ name, tone, items, status }: {
  name: string; tone: Tone; items: Activity[]; status?: AgentStatus;
}) {
  const visible = items.filter((it) => it.type !== "tool_call" || !HIDDEN.has(roomTool(it.name) ?? ""));

  return (
    <section className={`activity tone-${tone}`}>
      <header className="activity-head">
        <Avatar name={name} tone={tone} />
        <div>
          <div className="activity-name">{displayName(name)}</div>
          <div className="activity-state"><AgentStatusDot status={status} /> {status ?? "starting"}</div>
        </div>
      </header>
      <div className="activity-body">
        {visible.length === 0 && <p className="muted small">Nothing yet.</p>}
        {visible.map((item, i) => {
          switch (item.type) {
            case "text":
              return <Markdown key={i} className="thought">{item.text}</Markdown>;
            case "tool_call": {
              const { icon, text } = describe(item);
              const room = roomTool(item.name) !== null;
              return (
                <details key={i} className={`action ${item.isError ? "failed" : ""} ${room ? "room" : ""}`}>
                  <summary><span className="action-icon">{icon}</span><span className="action-text">{text}</span></summary>
                  <pre>{typeof item.input === "string" ? item.input : JSON.stringify(item.input, null, 2)}</pre>
                  {item.result !== undefined && <pre className="action-result">{item.result}</pre>}
                </details>
              );
            }
            case "error":
              return <p key={i} className="activity-error">{item.message}</p>;
            case "turn_end":
              return <div key={i} className="turn-break"><span>turn ended{money(item.costUsd ?? 0) && ` · ${money(item.costUsd ?? 0)}`}</span></div>;
          }
        })}
      </div>
    </section>
  );
}
