export type Tone = "a" | "b" | "you" | "exec" | "system";

export function toneOf(name: string, reviewers: string[]): Tone {
  if (name === "user") return "you";
  if (name === "system") return "system";
  if (name === "executor") return "exec";
  return reviewers.indexOf(name) === 1 ? "b" : "a";
}

export function displayName(name: string): string {
  return name === "user" ? "You" : name;
}

export function initials(name: string): string {
  if (name === "user") return "Y";
  const suffix = name.match(/-(\d+)$/)?.[1] ?? "";
  return name.charAt(0).toUpperCase() + suffix;
}

export function taskTitle(task: string): string {
  const line = task.trim().split("\n")[0] ?? "";
  return line.length > 140 ? `${line.slice(0, 137)}…` : line;
}

export function shortPath(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts.length > 2 ? `…/${parts.slice(-2).join("/")}` : path;
}

export function timeAgo(seconds: number, now = Date.now() / 1000): string {
  const d = Math.max(0, now - seconds);
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return new Date(seconds * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function clock(seconds: number): string {
  return new Date(seconds * 1000).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function money(usd: number): string {
  return usd >= 0.01 ? `$${usd.toFixed(2)}` : "";
}
