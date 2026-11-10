import type { SimpleConfig, TeamConfig } from "./types";

/** Safe defaults (spec Part 3 §9, F12 "Reset to safe defaults"). */
export const DEFAULT_SIMPLE: SimpleConfig = {
  model: "sonnet",
  thinking: "medium",
  style: "balanced",
  tools: { web: true, code: false, files: true },
  maxTokens: 1200,
};

/** "On their own" is the default team style: cheap, and most of the gain of debate (Part 1 §7). */
export const DEFAULT_TEAM: TeamConfig = {
  source: "same",
  model: "sonnet",
  agents: 3,
  mixed: ["sonnet", "gpt", "gemini"],
  style: "independent",
  rounds: 2,
  composer: "auto",
};
