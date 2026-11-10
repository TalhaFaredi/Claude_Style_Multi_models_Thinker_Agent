"use client";

import { useUiStore } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";
import { StepList, type StepDef } from "../ui/StepList";

const STEPS: StepDef[] = [
  { title: "Pick old messages", detail: "Not pinned, not the last 10" },
  { title: "Save the facts", detail: "Into the numbered ledger" },
  { title: "Write a summary", detail: "With message numbers" },
  { title: "Check, then swap", detail: "Every number, name and date kept" },
];

/** Part 2 §7. No close button: the checked summary must finish before anything is swapped. */
export default function CompactDialog() {
  const step = useUiStore((s) => s.compactStep);
  return (
    <Modal title="Summarizing safely" maxWidth={520}>
      <ModalBody><StepList steps={STEPS} done={step} /></ModalBody>
    </Modal>
  );
}
