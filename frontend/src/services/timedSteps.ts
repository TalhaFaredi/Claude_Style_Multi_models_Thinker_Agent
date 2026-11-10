/**
 * Plays "step 1 done, step 2 done..." for the checked flows (summarize, import).
 * Returns a cancel function. Replace with real progress events from the backend.
 */
export function playSteps(count: number, intervalMs: number, onStep: (step: number) => void, onDone?: () => void): () => void {
  const timers: ReturnType<typeof setTimeout>[] = [];
  for (let k = 1; k <= count; k++) timers.push(setTimeout(() => onStep(k), k * intervalMs));
  if (onDone) timers.push(setTimeout(onDone, (count + 1) * intervalMs));
  return () => timers.forEach(clearTimeout);
}
