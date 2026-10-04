import { useState, type FormEvent } from "react";
import { api } from "../api";
import type { AgentKind, RunInput } from "../types";

const KINDS: AgentKind[] = ["claude", "codex"];

function Segmented<T extends string>({ value, options, onChange }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void;
}) {
  return (
    <div className="segmented" role="radiogroup">
      {options.map((o) => (
        <button type="button" key={o.value} role="radio" aria-checked={value === o.value}
          className={value === o.value ? "on" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

const kindOptions = KINDS.map((k) => ({ value: k, label: k }));

export function StartForm() {
  const [task, setTask] = useState("");
  const [cwd, setCwd] = useState("");
  const [attachments, setAttachments] = useState("");
  const [agentA, setAgentA] = useState<AgentKind>("claude");
  const [agentB, setAgentB] = useState<AgentKind>("codex");
  const [executor, setExecutor] = useState<AgentKind>("claude");
  const [mode, setMode] = useState<RunInput["default_mode"]>("independent");
  const [autoApply, setAutoApply] = useState(false);
  const [maxMessages, setMaxMessages] = useState(80);
  const [maxMinutes, setMaxMinutes] = useState(30);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { id } = await api.createRun({
        task, cwd: cwd.trim(),
        attachments: attachments.split("\n").map((a) => a.trim()).filter(Boolean),
        agents: [agentA, agentB], executor, default_mode: mode, auto_apply: autoApply,
        budget: { max_messages: maxMessages, max_minutes: maxMinutes },
      });
      window.location.hash = `#/run/${id}`;
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="page narrow">
      <div className="page-head">
        <div>
          <a href="#/" className="back">← All runs</a>
          <h1>New run</h1>
        </div>
      </div>

      <form className="form" onSubmit={submit}>
        <section className="form-card">
          <label className="field">
            <span className="field-label">Task</span>
            <textarea required rows={6} value={task} onChange={(e) => setTask(e.target.value)} autoFocus
              placeholder="e.g. Read the attached eval report and work out prompt changes that fix the failing cases." />
          </label>
          <label className="field">
            <span className="field-label">Working directory</span>
            <span className="field-hint">Both agents run here. The executor edits files here.</span>
            <input required className="mono" value={cwd} onChange={(e) => setCwd(e.target.value)} placeholder="/path/to/your/repo" />
          </label>
          <label className="field">
            <span className="field-label">Attached files <span className="optional">optional</span></span>
            <span className="field-hint">One path per line.</span>
            <textarea rows={2} className="mono" value={attachments} onChange={(e) => setAttachments(e.target.value)}
              placeholder="/path/to/eval-report.json" />
          </label>
        </section>

        <section className="form-card">
          <h2>Who works on it</h2>
          <div className="field-row">
            <div className="field"><span className="field-label">Agent A</span><Segmented value={agentA} options={kindOptions} onChange={setAgentA} /></div>
            <div className="field"><span className="field-label">Agent B</span><Segmented value={agentB} options={kindOptions} onChange={setAgentB} /></div>
            <div className="field"><span className="field-label">Executor</span><Segmented value={executor} options={kindOptions} onChange={setExecutor} /></div>
          </div>
          <div className="field">
            <span className="field-label">How they start</span>
            <Segmented value={mode} onChange={setMode} options={[
              { value: "independent", label: "Both review everything" },
              { value: "split", label: "Split the work" },
            ]} />
          </div>
        </section>

        <section className="form-card">
          <h2>Limits</h2>
          <div className="field-row">
            <label className="field"><span className="field-label">Max messages</span>
              <input type="number" min={2} value={maxMessages} onChange={(e) => setMaxMessages(+e.target.value)} /></label>
            <label className="field"><span className="field-label">Max minutes</span>
              <input type="number" min={1} value={maxMinutes} onChange={(e) => setMaxMinutes(+e.target.value)} /></label>
          </div>
          <label className="toggle">
            <input type="checkbox" checked={autoApply} onChange={(e) => setAutoApply(e.target.checked)} />
            <span className="toggle-track"><span /></span>
            <span>
              <b>Auto-apply</b>
              <span className="field-hint">Start the executor as soon as they agree, without asking me first.</span>
            </span>
          </label>
        </section>

        {error && <p className="banner-error">{error}</p>}
        <div className="form-actions">
          <a href="#/" className="button ghost">Cancel</a>
          <button type="submit" disabled={busy}>{busy ? "Starting…" : "Start run"}</button>
        </div>
      </form>
    </div>
  );
}
