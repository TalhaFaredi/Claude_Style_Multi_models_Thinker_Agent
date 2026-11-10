import { getModel } from "@/data/sample";
import type { ComposerView } from "@/domain/events";
import { Pill } from "../ui/Pill";

export function ComposerCard({ composer }: { composer: ComposerView }) {
  const model = getModel(composer.model);
  return <div className="card green" role="status">
    <div className="row"><span className="strong">Composer: {model.id === composer.model ? model.name : composer.model}</span><Pill tone="green">{composer.status === "done" ? "Merged" : composer.status === "running" ? "Merging answers" : "Waiting"}</Pill></div>
    <span>{composer.explanation || "Combines shared conclusions and resolves disagreements, using each agent's role and evidence."}</span>
  </div>;
}
