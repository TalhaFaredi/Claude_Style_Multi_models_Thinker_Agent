import { beforeEach, describe, expect, it } from "vitest";
import { useChatStore } from "@/store/chatStore";
import { useSettingsStore, SAFE_DEFAULTS } from "@/store/settingsStore";
import { useUiStore } from "@/store/uiStore";
import { DEFAULT_SIMPLE, DEFAULT_TEAM } from "@/domain/defaults";
import type { AiMessage } from "@/domain/messages";

beforeEach(async () => {
  await useChatStore.getState().stop();
  useChatStore.setState({ mode: "simple", simple: DEFAULT_SIMPLE, team: DEFAULT_TEAM, running: false, preparing: false, messages: [], draft: "", budget: .05, allowOnce: false, pending: [] });
  useUiStore.getState().close();
});

describe("user-visible state transitions", () => {
  it("full reset restores every account setting without deleting memory or cached readings", async () => {
    useSettingsStore.setState({ tempChat: true, longMemory: false, chartDescriptions: false, monthBudget: 50, windowCap: 128000, parseCache: { original: true } });
    await useSettingsStore.getState().resetSafe();
    expect(useSettingsStore.getState()).toMatchObject(SAFE_DEFAULTS);
    expect(useSettingsStore.getState().parseCache.original).toBe(true);
  });
  it("Think deeper and Retry hit the budget dialog before replacing the earlier answer", async () => {
    const m = { id: "old", role: "ai", kind: "simple", prompt: "Compare options", auto: true, status: "done", snapshot: { simple: DEFAULT_SIMPLE, team: DEFAULT_TEAM, runIn: "auto" }, text: "Original answer" } as AiMessage;
    useChatStore.setState({ messages: [m], budget: .01 });
    await useChatStore.getState().thinkDeeper("old");
    expect(useUiStore.getState().dialog).toBe("cost");
    expect(useChatStore.getState().messages[0]).toBe(m);
    expect(useChatStore.getState().running).toBe(false);
    useUiStore.getState().close();
    useChatStore.setState({ mode: "thinker" });
    await useChatStore.getState().retry("old");
    expect(useUiStore.getState().dialog).toBe("cost");
    expect(useChatStore.getState().messages).toEqual([m]);
  });
  it("demo continuation carries actual prior content and file cards", async () => {
    useChatStore.setState({ messages: [{ id: "u1", role: "user", text: "Ticket ZX-4928", files: [] }], pending: [{ id: "file", name: "facts.pdf", status: "ready", cost: 0 }] });
    await useChatStore.getState().newChatFromSummary();
    expect(useChatStore.getState().messages[0].text).toContain("ZX-4928");
    expect(useChatStore.getState().pending[0].name).toBe("facts.pdf");
    expect(useChatStore.getState().messages[0].text).not.toContain("12 facts");
  });
});
