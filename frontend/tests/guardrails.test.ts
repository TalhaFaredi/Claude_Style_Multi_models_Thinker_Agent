import { describe, expect, it } from "vitest";
import { getModel } from "@/data/sample";
import {
  checkCanSend, isOverBudget, mixedStrengthWarning, modelDisabledReason, normalizeThinking,
  stepAgents, stepRounds, toggleMixedModel,
} from "@/domain/guardrails";
import { DEFAULT_TEAM } from "@/domain/defaults";

describe("guardrails (spec Part 3 §9)", () => {
  it("F1: empty message cannot be sent", () => {
    expect(checkCanSend("   ", "simple", DEFAULT_TEAM, "auto").ok).toBe(false);
    expect(checkCanSend("hi", "simple", DEFAULT_TEAM, "auto").ok).toBe(true);
  });

  it("F2: a mixed team needs at least 2 models", () => {
    const team = { ...DEFAULT_TEAM, source: "mixed" as const, mixed: ["sonnet"] };
    expect(checkCanSend("hi", "thinker", team, "auto")).toEqual({ ok: false, reason: "Pick at least 2 models" });
    // Simple mode does not use a team, so it is not blocked
    expect(checkCanSend("hi", "simple", team, "auto").ok).toBe(true);
    // Planner with every step in Simple does not use a team either (T1)
    expect(checkCanSend("hi", "planner", team, "simple").ok).toBe(true);
  });

  it("F3: agents stop at 2 and 5, rounds at 1 and 3", () => {
    expect(stepAgents(5, 1)).toEqual({ value: 5, toast: "At most 5 agents" });
    expect(stepAgents(2, -1)).toEqual({ value: 2, toast: "At least 2 agents" });
    expect(stepAgents(3, 1)).toEqual({ value: 4 });
    expect(stepRounds(3, 1).toast).toBe("Max 3 rounds");
    expect(stepRounds(1, -1).value).toBe(1);
  });

  it("F3: the mixed model list stays between 2 and 5", () => {
    expect(toggleMixedModel(["a", "b"], "a").toast).toBeDefined();
    expect(toggleMixedModel(["a", "b", "c", "d", "e"], "f").toast).toBeDefined();
    expect(toggleMixedModel(["a", "b"], "c").list).toEqual(["a", "b", "c"]);
  });

  it("F4/F5: models are greyed out with a reason", () => {
    const llama = getModel("llama"); // no tools, no vision
    expect(modelDisabledReason(llama, { tools: true, vision: false })).toMatch(/No tools/);
    expect(modelDisabledReason(llama, { tools: false, vision: true })).toMatch(/Cannot see images/);
    expect(modelDisabledReason(getModel("sonnet"), { tools: true, vision: true })).toBe("");
  });

  it("F6: a model that cannot think forces thinking Off", () => {
    expect(normalizeThinking(getModel("mistral"), "high")).toBe("off");
    expect(normalizeThinking(getModel("sonnet"), "high")).toBe("high");
  });

  it("F7: over budget blocks unless allowed once", () => {
    expect(isOverBudget(0.3, 0.25, false)).toBe(true);
    expect(isOverBudget(0.3, 0.25, true)).toBe(false);
    expect(isOverBudget(0.1, 0.25, false)).toBe(false);
  });

  it("F13: warns when strong and weak models are mixed", () => {
    const mixed = { ...DEFAULT_TEAM, source: "mixed" as const, mixed: ["opus", "llama"] };
    expect(mixedStrengthWarning(mixed)).toMatch(/similar strength/);
    expect(mixedStrengthWarning({ ...mixed, mixed: ["sonnet", "gpt"] })).toBe("");
  });
});
