"use client";

import { READERS } from "@/data/sample";
import { money } from "@/domain/format";
import { ASK_LIMIT_CHOICES, MONTH_BUDGET_CHOICES } from "@/domain/limits";
import { useModelsStore } from "@/store/modelsStore";
import { useSettingsStore } from "@/store/settingsStore";
import { Segmented } from "../ui/Segmented";
import { Switch } from "../ui/Switch";

/** Who reads your files, and when to ask before paying (Part 2 §4). Readers the server cannot run are greyed with the reason. */
export function FilesTab() {
  const reader = useSettingsStore((s) => s.reader);
  const askLimit = useSettingsStore((s) => s.askLimit);
  const monthBudget = useSettingsStore((s) => s.monthBudget);
  const readingSpent = useSettingsStore((s) => s.readingSpent);
  const chartDescriptions = useSettingsStore((s) => s.chartDescriptions);
  const keepPageImages = useSettingsStore((s) => s.keepPageImages);
  const set = useSettingsStore((s) => s.set);
  const availability = useModelsStore((s) => s.readers);

  return (
    <>
      <span className="hint">Who reads your files. You only pay for pages that need it, and see the price first.</span>
      <span className={readingSpent >= .8 * monthBudget ? "hint warn" : "hint"} role="status">Reading this month: {money(readingSpent)} of {money(monthBudget)}{readingSpent >= monthBudget ? ". Budget reached; choose a free reader or increase the budget." : readingSpent >= .8 * monthBudget ? " (over 80%)" : ""}</span>
      {READERS.map((r) => {
        const a = availability?.[r.id];
        const off = a ? !a.available : false;
        return (
          <button key={r.id} type="button" className={`mrow${reader === r.id ? " on" : ""}${off ? " off" : ""}`} aria-pressed={reader === r.id} disabled={off} onClick={() => set({ reader: r.id })}>
            <span className="mrow-main">
              <span className="strong">{r.name}</span>
              <span className="hint">{r.text}</span>
              {off && <span className="hint warn">{a?.reason}</span>}
            </span>
            <span className="hint">{r.cost}</span>
          </button>
        );
      })}
      <div className="field">
        <span className="field-label">Ask me before paying more than</span>
        <Segmented label="Ask limit" value={askLimit} onChange={(v) => set({ askLimit: v })} options={ASK_LIMIT_CHOICES.map((v) => ({ value: v, label: money(v) }))} />
      </div>
      <div className="field">
        <span className="field-label">Monthly budget (warns at 80%)</span>
        <Segmented label="Monthly budget" value={monthBudget} onChange={(v) => set({ monthBudget: v })} options={MONTH_BUDGET_CHOICES.map((v) => ({ value: v, label: `$${v}` }))} />
      </div>
      <Switch label="Describe charts (written description, page image kept)" checked={chartDescriptions} onChange={(v) => set({ chartDescriptions: v })} />
      <Switch label="Keep page images" checked={keepPageImages} onChange={(v) => set({ keepPageImages: v })} />
    </>
  );
}
