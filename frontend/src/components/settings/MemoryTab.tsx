"use client";

import { useEffect, useState } from "react";
import { isLive } from "@/services/api";
import { useSettingsStore } from "@/store/settingsStore";
import { toast } from "@/store/uiStore";
import { Segmented } from "../ui/Segmented";
import { Switch } from "../ui/Switch";

const WINDOWS = [8000, 16000, 32000, 64000, 128000];

/** Long-term facts with date and source. Delete asks Keep or Delete first (F11, C42). */
export function MemoryTab() {
  const longMemory = useSettingsStore((s) => s.longMemory);
  const autoCompact = useSettingsStore((s) => s.autoCompact);
  const windowCap = useSettingsStore((s) => s.windowCap);
  const promptCacheTtl = useSettingsStore((s) => s.promptCacheTtl);
  const memory = useSettingsStore((s) => s.memory);
  const set = useSettingsStore((s) => s.set);
  const deleteFact = useSettingsStore((s) => s.deleteFact);
  const loadMemory = useSettingsStore((s) => s.loadMemory);
  const [asking, setAsking] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  useEffect(() => { void loadMemory(); }, [loadMemory]);

  return (
    <>
      <Switch label="Remember facts across chats" checked={longMemory} onChange={(v) => set({ longMemory: v })} />
      <Switch label="Summarize automatically at 95% (else ask me)" checked={autoCompact} onChange={(v) => set({ autoCompact: v })} />
      <div className="field"><span className="field-label">Provider prompt cache</span><Segmented label="Prompt cache lifetime" value={promptCacheTtl} onChange={(v) => void set({ promptCacheTtl: v })} options={[{ value: "5m", label: "5 minutes" }, { value: "1h", label: "1 hour" }]} /><span className="hint">A longer cache can reduce repeated reads but costs more to write. Provider support varies.</span></div>
      {isLive && (
        <div className="field">
          <span className="field-label">Working window (tokens)</span>
          <Segmented label="Working window" value={windowCap} onChange={(v) => set({ windowCap: v })} options={WINDOWS.map((v) => ({ value: v, label: `${v / 1000}k` }))} />
          <span className="hint">Every message re-sends the whole window, so a bigger window costs more per message. The notice, alarm and summary levels apply to this size (or the model's own window if smaller).</span>
        </div>
      )}
      <span className="field-label">What I remember</span>
      {memory.length === 0 && <span className="hint">Nothing remembered yet.</span>}
      {memory.map((f) => (
        <div className="mrow static" key={f.id}>
          <span className="mrow-main"><span>{f.text}</span><span className="hint">{f.source}</span></span>
          {asking === f.id ? (
            <>
              <button type="button" className="btn small" onClick={() => setAsking(null)}>Keep</button>
              <button type="button" className="btn dark small" disabled={deleting === f.id} onClick={async () => { setDeleting(f.id); const ok = await deleteFact(f.id); setDeleting(null); if (ok) { setAsking(null); toast("Deleted everywhere"); } }}>{deleting === f.id ? "Deleting..." : "Delete"}</button>
            </>
          ) : (
            <button type="button" className="btn ghost small" onClick={() => setAsking(f.id)}>Delete</button>
          )}
        </div>
      ))}
    </>
  );
}
