"use client";

import { getModel } from "@/data/sample";
import type { CallUsageView } from "@/domain/events";
import { money, preciseMoney } from "@/domain/format";
import type { AiMessage } from "@/domain/messages";
import { Pill } from "../ui/Pill";

/** What each kind of model call is for, in plain words. The key is the backend's stage name. */
const JOBS: Record<string, string> = {
  router: "Safety check before answering",
  "router:safety": "Safety check, second opinion",
  answer: "Answer",
  "answer:retry": "Answer, rewritten after the quality check",
  checker: "Quality check of the answer",
  "memory:facts": "Memory: saving facts about you",
  "memory:ledger": "Memory: notes about this chat",
  "compact:summary": "Summarizing older messages",
  "compact:redo": "Summarizing older messages (second try)",
  "compact:ledger": "Summarizing: saving key details",
  "compact:merge": "Summarizing: merging summaries",
  "file:card": "File: writing its summary card",
  "file:ocr": "File: reading a scanned page",
  "file:chart": "File: describing a chart",
  "search:rewrite": "File search: rewording your question",
  "search:rerank": "File search: picking the best passages",
  plan: "Planner: writing the plan",
  step: "Planner: doing a step",
  "plan:assemble": "Planner: building the final result",
  "thinker:agent": "Thinker: an agent's answer",
  "thinker:change": "Thinker: an agent rethinks",
  "thinker:judge": "Thinker: checking if the agents agree",
  "thinker:compose": "Thinker: combining the answers",
};

export function jobLabel(stage: string): string {
  return JOBS[stage] ?? stage;
}

/** The registry name when the model is known, otherwise its id (never another model's name). */
export function modelName(id: string): string {
  const m = getModel(id);
  return m.id === id ? m.name : id;
}

/** The models the user chose for this answer: everything else is a small helper model the app picks for a side job. */
export function selectedModels(m: Pick<AiMessage, "kind" | "snapshot">): Set<string> {
  const { simple, team } = m.snapshot;
  const ids = new Set<string>([simple.model]);
  if (m.kind !== "simple") {
    for (const id of team.source === "same" ? [team.model] : team.mixed) ids.add(id);
    if (team.composer !== "auto") ids.add(team.composer);
  }
  return ids;
}

/** Every model call behind one answer: what it was for, which model, tokens and cost. Includes retries and helper calls. */
export function CallUsageSection({ m }: { m: AiMessage }) {
  const entries: CallUsageView[] = m.callUsages ?? [];
  const mine = selectedModels(m);
  const listed = entries.reduce((sum, e) => sum + e.usd, 0);
  // The answer's total is rounded to 6 decimals, so a tiny gap to the sum of the rows is rounding, not an extra charge.
  const total = m.costUsd - listed > 5e-6 ? m.costUsd : listed;
  return (
    <details className="card" style={{ marginTop: 10 }}>
      <summary>Cost of this answer: {money(total)} ({entries.length} model {entries.length === 1 ? "call" : "calls"})</summary>
      <p className="hint">
        Your selected {mine.size === 1 ? "model writes" : "models write"} the answer. Small, cheap helper models do the side jobs (safety check, quality check, memory).
        Every call is listed and counts toward your budget.
      </p>
      {entries.map((entry, index) => (
        <div className="mrow static" key={`${entry.stage}:${entry.label ?? ""}:${index}`}>
          <span className="mrow-main">
            <span className="strong">{jobLabel(entry.stage)}{entry.label ? ` (${entry.label})` : ""}</span>
            <span className="hint">
              {modelName(entry.model)} <Pill tone={mine.has(entry.model) ? "green" : undefined}>{mine.has(entry.model) ? "your model" : "helper"}</Pill>{" "}
              {entry.inTokens.toLocaleString()} tokens in, {entry.outTokens.toLocaleString()} out{entry.reasoningTokens ? ` (${entry.reasoningTokens.toLocaleString()} thinking)` : ""}
            </span>
            {!entry.ok && <span className="hint warn">Failed attempt{entry.estimated ? "; possible charge estimated" : ""}</span>}
          </span>
          <span className="strong">{preciseMoney(entry.usd)}{entry.estimated ? " estimated" : ""}</span>
        </div>
      ))}
      <div className="mrow static">
        <span className="mrow-main"><span className="strong">Total for this answer</span>
          {total > listed + 1e-9 && <span className="hint">Includes {preciseMoney(total - listed)} of file reading or search that is not a model call.</span>}
        </span>
        <span className="strong">{preciseMoney(total)}</span>
      </div>
    </details>
  );
}
