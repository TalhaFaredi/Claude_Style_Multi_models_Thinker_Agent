"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, isLive, type ImportReport } from "@/services/api";
import { playSteps } from "@/services/timedSteps";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";
import { StepList, type StepDef } from "../ui/StepList";
import { money } from "@/domain/format";

const STEPS: StepDef[] = [
  { title: "Check the file", detail: "Format and checksums" },
  { title: "Treat as data", detail: "Text inside cannot change rules" },
  { title: "Reuse file readings", detail: "$0" },
  { title: "Load the chat", detail: "Word for word if it fits" },
];

/** Part 2 §8 import: check, treat as data, reuse readings, load, then a report. A bad file is refused and the broken part named (C43). */
export default function ImportDialog() {
  const step = useUiStore((s) => s.importStep);
  const importing = useUiStore((s) => s.importing);
  const setImport = useUiStore((s) => s.setImport);
  const close = useUiStore((s) => s.close);
  const openImported = useChatStore((s) => s.openImportedChat);
  const cancel = useRef<(() => void) | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState("");
  const [password, setPassword] = useState("");
  const [reindexing, setReindexing] = useState<string | null>(null);
  const [indexed, setIndexed] = useState<Record<string, string>>({});
  const [completeIndexes, setCompleteIndexes] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setImport(0, false);
    return () => cancel.current?.();
  }, [setImport]);

  const runMock = () => {
    setImport(0, true);
    cancel.current = playSteps(4, 700, (k) => setImport(k, true));
  };

  const runLive = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    setImport(1, true); // the server checks the format and every checksum first
    try {
      const r = await api.importChat(file, password || undefined);
      setReport(r);
      cancel.current = playSteps(3, 350, (k) => setImport(k + 1, true));
    } catch (e) {
      setImport(0, false);
      setError(e instanceof ApiError ? e.message : "Import failed");
    }
  };

  const done = step >= 4;
  const reindex = async (file: NonNullable<ImportReport["reindexFiles"]>[number]) => {
    if (!report) return;
    setReindexing(file.fingerprint);
    setError("");
    try {
      const result = await api.reindexFile(file.fingerprint, report.chatId, file.usd);
      setIndexed((prior) => ({ ...prior, [file.fingerprint]: result.complete ? `Ready. Actual cost ${money(result.cost)}.` : result.warning || "Keyword search remains ready." }));
      setCompleteIndexes((prior) => ({ ...prior, [file.fingerprint]: result.complete }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The meaning index could not be rebuilt. Keyword search remains available.");
    } finally {
      setReindexing(null);
    }
  };
  return (
    <Modal
      title="Import a chat"
      onClose={close}
      maxWidth={520}
      footer={
        <>
          <button type="button" className="btn" onClick={close}>Close</button>
          {!importing && !done && (
            <button type="button" className="btn primary" onClick={() => (isLive ? picker.current?.click() : runMock())}>{isLive ? "Choose a chat .zip" : "Choose chat_export.zip"}</button>
          )}
          {done && <button type="button" className="btn primary" onClick={() => openImported(report?.chatId)}>Open the chat</button>}
        </>
      }
    >
      <ModalBody>
        {isLive && <label className="field"><span className="field-label">Password (if the export is locked)</span><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" /></label>}
        <input ref={picker} type="file" accept=".zip" hidden onChange={(e) => void runLive(e.target.files?.[0])} />
        <StepList steps={STEPS} done={importing || done ? step : -1} />
        {error && <div className="card warn" role="alert"><span>{error}</span></div>}
        {done && (
          <div className="card green">
            <span>{report ? `${report.messages} messages, ${report.files} files, ${report.facts} facts restored. Reading cost $${report.readingCostUsd.toFixed(0)}.` : "142 messages, 3 files, 21 facts restored. Reading cost $0."}</span>
            {report?.warnings.map((w) => <span className="hint" key={w}>{w}</span>)}
            {report?.reindexFiles?.map((file) => (
              <div className="field" key={file.fingerprint}>
                <span>{file.name}: {file.model}</span>
                <span className="hint">Saved text and keyword search are ready. Rebuilding meaning search does not repeat OCR.</span>
                {indexed[file.fingerprint] && <span role="status">{indexed[file.fingerprint]}</span>}
                {!completeIndexes[file.fingerprint] && <button type="button" className="btn" disabled={!file.available || !!reindexing} onClick={() => void reindex(file)}>{reindexing === file.fingerprint ? "Rebuilding..." : `Rebuild meaning index (up to ${money(file.usd)})`}</button>}
                {!file.available && <span className="hint warn">{file.reason}</span>}
              </div>
            ))}
          </div>
        )}
      </ModalBody>
    </Modal>
  );
}
