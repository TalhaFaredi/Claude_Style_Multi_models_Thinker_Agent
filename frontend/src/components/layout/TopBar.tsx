"use client";

import { memo } from "react";
import { meterClass } from "@/domain/context";
import { setupLabel } from "@/domain/describe";
import type { Mode } from "@/domain/types";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { Icon } from "../ui/Icon";
import { Pill } from "../ui/Pill";
import { Segmented } from "../ui/Segmented";

const MODES: { value: Mode; label: string }[] = [
  { value: "simple", label: "Simple" },
  { value: "thinker", label: "Thinker" },
  { value: "planner", label: "Planner" },
];

function ModeSwitch() {
  const mode = useChatStore((s) => s.mode);
  const running = useChatStore((s) => s.running || s.preparing);
  const setMode = useChatStore((s) => s.setMode);
  // F9: locked while an answer runs, with a dark pill saying so.
  return <Segmented label="Mode" options={MODES} value={mode} onChange={setMode} disabled={running} />;
}

function SetupButton() {
  const mode = useChatStore((s) => s.mode);
  const simple = useChatStore((s) => s.simple);
  const team = useChatStore((s) => s.team);
  const runIn = useChatStore((s) => s.runIn);
  const open = useUiStore((s) => s.open);
  const preparing = useChatStore((s) => s.preparing);
  return (
    <button type="button" className="btn" disabled={preparing} aria-label="Set up this mode" title="Change the model and options for this mode" onClick={() => open("setup")}>
      <span className="dot" />
      <span>{setupLabel(mode, simple, team, runIn)}</span>
      <Icon name="chevronDown" size={14} />
    </button>
  );
}

function ContextMeter() {
  const percent = useChatStore((s) => s.context);
  const open = useUiStore((s) => s.open);
  return (
    <button type="button" className="meter" aria-label={`Memory window ${percent}% full, open details`} onClick={() => open("context")}>
      <span className="hint" style={{ color: "var(--ink)" }}>Memory {percent}%</span>
      <span className="bar"><span className={`bar-fill ${meterClass(percent)}`} style={{ width: `${percent}%` }} /></span>
    </button>
  );
}

export const TopBar = memo(function TopBar() {
  const running = useChatStore((s) => s.running);
  return (
    <header className="topbar">
      <ModeSwitch />
      <SetupButton />
      <div className="grow" />
      {running && <Pill tone="dark">Working, mode locked</Pill>}
      <ContextMeter />
    </header>
  );
});
