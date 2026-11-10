import { useEffect, useMemo } from "react";
import { estimateCost } from "@/domain/cost";
import { api, isLive } from "@/services/api";
import { useChatStore } from "@/store/chatStore";

/**
 * Cost estimate for the next question, shown next to Send ("costs in sight").
 * Live: the server's number, built from real prices and this chat's real context size.
 * Mock, or while the server is answering: the local formula.
 */
export function useEstimate(): number {
  const mode = useChatStore((s) => s.mode);
  const simple = useChatStore((s) => s.simple);
  const team = useChatStore((s) => s.team);
  const runIn = useChatStore((s) => s.runIn);
  const server = useChatStore((s) => s.serverEstimate);
  const local = useMemo(() => estimateCost({ mode, simple, team, runIn }), [mode, simple, team, runIn]);
  return isLive && server != null ? server : local;
}

/** Keeps `serverEstimate` fresh: re-asks the server (debounced) when anything that changes the price changes. */
export function useServerEstimate(): void {
  const mode = useChatStore((s) => s.mode);
  const simple = useChatStore((s) => s.simple);
  const team = useChatStore((s) => s.team);
  const runIn = useChatStore((s) => s.runIn);
  const chatId = useChatStore((s) => s.chatId);
  const draft = useChatStore((s) => s.draft);
  const messageCount = useChatStore((s) => s.messages.length);
  const filesCount = useChatStore((s) => s.pending.length);
  const planModel = useChatStore((s) => s.planModel);
  const set = useChatStore((s) => s.setServerEstimate);

  useEffect(() => {
    if (!isLive) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.estimate({ mode, chatId, prompt: draft, simple, team, runIn, planModel }, controller.signal)
        .then((r) => set(r.usd))
        .catch(() => undefined); // keep the last number; the local formula covers an unreachable server
    }, 450);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [mode, simple, team, runIn, planModel, chatId, draft, messageCount, filesCount, set]);
}
