/**
 * SAMPLE DATA. Everything here is replaced by the backend later:
 *  - MODELS      -> Model Registry (GET /api/models, filled from OpenRouter + NVIDIA)
 *  - DEMO_FILES  -> real uploads
 *  - READERS     -> fixed list from the spec (Part 2 §4)
 */
import type { DemoFile, MemoryFact, ModelInfo, ReaderId } from "@/domain/types";

export const MODELS: ModelInfo[] = [
  { id: "opus", name: "Claude Opus 5.5", company: "Anthropic", provider: "openrouter", tools: true, vision: true, thinking: true, costLevel: "$$$", tier: 3, callCost: 0.06 },
  { id: "sonnet", name: "Claude Sonnet 5.5", company: "Anthropic", provider: "openrouter", tools: true, vision: true, thinking: true, costLevel: "$$", tier: 3, callCost: 0.02 },
  { id: "haiku", name: "Claude Haiku 5.5", company: "Anthropic", provider: "openrouter", tools: true, vision: true, thinking: true, costLevel: "$", tier: 2, callCost: 0.005 },
  { id: "gpt", name: "GPT (latest)", company: "OpenAI", provider: "openrouter", tools: true, vision: true, thinking: true, costLevel: "$$", tier: 3, callCost: 0.02 },
  { id: "gemini", name: "Gemini Pro (latest)", company: "Google", provider: "openrouter", tools: true, vision: true, thinking: true, costLevel: "$$", tier: 3, callCost: 0.02 },
  { id: "deepseek", name: "DeepSeek (latest)", company: "DeepSeek", provider: "openrouter", tools: true, vision: false, thinking: true, costLevel: "$", tier: 2, callCost: 0.004 },
  { id: "mistral", name: "Mistral Large", company: "Mistral", provider: "openrouter", tools: true, vision: false, thinking: false, costLevel: "$$", tier: 2, callCost: 0.01 },
  { id: "llama", name: "Llama 3.3 70B Instruct", company: "Meta", provider: "nvidia", tools: false, vision: false, thinking: false, costLevel: "$", tier: 1, callCost: 0.003 },
  { id: "nemotron", name: "Nemotron (latest)", company: "NVIDIA", provider: "nvidia", tools: true, vision: false, thinking: true, costLevel: "$", tier: 1, callCost: 0.003 },
  { id: "qwen", name: "Qwen VL (latest)", company: "Alibaba", provider: "nvidia", tools: true, vision: true, thinking: false, costLevel: "$", tier: 1, callCost: 0.004 },
];

let source: () => ModelInfo[] = () => MODELS;

/** modelsStore points this at the live registry once it is loaded (avoids a circular import). */
export function setModelSource(fn: () => ModelInfo[]): void {
  source = fn;
}

/** Look a model up by id. Falls back to the first model so the UI never crashes on a stale id. */
export function getModel(id: string): ModelInfo {
  const list = source();
  return list.find((m) => m.id === id) ?? list[0] ?? MODELS[1];
}

export const ROLES = ["Solver", "Critic", "Fact-checker", "Simplifier", "Devil's advocate"] as const;

export const DEMO_FILES: DemoFile[] = [
  { id: "report", name: "Q3_Report.pdf", pages: 200, text: 170, scan: 20, chart: 10 },
  { id: "contract", name: "Signed_contract_scan.pdf", pages: 12, text: 0, scan: 12, chart: 0 },
  { id: "sales", name: "Sales_2026.xlsx", pages: 3, text: 3, scan: 0, chart: 0 },
];

export interface ReaderOption {
  id: ReaderId;
  name: string;
  text: string;
  cost: string;
}

export const READERS: ReaderOption[] = [
  { id: "auto", name: "Auto (recommended)", text: "Cheapest reader that works, page by page", cost: "Lowest" },
  { id: "text", name: "Text only", text: "Free, but cannot read scans or charts", cost: "Free" },
  { id: "local", name: "Local open-source", text: "Docling or Tesseract on your server", cost: "No page fee" },
  { id: "api", name: "OCR API", text: "Mistral OCR 3: scans, forms, handwriting", cost: "$2 per 1,000 pages" },
  { id: "vision", name: "Vision model", text: "Looks at the page image; best for charts", cost: "About $0.003 a page" },
];

export const SAMPLE_CHATS = [
  { id: "c1", title: "System design review" },
  { id: "c2", title: "Memory and attachments" },
  { id: "c3", title: "OCR cost check" },
  { id: "c4", title: "Solar report plan" },
];

export const INITIAL_MEMORY: MemoryFact[] = [
  { id: 1, text: "Prefers short, simple explanations with examples", source: 'Oct 26, "System design review"' },
  { id: 2, text: "Builds a multi-mode assistant on OpenRouter and NVIDIA", source: 'Oct 26, "System design review"' },
  { id: 3, text: "Monthly budget is $20 (replaced $5 on Oct 20)", source: 'Oct 20, "OCR cost check"' },
];

export const EXAMPLES = [
  { mode: "Simple", text: "Explain what a context window is in simple words" },
  { mode: "Thinker", text: "Should a small team use one strong model or many cheaper ones?" },
  { mode: "Planner", text: "Make a 2-page PDF report on solar power" },
] as const;
