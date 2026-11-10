"use client";

import { useState } from "react";
import { plannerCost } from "@/domain/cost";
import type { StepStatus } from "@/domain/events";
import { money } from "@/domain/format";
import type { AiMessage } from "@/domain/messages";
import { useChatStore } from "@/store/chatStore";
import { Pill } from "../ui/Pill";

const LABEL: Record<StepStatus, string> = {
  planned: "Planned", planning: "Planning", waiting: "Waiting", running: "Running", checking: "Checking", retry: "Retry", done: "Done", failed: "Failed",
};

const numClass = (s: StepStatus) => (s === "done" ? " done" : s === "retry" || s === "failed" ? " retry" : s === "running" || s === "checking" ? " run" : "");

/** Numbered steps with task, mode, status pill; Approve / Edit / Cancel while waiting (F10, C15). */
export function PlanCard({ m }: { m: AiMessage }) {
  const approve = useChatStore((s) => s.approvePlan);
  const edit = useChatStore((s) => s.editPlan);
  const stop = useChatStore((s) => s.stop);
  const useTeam = useChatStore((s) => s.useTeamForStep);
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [sentVersion, setSentVersion] = useState<string | null>(null);
  if (!m.plan) return null;
  const { phase, steps, awaitingApproval } = m.plan;
  // the server's estimate includes every team step; the local formula is the mock fallback
  const cost = m.plan.estimateUsd ?? plannerCost(m.snapshot.runIn, m.snapshot.team);
  const version = m.plan.version ?? m.plan.phase;
  const controlState = `${version}:${phase}:${steps.map((step) => step.status).join(",")}`;
  const pending = busy || sentVersion === controlState;
  const submit = async (action: () => Promise<boolean>) => {
    setBusy(true);
    try { if (await action()) { setSentVersion(controlState); setEditing(false); setNote(""); } }
    finally { setBusy(false); }
  };

  return (
    <div className="card">
      <div className="row"><span className="strong">Plan</span><Pill>{phase}</Pill></div>
      {steps.map((st, i) => (
        <div className="step" key={`${i}-${st.task}`}>
          <span className={`step-num${numClass(st.status)}`}>{i + 1}</span>
          <div className="step-body">
            <span className="strong">{st.task}</span>
            <span className="hint">{st.modeLabel}</span>
            {st.kind && <span className="hint">{st.kind === "tool" ? "Tool step" : st.kind === "hard" ? "Hard step" : "Easy step"}</span>}
            {st.doneTest && <span className="hint">Done when: {st.doneTest}</span>}
            {st.note && <span className={st.noteTone === "warn" ? "hint warn" : "hint"}>{st.note}</span>}
            {st.canUseTeam && <button type="button" className="btn small" disabled={pending} onClick={() => void submit(() => useTeam(m.id, i))}>Use the team for step {i + 1}</button>}
          </div>
          <Pill tone={st.status === "done" ? "green" : st.status === "retry" || st.status === "failed" ? "warn" : "neutral"}>{LABEL[st.status]}</Pill>
        </div>
      ))}
      {m.controlError && <span className="hint warn" role="alert">{m.controlError}. Your plan is still waiting; try again.</span>}
      {!awaitingApproval && steps.some((step) => step.canUseTeam) && <button type="button" className="btn ghost" onClick={stop}>Cancel this plan</button>}
      {m.plan.overBudget && <div className="card warn" role="alert"><span>This plan costs about {money(cost)}, above the remaining {money(m.plan.remainingBudgetUsd ?? 0)} budget.</span><button type="button" className="btn small" disabled={pending} onClick={() => void submit(() => edit("Use fewer agents and one round to fit the remaining budget"))}>Use fewer agents and rounds</button><span className="hint">Or edit the plan to use fewer team steps or cheaper models.</span></div>}
      {awaitingApproval && !editing && (
        <div className="row">
          <button type="button" className="btn primary" disabled={pending || m.plan.overBudget} onClick={() => void submit(approve)}>{pending ? "Waiting for the plan update..." : "Approve and run"}</button>
          <button type="button" className="btn" disabled={pending} onClick={() => setEditing(true)}>Edit</button>
          <button type="button" className="btn ghost" onClick={stop}>Cancel</button>
          <span className="hint">About {money(cost)} · nothing runs before you approve</span>
        </div>
      )}
      {awaitingApproval && editing && (
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (note.trim()) void submit(() => edit(note.trim())); }}>
          <label className="grow">
            <span className="sr-only">What should change in the plan?</span>
            <input className="input" autoFocus placeholder="What should change? e.g. make it shorter, add a step for sources" value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <button type="submit" className="btn primary" disabled={pending || !note.trim()}>{pending ? "Updating..." : "Re-plan"}</button>
          <button type="button" className="btn ghost" onClick={() => setEditing(false)}>Back</button>
        </form>
      )}
    </div>
  );
}
