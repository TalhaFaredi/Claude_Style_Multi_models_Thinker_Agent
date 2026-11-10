import { memo } from "react";
import type { Message } from "@/domain/messages";
import { Pill } from "../ui/Pill";
import { AnswerBlock } from "./AnswerBlock";

/**
 * Memoized: the store replaces only the message that changed, so while one answer streams
 * every other message in the list skips rendering.
 */
export const MessageView = memo(function MessageView({ message }: { message: Message }) {
  if (message.role === "sys") return <div className="sys">{message.text}</div>;
  if (message.role === "user") {
    return (
      <div className="user">
        <div>{message.text}</div>
        {message.files.length > 0 && (
          <div className="row" style={{ marginTop: 6 }}>{message.files.map((f) => <Pill key={f}>{f}</Pill>)}</div>
        )}
      </div>
    );
  }
  return <AnswerBlock m={message} />;
});
