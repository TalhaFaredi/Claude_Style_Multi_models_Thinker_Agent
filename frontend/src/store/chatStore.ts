import { create } from "zustand";
import { persist } from "zustand/middleware";
import { DEMO_FILES, getModel } from "@/data/sample";
import { snoozeThreshold } from "@/domain/context";
import { estimateCost, fileReadingCost } from "@/domain/cost";
import { DEFAULT_SIMPLE, DEFAULT_TEAM } from "@/domain/defaults";
import type { ContextInfo, RunEvent, RunRequest } from "@/domain/events";
import { clamp, money, uid } from "@/domain/format";
import { isOverBudget, oneQuestionCap, normalizeThinking, stepAgents, stepRounds, teamGuardText, toggleMixedModel } from "@/domain/guardrails";
import { CONTEXT_LEVELS } from "@/domain/limits";
import type { AiMessage, Message } from "@/domain/messages";
import { reduceRunEvent } from "@/domain/reduceRunEvent";
import { routeAuto } from "@/domain/router";
import type { Mode, PendingFile, ReaderId, RunKind, SimpleConfig, StepRunMode, TeamConfig } from "@/domain/types";
import { api, ApiError, isLive, type ChatFile, type ServerConfig, type UploadedFile } from "@/services/api";
import { getRunner, type RunHandle } from "@/services/runner";
import { createEventBatcher } from "@/services/runner/batch";
import { playSteps } from "@/services/timedSteps";
import { useChatsStore } from "./chatsStore";
import { useModelsStore } from "./modelsStore";
import "./modelsStore"; // registers the live model list with getModel()
import { safeStorage } from "./safeStorage";
import { useSettingsStore } from "./settingsStore";
import { toast, useUiStore } from "./uiStore";

/** Short chat id. The live server creates the chat when it first sees the id. */
export const newChatId = () => Array.from({ length: 12 }, () => Math.floor(Math.random() * 16).toString(16)).join("");

interface ChatState {
  chatId: string;
  mode: Mode;
  simple: SimpleConfig;
  team: TeamConfig;
  runIn: StepRunMode;
  planModel: string;
  /** Money budget per question (USD). */
  budget: number;
  allowOnce: boolean;
  allowOnceCap: number | null;

  messages: Message[];
  draft: string;
  running: boolean;
  /** Memory window fill, 0 to 100. */
  context: number;
  /** Live: parts of the window, tokens and next-message price from the server. */
  contextInfo: ContextInfo | null;
  snoozeAt: number;
  pending: PendingFile[];
  /** Live: estimate from the server for the next question (null = use the local formula). */
  serverEstimate: number | null;
  loadingChat: boolean;
  preparing: boolean;

  // configuration
  setMode: (mode: Mode) => void;
  setModel: (id: string) => void;
  patchSimple: (patch: Partial<SimpleConfig>) => void;
  patchTeam: (patch: Partial<TeamConfig>) => void;
  setRunIn: (runIn: StepRunMode) => void;
  setPlanModel: (id: string) => void;
  setBudget: (budget: number) => void;
  stepAgentCount: (delta: 1 | -1) => void;
  stepRoundCount: (delta: 1 | -1) => void;
  toggleMixed: (id: string) => void;
  setTeamModel: (id: string) => void;
  setDraft: (draft: string) => void;
  allowThisOnce: () => void;
  setServerEstimate: (usd: number | null) => void;
  applyServerDefaults: (cfg: ServerConfig, modelIds: string[]) => void;
  resetConfig: () => void;
  // running
  send: (override?: string) => Promise<void>;
  stop: () => Promise<boolean>;
  approvePlan: () => Promise<boolean>;
  editPlan: (note: string) => Promise<boolean>;
  answerPermission: (messageId: string, allow: boolean) => Promise<boolean>;
  useTeamForStep: (messageId: string, step: number) => Promise<boolean>;
  retry: (id: string) => Promise<void>;
  thinkDeeper: (id: string) => Promise<void>;
  // chats
  openChat: (id: string, title: string) => Promise<void>;
  newChat: () => Promise<void>;
  newChatFromSummary: () => Promise<void>;
  openImportedChat: (chatId?: string) => void;
  snooze: () => void;
  compact: () => void;
  refreshContext: () => Promise<void>;
  // files
  attachFile: (fileId: string, textOnly: boolean) => void;
  attachLiveFile: (up: UploadedFile, textOnly: boolean, maxCost: number, readerOverride?: ReaderId, pages?: number[]) => Promise<void>;
  removePending: (fileId: string) => void;
}

/** The run in flight. Module-level on purpose: it is not render state. */
let active: { handle: RunHandle; batcher: ReturnType<typeof createEventBatcher> } | null = null;

const emptyAi = (id: string, kind: RunKind, prompt: string, auto: boolean, snapshot: AiMessage["snapshot"]): AiMessage => ({
  id, role: "ai", kind, prompt, auto, status: "live", statusText: "Starting", thinkingNotes: [], tool: null, text: "", citations: [],
  roundText: "", agents: [], plan: null, output: null, calls: 0, costUsd: 0, error: null, warning: null, thoughtSeconds: null, snapshot,
});

/** Turn a message saved by the server back into what the UI renders. */
function fromServer(raw: Record<string, unknown>, fallback: AiMessage["snapshot"]): Message {
  const role = raw.role as string;
  if (role === "user") return { id: String(raw.id), role: "user", text: String(raw.text ?? ""), files: (raw.files as string[]) ?? [] };
  if (role === "sys") return { id: String(raw.id), role: "sys", text: String(raw.text ?? "") };
  const base = emptyAi(String(raw.id), (raw.kind as RunKind) ?? "simple", String(raw.prompt ?? ""), Boolean(raw.auto), (raw.snapshot as AiMessage["snapshot"]) ?? fallback);
  const m = { ...base, ...(raw as Partial<AiMessage>), id: base.id, role: "ai" as const };
  // a run that was interrupted (reload, server stop) is shown as stopped, never as live forever
  if (m.status === "live" || m.status === "waiting") { m.status = "stopped"; m.permission = null; if (m.plan) m.plan = { ...m.plan, awaitingApproval: false }; }
  return m;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => {
      type Intent = { text: string; opts: { addUser: boolean; kind?: RunKind; auto: boolean; retryOf?: string } };
      let pendingIntent: Intent | null = null;
      const localEstimate = () => {
        const s = get();
        return estimateCost({ mode: s.mode, simple: s.simple, team: s.team, runIn: s.runIn });
      };
      const estimate = () => (isLive && get().serverEstimate != null ? (get().serverEstimate as number) : localEstimate());
      const modelId = () => get().simple.model;

      const patchMessage = (id: string, fn: (m: AiMessage) => AiMessage) =>
        set((s) => ({ messages: s.messages.map((m) => (m.id === id && m.role === "ai" ? fn(m) : m)) }));

      /** Events that belong to the chat, not to one answer: window meter, summarize dialog, notes. */
      const chatEvent = (e: RunEvent): Message[] => {
        const added: Message[] = [];
        if (e.type === "context") {
          const info = e.parts ? (e as unknown as ContextInfo) : null;
          set({ context: clamp(e.percent, 0, 999), ...(info ? { contextInfo: info } : {}) });
        } else if (e.type === "compact") {
          const ui = useUiStore.getState();
          if (e.step === 0 && ui.dialog !== "compact") ui.open("compact");
          ui.setCompactStep(e.step);
          if (e.done) setTimeout(() => useUiStore.getState().dialog === "compact" && useUiStore.getState().close(), 600);
        } else if (e.type === "note") {
          added.push({ id: uid("s"), role: "sys", text: e.text });
        }
        return added;
      };

      /** Apply a batch of server events in ONE store update. */
      const applyEvents = (id: string, events: RunEvent[]) => {
        let finished = false;
        let monthUsd: number | undefined;
        const before: Message[] = []; // routing notes go before the answer
        const after: Message[] = [];
        for (const e of events) {
          if (e.type === "done" || e.type === "error") finished = true;
          if (e.type === "done" && e.monthUsd !== undefined) monthUsd = e.monthUsd;
          if (e.type === "route" && e.reason) before.push({ id: uid("s"), role: "sys", text: e.reason });
          after.push(...chatEvent(e));
        }
        set((s) => {
          let msgs = s.messages.map((m) => (m.id === id && m.role === "ai" ? events.reduce(reduceRunEvent, m) : m));
          if (before.length) {
            const at = msgs.findIndex((m) => m.id === id);
            msgs = [...msgs.slice(0, at), ...before, ...msgs.slice(at)];
          }
          if (after.length) msgs = [...msgs, ...after];
          const offline = events.some((e) => e.type === "error" && e.offline);
          const failed = msgs.find((m) => m.id === id && m.role === "ai");
          return { messages: msgs, ...(offline && !s.draft && failed?.role === "ai" ? { draft: failed.prompt } : {}), ...(finished ? { running: false } : {}) };
        });
        if (!finished) return;
        active = null;
        const done = get().messages.find((m): m is AiMessage => m.id === id && m.role === "ai");
        const settings = useSettingsStore.getState();
        if (monthUsd !== undefined) useSettingsStore.setState({ monthSpent: monthUsd }); // live: the server's real total
        else if (!isLive && done?.status === "done") settings.addSpend(done.costUsd);
        if (isLive) void useChatsStore.getState().load();
        // C37 (mock): 95% -> auto-compact. The live server compacts by itself and streams `compact` events.
        if (!isLive && get().context >= CONTEXT_LEVELS.compact && settings.autoCompact) get().compact();
      };

      /** Start a run. `addUser` false = Retry (the question is already on screen). */
      const beginRun = (text: string, opts: { addUser: boolean; kind?: RunKind; auto: boolean; retryOf?: string }) => {
        const s = get();
        const live = isLive;
        // Mock: the client routes Auto. Live: the server does, and tells us with a `route` event.
        const route = opts.kind ? { kind: opts.kind, reason: "" } : s.mode === "auto" ? (live ? { kind: "simple" as RunKind, reason: "" } : routeAuto(text)) : { kind: s.mode as RunKind, reason: "" };
        const files = s.pending.filter((p) => p.status === "ready").map((p) => p.name);
        const now = Date.now();
        const aiId = uid("a");
        const ai = emptyAi(aiId, route.kind, text, opts.auto, { simple: s.simple, team: s.team, runIn: s.runIn });
        const added: Message[] = [];
        if (opts.addUser) added.push({ id: `u${now}`, role: "user", text, files });
        if (!live && opts.auto && s.mode === "auto" && route.reason) added.push({ id: `s${now}`, role: "sys", text: route.reason });
        added.push(ai);

        set({ messages: [...s.messages.filter((m) => m.id !== opts.retryOf), ...added], draft: "", pending: live ? s.pending : [], running: true, allowOnce: false });

        const request: RunRequest = {
          id: aiId, chatId: s.chatId, mode: opts.kind ?? s.mode, kind: route.kind, prompt: text, files,
          simple: s.simple, team: s.team, runIn: s.runIn, planModel: s.planModel,
          budgetUsd: s.allowOnce ? (s.allowOnceCap ?? s.budget) : s.budget, estimateUsd: estimate(), contextPercent: s.context, allowOver: s.allowOnce, retryOf: opts.retryOf,
        };
        const batcher = createEventBatcher((events) => applyEvents(aiId, events));
        const handle = getRunner().start(request, batcher.push);
        active = { handle, batcher };
      };

      /** All starts, including Retry and Think deeper, get a fresh estimate and the same F1/F2/F7 checks. */
      const prepareRun = async (intent: Intent) => {
        const s = get();
        if (s.running || s.preparing || !intent.text.trim()) return;
        if (s.pending.some((file) => file.status === "reading")) { toast("Wait for the attached files to finish reading."); return; }
        const mode = intent.opts.kind ?? s.mode;
        const guard = teamGuardText(mode, s.team, s.runIn);
        if (guard) { toast(guard); return; }
        set({ preparing: true });
        try {
          let usd = estimateCost({ mode, simple: s.simple, team: s.team, runIn: s.runIn });
          if (isLive) usd = (await api.estimate({ mode, chatId: s.chatId, prompt: intent.text, simple: s.simple, team: s.team, runIn: s.runIn, planModel: s.planModel })).usd;
          set({ serverEstimate: isLive ? usd : null });
          if (get().chatId !== s.chatId) return;
          if (get().simple !== s.simple || get().team !== s.team || get().planModel !== s.planModel || get().runIn !== s.runIn) { set({ draft: intent.text }); toast("Settings changed during the estimate. Press Send to check the updated cost."); return; }
          const allowed = get().allowOnce && usd <= (get().allowOnceCap ?? get().budget);
          if (isOverBudget(usd, get().budget, allowed)) {
            pendingIntent = intent;
            set({ draft: intent.text, allowOnce: false, allowOnceCap: null });
            useUiStore.getState().open("cost");
            return;
          }
          pendingIntent = null;
          beginRun(intent.text, intent.opts);
        } catch (e) {
          set({ draft: intent.text });
          toast(`${e instanceof Error ? e.message : "Connection lost"}. Your message is kept as a draft.`);
        } finally { set({ preparing: false }); }
      };

      const control = async (msg: AiMessage, action: () => void | Promise<void>) => {
        patchMessage(msg.id, (m) => ({ ...m, controlError: null }));
        try { await action(); return true; }
        catch (e) {
          const message = e instanceof Error ? e.message : "Connection lost. Please try again.";
          patchMessage(msg.id, (m) => ({ ...m, controlError: message }));
          toast(message);
          return false;
        }
      };

      const refreshContext = async () => {
        if (!isLive) return;
        try {
          const info = await api.context(get().chatId, modelId());
          set({ context: info.percent, contextInfo: info });
        } catch {
          /* the meter keeps its last value */
        }
      };

      return {
        chatId: isLive ? newChatId() : "c1",
        mode: "auto",
        simple: DEFAULT_SIMPLE,
        team: DEFAULT_TEAM,
        runIn: "auto",
        planModel: DEFAULT_SIMPLE.model,
        budget: 0.25,
        allowOnce: false,
        allowOnceCap: null,
        messages: [],
        draft: "",
        running: false,
        context: isLive ? 0 : 64,
        contextInfo: null,
        snoozeAt: 0,
        pending: [],
        serverEstimate: null,
        loadingChat: false,
        preparing: false,

        // F9: the mode switch is locked while an answer runs.
        setMode: (mode) => { if (!get().running && !get().preparing) set({ mode, serverEstimate: null }); },
        // F6: a model that cannot think forces thinking Off.
        setModel: (id) => set((s) => ({ simple: { ...s.simple, model: id, thinking: normalizeThinking(getModel(id), s.simple.thinking) } })),
        patchSimple: (patch) => set((s) => ({ simple: { ...s.simple, ...patch, thinking: normalizeThinking(getModel(patch.model ?? s.simple.model), patch.thinking ?? s.simple.thinking) }, serverEstimate: null })),
        patchTeam: (patch) => set((s) => ({ team: { ...s.team, ...patch } })),
        setRunIn: (runIn) => set({ runIn }),
        setPlanModel: (planModel) => set({ planModel, serverEstimate: null }),
        setBudget: (budget) => set({ budget }),
        stepAgentCount: (delta) => {
          const r = stepAgents(get().team.agents, delta);
          if (r.toast) toast(r.toast); else set((s) => ({ team: { ...s.team, agents: r.value } }));
        },
        stepRoundCount: (delta) => {
          const r = stepRounds(get().team.rounds, delta);
          if (r.toast) toast(r.toast); else set((s) => ({ team: { ...s.team, rounds: r.value } }));
        },
        toggleMixed: (id) => {
          const r = toggleMixedModel(get().team.mixed, id);
          if (r.toast) toast(r.toast); else set((s) => ({ team: { ...s.team, mixed: r.list } }));
        },
        setTeamModel: (id) => set((s) => ({ team: { ...s.team, model: id } })),
        setDraft: (draft) => set({ draft }),
        allowThisOnce: () => set({ allowOnce: true, allowOnceCap: oneQuestionCap(estimate(), get().budget) }),
        setServerEstimate: (usd) => set({ serverEstimate: usd }),

        // Saved preferences from another mode (or an old registry) may name models that no longer exist.
        applyServerDefaults: (cfg, ids) => {
          const ok = (id: string) => ids.includes(id);
          const s = get();
          const d = cfg.defaults;
          set({
            simple: { ...(ok(s.simple.model) ? s.simple : d.simple), tools: { ...(ok(s.simple.model) ? s.simple : d.simple).tools, code: cfg.capabilities.codeSandbox && (ok(s.simple.model) ? s.simple : d.simple).tools.code } },
            planModel: ok(s.planModel) ? s.planModel : (d.planModel ?? d.simple.model),
            team: ok(s.team.model) && s.team.mixed.every(ok) && ok(s.team.composer === "auto" ? s.team.model : s.team.composer) ? s.team : d.team,
          });
        },
        resetConfig: () => {
          if (get().running || get().preparing) { toast("Stop the current answer before resetting the mode setup."); return; }
          const presets = useModelsStore.getState().presets;
          const model = presets.balanced;
          pendingIntent = null;
          const mixed = [...new Set([presets.balanced, presets.best, ...useModelsStore.getState().models.filter((m) => m.available !== false).map((m) => m.id)])].slice(0, 3);
          set({ mode: "auto", simple: { ...DEFAULT_SIMPLE, model, thinking: normalizeThinking(getModel(model), DEFAULT_SIMPLE.thinking) }, planModel: model, team: { ...DEFAULT_TEAM, model, mixed, style: "independent" }, runIn: "auto", budget: 0.25, allowOnce: false, serverEstimate: null });
        },

        send: async (override) => {
          const s = get();
          const text = (override ?? s.draft).trim();
          await prepareRun(pendingIntent?.text === text ? pendingIntent : { text, opts: { addUser: true, auto: s.mode === "auto" } });
        },

        stop: async () => {
          try { await active?.handle.stop(); }
          catch (e) { toast(`Could not stop the server run: ${e instanceof Error ? e.message : "Connection lost"}. Please try Stop again.`); return false; }
          active?.batcher.cancel();
          active = null;
          set((s) => ({
            running: false,
            messages: s.messages.map((m) => (m.role === "ai" && (m.status === "live" || m.status === "waiting") ? { ...m, status: "stopped" as const, permission: null, plan: m.plan ? { ...m.plan, awaitingApproval: false } : null } : m)),
          }));
          return true;
        },

        approvePlan: async () => {
          const msg = get().messages.findLast((m): m is AiMessage => m.role === "ai" && m.status === "waiting");
          if (!msg || !active) return false;
          return control(msg, () => active!.handle.approve(msg.plan?.version));
        },

        // C15: the user edits the plan; the server re-plans and shows it again for approval.
        editPlan: async (note) => {
          const msg = get().messages.findLast((m): m is AiMessage => m.role === "ai" && m.status === "waiting");
          if (!msg || !active?.handle.edit) return false;
          return control(msg, () => active!.handle.edit!(note, msg.plan?.version));
        },
        answerPermission: async (messageId, allow) => {
          const msg = get().messages.find((m): m is AiMessage => m.id === messageId && m.role === "ai");
          if (!msg?.permission || !active?.handle.permission) return false;
          return control(msg, async () => { await active!.handle.permission!(msg.permission!.id, allow); patchMessage(msg.id, (m) => ({ ...m, permission: null, status: m.status === "waiting" ? "live" : m.status })); });
        },
        useTeamForStep: async (messageId, step) => {
          const msg = get().messages.find((m): m is AiMessage => m.id === messageId && m.role === "ai");
          if (!msg || !active?.handle.useTeam) return false;
          return control(msg, () => active!.handle.useTeam!(step));
        },

        retry: async (id) => {
          const msg = get().messages.find((m): m is AiMessage => m.id === id && m.role === "ai");
          if (!msg || get().running) return;
          await prepareRun({ text: msg.prompt, opts: { addUser: false, kind: msg.auto ? undefined : msg.kind, auto: msg.auto, retryOf: id } });
        },

        thinkDeeper: async (id) => {
          const msg = get().messages.find((m): m is AiMessage => m.id === id && m.role === "ai");
          if (!msg || get().running) return;
          set({ mode: "thinker" });
          await prepareRun({ text: msg.prompt, opts: { addUser: true, kind: "thinker", auto: false } });
        },

        openChat: async (id, title) => {
          if (get().running && !await get().stop()) return;
          if (!isLive) { set({ chatId: id }); toast(`Opened "${title}"`); return; }
          set({ loadingChat: true });
          try {
            const got = await api.getChat(id, modelId());
            const fallback = { simple: get().simple, team: get().team, runIn: get().runIn };
            set({
              chatId: id, loadingChat: false, snoozeAt: 0, draft: "",
              messages: (got.messages as Record<string, unknown>[]).map((m) => fromServer(m, fallback)),
              context: got.context.percent, contextInfo: got.context,
              pending: got.files.map((f: ChatFile) => ({ id: f.fingerprint, name: f.name, status: f.ready ? "ready" : "reading", cost: f.cost, pages: f.pages, card: f.card ?? undefined, charts: f.card?.charts.length ?? 0 })),
            });
          } catch (e) {
            set({ loadingChat: false });
            toast(e instanceof Error ? e.message : "Could not open the chat");
          }
        },

        newChat: async () => {
          if (get().running && !await get().stop()) return;
          pendingIntent = null;
          set({ messages: [], context: isLive ? 0 : 6, contextInfo: null, draft: "", pending: [], snoozeAt: 0, chatId: isLive ? newChatId() : "new" });
          useUiStore.getState().close();
          void refreshContext();
        },

        newChatFromSummary: async () => {
          if (get().running || get().loadingChat) return;
          const current = get();
          if (isLive) {
            set({ loadingChat: true });
            try {
              const result = await api.forkChat(current.chatId, modelId(), current.budget);
              await get().openChat(result.chatId, result.title ?? "Continued chat");
              useUiStore.getState().close();
              void useChatsStore.getState().load();
            } catch (e) { toast(e instanceof Error ? e.message : "Could not continue the chat. Your original chat is kept."); }
            finally { set({ loadingChat: false }); }
            return;
          }
          const summary = current.messages.filter((m) => m.role === "user" || m.role === "ai").map((m) => `${m.role}: ${m.text}`).join("\n");
          await get().newChat();
          set({ context: 14, pending: current.pending, messages: [{ id: uid("s"), role: "sys", text: `Continued from the previous chat (demo):\n${summary || "No previous messages."}` }] });
        },

        openImportedChat: (chatId) => {
          useUiStore.getState().close();
          if (isLive && chatId) { void get().openChat(chatId, "Imported chat"); void useChatsStore.getState().load(); return; }
          void get().newChat().then(() => set({ context: 41, messages: [{ id: uid("s"), role: "sys", text: 'Imported "System design review": 142 messages, 3 files, 21 facts. Reading cost $0.' }] }));
        },

        snooze: () => {
          const at = snoozeThreshold(get().context);
          set({ snoozeAt: at });
          toast(`I will ask again at ${at}%`);
        },

        // Part 2 §7: pick old turns -> save facts -> summarize -> check, then swap. Nothing is deleted.
        compact: () => {
          const ui = useUiStore.getState();
          if (isLive) {
            ui.open("compact");
            ui.setCompactStep(0);
            api.compact(get().chatId, modelId(), get().budget, (e) => {
              const notes = chatEvent(e);
              if (notes.length) set((s) => ({ messages: [...s.messages, ...notes] }));
              if (e.type === "done" && e.monthUsd !== undefined) useSettingsStore.setState({ monthSpent: e.monthUsd });
              if (e.type === "error") toast(e.message);
            }).catch((err: Error) => toast(err.message)).finally(() => {
              useUiStore.getState().close();
              set({ snoozeAt: 0 });
            });
            return;
          }
          ui.open("compact");
          ui.setCompactStep(0);
          playSteps(4, 800, ui.setCompactStep, () => {
            useUiStore.getState().close();
            set((s) => ({
              context: 34, snoozeAt: 0,
              messages: [...s.messages, { id: uid("s"), role: "sys", text: "Older messages summarized, 12 facts saved. Nothing deleted; every message is still searchable." }],
            }));
          });
        },

        refreshContext,

        // Mock: fingerprint -> reuse a saved reading ($0) or pay the reader once.
        attachFile: (fileId, textOnly) => {
          const file = DEMO_FILES.find((f) => f.id === fileId);
          if (!file) return;
          const settings = useSettingsStore.getState();
          const key = `${file.id}:${settings.reader}`;
          const seen = !textOnly && settings.parseCache[key];
          const cost = seen || textOnly ? 0 : fileReadingCost(file, settings.reader);
          const entry: PendingFile = { id: file.id, name: file.name, status: seen ? "ready" : "reading", cost, pages: file.pages, charts: file.chart };
          set((s) => ({ pending: [...s.pending.filter((p) => p.id !== file.id), entry] }));
          useUiStore.getState().close();
          if (seen) { toast("Reused the saved reading: $0"); return; }
          setTimeout(() => {
            if (!textOnly) settings.cacheReading(key);
            useSettingsStore.getState().addSpend(cost);
            set((s) => ({ pending: s.pending.map((p) => (p.id === file.id ? { ...p, status: "ready" as const } : p)) }));
            toast(`${file.name} ready, cost ${money(cost)}`);
          }, 1600);
        },

        // Live: the file was uploaded and checked for free; now read it with the chosen reader.
        attachLiveFile: async (up, textOnly, maxCost, readerOverride, pages) => {
          const reader = readerOverride ?? useSettingsStore.getState().reader;
          const entry: PendingFile = { id: up.fingerprint, name: up.name, status: "reading", cost: 0, pages: up.pages, charts: up.kinds.chart };
          set((s) => ({ pending: [...s.pending.filter((p) => p.id !== up.fingerprint), entry] }));
          useUiStore.getState().close();
          try {
            const r = await api.readFile(up.fingerprint, { chatId: get().chatId, reader, textOnly, maxCost, pages });
            set((s) => ({ pending: s.pending.map((p) => (p.id === up.fingerprint ? { ...p, status: "ready" as const, cost: r.cost, card: r.card } : p)) }));
            toast(r.reused ? "Reused the saved reading: $0" : `${up.name} ready, cost ${money(r.cost)}`);
            const u = await api.usage().catch(() => null);
            if (u) useSettingsStore.setState({ monthSpent: u.totalUsd, readingSpent: u.readingUsd ?? useSettingsStore.getState().readingSpent });
            void refreshContext();
          } catch (e) {
            set((s) => ({ pending: s.pending.filter((p) => p.id !== up.fingerprint) }));
            toast(e instanceof ApiError ? e.message : "Could not read the file");
          }
        },

        removePending: (fileId) => {
          if (isLive) api.detachFile(get().chatId, fileId).then(() => refreshContext()).catch(() => undefined);
          set((s) => ({ pending: s.pending.filter((p) => p.id !== fileId) }));
        },
      };
    },
    {
      // Live and mock keep separate preferences: their model ids are different.
      name: isLive ? "mma-chat-config-live" : "mma-chat-config",
      version: 1,
      storage: safeStorage(),
      skipHydration: true,
      // Only user preferences persist; messages and runs are per-session here.
      partialize: ({ mode, simple, team, runIn, planModel, budget }) => ({ mode, simple, team, runIn, planModel, budget }),
    },
  ),
);

