"use client";

import { useState } from "react";
import { Icon } from "../ui/Icon";

interface Props {
  notes: string[];
  live: boolean;
  /** Simple shows "Thought for 4 seconds"; teams and plans show "How this was built". */
  simple: boolean;
  /** Real thinking time from the server, when known. */
  seconds?: number | null;
}

/** Collapsed line that opens to short reasoning notes. Open state is local to this block. */
export function ThinkingSection({ notes, live, simple, seconds }: Props) {
  const [open, setOpen] = useState(false);
  const label = live ? "Thinking..." : simple ? `Thought for ${seconds ?? 4} seconds` : "How this was built";
  return (
    <>
      <button type="button" className="toggle-line" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <Icon name="chevronRight" size={14} />
        {label}
      </button>
      {open && (
        <div className="think">
          {notes.map((n) => <span key={n}>{n}</span>)}
        </div>
      )}
    </>
  );
}
