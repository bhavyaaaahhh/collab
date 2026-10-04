import { displayName, toneOf } from "../format";
import type { Finding, FindingStatus } from "../types";
import { Avatar, Markdown, Pill } from "./Primitives";

const ORDER: FindingStatus[] = ["contested", "open", "resolved", "agreed"];

export function FindingsBoard({ findings, reviewers }: {
  findings: { finding: Finding; status: FindingStatus }[]; reviewers: string[];
}) {
  if (!findings.length) {
    return (
      <div className="empty">
        <div className="empty-mark">✦</div>
        <p>No findings yet. Each agent posts its own before reading the other's.</p>
      </div>
    );
  }
  const counts = Object.fromEntries(ORDER.map((s) => [s, findings.filter((f) => f.status === s).length]));
  const sorted = [...findings].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));

  return (
    <div className="findings">
      <div className="findings-summary">
        {ORDER.filter((s) => counts[s]).map((s) => (
          <span key={s} className={`count s-${s}`}><b>{counts[s]}</b> {s}</span>
        ))}
      </div>
      <div className="finding-grid">
        {sorted.map(({ finding: f, status }) => (
          <article key={f.id} className={`finding s-${status}`}>
            <header>
              <Avatar name={f.author} tone={toneOf(f.author, reviewers)} size="sm" />
              <span className="finding-id">{f.id}</span>
              {f.revision > 0 && <span className="tag">revised</span>}
              <span className="spacer" />
              <Pill status={status} />
            </header>
            <h3>{f.issue}</h3>
            <div className="finding-change">
              <span className="label">Proposed change</span>
              <Markdown>{f.proposed_change}</Markdown>
            </div>
            <details className="finding-evidence">
              <summary>Evidence · cases {f.cases.join(", ")} · {f.confidence} confidence</summary>
              <Markdown>{f.evidence}</Markdown>
            </details>
            {f.stances.length > 0 && (
              <ul className="stances">
                {f.stances.map((s, i) => (
                  <li key={i}>
                    <Avatar name={s.by} tone={toneOf(s.by, reviewers)} size="sm" />
                    <div>
                      <span className={`stance st-${s.stance}`}>{displayName(s.by)} {s.stance === "partial" ? "partly agrees" : `${s.stance}s`}</span>
                      <p>{s.reasoning}</p>
                      {s.amended_change && <p className="amended">Suggests: {s.amended_change}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
