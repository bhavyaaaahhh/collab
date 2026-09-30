import { useEffect, useState } from "react";
import { RunView } from "./views/RunView";
import { RunsList } from "./views/RunsList";
import { StartForm } from "./views/StartForm";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export function App() {
  const hash = useHash();
  const runId = hash.match(/^#\/run\/(.+)$/)?.[1];
  return (
    <div className="app">
      <header className="topbar">
        <a href="#/" className="brand">collab</a>
        <a href="#/new" className="button">New run</a>
      </header>
      {runId ? <RunView key={runId} id={runId} /> : hash === "#/new" ? <StartForm /> : <RunsList />}
    </div>
  );
}
