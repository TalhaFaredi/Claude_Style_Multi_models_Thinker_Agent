import { create } from "zustand";
import { persist } from "zustand/middleware";
import { INITIAL_MEMORY } from "@/data/sample";
import type { MemoryFact, ReaderId } from "@/domain/types";
import { api, isLive, type ServerSettings } from "@/services/api";
import { safeStorage } from "./safeStorage";
import { toast } from "./uiStore";

/** Account-level settings (spec Part 3 §8). Saved at once, no hidden Save button. */
interface SettingsState {
  saveStatus: "saved" | "saving" | "error";
  promptCacheTtl: "5m" | "1h";
  reader: ReaderId;
  /** Ask before paying when one file costs more than this (USD). */
  askLimit: number;
  monthBudget: number;
  monthSpent: number;
  readingSpent: number;
  longMemory: boolean;
  autoCompact: boolean;
  tempChat: boolean;
  /** Describe charts with a vision model (max 300 tokens each, C27). */
  chartDescriptions: boolean;
  keepPageImages: boolean;
  /** Working window in tokens (live). Every turn re-sends the whole window, so bigger = costlier. */
  windowCap: number;
  /** Parse Cache (mock only): "fileId:reader" -> already read. The live server keeps the real one. */
  parseCache: Record<string, true>;
  memory: MemoryFact[];

  set: (patch: Partial<Omit<SettingsState, "set" | "addSpend" | "cacheReading" | "deleteFact" | "resetSafe" | "hydrateFromServer" | "loadMemory">>) => Promise<boolean>;
  addSpend: (usd: number) => void;
  cacheReading: (key: string) => void;
  deleteFact: (id: number) => Promise<boolean>;
  resetSafe: () => Promise<boolean>;
  hydrateFromServer: (s: ServerSettings, monthUsd: number, readingUsd?: number) => void;
  loadMemory: () => Promise<void>;
}

export const SAFE_DEFAULTS = { reader: "auto", askLimit: 0.5, monthBudget: 5, longMemory: true, autoCompact: true, tempChat: false, chartDescriptions: true, keepPageImages: true, windowCap: 32000, promptCacheTtl: "5m" } as const;
let settingsSave: Promise<unknown> = Promise.resolve();

/** Settings the server stores and uses. The rest (month spend, caches) are display state. */
const SERVER_KEYS = ["reader", "askLimit", "monthBudget", "longMemory", "autoCompact", "tempChat", "chartDescriptions", "keepPageImages", "windowCap", "promptCacheTtl"] as const;

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      saveStatus: "saved",
      promptCacheTtl: "5m",
      reader: "auto",
      askLimit: 0.5,
      monthBudget: 5,
      monthSpent: 1.2,
      readingSpent: 0,
      longMemory: true,
      autoCompact: true,
      tempChat: false,
      chartDescriptions: true,
      keepPageImages: true,
      windowCap: 32000,
      parseCache: {},
      memory: isLive ? [] : INITIAL_MEMORY,

      set: async (patch) => {
        const before = get();
        set({ ...patch, saveStatus: isLive ? "saving" : "saved" });
        if (isLive) {
          const body: Record<string, unknown> = {};
          for (const k of SERVER_KEYS) if (k in patch) body[k] = (patch as Record<string, unknown>)[k];
          if (Object.keys(body).length) {
            const task = settingsSave.then(() => api.putSettings(body));
            settingsSave = task.catch(() => undefined);
            try { await task; set({ saveStatus: "saved" }); }
            catch (e) {
              const rollback: Record<string, unknown> = {};
              for (const k of SERVER_KEYS) if (k in patch && get()[k] === patch[k]) rollback[k] = before[k];
              set({ ...rollback, saveStatus: "error" });
              toast(`Could not save the setting: ${e instanceof Error ? e.message : "Connection lost"}. Previous value restored.`);
              return false;
            }
          }
        }
        return true;
      },
      addSpend: (usd) => set((s) => ({ monthSpent: s.monthSpent + usd })),
      cacheReading: (key) => set((s) => ({ parseCache: { ...s.parseCache, [key]: true } })),
      deleteFact: async (id) => {
        if (isLive) {
          try { await api.deleteFact(id); }
          catch (e) { toast(e instanceof Error ? e.message : "Could not delete the memory"); return false; }
        }
        set((s) => ({ memory: s.memory.filter((f) => f.id !== id) }));
        return true;
      },
      resetSafe: () => get().set({ ...SAFE_DEFAULTS }),
      hydrateFromServer: (s, monthUsd, readingUsd = 0) => set({ ...s, promptCacheTtl: s.promptCacheTtl ?? "5m", monthSpent: monthUsd, readingSpent: readingUsd }),
      loadMemory: async () => {
        if (!isLive) return;
        try {
          const { facts } = await api.memory();
          set({ memory: facts.map((f) => ({ id: f.id, text: f.text, source: f.source })) });
        } catch {
          /* the Memory tab shows what it has */
        }
      },
    }),
    {
      name: "mma-settings",
      version: 1,
      storage: safeStorage(!isLive), // in live mode the server is the source of truth
      skipHydration: true, // rehydrated after mount to avoid a server/client mismatch
      partialize: ({ reader, askLimit, monthBudget, monthSpent, longMemory, autoCompact, tempChat, chartDescriptions, keepPageImages, windowCap, promptCacheTtl, parseCache, memory }) => ({
        reader, askLimit, monthBudget, monthSpent, longMemory, autoCompact, tempChat, chartDescriptions, keepPageImages, windowCap, promptCacheTtl, parseCache, memory,
      }),
    },
  ),
);
