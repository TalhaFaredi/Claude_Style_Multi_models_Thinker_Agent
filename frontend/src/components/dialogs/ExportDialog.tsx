"use client";

import { useState } from "react";
import { api, isLive } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { useModelsStore } from "@/store/modelsStore";
import { toast, useUiStore } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";
import { Switch } from "../ui/Switch";

const PARTS = [
  ["manifest.json", "format version, models used, a checksum for every part"],
  ["messages.jsonl", "every message word for word"],
  ["ledger, summaries, memories", "with dates and sources"],
  ["files/ and readings/", "original files (optional) and saved readings"],
  ["transcript.md", "a plain copy for people to read"],
];

function save(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Part 2 §8: everything the chat knows, in one .zip. */
export default function ExportDialog() {
  const close = useUiStore((s) => s.close);
  const chatId = useChatStore((s) => s.chatId);
  const canLock = useModelsStore((s) => s.capabilities.zipPassword);
  const [includeFiles, setIncludeFiles] = useState(false);
  const [locked, setLocked] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const download = async () => {
    if (!isLive) { close(); toast("Download started (demo)"); return; }
    setBusy(true);
    try {
      const blob = await api.exportChat(chatId, includeFiles, locked ? password : undefined);
      save(blob, `chat_${chatId}.zip`);
      close();
      toast("Download started");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Download this chat"
      onClose={close}
      maxWidth={520}
      footer={
        <>
          <button type="button" className="btn" onClick={close}>Cancel</button>
          <button type="button" className="btn primary" disabled={busy || (locked && !password)} onClick={() => void download()}>{busy ? "Preparing..." : "Download .zip"}</button>
        </>
      }
    >
      <ModalBody>
        <span>One .zip with the messages, memory and file readings. Import it anywhere to continue here, with no reading cost.</span>
        <ul className="hint" style={{ margin: 0, paddingLeft: 18 }}>
          {PARTS.map(([name, text]) => <li key={name}><strong>{name}</strong>: {text}</li>)}
        </ul>
        <Switch label="Include original files" checked={includeFiles} onChange={setIncludeFiles} />
        {canLock ? (
          <>
            <Switch label="Lock with a password" checked={locked} onChange={setLocked} />
            {locked && <input className="input" type="password" aria-label="Password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />}
          </>
        ) : (
          <span className="hint">Password lock is not available on this server (no AES zip support installed).</span>
        )}
      </ModalBody>
    </Modal>
  );
}
