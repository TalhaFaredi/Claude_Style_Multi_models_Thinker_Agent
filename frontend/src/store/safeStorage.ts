import { createJSONStorage } from "zustand/middleware";

/**
 * localStorage that never breaks the app: it is missing on the server and can be blocked in
 * private windows. zustand catches an error thrown from this getter and runs without
 * persistence, so the app still works; it just forgets preferences.
 * Pass `enabled = false` to switch persistence off (account settings live on the server in live mode).
 */
export const safeStorage = <T>(enabled = true) =>
  createJSONStorage<T>(() => {
    if (!enabled || typeof window === "undefined") throw new Error("persistence is off here");
    return window.localStorage;
  });
