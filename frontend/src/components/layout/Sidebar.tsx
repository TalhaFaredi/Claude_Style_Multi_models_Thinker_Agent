"use client";

import { useEffect, useRef, useState } from "react";
import { money } from "@/domain/format";
import { isLive } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { useChatsStore } from "@/store/chatsStore";
import { useSettingsStore } from "@/store/settingsStore";
import { useUiStore } from "@/store/uiStore";
import { Icon } from "../ui/Icon";

/** New chat, search, recent chats, one Settings/memory/data button, month spend. */
export function Sidebar() {
  const [query, setQuery] = useState("");
  const chatId = useChatStore((s) => s.chatId);
  const newChat = useChatStore((s) => s.newChat);
  const openChat = useChatStore((s) => s.openChat);
  const openSettings = useUiStore((s) => s.openSettings);
  const openDelete = useUiStore((s) => s.openDeleteChat);
  const spent = useSettingsStore((s) => s.monthSpent);
  const budget = useSettingsStore((s) => s.monthBudget);
  const all = useChatsStore((s) => s.chats);
  const load = useChatsStore((s) => s.load);
  const first = useRef(true);

  // Live: the server searches titles and message text (and dates). Mock: filter the sample list below.
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    if (!isLive) return;
    const t = setTimeout(() => void load(query), 300);
    return () => clearTimeout(t);
  }, [query, load]);

  const chats = isLive ? all : all.filter((c) => !query || c.title.toLowerCase().includes(query.toLowerCase()));
  const overMonth = budget > 0 && spent >= 0.8 * budget;

  return (
    <nav className="side" aria-label="Chats">
      <div className="brand">
        <span className="mark"><Icon name="logo" size={14} stroke="#fff" width={2.4} /></span>
        <span className="brand-name">Multi-Mode Assistant</span>
      </div>
      <button type="button" className="btn primary" onClick={newChat}><Icon name="plus" />New chat</button>
      <label className="field">
        <span className="field-label">Search chats</span>
        <input className="input" placeholder="Words or dates" value={query} onChange={(e) => setQuery(e.target.value)} />
      </label>
      <div className="side-label">Recent</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, overflowY: "auto" }}>
        {chats.map((c) => (
          <div className="chatline" key={c.id}>
            <button type="button" className={`chatrow${chatId === c.id ? " on" : ""}`} aria-current={chatId === c.id} onClick={() => void openChat(c.id, c.title)}>
              {c.title}
            </button>
            {isLive && (
              <button type="button" className="chatdel" aria-label={`Delete chat ${c.title}`} onClick={() => openDelete(c.id)}>
                <Icon name="close" size={14} />
              </button>
            )}
          </div>
        ))}
        {isLive && chats.length === 0 && <span className="hint" style={{ padding: "6px 10px" }}>{query ? "No chat matches." : "Your chats appear here."}</span>}
      </div>
      <div className="grow" />
      <button type="button" className="btn ghost" style={{ justifyContent: "flex-start" }} onClick={() => openSettings()}>
        <Icon name="gear" size={18} />Settings, memory, data
      </button>
      <div className="row side-foot">
        <span className="mark dark">Y</span>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span className="strong">You</span>
          <span className={overMonth ? "hint warn" : "hint"}>Spent this month {money(spent)} of {money(budget)}{overMonth ? " (over 80%)" : ""}</span>
        </div>
      </div>
    </nav>
  );
}
