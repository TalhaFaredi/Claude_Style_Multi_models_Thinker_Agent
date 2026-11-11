"use client";

import type { AiMessage } from "@/domain/messages";
import { useChatStore } from "@/store/chatStore";
import { AnswerHeader } from "./AnswerHeader";
import { MetaLine } from "./MetaLine";
import { OutputCard } from "./OutputCard";
import { PlanCard } from "./PlanCard";
import { TeamProgress } from "./TeamProgress";
import { ThinkingSection } from "./ThinkingSection";
import { ToolChip } from "./ToolChip";
import { PermissionCard } from "./PermissionCard";
import { ComposerCard } from "./ComposerCard";
import { Markdown } from "./Markdown";
import { ModelThinkingSection } from "./ModelThinkingSection";
import { CallUsageSection } from "./CallUsageSection";

/** One assistant answer. Which blocks appear depends on the mode and what the server has sent so far. */
export function AnswerBlock({ m }: { m: AiMessage }) {
  const retry = useChatStore((s) => s.retry);
  const live = m.status === "live";
  const paragraphs = m.text ? m.text.split(/\n\n/) : [];
  const showThinking = m.thinkingNotes.length > 0;

  return (
    <article className={`ai${live ? " live" : ""}`} aria-label="Assistant answer">
      <AnswerHeader m={m} />
      {showThinking && <ThinkingSection notes={m.thinkingNotes} live={live && !m.text} simple={m.kind === "simple"} seconds={m.thoughtSeconds} />}
      {(m.modelThinking?.length ?? 0) > 0 && <ModelThinkingSection entries={m.modelThinking ?? []} />}
      {m.kind === "simple" && m.tool && <ToolChip label={m.tool.label} />}
      {m.kind === "thinker" && <TeamProgress m={m} />}
      {m.composer && <ComposerCard composer={m.composer} />}
      {m.permission && <PermissionCard message={m} />}
      {m.kind === "planner" && <PlanCard m={m} />}
      {m.kind === "planner" && m.output && <OutputCard file={m.output} />}

      {paragraphs.length > 0 && (
        <div className="answer">
          <Markdown text={m.text} />
          {m.citations.length > 0 && <div>{m.citations.map((c) => <span className="cite" key={c}>{c}</span>)}</div>}
        </div>
      )}

      {m.warning && <div className="card warn" role="status"><span>{m.warning}</span></div>}
      {m.status === "stopped" && <div className="card warn"><span>Stopped. What was done is kept.</span></div>}
      {(m.status === "error" || m.status === "offline") && (
        <div className="card warn" role="alert">
          <span>{m.status === "offline" ? "Connection lost. Your message is kept as a draft." : "Something went wrong:"} {m.error ?? "unknown error"}</span>
          <div className="row"><button type="button" className="btn small" onClick={() => retry(m.id)}>Retry</button></div>
        </div>
      )}
      {(m.status === "done" || m.status === "stopped") && <MetaLine m={m} />}
      {(m.callUsages?.length ?? 0) > 0 && <CallUsageSection entries={m.callUsages ?? []} />}
    </article>
  );
}
