import { getModel } from "@/data/sample";
import type { DemoFile, ReaderId, SimpleConfig, StepRunMode, TeamConfig, Mode } from "./types";

/** Composer price when set to "auto" (the strongest model inside the budget, C14). */
const AUTO_COMPOSER_COST = 0.02;
const PLANNER_BASE = 0.08;
const PLANNER_SIMPLE_STEPS = 0.03;
const callCost = (id: string): number => getModel(id).callCost ?? Infinity;

/** Spec Part 2 §4: OCR API $2 per 1,000 pages; vision about 1,600 in + 300 out tokens on Haiku. */
export const PAGE_COST = { ocr: 0.002, vision: 0.0031 } as const;

/** Agent calls in a team: n (+ n per extra round) plus one composer call (Part 1 §7). */
export function teamCalls(team: TeamConfig): number {
  const n = team.source === "same" ? team.agents : team.mixed.length;
  const rounds = team.style === "together" ? team.rounds : 1;
  return n * rounds + 1;
}

export function teamCost(team: TeamConfig): number {
  const perRound =
    team.source === "same"
      ? team.agents * callCost(team.model)
      : team.mixed.reduce((sum, id) => sum + callCost(id), 0);
  const rounds = team.style === "together" ? team.rounds : 1;
  const composer = team.composer === "auto" ? AUTO_COMPOSER_COST : callCost(team.composer);
  return perRound * rounds + composer;
}

export function plannerCost(runIn: StepRunMode, team: TeamConfig): number {
  return PLANNER_BASE + (runIn === "simple" ? PLANNER_SIMPLE_STEPS : teamCost(team));
}

export interface EstimateInput {
  mode: Mode;
  simple: SimpleConfig;
  team: TeamConfig;
  runIn: StepRunMode;
}

/** Cost estimate shown next to Send, before anything is spent (F7). */
export function estimateCost({ mode, simple, team, runIn }: EstimateInput): number {
  if (mode === "thinker") return teamCost(team);
  if (mode === "planner") return plannerCost(runIn, team);
  return callCost(simple.model);
}

/** Price of reading a file with the chosen reader (Part 2 §4). Text pages are always free. */
export function fileReadingCost(file: DemoFile, reader: ReaderId): number {
  switch (reader) {
    case "text":
    case "local":
      return 0;
    case "api":
      return (file.scan + file.chart) * PAGE_COST.ocr;
    case "vision":
      return (file.scan + file.chart) * PAGE_COST.vision;
    case "auto":
      return file.scan * PAGE_COST.ocr + file.chart * PAGE_COST.vision;
  }
}

export interface RouteRow {
  label: string;
  reader: string;
  cost: number;
}

/** Per-page-type breakdown shown in the Add-a-file dialog (Figure 6). */
export function fileRouteRows(file: DemoFile, reader: ReaderId): RouteRow[] {
  const free = reader === "text" || reader === "local";
  const rows: RouteRow[] = [{ label: `${file.text} normal pages`, reader: "Free text reading", cost: 0 }];
  if (file.scan) {
    rows.push({
      label: `${file.scan} scanned pages`,
      reader: reader === "text" ? "Cannot be read" : reader === "local" ? "Local OCR (free, slower)" : reader === "vision" ? "Vision model" : "OCR API",
      cost: free ? 0 : file.scan * (reader === "vision" ? PAGE_COST.vision : PAGE_COST.ocr),
    });
  }
  if (file.chart) {
    rows.push({
      label: `${file.chart} chart pages`,
      reader: reader === "text" ? "Cannot be read" : reader === "local" ? "Local layout parser" : reader === "api" ? "OCR API" : "Vision model + page image",
      cost: free ? 0 : file.chart * (reader === "api" ? PAGE_COST.ocr : PAGE_COST.vision),
    });
  }
  return rows;
}
