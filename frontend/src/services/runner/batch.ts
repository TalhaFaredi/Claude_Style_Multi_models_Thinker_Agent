import type { RunEvent } from "@/domain/events";

/**
 * Groups events that arrive within one frame (~16 ms) into a single store update.
 * Streaming text can deliver dozens of tiny deltas per second; without this,
 * each delta would trigger its own React render.
 */
export function createEventBatcher(apply: (events: RunEvent[]) => void, intervalMs = 16) {
  let queue: RunEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | null = null;

  const flush = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    if (queue.length === 0) return;
    const batch = queue;
    queue = [];
    apply(batch);
  };

  const push = (event: RunEvent) => {
    queue.push(event);
    // Terminal events flush immediately so the UI never waits on the timer to unlock.
    if (event.type === "done" || event.type === "error") flush();
    else if (!timer) timer = setTimeout(flush, intervalMs);
  };

  /** Drop pending events (used by Stop). */
  const cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    queue = [];
  };

  return { push, flush, cancel };
}
