import { useState } from "react";
import type { RunViewState } from "../reducer";
import type { Checkpoint } from "../types";

export function CheckpointPanel({ checkpoint, state, onResolve }: {
  checkpoint: Checkpoint;
  state: RunViewState;
  onResolve: (decision: "approved" | "rejected", selected?: number[], note?: string) => void;
}) {
  if (checkpoint.kind === "plan") {
    const plan = state.plans[checkpoint.ref_id];
    return (
      <div className="checkpoint">
        <h4>The agents want to split the work</h4>
        <ul>
          {Object.entries(plan?.slices ?? {}).map(([agent, slice]) => <li key={agent}><b>{agent}</b>: {slice}</li>)}
        </ul>
        <div className="actions">
          <button onClick={() => onResolve("approved")}>Approve split</button>
          <button className="secondary" onClick={() => onResolve("rejected")}>Reject — both review everything</button>
        </div>
      </div>
    );
  }
  return <ApplyGate changes={state.conclusions[checkpoint.ref_id]?.changes ?? []} onResolve={onResolve} />;
}

function ApplyGate({ changes, onResolve }: {
  changes: string[];
  onResolve: (decision: "approved" | "rejected", selected?: number[], note?: string) => void;
}) {
  const [selected, setSelected] = useState(() => changes.map(() => true));
  const [note, setNote] = useState("");
  const chosen = selected.flatMap((on, i) => (on ? [i] : []));

  return (
    <div className="checkpoint">
      <h4>Apply these changes?</h4>
      {changes.map((c, i) => (
        <label key={i} className="check">
          <input type="checkbox" checked={selected[i]}
            onChange={(e) => setSelected(selected.map((v, j) => (j === i ? e.target.checked : v)))} />
          {c}
        </label>
      ))}
      <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note for the executor" />
      <div className="actions">
        <button disabled={!chosen.length} onClick={() => onResolve("approved", chosen, note)}>
          Approve {chosen.length} change{chosen.length === 1 ? "" : "s"}
        </button>
        <button className="secondary" onClick={() => onResolve("rejected")}>Don't apply</button>
      </div>
    </div>
  );
}
