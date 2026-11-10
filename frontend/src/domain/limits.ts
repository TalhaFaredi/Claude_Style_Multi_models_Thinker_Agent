/**
 * Fixed safety limits and thresholds from the spec (Part 1 §8, Part 2 §7).
 * The UI can never exceed these; the backend enforces them again.
 */
export const LIMITS = {
  minAgents: 2,
  maxAgents: 5,
  minRounds: 1,
  maxRounds: 3,
  maxToolCalls: 10,
  maxRetries: 2,
  maxReplans: 2,
  maxPlanSteps: 20,
} as const;

/** Context window alarm levels, in percent of the usable window. */
export const CONTEXT_LEVELS = { notice: 70, alarm: 85, compact: 95, snoozeAgain: 90 } as const;

/** Share of the window reserved for the answer (spec Part 2 §6). */
export const ANSWER_RESERVE = 0.15;

export const BUDGET_CHOICES = [0.05, 0.25, 1] as const;
export const ASK_LIMIT_CHOICES = [0.1, 0.5, 2] as const;
export const MONTH_BUDGET_CHOICES = [5, 20, 50] as const;
