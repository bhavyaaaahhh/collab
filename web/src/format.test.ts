import { describe, expect, it } from "vitest";
import { duration, initials, shortPath, taskTitle, timeAgo, toneOf } from "./format";

describe("format", () => {
  it("assigns tones", () => {
    expect(toneOf("claude", ["claude", "codex"])).toBe("a");
    expect(toneOf("codex", ["claude", "codex"])).toBe("b");
    expect(toneOf("user", [])).toBe("you");
    expect(toneOf("executor", [])).toBe("exec");
  });
  it("formats names, titles and times", () => {
    expect(initials("claude-2")).toBe("C2");
    expect(taskTitle("  Fix evals\nmore detail")).toBe("Fix evals");
    expect(timeAgo(1000, 1000 + 125)).toBe("2m ago");
    expect(duration(754)).toBe("12m 34s");
    expect(shortPath("/a/b/c/toy")).toBe("…/c/toy");
  });
});
