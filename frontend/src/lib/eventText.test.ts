import { describe, expect, it } from "vitest";
import type { DurableEvent } from "../api/types";
import { runContract } from "../test/contract";
import { graphNode } from "../test/fixtures";
import { eventText } from "./eventText";

const nodes = [
  graphNode({ id: "n2", display_id: "D2", question: "Who saw it first?", spent_usd: 0.04 }),
  graphNode({ id: "n2c", display_id: "D2c", parent_id: "n2", question: "ESA Proba image, 2004: who identified it", spent_usd: 0.21 }),
  graphNode({ id: "n4", display_id: "D4", spent_usd: 0.04 }),
];

let seq = 0;
function ev(type: string, data: Record<string, unknown> = {}, over: Partial<DurableEvent> = {}): DurableEvent {
  seq += 1;
  return { seq, investigation_id: "inv", type, v: 1, at: "2026-11-13T14:02:31Z", actor: "node", node_id: "n2c", command_id: null, data, ...over };
}

const diff = { kept: ["n2"], superseded: ["n4"], proposed: ["n2c"], notes: [] };

// [event, who, actor class, expected text (a prefix: verb first, then the object)]
const TABLE: [DurableEvent, string, string, string][] = [
  [ev("investigation.created", { prompt: "p", settings: {} }, { actor: "user", node_id: null }), "You", "you", "created the investigation"],
  [ev("investigation.state_changed", { from: "Running", to: "Paused", origin: "system", cause: "spending_limit", detail: null }, { actor: "system", node_id: null }), "Netgrip", "sys", "paused: spending limit reached"],
  [ev("investigation.state_changed", { from: "Running", to: "Paused", origin: "user", cause: "user", detail: null }, { actor: "user", node_id: null }), "You", "you", "paused"],
  [ev("investigation.state_changed", { from: "Paused", to: "Running", origin: "user", cause: null, detail: null }, { actor: "user", node_id: null }), "You", "you", "resumed"],
  [ev("investigation.state_changed", { from: "Planning", to: "Running", origin: "user", cause: null, detail: null }, { actor: "user", node_id: null }), "You", "you", "approved the plan"],
  [ev("investigation.state_changed", { from: "Running", to: "Synthesising", origin: "orchestrator", cause: null, detail: null }, { actor: "orchestrator", node_id: null }), "Orchestrator", "orc", "started synthesising"],
  [ev("investigation.root_goal_set", { root_goal: "Establish whether" }, { actor: "orchestrator", node_id: null }), "Orchestrator", "orc", 'set the root goal · "Establish whether"'],
  [ev("premise.extracted", { premise_id: "p1", text: "It is visible.", node_id: "n2" }, { actor: "orchestrator", node_id: null }), "Orchestrator", "orc", 'extracted a premise · "It is visible."'],
  [ev("premise.outcome", { premise_id: "p1", outcome: "refuted" }), "D2c", "", "refuted the premise"],
  [ev("plan.version_created", { version: 1, instruction_id: null, diff: { ...diff, kept: [], superseded: [] } }, { actor: "orchestrator", node_id: null }), "Orchestrator", "orc", "drafted the plan · proposed D2c"],
  [ev("plan.version_created", { version: 2, instruction_id: "i1", diff }, { node_id: "n2" }), "D2", "", "re-planned · kept D2 · superseded D4 · proposed D2c"],
  [ev("plan.reverted", { to_version: 1, instruction_id: "i1" }, { actor: "user", node_id: null }), "You", "you", "reverted the plan to version 1"],
  [ev("plan.failed", { reason: "no usable answer" }, { actor: "orchestrator", node_id: null }), "Orchestrator", "orc", "failed to draft the plan · no usable answer"],
  [ev("plan.draft_requested", {}, { actor: "user", node_id: null }), "You", "you", "asked for a plan"],
  [ev("node.proposed", { display_id: "D2c", question: "ESA Proba image" }, { actor: "orchestrator" }), "Orchestrator", "orc", 'proposed D2c · "ESA Proba image"'],
  [ev("node.approved", { budget: { sources: 8, child_nodes: 2 } }, { actor: "orchestrator" }), "Orchestrator", "orc", 'approved D2c · "ESA Proba image, 2004: who identified it"'],
  [ev("node.rejected", { reason: "does not help answer the root goal", duplicate_of: null }, { actor: "orchestrator" }), "Orchestrator", "orc", 'rejected D2c · "ESA Proba image, 2004: who identified it" · does not help answer the root goal'],
  [ev("node.started", { attempt: 1, brief: {} }), "D2c", "", "started"],
  [ev("node.activity", { activity: "Searching", detail: "esa proba wall", step: "search", retry: null }), "D2c", "", "searching · esa proba wall"],
  [ev("node.activity", { activity: "Retrying", detail: "esa.int timed out after 30 s", step: "read", retry: { n: 2, m: 3 } }), "D2c", "", "retrying 2 of 3 · esa.int timed out after 30 s"],
  [ev("node.step_completed", { step: "read", kind: "fetch", summary: "read https://esa.int/a", route: "simple", page_version_id: "pv" }), "D2c", "", "finished read · read https://esa.int/a"],
  [ev("node.waiting_on_children", {}), "D2c", "", "waiting on children"],
  [ev("node.completed", { verdict: { text: "Yang could not see it", confidence: "high" }, open_questions: [], off_topic: false }), "D2c", "", "completed · verdict: Yang could not see it · high · $0.21"],
  [ev("node.failed", { reason: "no sources", auto_retry_used: false }), "D2c", "", "failed · no sources"],
  [ev("node.reset", { reason: "recovery" }, { actor: "system" }), "Netgrip", "sys", "reset D2c · after recovery"],
  [ev("node.off_topic", { reason: "about the Moon" }, { actor: "orchestrator" }), "Orchestrator", "orc", "marked D2c off-topic · about the Moon"],
  [ev("node.relevance_checked", { reason: "Bears on the goal." }, { actor: "orchestrator" }), "Orchestrator", "orc", "kept the result of D2c · Bears on the goal."],
  [ev("node.left_failed", { reason: "auto_retry_used" }, { actor: "orchestrator" }), "Orchestrator", "orc", "left D2c Failed · automatic retry already used"],
  [ev("node.paused", { node_ids: ["n2", "n2c"] }, { actor: "user", node_id: "n2" }), "You", "you", "paused branch D2 · 2 nodes"],
  [ev("node.resumed", { node_ids: ["n2"] }, { actor: "user", node_id: "n2" }), "You", "you", "resumed branch D2 · 1 node"],
  [ev("node.inclusion_changed", { node_ids: ["n4"], inclusion: "Ignored", by: "user", instruction_id: null }, { actor: "user", node_id: "n4" }), "You", "you", "ignored branch D4 · 1 node · $0.04 spent"],
  [ev("node.inclusion_changed", { node_ids: ["n4"], inclusion: "Included", by: "user", instruction_id: null }, { actor: "user", node_id: "n4" }), "You", "you", "restored branch D4 · 1 node"],
  [ev("node.inclusion_changed", { node_ids: ["n4"], inclusion: "Superseded", by: "replan", instruction_id: "i1" }, { actor: "orchestrator", node_id: null }), "Orchestrator", "orc", "superseded D4 · 1 node"],
  [ev("node.budget_changed", { budget: { sources: 12, child_nodes: 4 }, cause: "go_deeper" }, { actor: "user" }), "You", "you", "changed the budget of D2c · 12 sources · 4 child nodes"],
  [ev("focus.changed", { node_id: "n2" }, { actor: "user", node_id: null }), "You", "you", "ran only branch D2"],
  [ev("focus.changed", { node_id: null }, { actor: "user", node_id: null }), "You", "you", "ran everything"],
  [ev("instruction.queued", { instruction_id: "i1", text: "Only first-hand statements.", waiting_for: "replan" }, { actor: "user", node_id: "n2" }), "You", "you", 'instructed D2 · "Only first-hand statements."'],
  [ev("instruction.applied", { instruction_id: "i1", at_step: 3, diff }, { actor: "orchestrator", node_id: "n2" }), "Orchestrator", "orc", "applied the instruction to D2 · kept D2 · superseded D4 · proposed D2c"],
  [ev("source.recorded", { source_id: "s", url: "https://esa.int/a", title: "Proba image", page_version_id: "pv", credibility: "Primary", published_at: null, origin_key: "esa" }), "D2c", "", "recorded a source · Proba image · Primary"],
  [ev("page.unobtainable", { url: "xinhuanet.com/english/2003", attempts: [{}, {}, {}] }), "Netgrip", "sys", "page unobtainable · xinhuanet.com/english/2003 · 3 attempts · D2c"],
  [ev("claim.added", { claim_id: "c", text: "Chiao photographed a section", status: "Supported", supporting: [], contradicting: [] }), "D2c", "", 'claim added · "Chiao photographed a section" · Supported'],
  [ev("claim.updated", { claim_id: "c", status: "Confirmed", supporting: [], contradicting: [] }), "D2c", "", "claim updated · Confirmed"],
  [ev("claim.updated", { claim_id: "c", status: "Supported", supporting: [], contradicting: [], merged_into: "c0" }), "D2c", "", "claim merged · Supported"],
  [ev("claim.contradiction_recorded", { claim_ids: ["a", "b"] }), "D2c", "", "contradiction recorded · 2 claims"],
  [ev("claim.withdrawn", { claim_ids: ["a"], cause: "rerun" }, { actor: "user" }), "You", "you", "claims withdrawn · 1 claim · re-run"],
  [ev("limit.changed", { spending_limit_usd: 10 }, { actor: "user", node_id: null }), "You", "you", "set the spending limit · $10.00"],
  [ev("investigation.concluding", { cut_short_by: "budget" }, { actor: "orchestrator", node_id: null }), "Orchestrator", "orc", "decided to conclude · cut short by the budget"],
  [ev("system.recovered", { reset_node_ids: ["n2c"] }, { actor: "system", node_id: null }), "Netgrip", "sys", "recovered · reset 1 node"],
  [ev("report.created", { report_id: "r", ended_early: false, cut_short_by: null }, { actor: "orchestrator", node_id: null }), "Orchestrator", "orc", "wrote the report"],
];

describe("eventText", () => {
  it("eventText is verb-first for each event type", () => {
    for (const [e, who, actorClass, text] of TABLE) {
      const row = eventText(e, nodes);
      expect(row, e.type).not.toBeNull();
      expect({ type: e.type, who: row!.who, actorClass: row!.actorClass }).toEqual({ type: e.type, who, actorClass });
      expect(row!.text.startsWith(text), `${e.type}: "${row!.text}" should start with "${text}"`).toBe(true);
    }
  });

  it("covers every log event type of the contract", () => {
    const covered = new Set(TABLE.map(([e]) => e.type));
    const types = new Set(runContract().events.map((e) => e.type));
    for (const t of types) if (t !== "schedule.updated" && t !== "spend.recorded") expect(covered.has(t), t).toBe(true);
  });

  it("schedule and spend events are not log rows", () => {
    expect(eventText(ev("schedule.updated", { order: [], reasons: {}, slots: 2 }, { actor: "orchestrator" }), nodes)).toBeNull();
    expect(eventText(ev("spend.recorded", { tier: "strong", model: "m", amount_usd: "0.01" }), nodes)).toBeNull();
  });

  it("no row text contains a model prompt or page body", () => {
    const PAGE_BODY = "BODY-OF-THE-PAGE <script>alert(1)</script>";
    const KEY = "sk-or-v1-0123456789abcdef";
    const fixtures: DurableEvent[] = [
      ...runContract().events,
      ev("node.started", { attempt: 2, brief: { root_goal: "PROMPT-ROOT-GOAL-IN-BRIEF", task: { question: "PROMPT-TASK" } } }),
      ev("node.reset", { reason: "auto_retry", hint: "PROMPT-HINT-FOR-THE-RETRY" }, { actor: "orchestrator" }),
      ev("investigation.created", { prompt: "PROMPT-OF-THE-INVESTIGATION", settings: { tiers: { strong: KEY } } }, { actor: "user", node_id: null }),
      ev("investigation.state_changed", { from: "Running", to: "Paused", origin: "system", cause: "key_rejected", detail: `401 for key ${KEY}` }, { actor: "system", node_id: null }),
      ev("node.step_completed", { step: "read", kind: "fetch", summary: "read https://a.b", route: "simple", page_version_id: "pv", text: PAGE_BODY }),
      ev("source.recorded", { source_id: "s", url: "https://a.b", title: "T", page_version_id: "pv", credibility: "Weak", published_at: null, origin_key: "a", text: PAGE_BODY }),
    ];
    // Strings that are only ever sent to models: every string inside a brief, the retry hint.
    const secret: string[] = [PAGE_BODY, KEY, "PROMPT-HINT-FOR-THE-RETRY", "PROMPT-OF-THE-INVESTIGATION"];
    const strings = (v: unknown): string[] =>
      typeof v === "string" ? [v] : v && typeof v === "object" ? Object.values(v).flatMap(strings) : [];
    for (const e of fixtures) if (e.type === "node.started") secret.push(...strings(e.data.brief).filter((s) => s.length > 12));
    const rows = fixtures.map((e) => eventText(e, nodes)).filter((r) => r !== null);
    expect(rows.length).toBeGreaterThan(100);
    // A brief also repeats what other events record on their own rows: questions, claims,
    // verdicts, the root goal and premises. Those are not prompts.
    const ownRows = new Set(fixtures.flatMap((e) => [e.data.question, e.data.text, e.data.root_goal, (e.data.verdict as { text?: unknown } | undefined)?.text]
      .filter((v): v is string => typeof v === "string" && e.type !== "node.started")));
    for (const r of rows) {
      const line = `${r!.who} ${r!.text}`;
      for (const s of secret) {
        if (ownRows.has(s) && s !== PAGE_BODY) continue;
        expect(line.includes(s), `${line} contains ${s}`).toBe(false);
      }
    }
  });
});
