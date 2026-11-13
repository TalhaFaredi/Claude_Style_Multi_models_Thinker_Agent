import type { AgentView, CallUsageView, ComposerView, ModelThinkingView, PermissionView, OutputFile, PlanStepView } from "./events";
import type { RunKind, SimpleConfig, StepRunMode, TeamConfig } from "./types";

export interface UserMessage {
  id: string;
  role: "user";
  text: string;
  files: string[];
}

export interface SystemMessage {
  id: string;
  role: "sys";
  text: string;
}

export type AiStatus = "live" | "waiting" | "done" | "stopped" | "error" | "offline";

export interface AiMessage {
  id: string;
  role: "ai";
  kind: RunKind;
  /** The question that produced this answer (used for Retry and Think deeper). */
  prompt: string;
  /** Always false: kept because saved answers carry the field (it marked answers routed by the old Auto mode). */
  auto: boolean;
  /** True when this is a helper's question asked before an expensive Thinker or Planner run, not an answer. */
  clarify?: boolean;
  status: AiStatus;
  statusText: string;
  thinkingNotes: string[];
  tool: { state: "running" | "done"; label: string } | null;
  text: string;
  citations: string[];
  roundText: string;
  agents: AgentView[];
  plan: { phase: string; steps: PlanStepView[]; awaitingApproval: boolean; estimateUsd?: number | null; version?: string; overBudget?: boolean; remainingBudgetUsd?: number } | null;
  composer?: ComposerView;
  permission?: PermissionView | null;
  controlError?: string | null;
  output: OutputFile | null;
  calls: number;
  costUsd: number;
  callUsages?: CallUsageView[];
  modelThinking?: ModelThinkingView[];
  error: string | null;
  /** Shown with the answer (budget stop, failed check after retries...). */
  warning: string | null;
  /** Real thinking time, when the server reports it. */
  thoughtSeconds: number | null;
  /** Settings frozen at send time, so later edits never change an answer already shown. */
  snapshot: { simple: SimpleConfig; team: TeamConfig; runIn: StepRunMode };
}

export type Message = UserMessage | SystemMessage | AiMessage;
