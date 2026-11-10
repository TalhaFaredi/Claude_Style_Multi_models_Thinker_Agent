"use client";

import dynamic from "next/dynamic";
import { useUiStore, type DialogId } from "@/store/uiStore";

/**
 * Each dialog is its own lazy chunk: it downloads the first time it opens,
 * so the first page load only ships the chat screen.
 */
const DIALOGS: Record<DialogId, React.ComponentType> = {
  setup: dynamic(() => import("./SetupDialog"), { ssr: false }),
  models: dynamic(() => import("./ModelPickerDialog"), { ssr: false }),
  budget: dynamic(() => import("./BudgetDialog"), { ssr: false }),
  file: dynamic(() => import("./FileDialog"), { ssr: false }),
  card: dynamic(() => import("./DocumentCardDialog"), { ssr: false }),
  cost: dynamic(() => import("./CostDialog"), { ssr: false }),
  context: dynamic(() => import("./ContextDialog"), { ssr: false }),
  compact: dynamic(() => import("./CompactDialog"), { ssr: false }),
  export: dynamic(() => import("./ExportDialog"), { ssr: false }),
  import: dynamic(() => import("./ImportDialog"), { ssr: false }),
  settings: dynamic(() => import("./SettingsDialog"), { ssr: false }),
  deleteChat: dynamic(() => import("./DeleteChatDialog"), { ssr: false }),
};

export function DialogHost() {
  const id = useUiStore((s) => s.dialog);
  if (!id) return null;
  const Dialog = DIALOGS[id];
  return <Dialog />;
}
