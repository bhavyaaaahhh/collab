import { reviewerMessageCount, reviewerNames, type RunViewState } from "../reducer";

export function StatusBar({ state, live, onStop }: { state: RunViewState; live: boolean; onStop: () => void }) {
  const record = state.record!;
  const max = record.budget?.max_messages ?? 0;
  const used = reviewerMessageCount(state);
  const names = [...reviewerNames(record), ...(state.agentStatus.executor ? ["executor"] : [])];
  const cost = Object.values(state.costUsd).reduce((a, b) => a + b, 0);

  return (
    <div className="statusbar">
      <span className={`badge ${state.runStatus}`}>{state.runStatus}</span>
      <span className="mono muted">{record.id}</span>
      {names.map((n) => (
        <span key={n} className="chip">
          {n} <span className={`dot ${state.agentStatus[n] ?? "starting"}`} /> {state.agentStatus[n] ?? "starting"}
        </span>
      ))}
      {max > 0 && (
        <span className="budget" title={`${used} of ${max} messages`}>
          <span className="meter"><span style={{ width: `${Math.min(100, (used / max) * 100)}%` }} /></span>
          {used}/{max} msgs
        </span>
      )}
      {cost > 0 && <span className="muted">${cost.toFixed(2)}</span>}
      <span className="spacer" />
      {live && <button className="danger" onClick={onStop}>Stop</button>}
    </div>
  );
}
