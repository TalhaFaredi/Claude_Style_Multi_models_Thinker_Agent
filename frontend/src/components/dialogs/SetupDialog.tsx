"use client";

import { getModel } from "@/data/sample";
import { teamCalls } from "@/domain/cost";
import { setupSentence } from "@/domain/describe";
import { money } from "@/domain/format";
import type { StepRunMode } from "@/domain/types";
import { useEstimate } from "@/hooks/useEstimate";
import { useChatStore } from "@/store/chatStore";
import { useModelsStore } from "@/store/modelsStore";
import { useUiStore } from "@/store/uiStore";
import { isLive } from "@/services/api";
import { Modal, ModalBody } from "../ui/Modal";
import { Segmented } from "../ui/Segmented";
import { SimpleSetup, modelCaps } from "./setup/SimpleSetup";
import { TeamSetup } from "./setup/TeamSetup";

const MODE_NAME = { auto: "Auto", simple: "Simple", thinker: "Thinker", planner: "Planner" } as const;

const RUN_HINT: Record<StepRunMode, string> = {
  auto: "Auto: easy steps run in Simple, hard steps use the team below.",
  simple: "Every step runs in Simple. No team, cheapest.",
  thinker: "Every step uses the team below. Best, costs most.",
};

/** Quality presets for Auto: which model, and how much it thinks. The model ids come from the registry. */
const THINKING_FOR = { fast: "off", balanced: "medium", best: "high" } as const;

/** Direct choices for the mode, plus one sentence saying what will happen. */
export default function SetupDialog() {
  const mode = useChatStore((s) => s.mode);
  const simple = useChatStore((s) => s.simple);
  const planModel = useChatStore((s) => s.planModel);
  const team = useChatStore((s) => s.team);
  const runIn = useChatStore((s) => s.runIn);
  const setRunIn = useChatStore((s) => s.setRunIn);
  const setModel = useChatStore((s) => s.setModel);
  const patchSimple = useChatStore((s) => s.patchSimple);
  const close = useUiStore((s) => s.close);
  const open = useUiStore((s) => s.open);
  const openPicker = useUiStore((s) => s.openModelPicker);
  const estimate = useEstimate();
  const presets = useModelsStore((s) => s.presets);
  const QUALITY = [
    { value: presets.fast, label: "Fast", thinking: THINKING_FOR.fast },
    { value: presets.balanced, label: "Balanced", thinking: THINKING_FOR.balanced },
    { value: presets.best, label: "Best", thinking: THINKING_FOR.best },
  ] as const;

  const showTeam = mode === "thinker" || (mode === "planner" && runIn !== "simple");
  const calls = mode === "thinker" ? teamCalls(team) : mode === "planner" && showTeam ? teamCalls(team) : null;

  return (
    <Modal
      title={`Set up ${MODE_NAME[mode]}`}
      onClose={close}
      footer={
        <>
          <span className="hint" style={{ marginRight: "auto" }}>
            About {money(estimate)} per question{calls ? ` · up to ${calls} model calls${mode === "planner" ? " per team step" : ""}` : ""}
          </span>
          <button type="button" className="btn primary" onClick={close}>Done</button>
        </>
      }
    >
      <ModalBody>
        <div className="card green">
          <span className="strong">What will happen</span>
          <span>{setupSentence(mode, simple, team, runIn, planModel)}</span>
        </div>

        {mode === "auto" && (
          <>
            <div className="field">
              <span className="field-label">Quality</span>
              <Segmented
                label="Quality"
                value={simple.model}
                options={QUALITY.map((q) => ({ value: q.value, label: q.label }))}
                onChange={(id) => { setModel(id); patchSimple({ thinking: QUALITY.find((q) => q.value === id)?.thinking ?? "medium" }); }}
              />
              <span className="hint">Fast: cheapest. Balanced: good and fair price. Best: strongest, costs most.</span>
            </div>
            <span className="hint">How Auto decides: chat and simple facts go to Simple, comparisons to Thinker, many steps or a file to Planner.</span>
          </>
        )}

        {mode === "simple" && <SimpleSetup />}

        {mode === "planner" && (
          <div className="grid2">
            <div className="field">
              <span className="field-label">Who writes the plan</span>
              <button type="button" className="btn" style={{ justifyContent: "flex-start" }} onClick={() => openPicker("plan")}>{getModel(planModel).name}</button>
              <span className="hint">{modelCaps(planModel)}</span>
              <span className="field-label">Model for Simple steps</span>
              <button type="button" className="btn" style={{ justifyContent: "flex-start" }} onClick={() => openPicker("main")}>{getModel(simple.model).name}</button>
            </div>
            <div className="field">
              <span className="field-label">How steps run</span>
              <Segmented
                label="How steps run"
                value={runIn}
                onChange={setRunIn}
                options={[{ value: "auto", label: "Auto" }, { value: "simple", label: "Simple" }, { value: "thinker", label: "Thinker" }]}
              />
              <span className="hint">{RUN_HINT[runIn]}</span>
            </div>
          </div>
        )}

        {showTeam && <TeamSetup heading={mode === "thinker" ? "Your team of agents" : "Team for the hard steps (Thinker)"} />}

        <span className="lock">Always on: risky tools ask first, max 10 tool calls, max 2 retries per step, max 2 re-plans, max 20 plan steps. Planner waits for your approval.</span>
        <button type="button" className="btn" disabled={!isLive} onClick={() => open("prompts")}>View system and agent prompt templates</button>
        {!isLive && <span className="hint">Connect the backend to inspect its current prompt templates.</span>}
      </ModalBody>
    </Modal>
  );
}
