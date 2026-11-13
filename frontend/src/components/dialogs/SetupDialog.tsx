"use client";

import { getModel } from "@/data/sample";
import { teamCalls } from "@/domain/cost";
import { setupSentence } from "@/domain/describe";
import { money } from "@/domain/format";
import type { StepRunMode } from "@/domain/types";
import { useEstimate } from "@/hooks/useEstimate";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { isLive } from "@/services/api";
import { Modal, ModalBody } from "../ui/Modal";
import { Segmented } from "../ui/Segmented";
import { SimpleSetup, modelCaps } from "./setup/SimpleSetup";
import { TeamSetup } from "./setup/TeamSetup";

const MODE_NAME = { simple: "Simple", thinker: "Thinker", planner: "Planner" } as const;

const RUN_HINT: Record<StepRunMode, string> = {
  auto: "One model does the easy steps; the team below does the hard ones. A good balance.",
  simple: "One model does every step. No team. Cheapest.",
  thinker: "The team below does every step. Most thorough, costs the most.",
};

/** Direct choices for the mode, plus one sentence saying what will happen. */
export default function SetupDialog() {
  const mode = useChatStore((s) => s.mode);
  const simple = useChatStore((s) => s.simple);
  const planModel = useChatStore((s) => s.planModel);
  const team = useChatStore((s) => s.team);
  const runIn = useChatStore((s) => s.runIn);
  const setRunIn = useChatStore((s) => s.setRunIn);
  const close = useUiStore((s) => s.close);
  const open = useUiStore((s) => s.open);
  const openPicker = useUiStore((s) => s.openModelPicker);
  const estimate = useEstimate();
  const showTeam = mode === "thinker" || (mode === "planner" && runIn !== "simple");
  const calls = mode === "thinker" ? teamCalls(team) : mode === "planner" && showTeam ? teamCalls(team) : null;

  return (
    <Modal
      title={`Set up ${MODE_NAME[mode]}`}
      onClose={close}
      footer={
        <>
          <span className="hint" style={{ marginRight: "auto" }}>
            Estimated cost: about {money(estimate)} per question{calls ? ` · up to ${calls} model calls${mode === "planner" ? " per team step" : ""}` : ""}
          </span>
          <button type="button" className="btn primary" onClick={close}>Done</button>
        </>
      }
    >
      <ModalBody>
        <div className="card green">
          <span className="strong">What will happen when you send</span>
          <span>{setupSentence(mode, simple, team, runIn, planModel)}</span>
        </div>

        {mode === "simple" && <SimpleSetup />}

        {mode === "planner" && (
          <div className="grid2">
            <div className="field">
              <span className="field-label">Model that writes the plan</span>
              <button type="button" className="btn" style={{ justifyContent: "flex-start" }} onClick={() => openPicker("plan")}>{getModel(planModel).name}</button>
              <span className="hint">{modelCaps(planModel)}</span>
              <span className="field-label">Model that does the steps</span>
              <button type="button" className="btn" style={{ justifyContent: "flex-start" }} onClick={() => openPicker("main")}>{getModel(simple.model).name}</button>
            </div>
            <div className="field">
              <span className="field-label">Who does the steps</span>
              <Segmented
                label="Who does the steps"
                value={runIn}
                onChange={setRunIn}
                options={[{ value: "simple", label: "One model" }, { value: "auto", label: "Mixed" }, { value: "thinker", label: "Team" }]}
              />
              <span className="hint">{RUN_HINT[runIn]}</span>
            </div>
          </div>
        )}

        {showTeam && <TeamSetup heading={mode === "thinker" ? "Your team of agents" : runIn === "thinker" ? "Team that does every step" : "Team for the hard steps"} />}

        <span className="lock">Always on: risky tools ask first, max 10 tool calls, max 2 retries per step, max 2 re-plans, max 20 plan steps. Planner waits for your approval.</span>
        <button type="button" className="btn" disabled={!isLive} onClick={() => open("prompts")}>View system and agent prompt templates</button>
        {!isLive && <span className="hint">Connect the backend to inspect its current prompt templates.</span>}
      </ModalBody>
    </Modal>
  );
}
