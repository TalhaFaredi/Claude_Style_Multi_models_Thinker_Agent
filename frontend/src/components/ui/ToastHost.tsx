"use client";

import { useUiStore } from "@/store/uiStore";

/** Short black toast after each action. */
export function ToastHost() {
  const text = useUiStore((s) => s.toast);
  return text ? <div className="toast" role="status">{text}</div> : null;
}
