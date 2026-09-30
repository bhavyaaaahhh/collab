import { useEffect, useRef } from "react";
import type { Activity } from "../reducer";
import type { AgentStatus } from "../types";

function shortName(name: string): string {
  return name.replace(/^mcp__room__/, "room.");
}

function preview(input: unknown): string {
  if (input === null || input === undefined) return "";
  const s = typeof input === "string" ? input : JSON.stringify(input);
  return s.length > 80 ? `${s.slice(0, 80)}…` : s;
}

export function ActivityPanel({ name, items, status }: { name: string; items: Activity[]; status?: AgentStatus }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [items.length]);

  return (
    <aside className="activity">
      <h3>{name} <span className={`dot ${status ?? "starting"}`} /> <span className="muted">{status ?? "starting"}</span></h3>
      <div className="items">
        {items.map((item, i) => {
          switch (item.type) {
            case "text":
              return <p key={i} className="thought">{item.text}</p>;
            case "tool_call":
              return (
                <details key={i} className={`tool ${item.isError ? "failed" : ""}`}>
                  <summary><span className="mono">{shortName(item.name)}</span> <span className="muted">{preview(item.input)}</span></summary>
                  <pre>{JSON.stringify(item.input, null, 2)}</pre>
                  {item.result !== undefined && <pre className="result">{item.result}</pre>}
                </details>
              );
            case "error":
              return <p key={i} className="error">{item.message}</p>;
            case "turn_end":
              return <hr key={i} title={item.costUsd ? `turn cost $${item.costUsd.toFixed(3)}` : "turn ended"} />;
          }
        })}
        <div ref={end} />
      </div>
    </aside>
  );
}
