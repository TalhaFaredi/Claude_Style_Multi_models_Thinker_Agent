import { getModel } from "@/data/sample";
import type { AiMessage } from "@/domain/messages";
import { Icon } from "../ui/Icon";
import { Pill } from "../ui/Pill";

const KIND_LABEL = { simple: "Simple", thinker: "Thinker", planner: "Planner" } as const;

/** Model or team name, mode tag, live status line with a dot. */
export function AnswerHeader({ m }: { m: AiMessage }) {
  const title = m.kind === "simple" ? getModel(m.snapshot.simple.model).name : m.kind === "thinker" ? "Thinker team" : "Planner";
  return (
    <div className="ai-head">
      <span className="mark"><Icon name="logo" size={12} stroke="#fff" width={2.6} /></span>
      <span className="ai-name">{title}</span>
      <Pill>{KIND_LABEL[m.kind]}</Pill>
      {m.status === "live" && (
        <span className="status" role="status"><span className="dot" />{m.statusText}</span>
      )}
    </div>
  );
}
