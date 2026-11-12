import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { createInvestigation, getJSON, postJSON, sendCommand } from "../api/client";
import type { EffortBudget, EffortName, Estimate, InvestigationSettings, PageReuse, PresetName, Settings, Snapshot, Tier } from "../api/types";
import { money } from "../lib/format";
import { usePoll } from "../lib/usePoll";
import { Banner } from "../ui/Banner";
import { Button } from "../ui/Button";
import { Field, Input, NumberField, parseMoney, Seg } from "../ui/Field";
import { Page } from "./InvestigationRoute";
import { PromptBox } from "./PromptBox";

const EFFORTS: EffortName[] = ["Low", "Medium", "High"];
const PRESETS: PresetName[] = ["economy", "balanced", "maximum"];
export const PRESET_WORD: Record<PresetName, string> = { economy: "Economy", balanced: "Balanced", maximum: "Maximum quality" };
const TIERS: Tier[] = ["strong", "standard", "fast", "verifier"];
export const TIER_WORD: Record<Tier, string> = { strong: "Strong", standard: "Standard", fast: "Fast", verifier: "Verifier" };
export const TIER_DOES: Record<Tier, string> = {
  strong: "Orchestrator, final synthesis, judging contradictions",
  standard: "The agent inside each node",
  fast: "Reading pages, extracting claims",
  verifier: "Independent re-check of important claims",
};

export function effortLine(e: EffortBudget): string {
  const src = e.sources_to_confirm === 1 ? "1 independent source to confirm" : `${e.sources_to_confirm} independent sources to confirm`;
  return `depth ${e.max_depth} · ${e.max_nodes} nodes · ${e.sources_per_node} sources/node · ${e.parallel} in parallel · ${src}`;
}

const family = (model: string) => model.split("/")[0];
const range = (r: { low_usd: number; high_usd: number }) => `${money(r.low_usd)} – ${money(r.high_usd)}`;

/** "reddit.com, quora" → the list, or the first entry that is not a domain. */
export function parseDomains(text: string): { domains: string[]; bad: string | null } {
  const domains = text.split(/[,\s]+/).map((d) => d.trim().toLowerCase()).filter(Boolean);
  const bad = domains.find((d) => !/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(d)) ?? null;
  return { domains, bad };
}

type Choice = Omit<InvestigationSettings, "effort_budget">;

function defaultsFrom(s: Settings): Choice {
  return {
    effort: s.default_effort,
    preset: s.default_preset,
    tiers: { ...s.presets[s.default_preset] },
    excluded_domains: [...s.excluded_domains],
    prefer: "none",
    page_reuse: s.page_reuse,
    spending_limit_usd: s.spending_limit_usd,
  };
}

export function NewInvestigation({ draft }: { draft?: Snapshot["investigation"] }) {
  const { data: settings, error } = usePoll(() => getJSON<Settings>("/api/settings"), 3000, { untilLoaded: true });
  if (!settings) {
    return (
      <Page>
        {error != null && <Banner tone="warn" title="Netgrip cannot reach its service.">Retrying every 3 seconds. Nothing is lost.</Banner>}
      </Page>
    );
  }
  return <Form settings={settings} draft={draft} />;
}

function Form({ settings, draft }: { settings: Settings; draft?: Snapshot["investigation"] }) {
  const navigate = useNavigate();
  const location = useLocation();
  const saved = draft != null; // a saved draft cannot be edited until planning exists
  const [prompt, setPrompt] = useState<string>(draft?.prompt ?? (location.state as { prompt?: string } | null)?.prompt ?? "");
  const [c, setC] = useState<Choice>(() => (draft ? { ...defaultsFrom(settings), ...draft.settings } : defaultsFrom(settings)));
  const [domainsText, setDomainsText] = useState(c.excluded_domains.join(", "));
  const [limitValid, setLimitValid] = useState(true);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [sending, setSending] = useState<"draft" | "plan" | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  // One id for this form: repeated clicks create one investigation. A saved draft keeps its own.
  const idRef = useRef(draft?.id ?? crypto.randomUUID());
  const ids = { excl: useId(), pref: useId(), reuse: useId(), limit: useId() };

  const set = <K extends keyof Choice>(k: K, v: Choice[K]) => setC((old) => ({ ...old, [k]: v }));
  const budget = settings.effort[c.effort];
  const domains = parseDomains(domainsText);

  useEffect(() => {
    let live = true;
    postJSON<Estimate>("/api/estimate", { effort: c.effort, tiers: c.tiers })
      .then((e) => { if (live) setEstimate(e); })
      .catch(() => { if (live) setEstimate(null); });
    return () => { live = false; };
  }, [c.effort, c.tiers]);

  const modelOptions = useMemo(() => {
    const known = settings.models.map((m) => m.id);
    return Array.from(new Set([...known, ...Object.values(c.tiers)]));
  }, [settings.models, c.tiers]);

  const noKey = !settings.keys.model.set;
  const valid = prompt.trim() !== "" && limitValid && domains.bad == null;
  const unpriced = new Set(estimate?.unpriced_models ?? []);
  const sameFamily = family(c.tiers.verifier) === family(c.tiers.strong);

  const submit = async (kind: "draft" | "plan") => {
    if (sending || !valid) return;
    setSending(kind);
    setFailed(null);
    try {
      if (!saved) await createInvestigation(idRef.current, prompt, { ...c, excluded_domains: domains.domains });
      if (kind === "plan") {
        // Draft → Planning is recorded with the command; the plan itself arrives on the stream.
        await sendCommand(idRef.current, "draft_plan");
        navigate(`/investigations/${idRef.current}`, { state: { drafting: true } });
      } else {
        navigate("/");
      }
    } catch (e) {
      setFailed(e instanceof Error ? e.message : "Not saved.");
      setSending(null);
    }
  };

  return (
    <main className="ng-page">
      <div className="ng-page__in new-investigation">
        <div className="ng-col ng-col--loose">
          <div className="ng-col">
            <span className="ng-mono ng-muted">Investigations / {saved ? "Draft" : "New"}</span>
            <h1 className="ng-display">What should Netgrip find out?</h1>
          </div>
          <PromptBox value={prompt} onChange={setPrompt} autoFocus={!saved} />
          <Field label="Effort" hint="These values are provisional. Change them in Settings → Effort.">
            <div className="ng-row">
              <Seg aria-label="Effort" options={EFFORTS} value={c.effort} onChange={(v) => set("effort", v)} />
              <span className="ng-mono ng-muted">{effortLine(budget)}</span>
            </div>
          </Field>
          <Field label="Models">
            <div className="ng-row">
              <Seg aria-label="Models preset" options={PRESETS} labels={PRESET_WORD} value={c.preset}
                onChange={(p) => setC((old) => ({ ...old, preset: p, tiers: { ...settings.presets[p] } }))} />
              <span className="ng-small ng-muted">Preset from Settings. Override any tier for this run.</span>
            </div>
            <div className="ng-panel">
              <table className="ng-table">
                <thead><tr><th>Tier</th><th>Model</th><th className="num">Share of cost</th></tr></thead>
                <tbody>
                  {TIERS.map((t) => (
                    <tr key={t}>
                      <td><span className="ng-heading">{TIER_WORD[t]}</span><div className="ng-small ng-muted">{TIER_DOES[t]}</div></td>
                      <td>
                        <select className="ng-select ng-input--mono" aria-label={`${TIER_WORD[t]} model`} value={c.tiers[t]}
                          onChange={(e) => set("tiers", { ...c.tiers, [t]: e.target.value })}>
                          {modelOptions.map((m) => <option key={m} value={m}>{m}</option>)}
                        </select>
                        {unpriced.has(c.tiers[t]) && (
                          <div className="ng-field__hint ng-warn">
                            No price on record. The spending limit will be approximate. Set one in <Link to="/settings#models">Settings → Models</Link>.
                          </div>
                        )}
                        {t === "verifier" && (sameFamily
                          ? <div className="ng-field__hint ng-warn">Same model family as Strong. It may repeat the same mistake instead of catching it.</div>
                          : <div className="ng-field__hint">A different model family from Strong, so it does not repeat the same mistake.</div>)}
                      </td>
                      <td className="is-num">{estimate && !unpriced.has(c.tiers[t]) ? `≈ ${Math.round(estimate.per_tier[t].share * 100)}%` : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Field>
          <div className="two-col">
            <Field label="Exclude domains" htmlFor={ids.excl}
              error={domains.bad ? `"${domains.bad}" is not a domain. Write it as ${domains.bad.includes(".") ? "name.tld" : `${domains.bad}.com`}.` : undefined}
              hint="Listed in the report as a limit.">
              <Input id={ids.excl} mono error={domains.bad != null} value={domainsText} onChange={(e) => setDomainsText(e.target.value)} />
            </Field>
            <Field label="Prefer" htmlFor={ids.pref}>
              <select id={ids.pref} className="ng-select" value={c.prefer} onChange={(e) => set("prefer", e.target.value as Choice["prefer"])}>
                <option value="none">No preference</option>
                <option value="primary">Primary sources only</option>
              </select>
            </Field>
            <Field label="Reuse fetched pages up to" htmlFor={ids.reuse} hint='Choose "Always fetch again" for questions about current events.'>
              <select id={ids.reuse} className="ng-select" value={c.page_reuse} onChange={(e) => set("page_reuse", e.target.value as PageReuse)}>
                <option value="1d">1 day old{settings.page_reuse === "1d" ? " (default)" : ""}</option>
                <option value="always_refetch">Always fetch again{settings.page_reuse === "always_refetch" ? " (default)" : ""}</option>
              </select>
            </Field>
            <Field label="Spending limit" htmlFor={ids.limit}
              error={limitValid ? undefined : "Write an amount in dollars, such as $5.00."}
              hint="Reaching it pauses and asks you. Planning counts towards it.">
              <NumberField id={ids.limit} value={c.spending_limit_usd} parse={parseMoney} format={money}
                onCommit={(n) => set("spending_limit_usd", n)} onValidity={setLimitValid} />
            </Field>
          </div>
        </div>
        <aside className="ng-panel sticky">
          <div className="ng-panel__head"><span className="ng-label">Before you start</span></div>
          <div className="ng-panel__body ng-col ng-col--loose">
            <div className="ng-col">
              <span className="ng-label">Estimated cost</span>
              <span className="ng-display">{estimate ? `${unpriced.size ? "≈ " : ""}${range(estimate)}` : "–"}</span>
              <span className="ng-small ng-muted">
                {c.effort} effort, {PRESET_WORD[c.preset]} models. An estimate, not a quote: run length is not known in advance.
              </span>
            </div>
            {estimate && (
              <div className="ng-col" style={{ gap: 2 }}>
                {TIERS.map((t) => (
                  <div key={t} className="ng-row ng-mono">
                    <span className="ng-muted ng-grow">{TIER_WORD[t]}</span>
                    <span>{unpriced.has(c.tiers[t]) ? "no price" : range(estimate.per_tier[t])}</span>
                  </div>
                ))}
              </div>
            )}
            <hr className="ng-hr" />
            <div className="ng-col">
              <span className="ng-label">What happens next</span>
              <p className="ng-small">
                Netgrip drafts a plan: the root goal, the assumptions it found in your question, and a first split into lines of inquiry. No web research runs until you approve it.
              </p>
            </div>
            {failed && <p className="ng-small ng-danger">{failed}</p>}
            <Button variant="steer" className="wide" disabled={noKey || !valid} sent={sending === "plan"} sentLabel="Drafting…"
              onClick={() => submit("plan")} title={noKey ? "Add a model key in Settings → Keys" : undefined}>
              Draft the plan
            </Button>
            {noKey && <span className="ng-field__hint"><Link to="/settings#keys">Add a model key in Settings → Keys</Link></span>}
            {saved
              ? <span className="ng-field__hint">Saved as a draft. Drafting the plan uses the prompt and settings it was saved with.</span>
              : (
                <Button variant="quiet" className="wide" disabled={!valid} sent={sending === "draft"} sentLabel="Saving…" onClick={() => submit("draft")}>
                  Save as draft
                </Button>
              )}
          </div>
        </aside>
      </div>
    </main>
  );
}
