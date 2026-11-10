"use client";

import { BUDGET_CHOICES } from "@/domain/limits";
import { money } from "@/domain/format";
import { useEstimate } from "@/hooks/useEstimate";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";
import { Segmented } from "../ui/Segmented";

/** The cost link in the composer opens this: $0.05, $0.25 or $1 per question. */
export default function BudgetDialog() {
  const budget = useChatStore((s) => s.budget);
  const setBudget = useChatStore((s) => s.setBudget);
  const close = useUiStore((s) => s.close);
  const estimate = useEstimate();

  return (
    <Modal title="Budget per question" onClose={close} maxWidth={460} footer={<button type="button" className="btn primary" onClick={close}>Done</button>}>
      <ModalBody>
        <span>This question costs about <strong>{money(estimate)}</strong>. If a question would cost more than the budget, you are asked first.</span>
        <Segmented label="Budget per question" value={budget} onChange={setBudget} options={BUDGET_CHOICES.map((b) => ({ value: b, label: money(b) }))} />
      </ModalBody>
    </Modal>
  );
}
