"use client";

import { EXAMPLES } from "@/data/sample";
import type { Mode } from "@/domain/types";
import { useChatStore } from "@/store/chatStore";
import { isLive } from "@/services/api";
import { Pill } from "../ui/Pill";

const MODE_CARDS: { mode: Mode; title: string; text: string }[] = [
  { mode: "simple", title: "Simple", text: "One model answers. Fastest and cheapest. Best for questions and short tasks." },
  { mode: "thinker", title: "Thinker", text: "Several models answer, then one combines them. Best for decisions and comparisons." },
  { mode: "planner", title: "Planner", text: "Writes a plan you approve, then does it step by step. Best for reports and files." },
];

/** Greeting, the three mode cards, examples. */
export function EmptyState() {
  const mode = useChatStore((s) => s.mode);
  const setMode = useChatStore((s) => s.setMode);
  const setDraft = useChatStore((s) => s.setDraft);

  return (
    <>
      <h1 className="hello">What should we work on?</h1>
      <div className="modes">
        {MODE_CARDS.map((c) => (
          <button key={c.mode} type="button" className={`modecard${mode === c.mode ? " on" : ""}`} aria-pressed={mode === c.mode} onClick={() => setMode(c.mode)}>
            <span className="strong">{c.title}</span>
            <span className="hint">{c.text}</span>
          </button>
        ))}
      </div>
      {EXAMPLES.map((e) => (
        <button key={e.text} type="button" className="example" onClick={() => { setMode(e.mode.toLowerCase() as Mode); setDraft(e.text); }}>
          <span style={{ marginRight: 8 }}><Pill>{e.mode}</Pill></span>{e.text}
        </button>
      ))}
      <p className="hint" style={{ textAlign: "center", margin: 0 }}>
        {isLive ? "You choose the mode and the model. The model you pick writes the answer, and the cost is shown before and after every question." : "Prototype: answers, models and prices are samples."}
      </p>
    </>
  );
}
