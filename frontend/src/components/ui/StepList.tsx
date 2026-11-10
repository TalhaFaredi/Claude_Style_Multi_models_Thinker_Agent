import { Pill } from "./Pill";

export interface StepDef {
  title: string;
  detail: string;
}

/** Checked steps that tick off one by one (summarize, import). `done` = number of finished steps. */
export function StepList({ steps, done }: { steps: StepDef[]; done: number }) {
  return (
    <>
      {steps.map((s, i) => {
        const state = done > i ? "done" : done === i ? "run" : "wait";
        return (
          <div className="step" key={s.title}>
            <span className={`step-num${state === "done" ? " done" : state === "run" ? " run" : ""}`}>{i + 1}</span>
            <div className="step-body">
              <span className="strong">{s.title}</span>
              <span className="hint">{s.detail}</span>
            </div>
            <Pill tone={state === "done" ? "green" : "neutral"}>{state === "done" ? "Done" : state === "run" ? "Working" : "Waiting"}</Pill>
          </div>
        );
      })}
    </>
  );
}
