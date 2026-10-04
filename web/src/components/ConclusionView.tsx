import { useEffect, useState } from "react";
import { fetchArtifact } from "../api";
import { agreedConclusion, executorOutcome, type RunViewState } from "../reducer";
import { Markdown } from "./Primitives";

export function ConclusionView({ id, state }: { id: string; state: RunViewState }) {
  const conclusion = agreedConclusion(state);
  const executorStatus = executorOutcome(state);
  const executorDone = executorStatus === "done" || executorStatus === "failed";
  const [executor, setExecutor] = useState<string | null>(null);

  useEffect(() => {
    if (executorDone) fetchArtifact(id, "executor.md").then(setExecutor);
  }, [id, executorDone]);

  if (!conclusion) {
    return (
      <div className="empty">
        <div className="empty-mark">◎</div>
        <p>No shared conclusion yet. It appears here once both agents sign the same proposal.</p>
      </div>
    );
  }

  return (
    <div className="conclusion">
      <section className="paper">
        <p className="eyebrow">Agreed by {conclusion.agreed_by.join(" & ")}</p>
        <h2>What they recommend</h2>
        <ol className="change-list big">
          {conclusion.changes.map((c, i) => <li key={i}><Markdown>{c}</Markdown></li>)}
        </ol>
        {conclusion.unresolved.length > 0 && (
          <div className="unresolved">
            <h4>Still unresolved</h4>
            <ul>{conclusion.unresolved.map((u, i) => <li key={i}><Markdown>{u}</Markdown></li>)}</ul>
          </div>
        )}
      </section>
      {executor && (
        <section className={`paper applied ${executorStatus === "failed" ? "failed" : ""}`}>
          <p className="eyebrow">{executorStatus === "failed" ? "The executor failed" : "Applied by the executor"}</p>
          <Markdown>{executor.replace(/^# Executor (summary|failed)\s*/, "")}</Markdown>
        </section>
      )}
    </div>
  );
}
