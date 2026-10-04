import { displayName, money, shortPath, taskTitle, toneOf } from "../format";
import { executorOutcome, PHASES, progress, reviewerMessageCount, reviewerNames, type RunViewState } from "../reducer";
import { AgentStatusDot, Avatar, Pill } from "./Primitives";

export function RunHeader({ state, live, onStop }: { state: RunViewState; live: boolean; onStop: () => void }) {
  const record = state.record!;
  const reviewers = reviewerNames(record);
  const agents = [...reviewers, ...(state.agentStatus.executor ? ["executor"] : [])];
  const cost = Object.values(state.costUsd).reduce((a, b) => a + b, 0);
  const max = record.budget?.max_messages ?? 0;
  const used = reviewerMessageCount(state);
  const { current, complete } = progress(state);
  const statusOf = (name: string) =>
    name === "executor" && executorOutcome(state) === "failed" ? "failed" : state.agentStatus[name];
  const title = taskTitle(record.task);
  const hasMore = record.task.trim() !== title;

  return (
    <header className="run-header">
      <div className="run-header-top">
        <a href="#/" className="back">← All runs</a>
        <div className="run-header-actions">
          {state.runStatus && <Pill status={state.runStatus} />}
          {live && <button className="ghost danger" onClick={onStop}>Stop run</button>}
        </div>
      </div>

      <h1 className="run-title">{title}</h1>
      <div className="run-sub">
        <span className="mono" title={record.cwd}>{shortPath(record.cwd)}</span>
        {hasMore && (
          <details className="full-task">
            <summary>Full task</summary>
            <p>{record.task}</p>
          </details>
        )}
      </div>

      <div className="run-meta">
        <div className="agents">
          {agents.map((name) => (
            <span key={name} className="agent-chip">
              <Avatar name={name} tone={toneOf(name, reviewers)} size="sm" />
              <span className="agent-name">{displayName(name)}</span>
              <AgentStatusDot status={statusOf(name)} />
              <span className="agent-state">{statusOf(name) ?? "starting"}</span>
            </span>
          ))}
        </div>
        <div className="numbers">
          {max > 0 && (
            <span className="budget" title="Messages the two agents sent, against the budget">
              <span className="budget-track"><span style={{ width: `${Math.min(100, (used / max) * 100)}%` }} /></span>
              {used} / {max} messages
            </span>
          )}
          {money(cost) && <span className="cost">{money(cost)}</span>}
        </div>
      </div>

      <ol className="stepper">
        {PHASES.map((phase, i) => {
          const state_ = i < current || (i === current && complete) ? "done" : i === current ? "current" : "todo";
          return (
            <li key={phase} className={`step ${state_} ${live ? "live" : ""}`}>
              <span className="step-mark">{state_ === "done" ? "✓" : i + 1}</span>
              <span className="step-label">{phase}</span>
            </li>
          );
        })}
      </ol>
    </header>
  );
}
