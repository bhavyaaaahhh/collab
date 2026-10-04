import { useState, type FormEvent } from "react";
import type { RunViewState } from "../reducer";
import type { Checkpoint } from "../types";
import { Markdown } from "./Primitives";

type Resolve = (cp: Checkpoint, decision: "approved" | "rejected", selected?: number[], note?: string) => void;

/** Bottom of the run page: anything waiting on the user, then the message composer. */
export function Dock({ state, live, onSend, onResolve }: {
  state: RunViewState; live: boolean; onSend: (text: string) => void; onResolve: Resolve;
}) {
  const pending = Object.values(state.checkpoints).filter((c) => c.status === "pending");
  if (!live && !pending.length) return null;
  return (
    <div className="dock">
      <div className="dock-inner">
        {pending.map((cp) =>
          cp.kind === "plan"
            ? <PlanGate key={cp.id} cp={cp} state={state} onResolve={onResolve} />
            : <ApplyGate key={cp.id} cp={cp} state={state} onResolve={onResolve} />,
        )}
        {live && <Composer onSend={onSend} />}
      </div>
    </div>
  );
}

function Composer({ onSend }: { onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    onSend(text);
    setText("");
  }
  return (
    <form className="composer" onSubmit={submit}>
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Say something to both agents…" />
      <button type="submit" disabled={!text.trim()}>Send</button>
    </form>
  );
}

function PlanGate({ cp, state, onResolve }: { cp: Checkpoint; state: RunViewState; onResolve: Resolve }) {
  const plan = state.plans[cp.ref_id];
  return (
    <div className="gate">
      <div className="gate-head">
        <span className="gate-dot" />
        <h3>The agents want to split the work</h3>
      </div>
      <ul className="slices">
        {Object.entries(plan?.slices ?? {}).map(([agent, slice]) => <li key={agent}><b>{agent}</b> {slice}</li>)}
      </ul>
      <div className="gate-actions">
        <button onClick={() => onResolve(cp, "approved")}>Approve split</button>
        <button className="ghost" onClick={() => onResolve(cp, "rejected")}>Both review everything</button>
      </div>
    </div>
  );
}

function ApplyGate({ cp, state, onResolve }: { cp: Checkpoint; state: RunViewState; onResolve: Resolve }) {
  const changes = state.conclusions[cp.ref_id]?.changes ?? [];
  const [selected, setSelected] = useState(() => changes.map(() => true));
  const [note, setNote] = useState("");
  const chosen = selected.flatMap((on, i) => (on ? [i] : []));

  return (
    <div className="gate">
      <div className="gate-head">
        <span className="gate-dot" />
        <h3>Apply the agreed changes?</h3>
        <span className="muted small">Untick anything you don't want. Nothing is committed.</span>
      </div>
      <div className="gate-changes">
        {changes.map((c, i) => (
          <label key={i} className={`gate-change ${selected[i] ? "on" : ""}`}>
            <input type="checkbox" checked={selected[i]}
              onChange={(e) => setSelected(selected.map((v, j) => (j === i ? e.target.checked : v)))} />
            <Markdown>{c}</Markdown>
          </label>
        ))}
      </div>
      <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note for the executor (optional)" />
      <div className="gate-actions">
        <button disabled={!chosen.length} onClick={() => onResolve(cp, "approved", chosen, note)}>
          Apply {chosen.length} change{chosen.length === 1 ? "" : "s"}
        </button>
        <button className="ghost" onClick={() => onResolve(cp, "rejected")}>Don't apply</button>
      </div>
    </div>
  );
}
