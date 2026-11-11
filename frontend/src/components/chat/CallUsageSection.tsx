"use client";

import type { CallUsageView } from "@/domain/events";
import { preciseMoney } from "@/domain/format";

/** Individual settled provider attempts, including retries and estimated charges. */
export function CallUsageSection({ entries }: { entries: CallUsageView[] }) {
  return <details className="card" style={{ marginTop: 10 }}>
    <summary>Cost of each model call ({entries.length})</summary>
    <p className="hint">This is the model-call breakdown. The answer's total can also include routing, retrieval or memory work.</p>
    {entries.map((entry, index) => <div className="mrow static" key={`${entry.stage}:${entry.label ?? ""}:${index}`}>
      <span className="mrow-main">
        <span className="strong">{entry.label ? `${entry.label} - ` : ""}{entry.model}</span>
        <span className="hint">{entry.stage} - {entry.inTokens.toLocaleString()} input + {entry.outTokens.toLocaleString()} output tokens{entry.reasoningTokens ? ` (${entry.reasoningTokens.toLocaleString()} reasoning)` : ""}</span>
        {!entry.ok && <span className="hint warn">Failed attempt{entry.estimated ? "; possible charge estimated" : ""}</span>}
      </span>
      <span className="strong">{preciseMoney(entry.usd)}{entry.estimated ? " estimated" : ""}</span>
    </div>)}
  </details>;
}
