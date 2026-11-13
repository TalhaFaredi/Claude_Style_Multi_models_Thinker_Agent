"use client";

import { money } from "@/domain/format";
import { useEstimate } from "@/hooks/useEstimate";
import { toast, useUiStore } from "@/store/uiStore";
import { useChatStore } from "@/store/chatStore";
import { useModelsStore } from "@/store/modelsStore";
import { getModel } from "@/data/sample";
import { Modal, ModalBody } from "../ui/Modal";
import { oneQuestionCap } from "@/domain/guardrails";

/** F7: opened before anything is spent when the estimate is over the budget. */
export default function CostDialog() {
  const mode = useChatStore((s) => s.mode);
  const budget = useChatStore((s) => s.budget);
  const setModel = useChatStore((s) => s.setModel);
  const patchTeam = useChatStore((s) => s.patchTeam);
  const close = useUiStore((s) => s.close);
  const estimate = useEstimate();
  const cheap = useModelsStore((s) => s.presets.fast);
  const single = mode === "simple";

  const makeCheaper = () => {
    if (single) setModel(cheap);
    else patchTeam({ source: "same", model: cheap, agents: 3, rounds: 1 });
    close();
    toast("Cheaper setup chosen. Press Send.");
  };

  const allowOnce = () => {
    useChatStore.getState().allowThisOnce();
    close();
    useChatStore.getState().send();
  };

  return (
    <Modal title="Over your budget" onClose={close} maxWidth={520} footer={<button type="button" className="btn" onClick={close}>Cancel</button>}>
      <ModalBody>
        <span>About <strong>{money(estimate)}</strong>, budget <strong>{money(budget)}</strong>. Nothing is spent yet.</span>
        <button type="button" className="mrow" onClick={makeCheaper}>
          <span className="mrow-main">
            <span className="strong">Make it cheaper</span>
            <span className="hint">{single ? `Switch to ${getModel(cheap).name}` : `Use 3 copies of ${getModel(cheap).name}, 1 round`}</span>
          </span>
        </button>
        <button type="button" className="mrow" disabled={estimate > 50} onClick={allowOnce}>
          <span className="mrow-main">
            <span className="strong">Allow up to {money(oneQuestionCap(estimate, budget))} once</span>
            <span className="hint">{estimate > 50 ? "Choose a cheaper setup: the estimate exceeds the maximum $50 question cap." : "This question stops at that cap. Your saved budget stays the same."}</span>
          </span>
        </button>
      </ModalBody>
    </Modal>
  );
}
