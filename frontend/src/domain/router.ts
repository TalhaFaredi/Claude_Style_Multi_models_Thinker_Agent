import type { RunKind } from "./types";

export interface Route {
  kind: RunKind;
  /** One line shown as the Auto routing note (C5). */
  reason: string;
}

const PLANNER_WORDS = /\b(make|build|create|report|pdf|plan|steps?)\b/;
const THINKER_WORDS = /\b(should|compare|better|which|vs|pros|choose)\b/;

/**
 * Auto mode (C5): chat or simple fact -> Simple; judgment or comparison -> Thinker;
 * many steps or a file to make -> Planner. When unsure (C6) we stay on Simple and
 * the answer offers a "Think deeper" button.
 * In production the backend uses a small cheap model for this; this is the offline fallback.
 */
export function routeAuto(text: string): Route {
  const t = text.toLowerCase();
  if (PLANNER_WORDS.test(t)) return { kind: "planner", reason: "Auto chose Planner: it has several steps" };
  if (THINKER_WORDS.test(t)) return { kind: "thinker", reason: "Auto chose Thinker: it compares options" };
  return { kind: "simple", reason: "Auto chose Simple: a direct question" };
}
