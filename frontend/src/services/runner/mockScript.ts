/**
 * Builds the scripted event timeline for the offline demo.
 * Pure: (request) -> list of {delay, event | pause}. The mock runner just plays it.
 * Mirrors what the real backend will send (see domain/events.ts).
 */
import { getModel, ROLES } from "@/data/sample";
import { plannerCost, teamCalls } from "@/domain/cost";
import { teamLine } from "@/domain/describe";
import type { AgentStatus, AgentView, PlanStepView, RunEvent, RunRequest, StepStatus } from "@/domain/events";
import { activeTools } from "@/domain/guardrails";
import { contextBump } from "@/domain/context";

export type ScriptItem = { delay: number; event: RunEvent } | { delay: number; pause: "approval" };

export const STEP_MS = 650;
const WORD_MS = 28;

const words = (text: string, delay = WORD_MS): ScriptItem[] =>
  text.split(/(\s+)/).filter(Boolean).map((w) => ({ delay, event: { type: "text", delta: w } }));

const ev = (event: RunEvent, delay = STEP_MS): ScriptItem => ({ delay, event });

function agentViews(req: RunRequest, status: (i: number) => AgentStatus): AgentView[] {
  const { team } = req;
  const n = team.source === "same" ? team.agents : team.mixed.length;
  return Array.from({ length: n }, (_, i) => ({
    role: team.source === "same" ? ROLES[i] : `Agent ${i + 1}`,
    model: getModel(team.source === "same" ? team.model : team.mixed[i]).name,
    status: status(i),
  }));
}

function simpleScript(req: RunRequest): ScriptItem[] {
  const model = getModel(req.simple.model);
  const tools = activeTools(req.simple);
  const useWeb = tools.includes("web");
  const items: ScriptItem[] = [];

  if (req.simple.thinking !== "off" && model.thinking) {
    items.push(ev({ type: "status", text: "Thinking" }, 250));
    items.push(ev({ type: "thinking", notes: ["What is really asked?", useWeb ? "Current facts needed: use web search." : "Answer from knowledge.", "Short answer with one example."] }, 400));
  }
  if (useWeb) {
    items.push(ev({ type: "status", text: "Searching the web" }));
    items.push(ev({ type: "tool", state: "running", label: "Searching the web..." }, 100));
    items.push(ev({ type: "tool", state: "done", label: "Used 3 web sources" }));
  }
  items.push(ev({ type: "status", text: "Writing" }, 200));
  items.push(...words(`Here is a sample answer to "${req.prompt}". The chosen model writes it while you watch.\n\nFacts link to their sources; the line below shows model, calls and cost.`));
  if (useWeb) items.push(ev({ type: "citations", items: ["[1]", "[2]", "[3]"] }, 100));
  items.push(ev({ type: "cost", calls: useWeb ? 2 : 1, usd: req.estimateUsd }, 50));
  return items;
}

function thinkerScript(req: RunRequest): ScriptItem[] {
  const { team } = req;
  const rounds = team.style === "together" ? team.rounds : 1;
  const first = team.style === "together" ? `Round 1 of ${rounds}: each thinks alone` : "Thinking on their own";
  const n = team.source === "same" ? team.agents : team.mixed.length;
  const half = Math.ceil(n / 2);
  const send = (roundText: string, status: (i: number) => AgentStatus): ScriptItem =>
    ev({ type: "agents", roundText, agents: agentViews(req, status) });

  const items: ScriptItem[] = [
    ev({ type: "status", text: "Agents thinking" }, 250),
    ev({ type: "thinking", notes: ["Same question to every agent, each with a role.", team.style === "together" ? "Together: agents read the shared board and revise." : "On their own: nobody sees the others.", "A judge checks if the main conclusions match."] }, 100),
    send(first, () => "thinking"),
    send(first, (i) => (i < half ? "ready" : "thinking")),
    send(first, () => "ready"),
  ];
  for (let r = 2; r <= rounds; r++) {
    const label = `Round ${r} of ${rounds}: reading each other, revising`;
    items.push(ev({ type: "status", text: "Debating" }, 100));
    items.push(send(label, () => "revising"));
    items.push(send(r === rounds ? "They agree on the main point" : label, () => "ready"));
  }
  items.push(ev({ type: "status", text: "Composing" }, 100));
  items.push(ev({ type: "composer", model: team.composer === "auto" ? team.model : team.composer, status: "running", explanation: "Combines shared conclusions and resolves disagreements using roles and evidence." }, 0));
  items.push(send("Composer is writing the answer", () => "ready"));
  items.push(...words("All agents agree on the main point, stated first in plain words.\n\nWhere they disagreed, the composer says which view won and why."));
  items.push(send("Done", () => "ready"));
  items.push(ev({ type: "composer", model: team.composer === "auto" ? team.model : team.composer, status: "done", explanation: "Merged the supported conclusions and explained the disagreements." }, 0));
  items.push(ev({ type: "cost", calls: teamCalls(team), usd: req.estimateUsd }, 50));
  return items;
}

/** Row = status of plan steps 1..4 at one moment (same timeline as the prototype). */
type Row = StepStatus[];
const TIMELINE: Row[] = [
  ["running", "waiting", "waiting", "waiting"],
  ["checking", "waiting", "waiting", "waiting"],
  ["done", "running", "waiting", "waiting"],
  ["done", "checking", "waiting", "waiting"],
  ["done", "done", "running", "waiting"],
  ["done", "done", "running", "waiting"], // second round of the team step
  ["done", "done", "retry", "waiting"],
  ["done", "done", "checking", "waiting"],
  ["done", "done", "done", "running"],
  ["done", "done", "done", "checking"],
  ["done", "done", "done", "done"],
];

function plannerScript(req: RunRequest): ScriptItem[] {
  const useTeam = req.runIn !== "simple";
  const teamText = teamLine(req.team);
  const base = [
    { task: "Research solar power facts", modeLabel: "Simple + web search" },
    { task: "Write the outline", modeLabel: "Simple" },
    { task: "Write the sections", modeLabel: useTeam ? `Thinker: ${teamText}` : "Simple" },
    { task: "Make the PDF", modeLabel: "Simple + PDF skill" },
  ];
  const steps = (row: Row | StepStatus, tick = 0): PlanStepView[] =>
    base.map((b, i) => {
      const status = Array.isArray(row) ? row[i] : row;
      let note: string | undefined;
      let noteTone: "hint" | "warn" | undefined;
      if (i === 2 && useTeam && status === "running") {
        const second = tick === 5;
        note = req.team.style === "together"
          ? second ? "Round 2: agents read each other, then the composer merges" : "Round 1: each agent drafts alone"
          : second ? "Composer merging the drafts" : "Agents writing on their own";
      }
      if (status === "retry") { note = "Checker: section 2 has no source. Retry 1 of 2."; noteTone = "warn"; }
      return { ...b, status, note, noteTone, kind: i === 3 ? "tool" : i === 2 ? "hard" : "easy", doneTest: i === 3 ? "A readable PDF is produced." : "The result is complete and cites its supporting sources." };
    });

  const items: ScriptItem[] = [
    ev({ type: "plan", phase: "Writing the plan", steps: steps("planning"), awaitingApproval: false }, 300),
    ev({ type: "plan", phase: "Waiting for your approval", steps: steps("planned"), awaitingApproval: true }, STEP_MS),
    { delay: 0, pause: "approval" },
  ];
  TIMELINE.forEach((row, tick) => items.push(ev({ type: "plan", phase: "Running", steps: steps(row, tick), awaitingApproval: false })));
  items.push(ev({ type: "plan", phase: "Finished", steps: steps(TIMELINE[TIMELINE.length - 1]), awaitingApproval: false }, 200));
  items.push(ev({ type: "output", file: { name: "solar_power_report.pdf", pages: 2, sources: 6, checked: true } }, 200));
  items.push(...words("The report is ready. All 4 steps passed their checks; step 3 needed one retry."));
  items.push(ev({ type: "cost", calls: useTeam ? 3 + teamCalls(req.team) : 6, usd: plannerCost(req.runIn, req.team) }, 50));
  return items;
}

export function buildScript(req: RunRequest): ScriptItem[] {
  const body = req.kind === "simple" ? simpleScript(req) : req.kind === "thinker" ? thinkerScript(req) : plannerScript(req);
  return [
    { delay: 700, event: { type: "status", text: req.kind === "planner" ? "Writing the plan" : "Starting" } },
    ...body,
    ev({ type: "context", percent: Math.min(99, req.contextPercent + contextBump(req.kind, req.files.length > 0)) }, 0),
    ev({ type: "done" }, 120),
  ];
}
