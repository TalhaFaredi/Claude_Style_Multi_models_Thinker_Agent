"use client";

import { EXAMPLES } from "@/data/sample";
import type { Mode } from "@/domain/types";
import { useChatStore } from "@/store/chatStore";
import { isLive } from "@/services/api";
import { Pill } from "../ui/Pill";

const MODE_CARDS: { mode: Mode; title: string; text: string }[] = [
  { mode: "auto", title: "Auto", text: "Picks the mode for you" },
  { mode: "simple", title: "Simple", text: "One model, fast" },
  { mode: "thinker", title: "Thinker", text: "A team of agents" },
  { mode: "planner", title: "Planner", text: "Plans and checks big tasks" },
];

/** Greeting, 4 mode cards, examples. */
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
        <button key={e.text} type="button" className="example" onClick={() => setDraft(e.text)}>
          <span style={{ marginRight: 8 }}><Pill>{e.mode}</Pill></span>{e.text}
        </button>
      ))}
      <p className="hint" style={{ textAlign: "center", margin: 0 }}>{isLive ? "Live: real models and real prices. Cost is shown before every question." : "Prototype: answers, models and prices are samples."}</p>
    </>
  );
}
