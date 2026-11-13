import { getModel } from "@/data/sample";
import { activeTools } from "./guardrails";
import type { Mode, SimpleConfig, StepRunMode, TeamConfig } from "./types";

/** "3 x Claude Sonnet 5.5, together, 2 rounds" - the Thinker progress line. */
export function teamLine(team: TeamConfig): string {
  const who = team.source === "same" ? `${team.agents} x ${getModel(team.model).name}` : `${team.mixed.length} different models`;
  return `${who}, ${team.style === "together" ? `together, ${team.rounds} rounds` : "on their own"}`;
}

function teamSentence(team: TeamConfig): string {
  const who =
    team.source === "same"
      ? `${team.agents} copies of ${getModel(team.model).name}`
      : team.mixed.map((id) => getModel(id).name).join(", ");
  const how = team.style === "together" ? ` discuss for ${team.rounds} ${team.rounds === 1 ? "round" : "rounds"}` : " each answer on their own";
  const composer = `${team.composer === "auto" ? "the strongest model your budget allows" : getModel(team.composer).name} combines them into one answer.`;
  return `${who}${how}, then ${composer}`;
}

const TOOL_NAMES = { web: "web search", code: "code", files: "files" } as const;

/** The green "What will happen" sentence at the top of the Setup dialog. */
export function setupSentence(mode: Mode, simple: SimpleConfig, team: TeamConfig, runIn: StepRunMode, planModel = simple.model): string {
  const model = getModel(simple.model);
  if (mode === "thinker") return teamSentence(team);
  if (mode === "planner") {
    const writer = `${getModel(planModel).name} writes a plan and waits for your OK. `;
    if (runIn === "simple") return `${writer}Then ${model.name} does every step.`;
    return writer + (runIn === "auto" ? `Then ${model.name} does the easy steps. For the hard steps: ` : "Then for every step: ") + teamSentence(team);
  }
  const tools = activeTools(simple).map((k) => TOOL_NAMES[k as keyof typeof TOOL_NAMES]);
  const thinking = simple.thinking !== "off" && model.thinking ? `, thinks first (${simple.thinking})` : ", no thinking";
  return `${model.name} answers${thinking}${tools.length ? `, may use ${tools.join(", ")}` : ", no tools"}.`;
}

/** Short label on the Setup button in the top bar. */
export function setupLabel(mode: Mode, simple: SimpleConfig, team: TeamConfig, runIn: StepRunMode): string {
  const model = getModel(simple.model);
  if (mode === "thinker") return `Team: ${teamLine(team)}`;
  if (mode === "planner") return runIn === "simple" ? `Plan with ${model.name}` : runIn === "auto" ? "Plan: team for hard steps" : "Plan: team for every step";
  return `Model: ${model.name}`;
}
