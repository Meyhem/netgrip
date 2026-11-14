import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { ApiError, getJSON, patchJSON, postJSON, putJSON } from "../api/client";
import type { OfferedModel, RoutingSort, EffortBudget, EffortName, KeyStatus, ModelPrice, PresetName, Settings as SettingsT, Storage, Pools, Tier } from "../api/types";
import { bytes, money } from "../lib/format";
import { usePoll } from "../lib/usePoll";
import { Banner } from "../ui/Banner";
import { Button } from "../ui/Button";
import { Input, KeyField, NumberField, parseMoney, Seg, Toggle } from "../ui/Field";
import { ModelCombo, type PickableModel } from "../ui/ModelCombo";
import { browserHealthText } from "../ui/TopBar";
import { Page } from "./InvestigationRoute";
import { parseDomains, PRESET_WORD, TIER_WORD } from "./NewInvestigation";

const SECTIONS = [
  ["keys", "Keys"], ["models", "Models"], ["effort", "Effort"], ["spend", "Spending"],
  ["sources", "Sources"], ["capacity", "Capacity"], ["storage", "Storage"],
] as const;

const EFFORT_COLS: [keyof EffortBudget, string, string][] = [
  ["max_depth", "Max depth", "max depth"],
  ["max_nodes", "Max nodes", "max nodes"],
  ["sources_per_node", "Sources / node", "sources per node"],
  ["parallel", "In parallel", "in parallel"],
  ["sources_to_confirm", "Sources to confirm", "sources to confirm"],
];
const PRESETS: PresetName[] = ["economy", "balanced", "maximum"];
const TIER_ORDER: Tier[] = ["strong", "standard", "fast", "verifier"];
const SORT_WORD: Record<RoutingSort, string> = {
  default: "OpenRouter's balance of price and uptime",
  price: "Lowest price",
  throughput: "Highest throughput",
  latency: "Lowest latency",
};
const isOpenRouter = (url: string) => { try { return /(^|\.)openrouter\.ai$/.test(new URL(url).hostname); } catch { return false; } };
const integer = (s: string) => (/^\s*\d+\s*$/.test(s) && Number(s) > 0 ? Number(s) : null);
const price = (s: string) => (/^\s*\d+(\.\d+)?\s*$/.test(s) && Number(s) > 0 ? Number(s) : null);

type Patch = (field: string, partial: Record<string, unknown>) => Promise<void>;

function Row({ label, hint, saved, error, children }: { label: string; hint?: ReactNode; saved?: boolean; error?: string | null; children: ReactNode }) {
  return (
    <div className="ng-form-row">
      <div className="ng-col" style={{ gap: 2 }}>
        <span className="ng-field__label">{label}</span>
        {error ? <span className="ng-field__hint is-error">{error}</span>
          : <span className="ng-field__hint">{saved ? "Saved" : hint}</span>}
      </div>
      <div className="ng-col">{children}</div>
    </div>
  );
}

function Section({ id, title, intro, children, panel = true }: { id: string; title: string; intro?: ReactNode; children: ReactNode; panel?: boolean }) {
  return (
    <section className="ng-col" id={id}>
      <h2 className="ng-title">{title}</h2>
      {intro && <p className="ng-small ng-muted">{intro}</p>}
      {panel ? <div className="ng-panel form-panel">{children}</div> : children}
    </section>
  );
}

export function Settings() {
  const { data: loaded, error } = usePoll(() => getJSON<SettingsT>("/api/settings"), 3000, { untilLoaded: true });
  const { data: pools } = usePoll(() => getJSON<Pools>("/api/system/pools"), 5000);
  const { data: storage } = usePoll(() => getJSON<Storage>("/api/system/storage"), 10000);
  // What the provider offers; absent when it cannot be reached, and the pickers then offer only
  // the models already listed here.
  const { data: offered } = usePoll(() => getJSON<OfferedModel[]>("/api/settings/models/available"), 30000, { untilLoaded: true });
  const [s, setS] = useState<SettingsT | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [failed, setFailed] = useState<{ field: string; message: string } | null>(null);
  const savedTimer = useRef<ReturnType<typeof setTimeout>>();
  const { hash } = useLocation();
  const [rebuilt, setRebuilt] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [resetKey, setResetKey] = useState(0); // bumped when the server refuses a change

  useEffect(() => { if (loaded) setS(loaded); }, [loaded]);
  const ready = s != null;
  useEffect(() => {
    if (ready && hash) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [ready, hash]);

  if (!s) {
    return <Page>{error != null && <Banner tone="warn" title="Netgrip cannot reach its service.">Retrying every 3 seconds. Nothing is lost.</Banner>}</Page>;
  }

  const patch: Patch = async (field, partial) => {
    setFailed(null);
    try {
      setS(await patchJSON<SettingsT>("/api/settings", partial));
      setSaved(field);
      clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => setSaved(null), 2000);
    } catch (e) {
      setFailed({ field, message: e instanceof ApiError && e.status === 422 ? "Not saved: the value is out of range." : "Not saved: Netgrip could not be reached." });
      setResetKey((k) => k + 1); // remount the inputs so they show the server's value again
    }
  };
  const replaceKey = (name: "model" | "search") => async (value: string) => {
    const status = await putJSON<KeyStatus>(`/api/settings/keys/${name}`, { value });
    setS((old) => (old ? { ...old, keys: { ...old.keys, [name]: status } } : old));
  };
  const err = (field: string) => (failed?.field === field ? failed.message : null);
  const on = hash.slice(1) || "keys";
  const preset = s.presets[s.default_preset];
  const tierOf = (id: string) => (Object.keys(preset) as Tier[]).filter((t) => preset[t] === id).map((t) => TIER_WORD[t]).join(", ") || "–";
  const offeredById = new Map((offered ?? []).map((m) => [m.id, m]));
  const known = new Set(s.models.map((m) => m.id));
  /** Entry for a model picked from the provider's list: its price comes along. */
  const entryFor = (id: string): ModelPrice => {
    const o = offeredById.get(id);
    const priced = o?.price_in_per_m != null && o?.price_out_per_m != null;
    return { id, price_in_per_m: o?.price_in_per_m ?? null, price_out_per_m: o?.price_out_per_m ?? null, price_source: priced ? "provider" : null };
  };
  const pickTier = (p: PresetName, t: Tier, id: string) =>
    patch(`tier-${p}-${t}`, { presets: { [p]: { [t]: id } }, ...(known.has(id) ? {} : { models: [...s.models, entryFor(id)] }) });
  // Everything the pickers offer: the provider's list, plus models already listed here that the
  // provider no longer offers (or all of them when its list could not be fetched).
  const pickable: PickableModel[] = [...(offered ?? []), ...s.models.filter((m) => !offeredById.has(m.id))];
  const openRouter = isOpenRouter(s.model_endpoint);
  const addModel = (id: string) => patch("add-model", { models: [...s.models, entryFor(id)] });
  const setModel = (i: number, change: Partial<ModelPrice>) =>
    patch(`model-${i}`, { models: s.models.map((m, j) => (j === i ? { ...m, ...change, price_source: "you" } : m)) });

  return (
    <Page>
      <h1 className="ng-display">Settings</h1>
      <div className="ng-settings">
        <nav>
          {SECTIONS.map(([id, word]) => <a key={id} href={`#${id}`} className={on === id ? "is-on" : ""}>{word}</a>)}
        </nav>
        <div className="ng-col settings-sections" key={resetKey}>
          <Section id="keys" title="Keys" intro="Keys are stored in Netgrip's database on this machine. They can be replaced but never shown again. Treat the database file as a secret.">
            <Row label="Model provider" hint="OpenRouter, or any OpenAI-compatible endpoint." saved={saved === "endpoint"} error={err("endpoint")}>
              <TextSetting aria-label="Endpoint" value={s.model_endpoint} validate={(v) => (v.trim() ? null : "Enter the endpoint URL.")}
                onCommit={(v) => patch("endpoint", { model_endpoint: v.trim() })} />
              <KeyField label="Model provider key" status={s.keys.model} onReplace={replaceKey("model")} />
            </Row>
            <Row label="Web search" hint="Tavily.">
              <KeyField label="Web search key" status={s.keys.search} onReplace={replaceKey("search")} />
            </Row>
          </Section>

          <Section id="models" title="Models" panel={false}>
            <div className="ng-row">
              <span className="ng-field__label">Default preset</span>
              <Seg aria-label="Default preset" options={PRESETS} labels={PRESET_WORD} value={s.default_preset}
                onChange={(p) => patch("preset", { default_preset: p })} />
              <span className="ng-small ng-muted">{saved === "preset" ? "Saved" : "Each investigation can override any tier."}</span>
            </div>
            <div className="ng-panel">
              <table className="ng-table">
                <thead><tr><th>Tier</th>{PRESETS.map((p) => <th key={p}>{PRESET_WORD[p]}</th>)}</tr></thead>
                <tbody>
                  {TIER_ORDER.map((t) => (
                    <tr key={t}>
                      <td><span className="ng-heading">{TIER_WORD[t]}</span></td>
                      {PRESETS.map((p) => (
                        <td key={p}>
                          <ModelCombo label={`${PRESET_WORD[p]} ${TIER_WORD[t]} model`} value={s.presets[p][t]}
                            models={pickable} onPick={(id) => pickTier(p, t, id)} />
                          {saved === `tier-${p}-${t}` && <div className="ng-small ng-muted">Saved</div>}
                          {err(`tier-${p}-${t}`) && <div className="ng-small ng-danger">{err(`tier-${p}-${t}`)}</div>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="ng-panel">
              <table className="ng-table">
                <thead><tr><th>Model</th><th>Tier in {PRESET_WORD[s.default_preset]}</th><th className="num">$ / M input</th><th className="num">$ / M output</th><th>Price source</th></tr></thead>
                <tbody>
                  {s.models.map((m, i) => {
                    const unpriced = m.price_in_per_m == null || m.price_out_per_m == null;
                    return (
                      <tr key={m.id}>
                        <td className="ng-mono">{m.id}</td>
                        <td>{tierOf(m.id)}</td>
                        <td className="is-num">
                          <NumberField className="price" aria-label={`${m.id} input price`} placeholder="–" value={m.price_in_per_m} parse={price}
                            format={(n) => n.toFixed(2)} error={m.price_in_per_m == null} onCommit={(n) => setModel(i, { price_in_per_m: n })} />
                        </td>
                        <td className="is-num">
                          <NumberField className="price" aria-label={`${m.id} output price`} placeholder="–" value={m.price_out_per_m} parse={price}
                            format={(n) => n.toFixed(2)} error={m.price_out_per_m == null} onCommit={(n) => setModel(i, { price_out_per_m: n })} />
                        </td>
                        <td>
                          {saved === `model-${i}` ? <span className="ng-small ng-muted">Saved</span>
                            : err(`model-${i}`) ? <span className="ng-small ng-danger">{err(`model-${i}`)}</span>
                              : unpriced ? <span className="ng-small ng-warn">No price on record. Enter one, or spend will be approximate.</span>
                                : <span className="ng-small ng-muted">{m.price_source ?? "–"}</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="ng-row">
              <div className="add-model">
                <ModelCombo label="Add a model" value="" placeholder={!offered ? "The provider's models could not be loaded" : offered.length ? `Search ${offered.length.toLocaleString("en-US")} models from the provider…` : "The provider lists no models"}
                  disabled={!offered?.length} models={(offered ?? []).filter((m) => !known.has(m.id))} onPick={addModel} />
              </div>
              <span className="ng-small ng-muted">{saved === "add-model" ? "Saved" : err("add-model") ?? "Priced from the provider's list."}</span>
            </div>
            <div className="ng-panel form-panel">
              <Row label="Provider routing" saved={saved === "routing-sort"} error={err("routing-sort")}
                hint={openRouter ? "OpenRouter serves most models from several providers. This picks which one answers each call." : "Only OpenRouter routes between providers. Your endpoint ignores these settings."}>
                <select className="ng-select routing-select" aria-label="Provider routing" value={s.model_routing.sort} disabled={!openRouter}
                  onChange={(e) => patch("routing-sort", { model_routing: { sort: e.target.value } })}>
                  {(Object.keys(SORT_WORD) as RoutingSort[]).map((k) => <option key={k} value={k}>{SORT_WORD[k]}</option>)}
                </select>
              </Row>
              <Row label="Data policy" saved={saved === "routing-data"} error={err("routing-data")}
                hint="Fewer providers can answer, so some models may become unavailable.">
                <Toggle on={s.model_routing.deny_data_collection}
                  onChange={(v) => openRouter && patch("routing-data", { model_routing: { deny_data_collection: v } })}>
                  Only providers that do not store or train on prompts
                </Toggle>
                <Toggle on={s.model_routing.zero_retention}
                  onChange={(v) => openRouter && patch("routing-data", { model_routing: { zero_retention: v } })}>
                  Only providers with zero data retention
                </Toggle>
              </Row>
            </div>
          </Section>

          <Section id="effort" title="Effort" panel={false} intro="What Low, Medium and High mean. These are starting values, to be tuned after real runs.">
            <div className="ng-panel">
              <table className="ng-table">
                <thead><tr><th>Level</th>{EFFORT_COLS.map(([, head]) => <th key={head}>{head}</th>)}</tr></thead>
                <tbody>
                  {(["Low", "Medium", "High"] as EffortName[]).map((level) => (
                    <tr key={level}>
                      <td>
                        <span className="ng-heading">{level}</span>{" "}
                        {s.default_effort === level && <span className="ng-tag">DEFAULT</span>}
                        {saved === `effort-${level}` && <div className="ng-small ng-muted">Saved</div>}
                        {err(`effort-${level}`) && <div className="ng-small ng-danger">{err(`effort-${level}`)}</div>}
                      </td>
                      {EFFORT_COLS.map(([key, , words]) => (
                        <td key={key}>
                          <NumberField className="count" aria-label={`${level} ${words}`} value={s.effort[level][key]} parse={integer}
                            onCommit={(n) => patch(`effort-${level}`, { effort: { [level]: { [key]: n } } })} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="spend" title="Spending">
            <Row label="Default spending limit" hint="Per investigation. Reaching it pauses and asks you." saved={saved === "limit"} error={err("limit")}>
              <NumberField className="money" aria-label="Default limit" value={s.spending_limit_usd} parse={parseMoney} format={money}
                onCommit={(n) => patch("limit", { spending_limit_usd: n })} />
            </Row>
            <Row label="When a service stops responding" hint="How long Netgrip retries before it pauses the investigation." saved={saved === "retry"} error={err("retry")}>
              <select className="ng-select wide-select" aria-label="Retry window" value={s.retry_before_pause_seconds}
                onChange={(e) => patch("retry", { retry_before_pause_seconds: Number(e.target.value) })}>
                {withCurrent([60, 300, 900, 1800], s.retry_before_pause_seconds).map((n) => <option key={n} value={n}>Retry for {n % 60 ? `${n} seconds` : `${n / 60} minute${n === 60 ? "" : "s"}`}</option>)}
              </select>
            </Row>
          </Section>

          <Section id="sources" title="Sources">
            <Row label="Always exclude" hint="Applied to every new investigation and listed in its report." saved={saved === "excluded"} error={err("excluded")}>
              <TextSetting aria-label="Excluded domains" value={s.excluded_domains.join(", ")}
                validate={(v) => { const d = parseDomains(v); return d.bad ? `"${d.bad}" is not a domain. Write it as ${d.bad.includes(".") ? "name.tld" : `${d.bad}.com`}.` : null; }}
                onCommit={(v) => patch("excluded", { excluded_domains: parseDomains(v).domains })} />
            </Row>
            <Row label="Reuse fetched pages" hint="Pages are shared between investigations while fresh. Claims never are." saved={saved === "reuse"} error={err("reuse")}>
              <select className="ng-select wide-select" aria-label="Freshness" value={s.page_reuse} onChange={(e) => patch("reuse", { page_reuse: e.target.value })}>
                <option value="1d">Up to 1 day old</option>
                <option value="always_refetch">Always fetch again</option>
              </select>
            </Row>
            <Row label="Per-site politeness" hint="Slows requests to one site so your address is not blocked." saved={saved === "polite"} error={err("polite")}>
              <select className="ng-select wide-select" aria-label="Politeness" value={s.politeness_seconds} onChange={(e) => patch("polite", { politeness_seconds: Number(e.target.value) })}>
                {withCurrent([1, 2, 5, 10], s.politeness_seconds).map((n) => <option key={n} value={n}>1 request every {n} second{n === 1 ? "" : "s"}</option>)}
              </select>
            </Row>
          </Section>

          <Section id="capacity" title="Capacity" intro="Shared by all running investigations on this machine.">
            {([
              ["investigations", "Investigations in parallel", undefined, null],
              ["model_calls", "Model calls at once", undefined, pools && `now: ${pools.models.in_use} in use`],
              ["searches", "Searches at once", undefined, pools && `now: ${pools.search.in_use} in use`],
              ["browser_pages", "Browser pages at once", "Each uses memory. 6 suits a 16 GB machine.", pools && `now: ${browserHealthText(pools.browsers)}`],
            ] as const).map(([key, label, hint, now]) => (
              <Row key={key} label={label} hint={hint} saved={saved === `cap-${key}`} error={err(`cap-${key}`)}>
                <div className="ng-row">
                  <NumberField className="count" aria-label={label} value={s.capacity[key]} parse={integer}
                    onCommit={(n) => patch(`cap-${key}`, { capacity: { [key]: n } })} />
                  {now && <span className="ng-mono ng-muted">{now}</span>}
                </div>
              </Row>
            ))}
          </Section>

          <Section id="storage" title="Storage">
            <Row label="On disk" hint="Nothing is removed until you delete an investigation.">
              {storage && (
                <>
                  <span className="ng-mono">{bytes(storage.total_bytes)} · {storage.investigations} investigation{storage.investigations === 1 ? "" : "s"} · {storage.pages.toLocaleString("en-US")} pages</span>
                  <span className="ng-mono ng-muted">{storage.data_dir}</span>
                </>
              )}
            </Row>
            <Row label="Repair" hint="Rebuilds the current state from the event history. Safe; nothing is deleted.">
              <div className="ng-row">
                <Button sent={rebuilding} sentLabel="Rebuilding…" onClick={async () => {
                  setRebuilding(true);
                  setRebuilt(null);
                  try {
                    const r = await postJSON<{ replayed: number }>("/api/system/rebuild");
                    setRebuilt(`Rebuilt from ${r.replayed.toLocaleString("en-US")} events.`);
                  } catch {
                    setRebuilt("Not rebuilt: Netgrip could not be reached.");
                  } finally {
                    setRebuilding(false);
                  }
                }}>Rebuild state from history</Button>
                {rebuilt && <span className="ng-mono ng-muted">{rebuilt}</span>}
              </div>
            </Row>
          </Section>
        </div>
      </div>
    </Page>
  );
}

const withCurrent = (options: number[], current: number) => (options.includes(current) ? options : [...options, current].sort((a, b) => a - b));

/** A text input that commits on blur or Enter; an invalid value is marked and sends nothing. */
function TextSetting({ value, onCommit, validate, ...rest }: {
  value: string; onCommit: (v: string) => void; validate: (v: string) => string | null; "aria-label": string;
}) {
  const [text, setText] = useState(value);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setText(value); setError(null); }, [value]);
  const commit = () => {
    const e = validate(text);
    setError(e);
    if (!e && text !== value) onCommit(text);
  };
  return (
    <>
      <Input mono {...rest} error={error != null} value={text} onChange={(e) => setText(e.target.value)} onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); }} />
      {error && <span className="ng-field__hint is-error">{error}</span>}
    </>
  );
}
