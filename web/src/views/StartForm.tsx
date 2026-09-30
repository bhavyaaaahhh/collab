import { useState, type FormEvent } from "react";
import { api } from "../api";
import type { AgentKind, RunInput } from "../types";

const KINDS: AgentKind[] = ["claude", "codex"];

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

  const kindSelect = (value: AgentKind, set: (k: AgentKind) => void) => (
    <select value={value} onChange={(e) => set(e.target.value as AgentKind)}>
      {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
    </select>
  );

  return (
    <form className="start" onSubmit={submit}>
      <h2>New run</h2>
      <label>Task
        <textarea required rows={6} value={task} onChange={(e) => setTask(e.target.value)}
          placeholder="What should the two agents work out together?" />
      </label>
      <label>Working directory (both agents run here)
        <input required value={cwd} onChange={(e) => setCwd(e.target.value)} placeholder="/path/to/repo" />
      </label>
      <label>Attached files (one path per line, optional)
        <textarea rows={2} value={attachments} onChange={(e) => setAttachments(e.target.value)} placeholder="/path/to/eval-report.json" />
      </label>
      <div className="row">
        <label>Agent A {kindSelect(agentA, setAgentA)}</label>
        <label>Agent B {kindSelect(agentB, setAgentB)}</label>
        <label>Executor {kindSelect(executor, setExecutor)}</label>
      </div>
      <div className="row">
        <label>Default mode
          <select value={mode} onChange={(e) => setMode(e.target.value as RunInput["default_mode"])}>
            <option value="independent">independent (both review everything)</option>
            <option value="split">split (divide the work)</option>
          </select>
        </label>
        <label>Max messages <input type="number" min={2} value={maxMessages} onChange={(e) => setMaxMessages(+e.target.value)} /></label>
        <label>Max minutes <input type="number" min={1} value={maxMinutes} onChange={(e) => setMaxMinutes(+e.target.value)} /></label>
      </div>
      <label className="check">
        <input type="checkbox" checked={autoApply} onChange={(e) => setAutoApply(e.target.checked)} />
        Auto-apply: start the executor without asking me first
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? "Starting…" : "Start"}</button>
    </form>
  );
}
