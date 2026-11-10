"use client";

import { contextLevel } from "@/domain/context";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { isLive } from "@/services/api";

/** 70%: notice. 85%: alarm with Summarize, New chat, Download, Later (C35, C36). */
export function Banners() {
  const percent = useChatStore((s) => s.context);
  const snoozeAt = useChatStore((s) => s.snoozeAt);
  const compact = useChatStore((s) => s.compact);
  const newFromSummary = useChatStore((s) => s.newChatFromSummary);
  const snooze = useChatStore((s) => s.snooze);
  const open = useUiStore((s) => s.open);
  const level = contextLevel(percent);

  if (level === "notice") {
    return <div className="banner notice"><span>This chat is getting long ({percent}%). It will be summarized safely at 95%.</span></div>;
  }
  if ((level === "alarm" || level === "compact") && percent >= snoozeAt) {
    return (
      <div className="banner alarm" role="alert">
        <span className="strong">Chat is {percent}% full.</span>
        <button type="button" className="btn primary small" onClick={() => isLive ? open("context") : compact()}>Summarize now</button>
        <button type="button" className="btn small" onClick={() => isLive ? open("context") : void newFromSummary()}>New chat with summary</button>
        <button type="button" className="btn small" onClick={() => open("export")}>Download</button>
        <button type="button" className="btn ghost small" onClick={snooze}>Later</button>
      </div>
    );
  }
  return null;
}
