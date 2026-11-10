"use client";

import { getModel } from "@/data/sample";
import { mixedStrengthWarning } from "@/domain/guardrails";
import type { TeamSource, TeamStyle } from "@/domain/types";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { Stepper } from "../../ui/Stepper";

interface Choice<T> { value: T; title: string; text: string }

const SOURCES: Choice<TeamSource>[] = [
  { value: "same", title: "Same model", text: "Copies of one model. Each copy gets a role: Solver, Critic, Fact-checker..." },
  { value: "mixed", title: "Different models", text: "Each agent is a different model, so you get more varied views." },
];
const STYLES: Choice<TeamStyle>[] = [
  { value: "independent", title: "On their own", text: "Each agent answers alone. Nobody sees the others. Faster, cheaper." },
  { value: "together", title: "Together (debate)", text: "Each writes a draft, then they read each other and improve it, round by round." },
];

function Cards<T extends string>({ items, value, onPick }: { items: Choice<T>[]; value: T; onPick: (v: T) => void }) {
  return (
    <div className="presets">
      {items.map((c) => (
        <button key={c.value} type="button" className={`preset${c.value === value ? " on" : ""}`} aria-pressed={c.value === value} onClick={() => onPick(c.value)}>
          <span className="strong">{c.title}</span>
          <span className="hint">{c.text}</span>
        </button>
      ))}
    </div>
  );
}

/** The five team settings (spec Part 1 §7), shared by Thinker and Planner team steps. */
export function TeamSetup({ heading }: { heading: string }) {
  const team = useChatStore((s) => s.team);
  const patchTeam = useChatStore((s) => s.patchTeam);
  const stepAgentCount = useChatStore((s) => s.stepAgentCount);
  const stepRoundCount = useChatStore((s) => s.stepRoundCount);
  const openPicker = useUiStore((s) => s.openModelPicker);
  const warning = mixedStrengthWarning(team);

  return (
    <div className="card">
      <span className="strong">{heading}</span>

      <div className="field">
        <span className="field-label">Which models?</span>
        <Cards items={SOURCES} value={team.source} onPick={(source) => patchTeam({ source })} />
        {team.source === "same" ? (
          <div className="row">
            <button type="button" className="btn small" onClick={() => openPicker("team")}>Model: {getModel(team.model).name}</button>
            <span className="hint">Copies:</span>
            <Stepper value={team.agents} onDown={() => stepAgentCount(-1)} onUp={() => stepAgentCount(1)} downLabel="Fewer agents" upLabel="More agents" />
            <span className="hint">2 to 5</span>
          </div>
        ) : (
          <div className="row">
            <button type="button" className="btn small" onClick={() => openPicker("mixed")}>Pick models ({team.mixed.length} chosen)</button>
            <span className="hint">{team.mixed.map((id) => getModel(id).name).join(", ")}</span>
          </div>
        )}
        {warning && <span className="hint warn" role="alert">{warning}</span>}
      </div>

      <div className="field">
        <span className="field-label">How do they think?</span>
        <Cards items={STYLES} value={team.style} onPick={(style) => patchTeam({ style })} />
        {team.style === "together" && (
          <div className="row">
            <span className="hint">Rounds:</span>
            <Stepper value={team.rounds} onDown={() => stepRoundCount(-1)} onUp={() => stepRoundCount(1)} downLabel="Fewer rounds" upLabel="More rounds" />
            <span className="hint">1 to 3, stops early if they agree</span>
          </div>
        )}
      </div>

      <div className="field">
        <span className="field-label">Who writes the final answer?</span>
        <button type="button" className="btn small" style={{ alignSelf: "flex-start" }} onClick={() => openPicker("composer")}>
          {team.composer === "auto" ? "Auto (strongest in budget)" : getModel(team.composer).name}
        </button>
      </div>
    </div>
  );
}
