import type { Finding, FindingStatus } from "../types";

export function FindingsBoard({ findings }: { findings: { finding: Finding; status: FindingStatus }[] }) {
  if (!findings.length) return null;
  return (
    <section className="findings">
      <h3>Findings board</h3>
      <table>
        <thead>
          <tr><th>Id</th><th>Issue</th><th>Proposed change</th><th>Stances</th><th>Status</th></tr>
        </thead>
        <tbody>
          {findings.map(({ finding: f, status }) => (
            <tr key={f.id}>
              <td className="mono">{f.id}{f.revision > 0 && <span className="muted"> r{f.revision}</span>}</td>
              <td>
                {f.issue}
                <details><summary className="muted">evidence · cases {f.cases.join(", ")} · {f.confidence}</summary><p>{f.evidence}</p></details>
              </td>
              <td>{f.proposed_change}</td>
              <td>
                {f.stances.map((s, i) => (
                  <div key={i} className={`stance ${s.stance}`} title={s.reasoning}>
                    <b>{s.by}</b>: {s.stance} — {s.reasoning}
                    {s.amended_change && <div className="muted">amended: {s.amended_change}</div>}
                  </div>
                ))}
              </td>
              <td><span className={`badge ${status}`}>{status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
