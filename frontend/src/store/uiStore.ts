import { create } from "zustand";

export type DialogId =
  | "setup"
  | "models"
  | "budget"
  | "file"
  | "card"
  | "cost"
  | "context"
  | "compact"
  | "export"
  | "import"
  | "settings"
  | "deleteChat";

/** Which setting the model picker is choosing a model for. */
export type PickTarget = "main" | "plan" | "team" | "mixed" | "composer";
export type SettingsTab = "files" | "memory" | "data";

interface UiState {
  dialog: DialogId | null;
  pickTarget: PickTarget;
  settingsTab: SettingsTab;
  cardFileId: string;
  /** Chat the delete dialog is asking about (C42). */
  deleteChatId: string;
  toast: string;
  /** 0 to 4: progress of the "Summarizing safely" dialog. */
  compactStep: number;
  /** 0 to 4: progress of the import dialog. */
  importStep: number;
  importing: boolean;

  open: (dialog: DialogId) => void;
  close: () => void;
  openModelPicker: (target: PickTarget) => void;
  openCard: (fileId: string) => void;
  openDeleteChat: (chatId: string) => void;
  openSettings: (tab?: SettingsTab) => void;
  setSettingsTab: (tab: SettingsTab) => void;
  setCompactStep: (step: number) => void;
  setImport: (step: number, importing: boolean) => void;
  showToast: (text: string) => void;
}

let toastTimer: ReturnType<typeof setTimeout> | undefined;

export const useUiStore = create<UiState>((set) => ({
  dialog: null,
  pickTarget: "main",
  settingsTab: "files",
  cardFileId: "",
  deleteChatId: "",
  toast: "",
  compactStep: 0,
  importStep: 0,
  importing: false,

  open: (dialog) => set({ dialog }),
  close: () => set({ dialog: null }),
  openModelPicker: (pickTarget) => set({ dialog: "models", pickTarget }),
  openCard: (cardFileId) => set({ dialog: "card", cardFileId }),
  openDeleteChat: (deleteChatId) => set({ dialog: "deleteChat", deleteChatId }),
  openSettings: (tab = "files") => set({ dialog: "settings", settingsTab: tab }),
  setSettingsTab: (settingsTab) => set({ settingsTab }),
  setCompactStep: (compactStep) => set({ compactStep }),
  setImport: (importStep, importing) => set({ importStep, importing }),
  showToast: (text) => {
    set({ toast: text });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => set({ toast: "" }), 2600);
  },
}));

/** Shortcut for non-component code (stores, services). */
export const toast = (text: string) => useUiStore.getState().showToast(text);
