import { mockRunner } from "./mockRunner";
import { createSseRunner } from "./sseRunner";
import type { Runner } from "./types";

/** NEXT_PUBLIC_API_URL set -> real backend over SSE. Empty -> offline mock. */
export function getRunner(): Runner {
  const url = process.env.NEXT_PUBLIC_API_URL;
  return url ? createSseRunner(url) : mockRunner;
}

export const usingMock = !process.env.NEXT_PUBLIC_API_URL;   // same switch as isLive in ../api

export type { RunHandle, Runner } from "./types";
