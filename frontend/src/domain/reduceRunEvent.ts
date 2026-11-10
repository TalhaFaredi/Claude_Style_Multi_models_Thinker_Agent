import type { RunEvent } from "./events";
import type { AiMessage } from "./messages";

/** Pure reducer: folds one server event into an answer. Easy to unit-test. */
export function reduceRunEvent(m: AiMessage, e: RunEvent): AiMessage {
  if (m.status === "stopped") return m; // late events after Stop are ignored
  switch (e.type) {
    case "route":
      return { ...m, kind: e.kind };
    case "status":
      return { ...m, statusText: e.text, status: "live" };
    case "thinking":
      return { ...m, thinkingNotes: e.notes, thoughtSeconds: e.seconds ?? m.thoughtSeconds };
    case "tool":
      return { ...m, tool: { state: e.state, label: e.label } };
    case "text":
      return { ...m, text: e.replace ? e.delta : m.text + e.delta };
    case "citations":
      return { ...m, citations: e.items };
    case "agents":
      return { ...m, roundText: e.roundText, agents: e.agents };
    case "plan":
      return {
        ...m,
        plan: { phase: e.phase, steps: e.steps, awaitingApproval: e.awaitingApproval, estimateUsd: e.estimateUsd, version: e.version, overBudget: e.overBudget, remainingBudgetUsd: e.remainingBudgetUsd },
        controlError: null,
        status: e.awaitingApproval ? "waiting" : "live",
        statusText: e.phase,
      };
    case "output":
      return { ...m, output: e.file };
    case "composer":
      return { ...m, composer: { model: e.model, status: e.status, explanation: e.explanation } };
    case "permission":
      return { ...m, permission: e.resolved ? null : e, status: e.resolved ? "live" : "waiting", controlError: null };
    case "cost":
      return { ...m, calls: e.calls, costUsd: e.usd };
    case "warning":
      return { ...m, warning: m.warning ? `${m.warning} ${e.message}` : e.message };
    case "done":
      return { ...m, status: "done", statusText: "Done", permission: null, plan: m.plan ? { ...m.plan, awaitingApproval: false } : null };
    case "error":
      return { ...m, status: e.offline ? "offline" : "error", error: e.message };
    // handled by the store (window meter, summarize dialog, chat notes) or shown as the answer text
    case "context":
    case "compact":
    case "note":
    case "clarify":
      return m;
  }
}
