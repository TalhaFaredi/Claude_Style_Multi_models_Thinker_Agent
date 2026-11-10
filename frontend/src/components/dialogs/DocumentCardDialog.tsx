"use client";

import { DEMO_FILES } from "@/data/sample";
import { money } from "@/domain/format";
import { isLive } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { useUiStore } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";

/** Document Card: pages, readers, cost, summary, outline, tables and charts with page numbers. It always stays in memory. */
export default function DocumentCardDialog() {
  const id = useUiStore((s) => s.cardFileId);
  const close = useUiStore((s) => s.close);
  const pending = useChatStore((s) => s.pending.find((p) => p.id === id));
  const removePending = useChatStore((s) => s.removePending);
  const mockFile = DEMO_FILES.find((f) => f.id === id);
  const card = pending?.card;

  return (
    <Modal
      title={pending?.name ?? "Document Card"}
      onClose={close}
      maxWidth={560}
      footer={
        <>
          <button type="button" className="btn" onClick={() => { removePending(id); close(); }}>Remove</button>
          <button type="button" className="btn primary" onClick={close}>Done</button>
        </>
      }
    >
      <ModalBody>
        <div className="kv">
          <div><span className="hint">Pages</span><br />{card?.pages ?? pending?.pages ?? mockFile?.pages ?? "-"}</div>
          <div><span className="hint">Reading cost</span><br />{pending ? money(pending.cost) : "-"}</div>
        </div>
        {isLive && card ? (
          <>
            {card.readers?.length ? <span className="hint">Readers used: {card.readers.join(", ")}</span> : null}
            {card.summary && <div className="field"><span className="field-label">Summary</span><span>{card.summary}</span></div>}
            {card.outline.length > 0 && (
              <div className="field">
                <span className="field-label">Outline</span>
                <ul style={{ margin: 0, paddingLeft: 18 }}>{card.outline.slice(0, 12).map((o, i) => <li key={i}>{o.title} <span className="hint">(p.{o.page})</span></li>)}</ul>
              </div>
            )}
            {card.tables.length > 0 && <span className="hint">Tables on pages {card.tables.slice(0, 20).join(", ")}</span>}
            {card.charts.length > 0 && (
              <div className="field">
                <span className="field-label">Charts</span>
                {card.charts.slice(0, 5).map((c) => <span key={c.page} className="hint">p.{c.page}: {c.description}</span>)}
              </div>
            )}
            {card.weakPages.length > 0 && <span className="hint warn">Pages that could not be fully read: {card.weakPages.slice(0, 20).join(", ")}</span>}
          </>
        ) : (
          <span className="hint">Document Card: [summary, outline and table list with page numbers]. It always stays in memory, so the file is never forgotten.</span>
        )}
      </ModalBody>
    </Modal>
  );
}
