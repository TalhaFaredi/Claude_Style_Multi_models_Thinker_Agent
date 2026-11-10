/**
 * Typed client for the FastAPI backend. Only used when NEXT_PUBLIC_API_URL is set ("live" mode);
 * without it the app runs on the built-in mock and none of this is called.
 */
import type { ContextInfo, RunEvent } from "@/domain/events";
import type { DocumentCard, ModelInfo, ReaderId, SimpleConfig, StepRunMode, TeamConfig, Mode } from "@/domain/types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
export const isLive = API_URL !== "";

export class ApiError extends Error {
  constructor(message: string, public status: number, public detail?: Record<string, unknown>) {
    super(message);
  }
}

export async function toError(res: Response): Promise<ApiError> {
  let message = `Server answered ${res.status}`;
  let detail: Record<string, unknown> | undefined;
  try {
    const j = await res.json();
    const d = j?.detail;
    if (typeof d === "string") message = d;
    else if (d && typeof d === "object") {
      detail = d as Record<string, unknown>;
      message = String((d as { message?: string }).message ?? message);
    }
  } catch {
    /* body was not JSON */
  }
  return new ApiError(message, res.status, detail);
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(`Cannot reach the backend at ${API_URL}. Is it running?`, 0);
  }
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

/** Reads a Server-Sent Events response and calls `onEvent` for every `data:` message. */
export async function readSse(res: Response, onEvent: (e: RunEvent) => void): Promise<void> {
  if (!res.ok || !res.body) throw await toError(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, "\n");
    const messages = buffer.split("\n\n");
    buffer = messages.pop() ?? "";
    for (const message of messages) {
      const data = message.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
      if (data) onEvent(JSON.parse(data) as RunEvent);
    }
  }
}

export interface ServerConfig {
  version: string;
  defaults: { simple: SimpleConfig; team: TeamConfig; runIn: StepRunMode; budget: number; planModel?: string };
  qualityPresets: { fast: string; balanced: string; best: string };
  limits: Record<string, number>;
  providers: Record<string, { ok: boolean; reason: string; creditRemaining?: number | null; creditLimit?: number | null }>;
  readers: Record<ReaderId, { available: boolean; reason: string }>;
  capabilities: { codeSandbox: boolean; zipPassword: boolean; embeddings: boolean; webSearch: boolean };
  settings: ServerSettings;
  monthUsd: number;
  readingUsd?: number;
  readingBudgetPercent?: number;
  readingAlarm?: boolean;
}

export interface ServerSettings {
  reader: ReaderId;
  askLimit: number;
  monthBudget: number;
  longMemory: boolean;
  autoCompact: boolean;
  tempChat: boolean;
  chartDescriptions: boolean;
  keepPageImages: boolean;
  windowCap: number;
  embeddings: boolean;
  promptCacheTtl?: "5m" | "1h";
}

export interface ChatSummary {
  id: string;
  title: string;
  updated: number;
  temp: boolean;
}

export interface FilePlanRow {
  label: string;
  kind: string;
  count: number;
  reader: string;
  cost: number;
  expectedCost?: number;
}

export interface UploadedFile {
  fingerprint: string;
  name: string;
  size: number;
  pages: number;
  kinds: { text: number; scan: number; chart: number; tables: number };
  plans: Record<ReaderId, { rows: FilePlanRow[]; total: number }>;
  readers: Record<ReaderId, { available: boolean; reason: string }>;
  readBefore: Record<string, { cost: number; pagesRead?: number[]; complete?: boolean }>;
}

export interface ChatFile {
  fingerprint: string;
  name: string;
  pages: number;
  ready: boolean;
  card: DocumentCard | null;
  cost: number;
}

export interface EstimateResult {
  usd: number;
  calls: number;
  kind: string;
  breakdown: Record<string, number>;
  context?: ContextInfo;
}

export interface ImportReport {
  chatId: string;
  title: string;
  messages: number;
  files: number;
  filesReused: number;
  facts: number;
  ledger: number;
  summaries: number;
  readingCostUsd: number;
  warnings: string[];
  reindexApprovalRequired?: boolean;
  reindexFiles?: Array<{ fingerprint: string; name: string; usd: number; model: string; chunks: number; available: boolean; reason: string }>;
}

export interface ServerFact {
  id: number;
  text: string;
  source: string;
  replaced: boolean;
}

export const api = {
  config: () => call<ServerConfig>("/api/config"),
  models: (q = "") => call<ModelInfo[]>(`/api/models${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  putSettings: (patch: Partial<ServerSettings>) => call<ServerSettings>("/api/settings", json("PUT", patch)),
  usage: () => call<{ totalUsd: number; monthBudget: number; readingUsd?: number; readingBudgetPercent?: number; readingAlarm?: boolean }>("/api/usage"),
  estimate: (body: { mode: Mode; chatId: string; prompt: string; simple: SimpleConfig; team: TeamConfig; runIn: StepRunMode; planModel?: string }, signal?: AbortSignal) =>
    call<EstimateResult>("/api/estimate", { ...json("POST", body), signal }),
  chats: (q = "") => call<ChatSummary[]>(`/api/chats${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  getChat: (id: string, model: string) =>
    call<{ chat: { id: string; title: string; temp: boolean }; messages: unknown[]; context: ContextInfo; files: ChatFile[]; costUsd: number }>(`/api/chats/${id}?model=${encodeURIComponent(model)}`),
  deleteChat: (id: string, deleteMemories: boolean) => call<{ factsDeleted: number }>(`/api/chats/${id}?deleteMemories=${deleteMemories}`, { method: "DELETE" }),
  forkChat: (id: string, model: string, maxCost: number) => call<{ chatId: string; title?: string }>(`/api/chats/${id}/fork`, json("POST", { model, maxCost })),
  context: (id: string, model: string) => call<ContextInfo>(`/api/chats/${id}/context?model=${encodeURIComponent(model)}`),
  upload: (chatId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<UploadedFile>(`/api/chats/${chatId}/files`, { method: "POST", body: form });
  },
  readEstimate: (fp: string, body: { chatId: string; reader: ReaderId; textOnly?: boolean; pages?: number[] }) => call<{ rows: FilePlanRow[]; total: number; pages: number[]; cachedPages: number[] }>(`/api/files/${fp}/read-estimate`, json("POST", body)),
  reindexFile: (fp: string, chatId: string, maxCost: number) => call<{ cost: number; complete: boolean; indexed: number; remaining: number; warning: string | null }>(`/api/files/${fp}/reindex`, json("POST", { chatId, maxCost })),
  readFile: (fp: string, body: { chatId: string; reader: ReaderId; textOnly: boolean; maxCost: number; pages?: number[] }) =>
    call<{ fingerprint: string; reused: boolean; cost: number; card: DocumentCard }>(`/api/files/${fp}/read`, json("POST", body)),
  detachFile: (chatId: string, fp: string) => call<{ ok: boolean }>(`/api/chats/${chatId}/files/${fp}`, { method: "DELETE" }),
  memory: () => call<{ facts: ServerFact[]; enabled: boolean }>("/api/memory"),
  deleteFact: (id: number) => call<{ deleted: boolean }>(`/api/memory/${id}`, { method: "DELETE" }),
  rate: (messageId: string, value: 1 | -1) => call<{ ok: boolean }>(`/api/messages/${messageId}/rating`, json("POST", { value })),
  importChat: (file: File, password?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (password) form.append("password", password);
    return call<ImportReport>("/api/import", { method: "POST", body: form });
  },
  /** Downloads the chat .zip as a Blob. */
  exportChat: async (chatId: string, includeFiles: boolean, password?: string): Promise<Blob> => {
    const qs = new URLSearchParams({ includeFiles: String(includeFiles) });
    // The password goes in a header, never the URL, so it cannot land in server logs or browser history.
    const res = await fetch(`${API_URL}/api/chats/${chatId}/export?${qs}`, password ? { headers: { "X-Export-Password": password } } : undefined);
    if (!res.ok) throw await toError(res);
    return res.blob();
  },
  artifactUrl: (id: string) => `${API_URL}/api/artifacts/${id}`,
  /** "Summarize now": streams the four checked steps, then a note and the new context. */
  compact: async (chatId: string, model: string, maxCost: number, onEvent: (e: RunEvent) => void) => {
    const res = await fetch(`${API_URL}/api/chats/${chatId}/compact`, json("POST", { model, maxCost }));
    await readSse(res, onEvent);
  },
};
