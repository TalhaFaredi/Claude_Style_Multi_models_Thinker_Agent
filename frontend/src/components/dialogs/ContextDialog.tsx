"use client";

import { contextBreakdown } from "@/domain/context";
import { money } from "@/domain/format";
import { useEstimate } from "@/hooks/useEstimate";
import { isLive } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";

/** Parts of the window with bars, the 70/85/95 levels and the price of the next message. */
export default function ContextDialog() {
  const percent = useChatStore((s) => s.context);
  const info = useChatStore((s) => s.contextInfo);
  const compact = useChatStore((s) => s.compact);
  const newFromSummary = useChatStore((s) => s.newChatFromSummary);
  const open = useUiStore((s) => s.open);
  const budget = useChatStore((s) => s.budget);
  const loading = useChatStore((s) => s.loadingChat);
  const estimate = useEstimate();
  // Live: the server's real parts and token counts. Mock: a sample split.
  const parts = isLive && info ? info.parts : contextBreakdown(percent);

  return (
    <Modal
      title={`Memory window ${percent}% full`}
      onClose={() => useUiStore.getState().close()}
      maxWidth={560}
      footer={
        <>
          <button type="button" className="btn" onClick={() => open("export")}>Download</button>
          <button type="button" className="btn" disabled={loading} onClick={() => void newFromSummary()}>{isLive ? `New chat with summary (up to ${money(budget)})` : "New chat with summary"}</button>
          <button type="button" className="btn primary" disabled={loading} onClick={compact}>{isLive ? `Summarize (up to ${money(budget)})` : "Summarize now"}</button>
        </>
      }
    >
      <ModalBody>
        {isLive && info && (
          <span className="hint">
            {info.usedTokens.toLocaleString()} of {info.usableTokens.toLocaleString()} usable tokens (window {info.windowTokens.toLocaleString()}, 15% kept free for the answer).
          </span>
        )}
        {parts.map((p) => (
          <div key={p.label} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div className="row"><span>{p.label}</span><div className="grow" /><span className="hint">{p.percent}%{"tokens" in p && p.tokens ? ` · ${p.tokens.toLocaleString()} tokens` : ""}</span></div>
            <div className="mini-bar"><div style={{ width: `${Math.min(100, p.percent)}%` }} /></div>
          </div>
        ))}
        <span className="hint">
          Next message: about {money(estimate)}
          {isLive && info?.nextMessageCachedUsd != null ? ` for the window alone: ${money(info.nextMessageUsd ?? 0)}, or ${money(info.nextMessageCachedUsd)} when the provider's prompt cache applies` : " (the cached part costs less, since every turn sends the whole window again)"}.
        </span>
        <span className="hint">Notice at 70%, alarm at 85%, safe summary at 95%. 15% is kept free for the answer. Summarizing keeps every original message.</span>
        {isLive && <span className="hint">A summary or continuation may use models. Each action stops at the displayed cap. Close this dialog to cancel.</span>}
      </ModalBody>
    </Modal>
  );
}
