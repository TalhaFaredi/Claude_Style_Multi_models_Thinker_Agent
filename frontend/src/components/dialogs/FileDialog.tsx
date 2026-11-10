"use client";

import { useState } from "react";
import { DEMO_FILES, READERS } from "@/data/sample";
import { fileReadingCost, fileRouteRows } from "@/domain/cost";
import { money } from "@/domain/format";
import { isOverAskLimit } from "@/domain/guardrails";
import { useChatStore } from "@/store/chatStore";
import { useSettingsStore } from "@/store/settingsStore";
import { useUiStore } from "@/store/uiStore";
import { isLive } from "@/services/api";
import LiveFileDialog from "./LiveFileDialog";
import { Modal, ModalBody } from "../ui/Modal";
import { Pill } from "../ui/Pill";

/**
 * Attach a file (Figure 6): every page is checked for free and shown by type with its reader and cost.
 * Same file + same reader as before = saved reading reused for $0.
 */
function MockFileDialog() {
  const close = useUiStore((s) => s.close);
  const attachFile = useChatStore((s) => s.attachFile);
  const reader = useSettingsStore((s) => s.reader);
  const askLimit = useSettingsStore((s) => s.askLimit);
  const cache = useSettingsStore((s) => s.parseCache);
  const [selected, setSelected] = useState<string | null>(null);

  const file = DEMO_FILES.find((f) => f.id === selected);

  if (!file) {
    return (
      <Modal title="Add a file" onClose={close}>
        <ModalBody>
          <span className="hint">Demo files (in the real app: file picker or drag and drop).</span>
          {DEMO_FILES.map((f) => (
            <button key={f.id} type="button" className="mrow" onClick={() => setSelected(f.id)}>
              <span className="mrow-main"><span className="strong">{f.name}</span><span className="hint">{f.pages} pages</span></span>
              {cache[`${f.id}:${reader}`] && <Pill tone="green">Read before · $0</Pill>}
            </button>
          ))}
        </ModalBody>
      </Modal>
    );
  }

  const seen = !!cache[`${file.id}:${reader}`];
  const cost = fileReadingCost(file, reader);
  const over = isOverAskLimit(cost, askLimit);
  const readerName = READERS.find((r) => r.id === reader)?.name ?? reader;
  const unreadable = reader === "text" && (file.scan > 0 || file.chart > 0);

  return (
    <Modal
      title={file.name}
      onClose={close}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={() => setSelected(null)}>Back</button>
          {!seen && <button type="button" className="btn" onClick={() => attachFile(file.id, true)}>Text only (free)</button>}
          <button type="button" className="btn primary" onClick={() => attachFile(file.id, false)}>{seen ? "Attach ($0)" : `Read file (${money(cost)})`}</button>
        </>
      }
    >
      <ModalBody>
        {seen ? (
          <div className="card green"><span>Read before with the same reader. The saved reading is reused: <strong>$0</strong>.</span></div>
        ) : (
          <>
            <span className="hint">Pages checked for free. Reader: {readerName} (change in Settings).</span>
            {fileRouteRows(file, reader).map((r) => (
              <div className="mrow static" key={r.label}>
                <span className="mrow-main"><span className="strong">{r.label}</span><span className="hint">{r.reader}</span></span>
                <span className="strong">{money(r.cost)}</span>
              </div>
            ))}
            <div className="row">
              <span className="strong">Total about {money(cost)}</span>
              {over && <Pill tone="warn">Over your {money(askLimit)} ask-me limit</Pill>}
            </div>
            {unreadable && <span className="hint warn">Some pages cannot be read with Text only.</span>}
          </>
        )}
      </ModalBody>
    </Modal>
  );
}

export default function FileDialog() {
  return isLive ? <LiveFileDialog /> : <MockFileDialog />;
}
