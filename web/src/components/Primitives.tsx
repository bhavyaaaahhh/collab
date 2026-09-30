import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { initials, type Tone } from "../format";
import type { AgentStatus } from "../types";

export function Avatar({ name, tone, size = "md" }: { name: string; tone: Tone; size?: "sm" | "md" }) {
  return <span className={`avatar tone-${tone} ${size}`} aria-hidden>{initials(name)}</span>;
}

export function Markdown({ children, className = "" }: { children: string; className?: string }) {
  return (
    <div className={`md ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: (p) => <a {...p} target="_blank" rel="noreferrer" /> }}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = {
  running: "Running", waiting: "Needs you", completed: "Completed", stopped: "Stopped", failed: "Failed",
  interrupted: "Interrupted", agreed: "Agreed", resolved: "Resolved", contested: "Contested", open: "Open",
  rejected: "Rejected", pending: "Pending",
};

export function Pill({ status }: { status: string }) {
  return <span className={`pill s-${status}`}>{STATUS_LABEL[status] ?? status}</span>;
}

export function AgentStatusDot({ status }: { status?: AgentStatus }) {
  return <span className={`status-dot a-${status ?? "starting"}`} title={status ?? "starting"} />;
}
