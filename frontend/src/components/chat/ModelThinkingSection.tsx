"use client";

import type { ModelThinkingView } from "@/domain/events";

/** Provider-exposed notes only; unsupported or withheld details stay explicitly unavailable. */
export function ModelThinkingSection({ entries }: { entries: ModelThinkingView[] }) {
  return <details className="card" style={{ marginTop: 12 }}>
    <summary>Thinking details by model ({entries.length})</summary>
    <p className="hint">These notes appear only when a provider includes reasoning in its response. A model may think internally without returning any details.</p>
    {entries.map((entry, index) => <div className="mrow static" key={`${entry.stage}:${entry.label ?? ""}:${index}`}>
      <span className="mrow-main">
        <span className="strong">{entry.label ? `${entry.label} - ` : ""}{entry.model}</span>
        <span className="hint">{entry.stage}</span>
        {entry.available && entry.notes.length > 0 ? entry.notes.map((note, i) => <span key={i}>{note}</span>) : <span className="hint">No thinking details provided by model.</span>}
      </span>
    </div>)}
  </details>;
}
