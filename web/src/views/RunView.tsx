import { useEffect, useReducer, useState } from "react";
import { api } from "../api";
import { ActivityPanel } from "../components/ActivityPanel";
import { Chat } from "../components/Chat";
import { CheckpointPanel } from "../components/CheckpointPanel";
import { FindingsBoard } from "../components/FindingsBoard";
import { StatusBar } from "../components/StatusBar";
import { agreedConclusion, initialState, reducer, reviewerNames, withRecord, type RunViewState } from "../reducer";
import type { RunRecord, StoredEvent } from "../types";

type Action = { record: RunRecord } | { event: StoredEvent };

function viewReducer(state: RunViewState, action: Action): RunViewState {
  return "record" in action ? withRecord(state, action.record) : reducer(state, action.event);
}

const TERMINAL = new Set(["completed", "stopped", "failed", "interrupted"]);

export function RunView({ id }: { id: string }) {
  const [state, dispatch] = useReducer(viewReducer, undefined, initialState);
  const [error, setError] = useState("");

  useEffect(() => {
    const source = new EventSource(api.streamUrl(id));
    source.addEventListener("record", (e) => dispatch({ record: JSON.parse((e as MessageEvent).data) }));
    source.onmessage = (e) => dispatch({ event: JSON.parse(e.data) });
    // A finished run's stream just ends; don't let EventSource reconnect and replay it forever.
    source.onerror = () => source.close();
    return () => source.close();
  }, [id]);

  const act = (p: Promise<unknown>) => p.then(() => setError("")).catch((e) => setError(e.message));
  const live = state.runStatus !== null && !TERMINAL.has(state.runStatus);
  const [a, b] = reviewerNames(state.record);
  const conclusion = agreedConclusion(state);
  const pending = Object.values(state.checkpoints).filter((c) => c.status === "pending");

  if (!state.record) return <p className="muted pad">Loading run…</p>;

  return (
    <div className="run">
      <StatusBar state={state} live={live} onStop={() => act(api.stop(id))} />
      <details className="task-box">
        <summary>Task</summary>
        <pre>{state.record.task}</pre>
        <p className="muted">in <span className="mono">{state.record.cwd}</span></p>
      </details>
      {error && <p className="error">{error}</p>}
      <div className="columns">
        <ActivityPanel name={a} items={state.activity[a] ?? []} status={state.agentStatus[a]} />
        <div className="center">
          <Chat messages={state.messages} reviewers={[a, b]} live={live} onSend={(text) => act(api.sendMessage(id, text))}>
            {pending.map((cp) => (
              <CheckpointPanel key={cp.id} checkpoint={cp} state={state}
                onResolve={(decision, selected, note) => act(api.resolveCheckpoint(id, cp.id, decision, selected, note))} />
            ))}
          </Chat>
          {conclusion && (
            <section className="conclusion">
              <h3>Conclusion <span className="muted">({conclusion.id}, agreed by {conclusion.agreed_by.join(" & ")})</span></h3>
              <ol>{conclusion.changes.map((c, i) => <li key={i}>{c}</li>)}</ol>
              {conclusion.unresolved.length > 0 && (
                <>
                  <h4>Unresolved</h4>
                  <ul>{conclusion.unresolved.map((c, i) => <li key={i}>{c}</li>)}</ul>
                </>
              )}
            </section>
          )}
          <FindingsBoard findings={Object.values(state.findings)} />
        </div>
        <ActivityPanel name={b} items={state.activity[b] ?? []} status={state.agentStatus[b]} />
      </div>
      {state.activity.executor && (
        <div className="executor">
          <ActivityPanel name="executor" items={state.activity.executor} status={state.agentStatus.executor} />
        </div>
      )}
    </div>
  );
}
