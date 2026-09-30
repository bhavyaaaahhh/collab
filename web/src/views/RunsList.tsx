import { useEffect, useState } from "react";
import { api } from "../api";
import type { RunRecord } from "../types";

export function RunsList() {
  const [runs, setRuns] = useState<RunRecord[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listRuns().then(setRuns).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!runs) return <p className="muted">Loading…</p>;
  if (!runs.length) return <p className="muted pad">No runs yet. Start one with <a href="#/new">New run</a>.</p>;

  return (
    <table className="runs">
      <thead>
        <tr><th>Run</th><th>Task</th><th>Agents</th><th>Status</th></tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id} onClick={() => (window.location.hash = `#/run/${r.id}`)}>
            <td className="mono">{r.id}</td>
            <td className="task">{r.task}</td>
            <td>{r.agents.join(" + ")}</td>
            <td><span className={`badge ${r.status}`}>{r.status}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
