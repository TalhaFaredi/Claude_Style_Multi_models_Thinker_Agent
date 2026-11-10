import type { RunEvent, RunRequest } from "@/domain/events";
import { ApiError, readSse, toError } from "../api";
import type { RunHandle, Runner } from "./types";

/**
 * Real backend runner (FastAPI). Contract:
 *   POST {base}/api/runs               body = RunRequest (below), response = text/event-stream
 *        each message:  data: {"type":"text","delta":"..."}\n\n   (one RunEvent per message)
 *   POST {base}/api/runs/{id}/approve  Planner: user approved the plan
 *   POST {base}/api/runs/{id}/edit     Planner: {"note": "..."} re-plan and show it again
 *   POST {base}/api/runs/{id}/stop     Stop button
 * Provider keys (OpenRouter / NVIDIA) live ONLY on the server.
 */
export function createSseRunner(baseUrl: string): Runner {
  const base = baseUrl.replace(/\/$/, "");

  return {
    start(request: RunRequest, emit: (event: RunEvent) => void): RunHandle {
      const controller = new AbortController();
      let terminal = false;
      let stopping = false;
      // Send only what the server reads: `kind`, `estimateUsd` and `contextPercent` are mock-runner inputs.
      const body = {
        id: request.id, chatId: request.chatId, mode: request.mode, prompt: request.prompt, files: request.files,
        simple: request.simple, team: request.team, runIn: request.runIn, budgetUsd: request.budgetUsd,
        planModel: request.planModel,
        allowOver: request.allowOver ?? false, retryOf: request.retryOf ?? null,
      };

      void (async () => {
        try {
          const res = await fetch(`${base}/api/runs`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify(body),
            signal: controller.signal,
          });
          await readSse(res, (event) => {
            if (event.type === "done" || event.type === "error") terminal = true;
            emit(event);
          });
          if (!terminal && !stopping && !controller.signal.aborted) throw new TypeError("Connection ended before the answer finished. Your message is kept as a draft.");
        } catch (err) {
          if (controller.signal.aborted || stopping) return;
          emit({ type: "error", message: err instanceof Error ? err.message : "Connection lost", offline: !(err instanceof ApiError) || err.status === 0 });
        }
      })();

      const post = async (path: string, payload?: unknown) => {
        const response = await fetch(`${base}/api/runs/${request.id}/${path}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: payload === undefined ? undefined : JSON.stringify(payload),
        });
        if (!response.ok) throw await toError(response);
        return response.json().catch(() => ({})) as Promise<{ usd?: number; calls?: number }>;
      };

      return {
        async stop() {
          // Abort the local reader only after the server confirms cancellation.
          stopping = true;
          try {
            const result = await post("stop");
            if (typeof result.usd === "number" && typeof result.calls === "number") emit({ type: "cost", usd: result.usd, calls: result.calls });
            controller.abort();
          } catch (error) {
            stopping = false;
            throw error;
          }
        },
        async approve(planVersion) {
          await post("approve", { planVersion });
        },
        async edit(note: string, planVersion) {
          await post("edit", { note, planVersion });
        },
        permission: async (id, allow) => { await post("permission", { id, allow }); },
        useTeam: async (step) => { await post("use-team", { step }); },
      };
    },
  };
}
