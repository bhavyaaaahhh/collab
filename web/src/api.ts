import type { RunInput, RunListItem } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? res.statusText);
    throw new Error(detail);
  }
  return res.json();
}

const post = <T>(path: string, body: unknown = {}) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  listRuns: () => request<RunListItem[]>("/api/runs"),
  createRun: (input: RunInput) => post<{ id: string }>("/api/runs", input),
  sendMessage: (id: string, text: string) => post(`/api/runs/${id}/message`, { text }),
  resolveCheckpoint: (id: string, cid: string, decision: "approved" | "rejected", selected?: number[], note?: string) =>
    post(`/api/runs/${id}/checkpoints/${cid}`, { decision, selected, note: note || null }),
  stop: (id: string) => post(`/api/runs/${id}/stop`),
  streamUrl: (id: string) => `/api/runs/${id}/stream`,
};

export async function fetchArtifact(id: string, name: string): Promise<string | null> {
  const res = await fetch(`/api/runs/${id}/artifacts/${name}`);
  return res.ok ? res.text() : null;
}
