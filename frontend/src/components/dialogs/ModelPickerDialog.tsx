"use client";

import { useEffect, useMemo, useState } from "react";
import { money } from "@/domain/format";
import { modelDisabledReason } from "@/domain/guardrails";
import type { ModelInfo, Provider } from "@/domain/types";
import { isLive } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { useModelsStore } from "@/store/modelsStore";
import { useUiStore, type PickTarget } from "@/store/uiStore";
import { Modal, ModalBody } from "../ui/Modal";
import { Pill } from "../ui/Pill";
import { Segmented } from "../ui/Segmented";

const TITLES: Record<PickTarget, string> = {
  main: "Choose a model",
  plan: "Plan writer model",
  team: "Model for the agents",
  mixed: "Pick 2 to 5 models",
  composer: "Composer model",
};

type Caps = { tools: boolean; vision: boolean; thinking: boolean };

/** Per-million-token price, so cost is visible before choosing. */
const priceLine = (m: ModelInfo) =>
  m.priceIn != null && m.priceOut != null ? `${m.priceKnown === false ? "price unknown" : `${money(m.priceIn)} in / ${money(m.priceOut)} out per 1M tokens`}` : "";

/** Search, provider filter, must-have filter. Rows that do not fit the task are grey with the reason (F4, F5). */
export default function ModelPickerDialog() {
  const target = useUiStore((s) => s.pickTarget);
  const open = useUiStore((s) => s.open);
  const mode = useChatStore((s) => s.mode);
  const simple = useChatStore((s) => s.simple);
  const team = useChatStore((s) => s.team);
  const pending = useChatStore((s) => s.pending);
  const setModel = useChatStore((s) => s.setModel);
  const planModel = useChatStore((s) => s.planModel);
  const setPlanModel = useChatStore((s) => s.setPlanModel);
  const setTeamModel = useChatStore((s) => s.setTeamModel);
  const toggleMixed = useChatStore((s) => s.toggleMixed);
  const patchTeam = useChatStore((s) => s.patchTeam);
  const models = useModelsStore((s) => s.models);
  const providers = useModelsStore((s) => s.providers);
  const search = useModelsStore((s) => s.search);

  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState<Provider | "all">("all");
  const [caps, setCaps] = useState<Caps>({ tools: false, vision: false, thinking: false });
  const [found, setFound] = useState<ModelInfo[]>([]);

  // Live: typing searches the WHOLE registry (hundreds of models), not just the curated cheap list.
  useEffect(() => {
    if (!isLive || !query.trim()) { setFound([]); return; }
    let current = true;
    const t = setTimeout(() => { void search(query).then((rows) => { if (current) setFound(rows); }).catch(() => { if (current) setFound([]); }); }, 250);
    return () => { current = false; clearTimeout(t); };
  }, [query, search]);

  const needs = useMemo(() => ({
    tools: target === "main" && Object.values(simple.tools).some(Boolean),
    vision: pending.some((p) => (p.charts ?? 0) > 0),
  }), [target, mode, simple.tools, pending]);

  const rows = useMemo(() => {
    const q = query.toLowerCase();
    const base = isLive && query.trim() ? found : models;
    return base.filter((m) =>
      (provider === "all" || m.provider === provider) &&
      (!caps.tools || m.tools) && (!caps.vision || m.vision) && (!caps.thinking || m.thinking) &&
      (isLive || !q || `${m.name} ${m.company}`.toLowerCase().includes(q)));
  }, [query, provider, caps, models, found]);

  const isSelected = (m: ModelInfo) =>
    target === "mixed" ? team.mixed.includes(m.id) : target === "composer" ? team.composer === m.id : target === "team" ? team.model === m.id : target === "plan" ? planModel === m.id : simple.model === m.id;

  const pick = (id: string) => {
    // a model found by search may not be in the curated list yet: register it so names and prices resolve
    const m = rows.find((r) => r.id === id);
    if (m && !models.some((x) => x.id === id)) useModelsStore.setState({ models: [...models, m] });
    if (target === "mixed") toggleMixed(id);
    else if (target === "composer") patchTeam({ composer: id });
    else if (target === "team") setTeamModel(id);
    else if (target === "plan") setPlanModel(id);
    else setModel(id);
  };

  const back = () => open("setup");
  const note = needs.tools ? "Tools are on, so models without tools are greyed out." : needs.vision ? "Your file has charts, so models without vision are greyed out." : "";
  const down = Object.entries(providers).filter(([, v]) => !v.ok);

  return (
    <Modal title={TITLES[target]} onClose={back} footer={<button type="button" className="btn primary" onClick={back}>Done</button>}>
      <ModalBody>
        <input className="input" aria-label="Search models" placeholder={isLive ? "Search every model by name or company" : "Search by name or company"} value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="row">
          <Segmented<Provider | "all">
            label="Provider"
            value={provider}
            onChange={setProvider}
            options={[{ value: "all", label: "All" }, { value: "openrouter", label: "OpenRouter" }, { value: "nvidia", label: "NVIDIA" }]}
          />
          {(["tools", "vision", "thinking"] as const).map((c) => (
            <button key={c} type="button" className={`seg-btn${caps[c] ? " on" : ""}`} style={{ border: "1px solid var(--line-strong)" }} aria-pressed={caps[c]} onClick={() => setCaps({ ...caps, [c]: !caps[c] })}>
              {c[0].toUpperCase() + c.slice(1)}
            </button>
          ))}
        </div>
        {note && <span className="hint warn">{note}</span>}
        {down.map(([name, v]) => <span className="hint warn" key={name} role="status">{name === "nvidia" ? "NVIDIA" : "OpenRouter"} models are unavailable: {v.reason}. Calls fall back to another provider.</span>)}

        <div className="list">
          {target === "composer" && (
            <button type="button" className={`mrow${team.composer === "auto" ? " on" : ""}`} aria-pressed={team.composer === "auto"} onClick={() => patchTeam({ composer: "auto" })}>
              <span className="mrow-main"><span className="strong">Auto (strongest in budget)</span><span className="hint">Default: the strongest model that fits the budget</span></span>
              {team.composer === "auto" && <Pill tone="green">Selected</Pill>}
            </button>
          )}
          {rows.map((m) => {
            const why = modelDisabledReason(m, needs);
            const on = isSelected(m);
            const features = [m.tools && "Tools", m.vision && "Vision", m.thinking && "Thinking"].filter(Boolean).join(", ");
            return (
              <button key={m.id} type="button" className={`mrow${on ? " on" : ""}${why ? " off" : ""}`} aria-pressed={on} disabled={!!why} onClick={() => pick(m.id)}>
                <span className="mrow-main">
                  <span className="strong">{m.name}</span>
                  <span className="hint">{m.company} · {m.provider === "nvidia" ? "NVIDIA" : "OpenRouter"}{features ? ` · ${features}` : ""}</span>
                  {priceLine(m) && <span className="hint">{priceLine(m)}</span>}
                  <span className="hint">Speed: {m.speed ?? "not measured yet"}</span>
                  {why && <span className="hint warn">{why}</span>}
                </span>
                <span className="mrow-side">
                  <span className="strong">{m.costLevel}</span>
                  {on && <Pill tone="green">Selected</Pill>}
                </span>
              </button>
            );
          })}
          {rows.length === 0 && <span className="hint">No model matches. Clear a filter.</span>}
        </div>
      </ModalBody>
    </Modal>
  );
}
