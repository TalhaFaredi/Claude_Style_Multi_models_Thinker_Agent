import type { RunEvent, RunRequest } from "@/domain/events";
import { buildScript } from "./mockScript";
import type { RunHandle, Runner } from "./types";

/** Offline demo runner: plays a scripted timeline, honors Stop and plan approval. */
export const mockRunner: Runner = {
  start(request: RunRequest, emit: (event: RunEvent) => void): RunHandle {
    let script = buildScript(request);
    let revision = 1;
    let index = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    let paused = false;

    const next = () => {
      if (stopped || index >= script.length) return;
      const item = script[index];
      timer = setTimeout(() => {
        if (stopped) return;
        index += 1;
        if ("pause" in item) {
          paused = true; // wait for approve()
          return;
        }
        emit(item.event.type === "plan" ? { ...item.event, version: `demo-${revision}` } : item.event);
        next();
      }, item.delay);
    };

    next();

    return {
      stop() {
        stopped = true;
        if (timer) clearTimeout(timer);
      },
      approve() {
        if (!paused) return;
        paused = false;
        next();
      },
      edit(note) {
        if (!paused) throw new Error("The plan is no longer waiting for edits.");
        revision++;
        script = buildScript({ ...request, prompt: `${request.prompt}\nRequested plan change: ${note}` });
        index = 0;
        paused = false;
        next();
      },
    };
  },
};
