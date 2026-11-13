"use client";

import { memo } from "react";
import { money } from "@/domain/format";
import { checkCanSend, teamGuardText } from "@/domain/guardrails";
import { useEstimate } from "@/hooks/useEstimate";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { Icon } from "../ui/Icon";
import { Pill } from "../ui/Pill";

function FileChips() {
  const pending = useChatStore((s) => s.pending);
  const openCard = useUiStore((s) => s.openCard);
  const remove = useChatStore((s) => s.removePending);
  if (pending.length === 0) return null;
  return (
    <div className="row">
      {pending.map((f) => (
        <span key={f.id} className="fchip">
          <button type="button" className="fchip-open" onClick={() => f.status === "ready" && openCard(f.id)} aria-label={`Open Document Card for ${f.name}`}>
            {f.name}
            <Pill tone={f.status === "ready" ? "green" : "neutral"}>{f.status === "ready" ? "Ready" : "Reading..."}</Pill>
          </button>
          {f.status === "ready" && <button type="button" className="fchip-x" aria-label={`Remove ${f.name}`} onClick={() => remove(f.id)}>x</button>}
        </span>
      ))}
    </div>
  );
}

/** File chips, message box (Enter sends, Shift+Enter new line), Attach, cost link, Send or Stop. */
export const Composer = memo(function Composer() {
  const draft = useChatStore((s) => s.draft);
  const mode = useChatStore((s) => s.mode);
  const team = useChatStore((s) => s.team);
  const runIn = useChatStore((s) => s.runIn);
  const running = useChatStore((s) => s.running);
  const preparing = useChatStore((s) => s.preparing);
  const budget = useChatStore((s) => s.budget);
  const setDraft = useChatStore((s) => s.setDraft);
  const send = useChatStore((s) => s.send);
  const stop = useChatStore((s) => s.stop);
  const open = useUiStore((s) => s.open);
  const estimate = useEstimate();

  const guard = teamGuardText(mode, team, runIn);
  const canSend = checkCanSend(draft, mode, team, runIn).ok;

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="composer">
      <FileChips />
      <label style={{ display: "block" }}>
        <span className="sr-only">Message</span>
        <textarea
          className="ta"
          placeholder={mode === "planner" ? "Describe the goal. You approve the plan first." : "Message the assistant"}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </label>
      <div className="row">
        <button type="button" className="iconbtn" aria-label="Attach a file" onClick={() => open("file")}><Icon name="paperclip" size={18} /></button>
        <button type="button" className="costlink" onClick={() => open("budget")}>Estimated cost about {money(estimate)} · limit {money(budget)} per question</button>
        <div className="grow" />
        {guard && <span className="hint warn">{guard}</span>}
        {running ? (
          <button type="button" className="btn dark" onClick={stop}>Stop</button>
        ) : (
          <button type="button" className="btn primary" disabled={!canSend || preparing} onClick={() => void send()}>{preparing ? "Checking cost..." : "Send"}</button>
        )}
      </div>
    </div>
  );
});
