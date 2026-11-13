"use client";

import { getModel } from "@/data/sample";
import type { AnswerStyle, ThinkingLevel, ToolId } from "@/domain/types";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { useModelsStore } from "@/store/modelsStore";
import { Segmented } from "../../ui/Segmented";

const THINKING: ThinkingLevel[] = ["off", "low", "medium", "high"];
const STYLES: { value: AnswerStyle; label: string }[] = [
  { value: "precise", label: "Precise" },
  { value: "balanced", label: "Balanced" },
  { value: "creative", label: "Creative" },
];
const TOOLS: { id: ToolId; label: string }[] = [
  { id: "web", label: "Web search" },
  { id: "code", label: "Code" },
  { id: "files", label: "Files" },
];

export function modelCaps(id: string): string {
  const m = getModel(id);
  return [m.tools ? "Tools" : "No tools", m.vision ? "Vision" : "No vision", m.thinking ? "Thinking" : "No thinking"].join(" · ");
}

/** Model, thinking level, answer style (temperature), tools. Controls grey out with a reason (F4, F6). */
export function SimpleSetup() {
  const simple = useChatStore((s) => s.simple);
  const patchSimple = useChatStore((s) => s.patchSimple);
  const openPicker = useUiStore((s) => s.openModelPicker);
  const model = getModel(simple.model);
  const sandbox = useModelsStore((s) => s.capabilities.codeSandbox);

  return (
    <div className="grid2">
      <div className="field">
        <span className="field-label">Model that answers</span>
        <button type="button" className="btn" style={{ justifyContent: "flex-start" }} onClick={() => openPicker("main")}>{model.name}</button>
        <span className="hint">{modelCaps(simple.model)}</span>
      </div>

      <div className="field">
        <span className="field-label">Thinking before answering</span>
        <Segmented
          label="Thinking level"
          value={simple.thinking}
          onChange={(thinking) => patchSimple({ thinking })}
          options={THINKING.map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1), disabled: !model.thinking && v !== "off" }))}
        />
        {model.thinking ? <span className="hint">More thinking gives better answers to hard questions, and costs more.</span> : <span className="hint warn">This model cannot think step by step.</span>}
      </div>

      <div className="field">
        <span className="field-label">Answer style</span>
        <Segmented label="Answer style" value={simple.style} onChange={(style) => patchSimple({ style })} options={STYLES} />
        <span className="hint">Precise: sticks to facts. Creative: more varied wording and ideas.</span>
      </div>

      <div className="field">
        <label className="field-label" htmlFor="max-answer-length">Longest answer allowed (tokens)</label>
        <input id="max-answer-length" className="input" type="number" min={256} max={8192} step={256} value={simple.maxTokens ?? 1200} onChange={(e) => patchSimple({ maxTokens: Math.max(256, Math.min(8192, Number(e.target.value) || 1200)) })} />
        <span className="hint">About {Math.round(((simple.maxTokens ?? 1200) * 0.75) / 50) * 50} words. A higher limit can cost more.</span>
      </div>

      <div className="field">
        <span className="field-label">Tools it may use</span>
        <div className="row">
          {TOOLS.map((t) => {
            const on = simple.tools[t.id] && model.tools;
            return (
              <button
                key={t.id}
                type="button"
                className={`seg-btn${on ? " on" : ""}${!model.tools ? " dis" : ""}`}
                style={{ border: "1px solid var(--line-strong)" }}
                aria-pressed={on}
                disabled={!model.tools || (t.id === "code" && !sandbox)}
                onClick={() => patchSimple({ tools: { ...simple.tools, [t.id]: !simple.tools[t.id] } })}
              >
                {t.label}
              </button>
            );
          })}
        </div>
        {!model.tools && <span className="hint warn">This model has no tools.</span>}
        {!sandbox && <span className="hint">Code sandbox is unavailable on this server.</span>}
      </div>
    </div>
  );
}
