import { describe, expect, it } from "vitest";
import { contextLevel, fillPercent, meterClass, snoozeThreshold } from "@/domain/context";
import { estimateCost, fileReadingCost, teamCalls } from "@/domain/cost";
import type { AiMessage } from "@/domain/messages";
import { money } from "@/domain/format";
import { reduceRunEvent } from "@/domain/reduceRunEvent";
import { jobLabel, selectedModels } from "@/components/chat/CallUsageSection";
import { setupLabel, setupSentence } from "@/domain/describe";
import { DEMO_FILES } from "@/data/sample";
import { DEFAULT_SIMPLE, DEFAULT_TEAM } from "@/domain/defaults";
import { buildScript } from "@/services/runner/mockScript";

describe("money", () => {
  it("never rounds a real tiny price to $0.00", () => {
    expect(money(0)).toBe("$0");
    expect(money(0.25)).toBe("$0.25");
    expect(money(0.0034)).toBe("$0.0034");
    expect(money(0.00005)).toBe("$0.00005");
    expect(money(0.000001)).toBe("$0.00001");
  });
});

describe("context window (spec Part 2 §7)", () => {
  it("matches the spec example: 150,000 / (200,000 - 15%) = 88%", () => {
    expect(fillPercent(150_000, 200_000)).toBe(88);
  });
  it("acts at 70, 85 and 95 percent", () => {
    expect(contextLevel(69)).toBe("normal");
    expect(contextLevel(70)).toBe("notice");
    expect(contextLevel(85)).toBe("alarm");
    expect(contextLevel(95)).toBe("compact");
    expect(meterClass(96)).toBe("crit");
  });
  it("Later asks again at 90%, or at 95% when already past 90%", () => {
    expect(snoozeThreshold(86)).toBe(90);
    expect(snoozeThreshold(93)).toBe(95);
  });
});

describe("cost (spec Part 1 §7, Part 2 §4)", () => {
  it("counts team calls: 3 agents, together, 2 rounds = 7", () => {
    expect(teamCalls({ ...DEFAULT_TEAM, agents: 3, rounds: 2, style: "together" })).toBe(7);
    expect(teamCalls({ ...DEFAULT_TEAM, agents: 3, style: "independent" })).toBe(4);
  });
  it("prices the 200-page example at about $0.071 with Auto", () => {
    const report = DEMO_FILES.find((f) => f.id === "report")!;
    expect(fileReadingCost(report, "auto")).toBeCloseTo(0.071, 3);
    expect(fileReadingCost(report, "text")).toBe(0);
  });
  it("Simple costs one call; Thinker costs more than Simple", () => {
    const base = { simple: DEFAULT_SIMPLE, team: DEFAULT_TEAM, runIn: "auto" as const };
    expect(estimateCost({ ...base, mode: "simple" })).toBeLessThan(estimateCost({ ...base, mode: "thinker" }));
  });
});

describe("the user picks the mode: plain-word labels, no Auto", () => {
  it("the top-bar button says what will answer", () => {
    expect(setupLabel("simple", DEFAULT_SIMPLE, DEFAULT_TEAM, "auto")).toMatch(/^Model: /);
    expect(setupLabel("thinker", DEFAULT_SIMPLE, DEFAULT_TEAM, "auto")).toMatch(/^Team: /);
    expect(setupLabel("planner", DEFAULT_SIMPLE, DEFAULT_TEAM, "simple")).toMatch(/^Plan with /);
    for (const mode of ["simple", "thinker", "planner"] as const) {
      expect(setupLabel(mode, DEFAULT_SIMPLE, DEFAULT_TEAM, "auto")).not.toMatch(/auto/i);
      expect(setupSentence(mode, DEFAULT_SIMPLE, DEFAULT_TEAM, "simple")).not.toMatch(/Auto/);
    }
  });
  it("cost rows are named by the job and split into your models and helpers", () => {
    expect(jobLabel("router")).toBe("Safety check before answering");
    expect(jobLabel("answer")).toBe("Answer");
    expect(jobLabel("something:new")).toBe("something:new");
    const snapshot = { simple: { ...DEFAULT_SIMPLE, model: "deepseek/deepseek-chat" }, team: { ...DEFAULT_TEAM, source: "mixed" as const, mixed: ["a/one", "b/two"], composer: "c/three" }, runIn: "auto" as const };
    expect([...selectedModels({ kind: "simple", snapshot })]).toEqual(["deepseek/deepseek-chat"]);
    expect([...selectedModels({ kind: "thinker", snapshot })].sort()).toEqual(["a/one", "b/two", "c/three", "deepseek/deepseek-chat"]);
  });
});

const blank: AiMessage = {
  id: "a1", role: "ai", kind: "simple", prompt: "q", auto: false, status: "live", statusText: "", thinkingNotes: [],
  tool: null, text: "", citations: [], roundText: "", agents: [], plan: null, output: null, calls: 0, costUsd: 0, error: null, warning: null, thoughtSeconds: null,
  snapshot: { simple: DEFAULT_SIMPLE, team: DEFAULT_TEAM, runIn: "auto" },
};

describe("reduceRunEvent", () => {
  it("streams text deltas and finishes", () => {
    let m = reduceRunEvent(blank, { type: "text", delta: "Hello " });
    m = reduceRunEvent(m, { type: "text", delta: "world" });
    m = reduceRunEvent(m, { type: "done" });
    expect(m.text).toBe("Hello world");
    expect(m.status).toBe("done");
  });
  it("ignores late events after Stop", () => {
    const stopped = { ...blank, status: "stopped" as const };
    expect(reduceRunEvent(stopped, { type: "text", delta: "late" })).toBe(stopped);
  });
  it("Checker rejection replaces the draft instead of appending to it", () => {
    let m = reduceRunEvent(blank, { type: "text", delta: "bad draft" });
    m = reduceRunEvent(m, { type: "text", delta: "", replace: true });
    m = reduceRunEvent(m, { type: "text", delta: "good answer" });
    expect(m.text).toBe("good answer");
  });
  it("the mode, warnings and thinking time arrive as events", () => {
    let m = reduceRunEvent(blank, { type: "route", kind: "planner", reason: "x" });
    expect(m.kind).toBe("planner");
    m = reduceRunEvent(m, { type: "warning", message: "Stopped at the budget" });
    m = reduceRunEvent(m, { type: "warning", message: "Check failed" });
    expect(m.warning).toBe("Stopped at the budget Check failed");
    expect(reduceRunEvent(m, { type: "thinking", notes: ["a"], seconds: 7 }).thoughtSeconds).toBe(7);
  });
  it("a helper's question before a team run is marked, so it is not shown as the team's answer", () => {
    expect(blank.clarify).toBeUndefined();
    expect(reduceRunEvent(blank, { type: "clarify", question: "Which report?" }).clarify).toBe(true);
  });
  it("window and summarize events belong to the chat, not the answer", () => {
    expect(reduceRunEvent(blank, { type: "context", percent: 91 })).toBe(blank);
    expect(reduceRunEvent(blank, { type: "compact", step: 2, done: false })).toBe(blank);
    expect(reduceRunEvent(blank, { type: "note", text: "Older messages summarized" })).toBe(blank);
  });
  it("a plan waiting for approval sets status waiting (F10)", () => {
    const m = reduceRunEvent(blank, { type: "plan", phase: "Waiting for your approval", steps: [], awaitingApproval: true });
    expect(m.status).toBe("waiting");
  });
});

describe("mock script", () => {
  const req = (kind: "simple" | "thinker" | "planner") => ({
    id: "r", chatId: "c", mode: kind, kind, prompt: "q", files: [], simple: DEFAULT_SIMPLE, team: DEFAULT_TEAM, runIn: "auto" as const,
    budgetUsd: 1, estimateUsd: 0.1, contextPercent: 10,
  });
  it("every run ends with done", () => {
    for (const k of ["simple", "thinker", "planner"] as const) {
      const last = buildScript(req(k)).at(-1)!;
      expect("event" in last && last.event.type).toBe("done");
    }
  });
  it("Planner pauses for approval before running any step (F10)", () => {
    const script = buildScript(req("planner"));
    const pause = script.findIndex((i) => "pause" in i);
    const firstRun = script.findIndex((i) => "event" in i && i.event.type === "plan" && i.event.phase === "Running");
    expect(pause).toBeGreaterThan(-1);
    expect(pause).toBeLessThan(firstRun);
  });
});
