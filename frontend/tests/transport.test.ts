import { afterEach, describe, expect, it, vi } from "vitest";
import { readSse } from "@/services/api";
import { createSseRunner } from "@/services/runner/sseRunner";
import { DEFAULT_SIMPLE, DEFAULT_TEAM } from "@/domain/defaults";
import type { RunEvent, RunRequest } from "@/domain/events";

const request: RunRequest = { id: "a1", chatId: "c1", mode: "planner", kind: "planner", prompt: "Make a report", files: [], simple: DEFAULT_SIMPLE, team: DEFAULT_TEAM, runIn: "auto", budgetUsd: 1, estimateUsd: .1, contextPercent: 0 };
afterEach(() => vi.unstubAllGlobals());

describe("SSE transport and acknowledged controls", () => {
  it("handles CRLF events split across streamed chunks", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({ start(c) { for (const value of ['data: {"type":"text","delta":"hel', 'lo"}\r\n\r\n', 'data: {"type":"done"}\n\n']) c.enqueue(encoder.encode(value)); c.close(); } });
    const events: RunEvent[] = [];
    await readSse(new Response(body), (e) => events.push(e));
    expect(events).toEqual([{ type: "text", delta: "hello" }, { type: "done" }]);
  });
  it("turns an incomplete stream into a recoverable offline error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('data: {"type":"text","delta":"partial"}\n\n')));
    const events: RunEvent[] = [];
    createSseRunner("http://test").start(request, (e) => events.push(e));
    await vi.waitFor(() => expect(events.at(-1)?.type).toBe("error"));
    expect(events.at(-1)).toMatchObject({ offline: true });
  });
  it("rejects a failed approval and sends the exact plan version", async () => {
    const fetch = vi.fn(async (url: string) => url.endsWith("/approve") ? new Response(JSON.stringify({ detail: "Plan changed" }), { status: 409 }) : new Response('data: {"type":"done"}\n\n'));
    vi.stubGlobal("fetch", fetch);
    const handle = createSseRunner("http://test").start(request, () => {});
    await expect(handle.approve("version-7")).rejects.toThrow("Plan changed");
    expect(JSON.parse((fetch.mock.calls.find(([url]) => url.endsWith("/approve")) as unknown as [string, RequestInit])[1].body as string)).toEqual({ planVersion: "version-7" });
  });
  it("Stop waits for accounting and does not misclassify intentional EOF as offline", async () => {
    const encoder = new TextEncoder();
    let stream!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({ start(controller) { stream = controller; controller.enqueue(encoder.encode('data: {"type":"status","text":"Working"}\n\n')); } });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/stop")) { stream.close(); return new Response(JSON.stringify({ stopped: true, usd: .023, calls: 4 })); }
      return new Response(body);
    }));
    const events: RunEvent[] = [];
    const handle = createSseRunner("http://test").start(request, (event) => events.push(event));
    await vi.waitFor(() => expect(events[0]?.type).toBe("status"));
    await handle.stop();
    expect(events).toContainEqual({ type: "cost", usd: .023, calls: 4 });
    expect(events.some((event) => event.type === "error")).toBe(false);
  });
});
