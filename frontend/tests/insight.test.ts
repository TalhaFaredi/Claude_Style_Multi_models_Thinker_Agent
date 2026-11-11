import { describe, expect, it } from "vitest";
import { reduceRunEvent } from "@/domain/reduceRunEvent";
import { preciseMoney } from "@/domain/format";
import { modelDisabledReason } from "@/domain/guardrails";
import { MODELS } from "@/data/sample";
import type { AiMessage } from "@/domain/messages";

describe("model and run transparency", () => {
  it("keeps settled call charges and unavailable provider thinking distinct from workflow notes", () => {
    const base = {
      status: "live", thinkingNotes: ["Checking the task"], callUsages: [], modelThinking: [],
    } as unknown as AiMessage;
    const withUsage = reduceRunEvent(base, { type: "call_usage", stage: "thinker:agent", model: "example/model", provider: "openrouter", label: "Critic",
      inTokens: 800, outTokens: 120, reasoningTokens: 25, usd: 0.00000213, estimated: false, ok: true });
    const withReasoning = reduceRunEvent(withUsage, { type: "model_thinking", stage: "thinker:agent", model: "example/model", label: "Critic", notes: [], available: false });
    expect(withReasoning.callUsages?.[0]).toMatchObject({ label: "Critic", usd: 0.00000213, reasoningTokens: 25 });
    expect(withReasoning.modelThinking?.[0]).toMatchObject({ label: "Critic", available: false, notes: [] });
    expect(withReasoning.thinkingNotes).toEqual(["Checking the task"]);
    expect(preciseMoney(0.00000213)).toBe("$0.00000213");
    expect(preciseMoney(0.01345)).toBe("$0.01345");
  });

  it("disables a catalog model that cannot answer chat prompts", () => {
    expect(modelDisabledReason({ ...MODELS[0], chatCompatible: false }, { tools: false, vision: false })).toMatch(/cannot answer chat/i);
  });
});
