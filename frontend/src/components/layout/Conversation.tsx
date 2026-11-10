"use client";

import { useEffect, useRef } from "react";
import { useChatStore } from "@/store/chatStore";
import { EmptyState } from "../chat/EmptyState";
import { MessageView } from "../chat/MessageView";

const STICK_PX = 120;

/** Scrolling message list. Follows new text only while the reader is near the bottom. */
export function Conversation() {
  const messages = useChatStore((s) => s.messages);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const onScroll = () => {
    const el = scroller.current;
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
  };

  return (
    <div className="scroll" ref={scroller} onScroll={onScroll} role="log" aria-label="Conversation">
      <div className="col">
        {messages.length === 0 && <EmptyState />}
        {messages.map((m) => <MessageView key={m.id} message={m} />)}
      </div>
    </div>
  );
}
