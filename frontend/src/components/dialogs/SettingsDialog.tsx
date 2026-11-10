"use client";

import { useUiStore, type SettingsTab } from "@/store/uiStore";
import { useSettingsStore } from "@/store/settingsStore";
import { DataTab } from "../settings/DataTab";
import { FilesTab } from "../settings/FilesTab";
import { MemoryTab } from "../settings/MemoryTab";
import { Modal, ModalBody } from "../ui/Modal";

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "files", label: "Files" },
  { id: "memory", label: "Memory" },
  { id: "data", label: "Data and safety" },
];

/** Changes save at once and the footer says so; there is no hidden Save button to forget. */
export default function SettingsDialog() {
  const tab = useUiStore((s) => s.settingsTab);
  const setTab = useUiStore((s) => s.setSettingsTab);
  const close = useUiStore((s) => s.close);
  const saveStatus = useSettingsStore((s) => s.saveStatus);

  return (
    <Modal
      title="Settings"
      onClose={close}
      maxWidth={700}
      footer={
        <>
          <span className="hint" role="status" style={{ marginRight: "auto" }}>{saveStatus === "saving" ? "Saving changes..." : saveStatus === "error" ? "A change could not be saved. Please try again." : "Changes save automatically."}</span>
          <button type="button" className="btn primary" onClick={close}>Done</button>
        </>
      }
    >
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className={`tab${tab === t.id ? " on" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <ModalBody>
        {tab === "files" && <FilesTab />}
        {tab === "memory" && <MemoryTab />}
        {tab === "data" && <DataTab />}
      </ModalBody>
    </Modal>
  );
}
