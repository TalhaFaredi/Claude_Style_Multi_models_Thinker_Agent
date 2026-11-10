import { create } from "zustand";
import { MODELS as SAMPLE_MODELS, setModelSource } from "@/data/sample";
import type { ModelInfo, ReaderId } from "@/domain/types";
import { api, isLive, type ServerConfig } from "@/services/api";

type Presets = { fast: string; balanced: string; best: string };
type Readers = Record<ReaderId, { available: boolean; reason: string }>;

interface ModelsState {
  models: ModelInfo[];
  /** Auto's Fast / Balanced / Best choices. */
  presets: Presets;
  providers: ServerConfig["providers"];
  readers: Readers | null;
  capabilities: ServerConfig["capabilities"];
  setFromConfig: (cfg: ServerConfig, models: ModelInfo[]) => void;
  /** Search the whole registry (every OpenRouter model), not just the curated list. */
  search: (q: string) => Promise<ModelInfo[]>;
}

export const useModelsStore = create<ModelsState>((set) => ({
  models: SAMPLE_MODELS,
  presets: { fast: "haiku", balanced: "sonnet", best: "opus" },
  providers: {},
  readers: null,
  capabilities: { codeSandbox: false, zipPassword: true, embeddings: false, webSearch: true },
  setFromConfig: (cfg, models) => set({ models, presets: cfg.qualityPresets, providers: cfg.providers, readers: cfg.readers, capabilities: cfg.capabilities }),
  search: async (q) => (isLive && q.trim() ? api.models(q.trim()) : []),
}));

// getModel() is used by pure domain code, so it reads the current list through this hook.
setModelSource(() => useModelsStore.getState().models);
