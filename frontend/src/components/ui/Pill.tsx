import type { ReactNode } from "react";

type Tone = "neutral" | "green" | "warn" | "dark";

/** State is always shown as text, never by colour alone (spec Part 3 §10). */
export function Pill({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`pill${tone === "neutral" ? "" : ` ${tone}`}`}>{children}</span>;
}
