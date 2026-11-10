"use client";

import { useChatStore } from "@/store/chatStore";
import { useSettingsStore } from "@/store/settingsStore";
import { toast, useUiStore } from "@/store/uiStore";
import { Switch } from "../ui/Switch";

/** Download, import, temporary chat, reset. Safety limits are fixed and not listed here (F12). */
export function DataTab() {
  const open = useUiStore((s) => s.open);
  const tempChat = useSettingsStore((s) => s.tempChat);
  const set = useSettingsStore((s) => s.set);
  const resetSafe = useSettingsStore((s) => s.resetSafe);
  const resetConfig = useChatStore((s) => s.resetConfig);
  const locked = useChatStore((s) => s.running || s.preparing);

  return (
    <>
      <button type="button" className="mrow" onClick={() => open("export")}>
        <span className="mrow-main"><span className="strong">Download this chat</span><span className="hint">Messages, memory and file readings in one .zip</span></span>
      </button>
      <button type="button" className="mrow" onClick={() => open("import")}>
        <span className="mrow-main"><span className="strong">Import a chat</span><span className="hint">Checked first; file readings reused at $0</span></span>
      </button>
      <Switch label="Temporary chat (nothing saved to memory)" checked={tempChat} onChange={(v) => set({ tempChat: v })} />
      <button type="button" className="btn" disabled={locked} style={{ alignSelf: "flex-start" }} onClick={async () => { if (await resetSafe()) { resetConfig(); toast("Safe defaults restored"); } }}>
        Reset everything to safe defaults
      </button>
      {locked && <span className="hint">Stop the current answer before resetting the mode setup.</span>}
    </>
  );
}
