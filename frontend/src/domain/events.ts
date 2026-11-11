import type { RunKind, SimpleConfig, StepRunMode, TeamConfig } from "./types";

/**
 * The wire contract between backend and UI (spec Part 3 §11):
 * "The server sends small events: status, text, tool, agent, step, cost, done".
 * The mock runner and the SSE runner both emit exactly these.
 */
export type AgentStatus = "thinking" | "revising" | "ready";

export interface AgentView {
  role: string;
  model: string;
  status: AgentStatus;
}

export type StepStatus = "planned" | "planning" | "waiting" | "running" | "checking" | "retry" | "done" | "failed";

export interface PlanStepView {
  task: string;
  /** Human label, e.g. "Simple + web search" or "Thinker: 3 x Sonnet". */
  modeLabel: string;
  status: StepStatus;
  note?: string;
  noteTone?: "hint" | "warn";
  doneTest?: string;
  kind?: "easy" | "hard" | "tool";
  canUseTeam?: boolean;
}

export interface PermissionView {
  id: string;
  tool: string;
  description: string;
  arguments?: unknown;
  resolved?: boolean;
}

export interface ComposerView {
  model: string;
  status: "waiting" | "running" | "done";
  explanation: string;
}

export interface OutputFile {
  /** Live: artifact id, downloaded from GET /api/artifacts/{id}. */
  id?: string;
  name: string;
  pages: number;
  sources: number;
  checked?: boolean;
  warning?: string;
}

export interface ContextPartInfo {
  label: string;
  percent: number;
  tokens?: number;
}

/** A settled provider attempt. A failed attempt may still have an estimated charge. */
export interface CallUsageView {
  stage: string;
  model: string;
  provider: string;
  label?: string;
  inTokens: number;
  outTokens: number;
  reasoningTokens: number;
  usd: number;
  estimated: boolean;
  ok: boolean;
}

/** Short notes only when the provider included reasoning in its response. */
export interface ModelThinkingView {
  stage: string;
  model: string;
  label?: string;
  notes: string[];
  available: boolean;
}

export type ContextLevelName = "normal" | "notice" | "alarm" | "compact";

/** Server-reported state of the memory window (live backend). */
export interface ContextInfo {
  percent: number;
  level: ContextLevelName;
  parts: ContextPartInfo[];
  windowTokens: number;
  usableTokens: number;
  usedTokens: number;
  nextMessageUsd?: number;
  nextMessageCachedUsd?: number;
}

export type RunEvent =
  /** Auto mode resolved to a mode (C5/C6). `reason` is the one-line routing note. */
  | { type: "route"; kind: RunKind; reason: string }
  | { type: "status"; text: string }
  | { type: "thinking"; notes: string[]; seconds?: number }
  | { type: "tool"; state: "running" | "done"; label: string }
  /** `replace: true` = the Checker rejected the draft: start the answer over. */
  | { type: "text"; delta: string; replace?: boolean }
  | { type: "citations"; items: string[] }
  | { type: "agents"; roundText: string; agents: AgentView[] }
  | { type: "plan"; phase: string; steps: PlanStepView[]; awaitingApproval: boolean; estimateUsd?: number | null; version?: string; overBudget?: boolean; remainingBudgetUsd?: number }
  | ({ type: "composer" } & ComposerView)
  | ({ type: "permission" } & PermissionView)
  | { type: "output"; file: OutputFile }
  | { type: "cost"; calls: number; usd: number }
  | ({ type: "call_usage" } & CallUsageView)
  | ({ type: "model_thinking" } & ModelThinkingView)
  /** New fill level of the memory window. Live servers also send level, parts and prices. */
  | ({ type: "context"; percent: number } & Partial<Omit<ContextInfo, "percent">>)
  /** Warning shown with the answer: budget stop, failed check after retries (C19), mixed strengths (T5)... */
  | { type: "warning"; message: string }
  /** The router needs one short question before it can answer (C2). */
  | { type: "clarify"; question: string }
  /** Safe summary progress: step 0 to 3 working, 4 = finished (Part 2 section 7). */
  | { type: "compact"; step: number; done: boolean }
  /** A system note for the chat ("Older messages summarized..."). */
  | { type: "note"; text: string }
  | { type: "done"; monthUsd?: number }
  | { type: "error"; message: string; offline?: boolean };

/** What the UI sends to start a run. */
export interface RunRequest {
  id: string;
  /** Chat this run belongs to (live backend). */
  chatId: string;
  /** What the user picked. Auto is resolved by the router (live) or by `kind` (mock). */
  mode: "auto" | "simple" | "thinker" | "planner";
  /** Mock runner only: the already-resolved mode. */
  kind: RunKind;
  prompt: string;
  files: string[];
  simple: SimpleConfig;
  team: TeamConfig;
  runIn: StepRunMode;
  planModel?: string;
  budgetUsd: number;
  estimateUsd: number;
  /** How full the memory window is now (0 to 100). */
  contextPercent: number;
  /** "Allow for this question only" from the cost dialog. */
  allowOver?: boolean;
  /** Retry of a failed answer: the server replaces it instead of adding a second question. */
  retryOf?: string;
}
