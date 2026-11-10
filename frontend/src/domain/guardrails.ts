/**
 * Guardrails F1 to F13 (spec Part 3 §9) as pure functions.
 * The UI asks these; it never re-implements the rules inline.
 */
import { getModel } from "@/data/sample";
import { LIMITS } from "./limits";
import type { DemoFile, ModelInfo, SimpleConfig, TeamConfig, Mode, ThinkingLevel } from "./types";

export interface SendCheck {
  ok: boolean;
  /** Shown beside the Send button. Empty for F1 (Send just stays grey). */
  reason: string;
}

/** F1 empty message, F2 fewer than 2 models in a team. */
export function checkCanSend(draft: string, mode: Mode, team: TeamConfig, runIn: string): SendCheck {
  if (!draft.trim()) return { ok: false, reason: "" };
  const usesTeam = mode === "thinker" || (mode === "planner" && runIn !== "simple");
  if (usesTeam && team.source === "mixed" && team.mixed.length < LIMITS.minAgents) {
    return { ok: false, reason: "Pick at least 2 models" };
  }
  return { ok: true, reason: "" };
}

/** F2 reason without the draft check (so the hint shows even before typing). */
export function teamGuardText(mode: Mode, team: TeamConfig, runIn: string): string {
  const usesTeam = mode === "thinker" || (mode === "planner" && runIn !== "simple");
  return usesTeam && team.source === "mixed" && team.mixed.length < LIMITS.minAgents ? "Pick at least 2 models" : "";
}

export interface LimitResult {
  value: number;
  /** Set when the user hit a limit: show it in a toast (F3). */
  toast?: string;
}

/** F3 steppers stop at 2 to 5 agents. */
export function stepAgents(current: number, delta: 1 | -1): LimitResult {
  const next = current + delta;
  if (next < LIMITS.minAgents) return { value: current, toast: `At least ${LIMITS.minAgents} agents` };
  if (next > LIMITS.maxAgents) return { value: current, toast: `At most ${LIMITS.maxAgents} agents` };
  return { value: next };
}

/** F3 steppers stop at 1 to 3 rounds. */
export function stepRounds(current: number, delta: 1 | -1): LimitResult {
  const next = current + delta;
  if (next < LIMITS.minRounds) return { value: current, toast: `At least ${LIMITS.minRounds} round` };
  if (next > LIMITS.maxRounds) return { value: current, toast: `Max ${LIMITS.maxRounds} rounds` };
  return { value: next };
}

/** F3 for the "pick 2 to 5 models" list. Returns the new list, or a toast if blocked. */
export function toggleMixedModel(list: string[], id: string): { list: string[]; toast?: string } {
  if (list.includes(id)) {
    if (list.length <= LIMITS.minAgents) return { list, toast: `Needs at least ${LIMITS.minAgents} models` };
    return { list: list.filter((x) => x !== id) };
  }
  if (list.length >= LIMITS.maxAgents) return { list, toast: `At most ${LIMITS.maxAgents} models` };
  return { list: [...list, id] };
}

export interface ModelNeeds {
  /** Tools are switched on for the main model (F4). */
  tools: boolean;
  /** A file with charts is attached (F5). */
  vision: boolean;
}

/** F4 + F5: why a model row is greyed out, or "" when it is usable. */
export function modelDisabledReason(model: ModelInfo, needs: ModelNeeds): string {
  if (model.available === false) return model.whyUnavailable || "Provider unavailable";
  if (needs.tools && !model.tools) return "No tools, and your tools are on";
  if (needs.vision && !model.vision) return "Cannot see images; your file has charts";
  return "";
}

/** F6: a model that cannot think forces thinking to Off. */
export function normalizeThinking(model: ModelInfo, level: ThinkingLevel): ThinkingLevel {
  return model.thinking ? level : "off";
}

/** Tools actually sent to the model: only those it supports (C9). */
export function activeTools(simple: SimpleConfig): string[] {
  const model = getModel(simple.model);
  if (!model.tools) return [];
  return (Object.keys(simple.tools) as (keyof SimpleConfig["tools"])[]).filter((k) => simple.tools[k]);
}

/** F7: over budget opens the cost dialog before anything is spent. */
export function isOverBudget(estimate: number, budget: number, allowOnce: boolean): boolean {
  return estimate > budget && !allowOnce;
}

/** An explicit one-question cap; never exceed the server's maximum accepted budget. */
export function oneQuestionCap(estimate: number, budget: number): number {
  return Math.min(50, Math.max(budget, estimate * 1.25));
}

/** F8: a file over the ask-me limit is marked amber and offers Text only. */
export function isOverAskLimit(fileCost: number, askLimit: number): boolean {
  return fileCost > askLimit;
}

/** True when the attached files have chart pages (F5 needs a vision model). */
export function needsVision(files: Pick<DemoFile, "chart">[]): boolean {
  return files.some((f) => f.chart > 0);
}

/** F13 / T5: warn when strong and weak models are mixed in one team. */
export function mixedStrengthWarning(team: TeamConfig): string {
  if (team.source !== "mixed" || team.mixed.length < 2) return "";
  const tiers = team.mixed.map((id) => getModel(id).tier);
  if (Math.max(...tiers) - Math.min(...tiers) >= 2) {
    return "Strong and weak models are mixed. A weak model can pull the answer down. Pick models of similar strength.";
  }
  return "";
}
