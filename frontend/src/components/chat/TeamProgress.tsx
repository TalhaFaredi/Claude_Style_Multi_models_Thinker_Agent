"use client";

import { useState } from "react";
import { teamLine } from "@/domain/describe";
import type { AiMessage } from "@/domain/messages";

/** One progress line; "Show agents" opens one card per agent. */
export function TeamProgress({ m }: { m: AiMessage }) {
  const [open, setOpen] = useState(false);
  const total = m.agents.length;
  const ready = m.agents.filter((a) => a.status === "ready").length;
  const finished = m.status === "done";
  const roundText = finished ? `All ${total} agents finished` : m.roundText ? `${m.roundText} · ${ready} of ${total} ready` : "Starting the agents";

  return (
    <>
      <div className="progress">
        <span className="dot" />
        <span className="strong">{teamLine(m.snapshot.team)}</span>
        <span className="hint">{roundText}</span>
        <div className="grow" />
        <button type="button" className="btn ghost small" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? "Hide agents" : "Show agents"}
        </button>
      </div>
      {open && (
        <div className="agents">
          {m.agents.map((a) => (
            <div key={a.role} className={`agent${a.status === "ready" ? " done" : ""}`}>
              <span className="agent-role">{a.role}</span>
              <span className="hint">{a.model}</span>
              <span className="status"><span className="dot" />{a.status === "ready" ? "Ready" : a.status === "revising" ? "Revising" : "Thinking"}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
