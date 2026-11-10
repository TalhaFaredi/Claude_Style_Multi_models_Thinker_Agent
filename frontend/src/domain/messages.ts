import type { AgentView, ComposerView, PermissionView, OutputFile, PlanStepView } from "./events";
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
  /** True when Auto picked the mode, so "Think deeper" is offered under Simple answers. */
  auto: boolean;
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
  error: string | null;
  /** Shown with the answer (budget stop, failed check after retries...). */
  warning: string | null;
  /** Real thinking time, when the server reports it. */
  thoughtSeconds: number | null;
  /** Settings frozen at send time, so later edits never change an answer already shown. */
  snapshot: { simple: SimpleConfig; team: TeamConfig; runIn: StepRunMode };
}

export type Message = UserMessage | SystemMessage | AiMessage;
