"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { money } from "@/domain/format";
import { isOverAskLimit } from "@/domain/guardrails";
import { parsePageSelection } from "@/domain/pages";
import type { ReaderId } from "@/domain/types";
import { api, ApiError, type UploadedFile } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { useModelsStore } from "@/store/modelsStore";
import { useSettingsStore } from "@/store/settingsStore";
import { useUiStore } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";
import { Pill } from "../ui/Pill";

const READER_NAMES = { auto: "Auto (recommended)", text: "Text only", local: "Local open-source", api: "OCR API", vision: "Vision model" } as const;
const ACCEPT = ".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.json,.py,.js,.ts,.html,.png,.jpg,.jpeg,.webp";

/**
 * Attach a real file (Part 2 section 3). The upload is fingerprinted and every page is checked for free; you see
 * the price per page type BEFORE any paid reader runs. A file read before costs $0.
 */
export default function LiveFileDialog() {
  const close = useUiStore((s) => s.close);
  const chatId = useChatStore((s) => s.chatId);
  const attach = useChatStore((s) => s.attachLiveFile);
  const reader = useSettingsStore((s) => s.reader);
  const askLimit = useSettingsStore((s) => s.askLimit);
  const readingSpent = useSettingsStore((s) => s.readingSpent);
  const monthBudget = useSettingsStore((s) => s.monthBudget);
  const availability = useModelsStore((s) => s.readers);
  const [file, setFile] = useState<UploadedFile | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [choice, setChoice] = useState<ReaderId>(reader);
  const [pageText, setPageText] = useState("");
  const [readingEstimate, setReadingEstimate] = useState<Awaited<ReturnType<typeof api.readEstimate>> | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [estimateKey, setEstimateKey] = useState("");
  const selection = useMemo(() => parsePageSelection(pageText, file?.pages ?? 0), [pageText, file?.pages]);
  const queryKey = `${file?.fingerprint}:${choice}:${pageText}`;
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    setError("");
    if (!file || selection.error || (choice === reader && !pageText.trim() && !file.readBefore[choice])) { setReadingEstimate(null); setEstimating(false); return; }
    let current = true;
    setEstimating(true);
    const timer = setTimeout(() => {
      api.readEstimate(file.fingerprint, { chatId, reader: choice, pages: selection.pages }).then((estimate) => { if (current) { setReadingEstimate(estimate); setEstimateKey(queryKey); setError(""); } }).catch((e) => { if (current) setError(e instanceof Error ? e.message : "Could not estimate the selected pages"); }).finally(() => { if (current) setEstimating(false); });
    }, 250);
    return () => { current = false; clearTimeout(timer); };
  }, [file, choice, reader, selection, pageText, chatId, queryKey]);

  const choose = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true);
    setError("");
    try {
      setFile(await api.upload(chatId, f));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  if (!file) {
    return (
      <Modal title="Add a file" onClose={close}>
        <ModalBody>
          <span className="hint">PDF, Word, PowerPoint, Excel, CSV, text, code or an image. Up to 25 MB. Pages are checked for free before anything is paid.</span>
          <div
            className="dropzone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); void choose(e.dataTransfer.files[0]); }}
          >
            <button type="button" className="btn primary" disabled={busy} onClick={() => input.current?.click()}>{busy ? "Checking pages..." : "Choose a file"}</button>
            <span className="hint">or drop it here</span>
            <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => void choose(e.target.files?.[0])} />
          </div>
          {error && <span className="hint warn" role="alert">{error}</span>}
        </ModalBody>
      </Modal>
    );
  }

  const plan = readingEstimate ?? file.plans[choice];
  const readerInfo = (availability ?? file.readers)[choice];
  const cached = file.readBefore[choice];
  const seen = !!cached && (selection.pages ? selection.pages.every((p) => cached.complete || cached.pagesRead?.includes(p)) : cached.complete !== false);
  const estimateReady = (choice === reader && !pageText.trim() && !cached) || estimateKey === queryKey;
  const monthBlocked = readingSpent >= monthBudget && plan.total > 0 && !seen;
  const over = isOverAskLimit(plan.total, askLimit);
  const unreadable = choice === "text" && (file.kinds.scan > 0 || file.kinds.chart > 0);
  const blocked = !readerInfo.available && !seen;

  return (
    <Modal
      title={file.name}
      onClose={close}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={() => setFile(null)}>Back</button>
          {!seen && choice !== "text" && <button type="button" className="btn" disabled={!!selection.error} onClick={() => void attach(file, true, 0, choice, selection.pages)}>Text only (free)</button>}
          <button type="button" className="btn primary" disabled={blocked || monthBlocked || estimating || !estimateReady || !!selection.error || !!error} onClick={() => void attach(file, false, plan.total + 1e-6, choice, selection.pages)}>
            {seen ? "Attach ($0)" : `Read file (${money(plan.total)})`}
          </button>
        </>
      }
    >
      <ModalBody>
        {readingSpent >= .8 * monthBudget && <span className="hint warn" role="alert">Reading this month: {money(readingSpent)} of {money(monthBudget)}{monthBlocked ? ". Budget reached. Use Text only or change the budget in Settings." : " (over 80%)."}</span>}
        <div className="grid2"><label className="field"><span className="field-label">Reader for this file</span><select className="input" value={choice} onChange={(e) => setChoice(e.target.value as ReaderId)}>{(Object.keys(READER_NAMES) as ReaderId[]).map((id) => <option key={id} value={id} disabled={!(availability ?? file.readers)[id].available}>{READER_NAMES[id]}</option>)}</select></label><label className="field"><span className="field-label">Pages to read (blank means all)</span><input className="input" placeholder="e.g. 1-3, 7" value={pageText} onChange={(e) => setPageText(e.target.value)} /></label></div>
        {(selection.error || error) && <span className="hint warn" role="alert">{selection.error || error}</span>}
        {estimating && <span className="hint" role="status">Checking the cost of these pages...</span>}
        <div className="kv">
          <div><span className="hint">Pages</span><br />{file.pages}</div>
          <div><span className="hint">Normal / scanned / charts</span><br />{file.kinds.text} / {file.kinds.scan} / {file.kinds.chart}</div>
        </div>
        {seen ? (
          <div className="card green"><span>Read before with the same reader. The saved reading is reused: <strong>$0</strong>.</span></div>
        ) : (
          <>
            <span className="hint">Pages checked for free. Reader: {READER_NAMES[choice]}. {selection.pages ? `${selection.pages.length} pages selected.` : "All pages selected."}</span>
            {plan.rows.map((r) => (
              <div className="mrow static" key={r.label}>
                <span className="mrow-main"><span className="strong">{r.label}</span><span className="hint">{r.reader}</span></span>
                <span className="strong">{r.expectedCost !== undefined ? <><span className="hint">Expected {money(r.expectedCost)} · </span>up to {money(r.cost)}</> : money(r.cost)}</span>
              </div>
            ))}
            <div className="row">
              <span className="strong">Approved maximum {money(plan.total)}</span>
              {over && <Pill tone="warn">Over your {money(askLimit)} ask-me limit</Pill>}
            </div>
            {unreadable && <span className="hint warn">Scanned and chart pages cannot be read with Text only.</span>}
            {over && <span className="hint warn">Choose a cheaper reader, select fewer pages, use Text only, or approve the displayed cost with Read file.</span>}
          </>
        )}
        {blocked && <span className="hint warn" role="alert">{readerInfo.reason}. Pick another reader in Settings.</span>}
      </ModalBody>
    </Modal>
  );
}
