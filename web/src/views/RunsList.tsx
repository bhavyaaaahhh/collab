import { useEffect, useState } from "react";
import { api } from "../api";
import { Avatar, Pill } from "../components/Primitives";
import { duration, money, taskTitle, timeAgo } from "../format";
import type { RunListItem } from "../types";

function outcome(run: RunListItem): string {
  const s = run.summary;
  if (!s) return "";
  if (s.executor === "failed") return "Executor failed, not applied";
  if (s.executor === "done" && s.agreed_changes) return `${s.agreed_changes} change${s.agreed_changes === 1 ? "" : "s"} applied`;
  if (s.agreed_changes !== null) return `Agreed on ${s.agreed_changes} change${s.agreed_changes === 1 ? "" : "s"}`;
  if (run.status === "running") return "Collaborating…";
  if (run.status === "waiting") return "Waiting for your approval";
  return s.findings ? `${s.findings} findings, no agreement` : "No findings";
}

export function RunsList() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listRuns().then(setRuns).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Two agents, one conversation</p>
          <h1>Runs</h1>
        </div>
        <a href="#/new" className="button">Start a run</a>
      </div>

      {error && <p className="banner-error">{error}</p>}
      {!runs && !error && <div className="page-loading">Loading…</div>}
      {runs && !runs.length && (
        <div className="empty big">
          <div className="empty-mark">◌</div>
          <h2>No runs yet</h2>
          <p>Give two agents a task and watch them work it out together.</p>
          <a href="#/new" className="button">Start your first run</a>
        </div>
      )}

      <ul className="run-cards">
        {runs?.map((r, i) => (
          <li key={r.id} style={{ animationDelay: `${Math.min(i, 12) * 40}ms` }}>
            <a href={`#/run/${r.id}`} className={`run-card s-${r.status}`}>
              <div className="run-card-main">
                <h2>{taskTitle(r.task)}</h2>
                <div className="run-card-meta">
                  <span className="pair">
                    <Avatar name={r.agents[0]} tone="a" size="sm" />
                    <Avatar name={r.agents[1]} tone="b" size="sm" />
                    {r.agents[0] === r.agents[1] ? `2 × ${r.agents[0]}` : `${r.agents[0]} + ${r.agents[1]}`}
                  </span>
                  <span>{timeAgo(r.created_at)}</span>
                  {r.summary && (
                    <>
                      <span>{duration(r.summary.ended_at - r.created_at)}</span>
                      <span>{r.summary.messages} messages</span>
                      {money(r.summary.cost_usd) && <span>{money(r.summary.cost_usd)}</span>}
                    </>
                  )}
                </div>
              </div>
              <div className="run-card-side">
                <Pill status={r.status} />
                <span className="outcome">{outcome(r)}</span>
              </div>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
