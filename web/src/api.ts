import type { RunInput, RunRecord } from "./types";

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
  listRuns: () => request<RunRecord[]>("/api/runs"),
  createRun: (input: RunInput) => post<{ id: string }>("/api/runs", input),
  sendMessage: (id: string, text: string) => post(`/api/runs/${id}/message`, { text }),
  resolveCheckpoint: (id: string, cid: string, decision: "approved" | "rejected", selected?: number[], note?: string) =>
    post(`/api/runs/${id}/checkpoints/${cid}`, { decision, selected, note: note || null }),
  stop: (id: string) => post(`/api/runs/${id}/stop`),
  streamUrl: (id: string) => `/api/runs/${id}/stream`,
};
