"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type PromptCatalog } from "@/services/api";
import { useUiStore } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";

/** Shows shipped templates only. Runtime user content, files and secrets are never sent by this endpoint. */
export default function PromptDialog() {
  const open = useUiStore((s) => s.open);
  const [catalog, setCatalog] = useState<PromptCatalog | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    api.prompts().then((result) => {
      if (!current) return;
      setCatalog(result);
      setSelectedId(result.templates[0]?.id ?? "");
    }).catch((cause) => { if (current) setError(cause instanceof Error ? cause.message : "Could not load prompts"); });
    return () => { current = false; };
  }, []);
  const rows = useMemo(() => catalog?.templates.filter((item) => `${item.id} ${item.title} ${item.role}`.toLowerCase().includes(query.toLowerCase())) ?? [], [catalog, query]);
  const selected = catalog?.templates.find((item) => item.id === selectedId);
  return (
    <Modal title="System and agent prompts" onClose={() => open("setup")} maxWidth={760} footer={<button type="button" className="btn primary" onClick={() => open("setup")}>Back to setup</button>}>
      <ModalBody>
        <span className="hint">These are the backend's shipped prompt templates, version {catalog?.version ?? "loading"}. An agent's effective prompt combines templates with its role, your question and runtime context. Private chat/file content and tool results are not shown here.</span>
        {error && <span className="hint warn" role="alert">{error}</span>}
        {!catalog && !error && <span className="hint" role="status">Loading prompt templates...</span>}
        {catalog && <>
          <input className="input" aria-label="Search prompt templates" placeholder="Search by agent or role" value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="grid2">
            <div className="list" role="group" aria-label="Prompt templates">
              {rows.map((item) => <button key={item.id} type="button" className={`mrow${item.id === selectedId ? " on" : ""}`} aria-pressed={item.id === selectedId} onClick={() => setSelectedId(item.id)}><span className="mrow-main"><span className="strong">{item.title}</span><span className="hint">{item.role} - {item.id}</span></span></button>)}
              {rows.length === 0 && <span className="hint">No matching template.</span>}
            </div>
            <div className="card"><span className="strong">{selected?.title ?? "Select a template"}</span>{selected && <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit", fontSize: "0.85rem" }}>{selected.content}</pre>}</div>
          </div>
        </>}
      </ModalBody>
    </Modal>
  );
}
