/** The user always picks the mode. (There used to be an "auto" mode that picked for them; it is gone.) */
export type Mode = "simple" | "thinker" | "planner";
/** The mode that runs: the same three values. */
export type RunKind = Mode;

export type Provider = "openrouter" | "nvidia";
export type CostLevel = "$" | "$$" | "$$$" | "unknown";

export interface ModelInfo {
  id: string;
  name: string;
  company: string;
  provider: Provider;
  tools: boolean;
  vision: boolean;
  thinking: boolean;
  costLevel: CostLevel;
  /** Strength tier 1 (small) to 3 (frontier). Used for the mixed-strength warning (F13 / T5). */
  tier: 1 | 2 | 3;
  /** Price of one typical call in USD (1,500 tokens in, 600 out). From the Model Registry. */
  callCost: number | null;
  /** USD per 1M input / output tokens (live registry only). */
  priceIn?: number;
  priceOut?: number;
  context?: number;
  /** False when the provider key is rejected: the picker greys the row and shows why. */
  available?: boolean;
  whyUnavailable?: string;
  priceKnown?: boolean;
  featured?: boolean;
  speed?: string;
  /** Tentative price for one model call; not the full question budget. */
  tentativeCosts?: Record<"small" | "medium" | "high", { minTokens: number; maxTokens: number; minUsd: number | null; maxUsd: number | null; fits: boolean; available?: boolean } | null>;
  pricingNote?: string;
  chatCompatible?: boolean;
}

export type ThinkingLevel = "off" | "low" | "medium" | "high";
export type AnswerStyle = "precise" | "balanced" | "creative";
export type ToolId = "web" | "code" | "files";

export interface SimpleConfig {
  model: string;
  thinking: ThinkingLevel;
  style: AnswerStyle;
  tools: Record<ToolId, boolean>;
  maxTokens?: number;
}

export type TeamSource = "same" | "mixed";
export type TeamStyle = "independent" | "together";

export interface TeamConfig {
  source: TeamSource;
  /** Model used for every copy when source = "same". */
  model: string;
  agents: number;
  /** Model ids when source = "mixed". */
  mixed: string[];
  style: TeamStyle;
  rounds: number;
  /** A model id, or "auto" = strongest model inside the budget (C14). */
  composer: string;
}

/** How Planner steps run: T1 (simple), T2 (auto), or every step with the team. */
export type StepRunMode = "auto" | "simple" | "thinker";

export type ReaderId = "auto" | "text" | "local" | "api" | "vision";

export interface DemoFile {
  id: string;
  name: string;
  pages: number;
  /** Page counts by type, used to price the reading. */
  text: number;
  scan: number;
  chart: number;
}

export interface DocumentCard {
  title: string;
  pages: number;
  summary: string;
  outline: { title: string; page: number }[];
  tables: number[];
  charts: { page: number; description: string }[];
  weakPages: number[];
  cost: number;
  readers?: string[];
}

export interface PendingFile {
  /** Mock: demo file id. Live: the file's SHA-256 fingerprint. */
  id: string;
  name: string;
  status: "reading" | "ready";
  cost: number;
  pages?: number;
  /** Chart pages: files with charts need a model that can see images (F5). */
  charts?: number;
  card?: DocumentCard;
}

export interface MemoryFact {
  id: number;
  text: string;
  source: string;
}
