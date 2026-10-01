import { useEffect, useReducer, useState } from "react";
import { api } from "../api";
import { ActivityPanel } from "../components/ActivityPanel";
import { Chat } from "../components/Chat";
import { ConclusionView } from "../components/ConclusionView";
import { Dock } from "../components/Dock";
import { FindingsBoard } from "../components/FindingsBoard";
import { RunHeader } from "../components/RunHeader";
import { toneOf } from "../format";
import { agreedConclusion, initialState, reducer, reviewerNames, withRecord, type RunViewState } from "../reducer";
import type { RunRecord, StoredEvent } from "../types";

type Action = { record: RunRecord } | { event: StoredEvent };
type Tab = "conversation" | "findings" | "conclusion" | "activity";

function viewReducer(state: RunViewState, action: Action): RunViewState {
  return "record" in action ? withRecord(state, action.record) : reducer(state, action.event);
}

const TERMINAL = new Set(["completed", "stopped", "failed", "interrupted"]);

export function RunView({ id }: { id: string }) {
  const [state, dispatch] = useReducer(viewReducer, undefined, initialState);
  const [tab, setTab] = useState<Tab>("conversation");
  const [error, setError] = useState("");

  useEffect(() => {
    const source = new EventSource(api.streamUrl(id));
    source.addEventListener("record", (e) => dispatch({ record: JSON.parse((e as MessageEvent).data) }));
    source.onmessage = (e) => dispatch({ event: JSON.parse(e.data) });
    // A finished run's stream just ends; don't let EventSource reconnect and replay it forever.
    source.onerror = () => source.close();
    return () => source.close();
  }, [id]);

  if (!state.record) return <div className="page-loading">Loading run…</div>;

  const act = (p: Promise<unknown>) => p.then(() => setError("")).catch((e) => setError(e.message));
  const live = state.runStatus !== null && !TERMINAL.has(state.runStatus);
  const reviewers = reviewerNames(state.record);
  const findingCount = Object.keys(state.findings).length;
  const tabs: { key: Tab; label: string; badge?: number | string }[] = [
    { key: "conversation", label: "Conversation", badge: state.messages.filter((m) => m.sender !== "system").length || undefined },
    { key: "findings", label: "Findings", badge: findingCount || undefined },
    { key: "conclusion", label: "Conclusion", badge: agreedConclusion(state) ? "✓" : undefined },
    { key: "activity", label: "Behind the scenes" },
  ];
  const panels = [...reviewers, ...(state.activity.executor ? ["executor"] : [])];

  return (
    <div className="run">
      <RunHeader state={state} live={live} onStop={() => act(api.stop(id))} />

      <nav className="tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={`tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}>
            {t.label}{t.badge !== undefined && <span className="tab-badge">{t.badge}</span>}
          </button>
        ))}
      </nav>

      {error && <p className="banner-error">{error}</p>}

      <main key={tab} className={`run-body tab-${tab}`}>
        {tab === "conversation" && <Chat state={state} />}
        {tab === "findings" && <FindingsBoard findings={Object.values(state.findings)} reviewers={reviewers} />}
        {tab === "conclusion" && <ConclusionView id={id} state={state} />}
        {tab === "activity" && (
          <div className={`activity-grid cols-${panels.length}`}>
            {panels.map((name) => (
              <ActivityPanel key={name} name={name} tone={toneOf(name, reviewers)}
                items={state.activity[name] ?? []} status={state.agentStatus[name]} />
            ))}
          </div>
        )}
      </main>

      <Dock state={state} live={live} onSend={(text) => act(api.sendMessage(id, text))}
        onResolve={(cp, decision, selected, note) => act(api.resolveCheckpoint(id, cp.id, decision, selected, note))} />
    </div>
  );
}
