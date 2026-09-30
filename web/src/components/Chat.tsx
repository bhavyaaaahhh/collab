import { useEffect, useRef } from "react";
import { clock, displayName, toneOf } from "../format";
import { conclusionStatus, reviewerNames, type RunViewState } from "../reducer";
import type { Message } from "../types";
import { Avatar, Markdown, Pill } from "./Primitives";

const PROPOSAL = /^(\S+) proposed (conclusion-\d+)\./;
const REJECTION = /^Rejected (conclusion-\d+): ([\s\S]*)$/;

export function Chat({ state }: { state: RunViewState }) {
  const end = useRef<HTMLDivElement>(null);
  const reviewers = reviewerNames(state.record);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [state.messages.length]);

  if (!state.messages.length) {
    return (
      <div className="empty">
        <div className="empty-mark">⋯</div>
        <p>The agents are reading the task. Their conversation will appear here.</p>
      </div>
    );
  }

  return (
    <div className="chat">
      {state.messages.map((m, i) => {
        const prev = state.messages[i - 1];
        const grouped = prev && prev.sender === m.sender && m.sender !== "system" && m.at - prev.at < 300;
        return <Entry key={m.seq} message={m} grouped={!!grouped} state={state} reviewers={reviewers} />;
      })}
      <div ref={end} />
    </div>
  );
}

function Entry({ message: m, grouped, state, reviewers }: {
  message: Message; grouped: boolean; state: RunViewState; reviewers: string[];
}) {
  if (m.sender === "system") {
    const proposal = m.text.match(PROPOSAL);
    const conclusion = proposal && state.conclusions[proposal[2]];
    if (proposal && conclusion) {
      const tone = toneOf(proposal[1], reviewers);
      return (
        <details className="proposal">
          <summary>
            <Avatar name={proposal[1]} tone={tone} size="sm" />
            <span><b>{proposal[1]}</b> proposed a conclusion</span>
            <span className="muted">{conclusion.changes.length} change{conclusion.changes.length === 1 ? "" : "s"}</span>
            <span className="spacer" />
            <Pill status={conclusionStatus(state, conclusion)} />
          </summary>
          <ol className="change-list">
            {conclusion.changes.map((c, i) => <li key={i}><Markdown>{c}</Markdown></li>)}
          </ol>
          {conclusion.unresolved.length > 0 && (
            <div className="unresolved">
              <h4>Unresolved</h4>
              <ul>{conclusion.unresolved.map((u, i) => <li key={i}><Markdown>{u}</Markdown></li>)}</ul>
            </div>
          )}
        </details>
      );
    }
    return <div className="system-line"><span>{m.text}</span></div>;
  }

  const tone = toneOf(m.sender, reviewers);
  const rejection = m.text.match(REJECTION);
  return (
    <article className={`message tone-${tone} ${grouped ? "grouped" : ""}`}>
      <div className="message-gutter">{!grouped && <Avatar name={m.sender} tone={tone} />}</div>
      <div className="message-main">
        {!grouped && (
          <div className="message-head">
            <span className="message-author">{displayName(m.sender)}</span>
            <time>{clock(m.at)}</time>
          </div>
        )}
        {rejection ? (
          <>
            <span className="tag tag-bad">Rejected {rejection[1]}</span>
            <Markdown>{rejection[2]}</Markdown>
          </>
        ) : (
          <Markdown>{m.text}</Markdown>
        )}
      </div>
    </article>
  );
}
