"use client";

import { getModel } from "@/data/sample";
import { money } from "@/domain/format";
import type { AiMessage } from "@/domain/messages";
import { api, isLive } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { toast } from "@/store/uiStore";

/** Model or team, calls, cost; Copy, Good, Bad; and "Ask a team" under a Simple answer. */
export function MetaLine({ m }: { m: AiMessage }) {
  const thinkDeeper = useChatStore((s) => s.thinkDeeper);
  const who = m.clarify ? "Helper model" : m.kind === "simple" ? getModel(m.snapshot.simple.model).name : m.kind === "thinker" ? `${m.agents.length || m.snapshot.team.agents} agents` : `${m.plan?.steps.length ?? 0} steps`;
  const cost = m.calls > 0 || m.costUsd > 0 ? ` · ${m.calls} model ${m.calls === 1 ? "call" : "calls"} · cost ${money(m.costUsd)}` : "";

  const copy = async () => {
    try { await navigator.clipboard.writeText(m.text); toast("Copied"); } catch { toast("Could not copy"); }
  };
  // Ratings are saved with the message, so problems can be found later (spec: "Logs and Feedback")
  const rate = (value: 1 | -1) => {
    if (!isLive) { toast("Thanks, rating saved"); return; }
    api.rate(m.id, value).then(() => toast("Thanks, rating saved")).catch(() => toast("Could not save the rating"));
  };

  return (
    <div className="foot">
      <span>{who}{cost}{isLive ? "" : " · sample cost"}</span>
      <button type="button" className="btn ghost small" onClick={copy}>Copy</button>
      <button type="button" className="btn ghost small" onClick={() => rate(1)}>Good</button>
      <button type="button" className="btn ghost small" onClick={() => rate(-1)}>Bad</button>
      {m.kind === "simple" && m.status === "done" && !m.clarify && (
        <button type="button" className="btn small" title="Ask the same question in Thinker mode: several models answer and one combines them" onClick={() => thinkDeeper(m.id)}>Ask a team instead</button>
      )}
    </div>
  );
}
