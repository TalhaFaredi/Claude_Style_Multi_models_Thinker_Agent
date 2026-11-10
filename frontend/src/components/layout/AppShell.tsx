"use client";

import { useCallback, useEffect, useState } from "react";
import { useServerEstimate } from "@/hooks/useEstimate";
import { API_URL, isLive } from "@/services/api";
import { bootstrap } from "@/services/bootstrap";
import { useChatStore } from "@/store/chatStore";
import { useSettingsStore } from "@/store/settingsStore";
import { DialogHost } from "../dialogs/DialogHost";
import { ToastHost } from "../ui/ToastHost";
import { Banners } from "./Banners";
import { Composer } from "./Composer";
import { Conversation } from "./Conversation";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

type Boot = "loading" | "ready" | "error";

function LiveSync() {
  useServerEstimate();
  const chatId = useChatStore((s) => s.chatId);
  const model = useChatStore((s) => s.simple.model);
  const refresh = useChatStore((s) => s.refreshContext);
  // the window meter depends on the chat and on the model's window size
  useEffect(() => { void refresh(); }, [chatId, model, refresh]);
  return null;
}

/** The one screen. Only the Setup dialog and the answer blocks change per mode. */
export function AppShell() {
  const [boot, setBoot] = useState<Boot>(isLive ? "loading" : "ready");
  const [error, setError] = useState("");

  const start = useCallback(async () => {
    setBoot("loading");
    try {
      // Saved preferences load after mount so the first paint matches the server HTML.
      if (!isLive) void useSettingsStore.persist.rehydrate();
      await useChatStore.persist.rehydrate();
      await bootstrap();
      setBoot("ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start");
      setBoot("error");
    }
  }, []);

  useEffect(() => { void start(); }, [start]);

  if (boot !== "ready") {
    return (
      <main className="boot" role="status">
        {boot === "loading" ? (
          <p>Connecting to the assistant...</p>
        ) : (
          <div className="card" role="alert" style={{ maxWidth: 520 }}>
            <span className="strong">Cannot reach the backend</span>
            <span>{error}</span>
            <span className="hint">Start it with <code>uvicorn app.main:app --port 8000</code> in the <code>backend</code> folder. The app expects it at {API_URL}.</span>
            <div className="row"><button type="button" className="btn primary" onClick={() => void start()}>Try again</button></div>
          </div>
        )}
      </main>
    );
  }

  return (
    <div className="app">
      {isLive && <LiveSync />}
      <Sidebar />
      <main className="main">
        <TopBar />
        <Conversation />
        <div className="dock">
          <Banners />
          <Composer />
        </div>
      </main>
      <DialogHost />
      <ToastHost />
    </div>
  );
}
