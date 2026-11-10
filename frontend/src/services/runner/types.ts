import type { RunEvent, RunRequest } from "@/domain/events";

export interface RunHandle {
  /** Stop button (C20): keep what was done. */
  stop(): void | Promise<void>;
  /** Planner: the user approved the plan (F10). Nothing runs before this. */
  approve(planVersion?: string): void | Promise<void>;
  /** Planner: the user asked for a change; the server re-plans and shows the plan again (C15). */
  edit?(note: string, planVersion?: string): void | Promise<void>;
  permission?(id: string, allow: boolean): void | Promise<void>;
  useTeam?(step: number): void | Promise<void>;
}

/**
 * Anything that can run a question and stream back events.
 * Implementations: mockRunner (offline demo) and sseRunner (FastAPI backend).
 */
export interface Runner {
  start(request: RunRequest, emit: (event: RunEvent) => void): RunHandle;
}
