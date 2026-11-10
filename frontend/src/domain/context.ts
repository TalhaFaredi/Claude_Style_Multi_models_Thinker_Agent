import { ANSWER_RESERVE, CONTEXT_LEVELS } from "./limits";

export type ContextLevel = "normal" | "notice" | "alarm" | "compact";

/** Part 2 §7: how full is the window. next prompt / (window - answer space). */
export function fillPercent(nextPromptTokens: number, windowTokens: number, reserve = ANSWER_RESERVE): number {
  const usable = windowTokens - windowTokens * reserve;
  return Math.round((nextPromptTokens / usable) * 100);
}

/** C34 to C37: which action the fill level triggers. */
export function contextLevel(percent: number): ContextLevel {
  if (percent >= CONTEXT_LEVELS.compact) return "compact";
  if (percent >= CONTEXT_LEVELS.alarm) return "alarm";
  if (percent >= CONTEXT_LEVELS.notice) return "notice";
  return "normal";
}

/**
 * "Later" (C36) asks again at 90%. If the chat is already past 90%, the next
 * point worth interrupting for is 95% (safe summary), not "right now".
 */
export function snoozeThreshold(percent: number): number {
  return percent < CONTEXT_LEVELS.snoozeAgain ? CONTEXT_LEVELS.snoozeAgain : CONTEXT_LEVELS.compact;
}

/** CSS modifier for the meter bar: green, amber at 70, rust at 85, red at 95. */
export function meterClass(percent: number): string {
  const level = contextLevel(percent);
  return level === "compact" ? "crit" : level === "alarm" ? "alarm" : level === "notice" ? "warn" : "";
}

export interface ContextPart {
  label: string;
  percent: number;
}

/** Breakdown of the window by part (Figure 8). Sample split until the backend reports it. */
export function contextBreakdown(percent: number): ContextPart[] {
  const parts: ContextPart[] = [
    { label: "Rules and tools", percent: 4 },
    { label: "Files", percent: Math.round(percent * 0.3) },
    { label: "Memory", percent: 6 },
    { label: "Summary", percent: percent > 40 ? 4 : 1 },
  ];
  const used = parts.reduce((sum, p) => sum + p.percent, 0);
  parts.push({ label: "Recent messages", percent: Math.max(0, percent - used) });
  return parts;
}

/** Sample growth per answer, until the server sends real `context` events. */
export function contextBump(kind: "simple" | "thinker" | "planner", hasFiles: boolean): number {
  return (kind === "simple" ? 7 : kind === "thinker" ? 10 : 12) + (hasFiles ? 6 : 0);
}
