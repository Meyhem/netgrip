import type { DurableEvent, GraphNode } from "../api/types";
import { money } from "./format";

/** One event log row's who and what (EventLog README). */
export interface EventText {
  who: string;
  /** The row's actor modifier: ng-log__row--you, --orc, --sys, or none for a node. */
  actorClass: "you" | "orc" | "sys" | "";
  /** Verb first, then the object, then quoted text or numbers. */
  text: string;
}

const byIdCache = new WeakMap<readonly GraphNode[], Map<string, GraphNode>>();
function index(nodes: readonly GraphNode[]): Map<string, GraphNode> {
  let m = byIdCache.get(nodes);
  if (!m) byIdCache.set(nodes, (m = new Map(nodes.map((n) => [n.id, n]))));
  return m;
}

const PAUSED_BY: Record<string, string> = {
  spending_limit: "spending limit reached",
  model_unavailable: "model service unavailable",
  search_unavailable: "search unavailable",
  key_rejected: "key rejected",
  credit_exhausted: "credit exhausted",
};

const RESET_WHY: Record<string, string> = {
  recovery: "after recovery",
  rerun: "to re-run",
  auto_retry: "for an automatic retry",
  outage: "after an outage",
};

const LEFT_FAILED_WHY: Record<string, string> = {
  auto_retry_used: "automatic retry already used",
  spending_limit: "spending limit",
};

const str = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);
const quote = (v: unknown) => `"${String(v ?? "")}"`;
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const join = (...parts: (string | null | false | undefined)[]) => parts.filter(Boolean).join(" · ");

/** The text of one event log row, or `null` for events that are not log rows. Only the fields
 * named here are read: briefs, retry hints, the investigation's settings and error details
 * (which can carry what was sent to a model, page text or keys) are never shown. */
export function eventText(ev: DurableEvent, nodes: readonly GraphNode[]): EventText | null {
  const byId = index(nodes);
  const d = ev.data ?? {};
  const name = (id: unknown) => (typeof id === "string" && byId.get(id)?.display_id) || "a node";
  const node = ev.node_id ? byId.get(ev.node_id) : undefined;
  const self = name(ev.node_id);
  const ids = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
  const list = (v: unknown, max = 4) => {
    const all = ids(v).map(name);
    return all.length > max ? `${all.slice(0, max).join(", ")} +${all.length - max}` : all.join(", ");
  };
  const diffText = (diff: unknown) => {
    const x = (diff ?? {}) as Record<string, unknown>;
    return join(ids(x.kept).length > 0 && `kept ${list(x.kept)}`, ids(x.superseded).length > 0 && `superseded ${list(x.superseded)}`,
      ids(x.proposed).length > 0 && `proposed ${list(x.proposed)}`);
  };
  const spentOf = (v: unknown) => ids(v).reduce((sum, id) => sum + (byId.get(id)?.spent_usd ?? 0), 0);

  let text: string;
  let actor = ev.actor;
  switch (ev.type) {
    case "schedule.updated":
    case "spend.recorded":
      return null;
    case "investigation.created":
      text = "created the investigation";
      break;
    case "investigation.state_changed": {
      const to = d.to, from = d.from;
      if (to === "Paused") text = PAUSED_BY[String(d.cause)] ? `paused: ${PAUSED_BY[String(d.cause)]}` : "paused";
      else if (to === "Running") text = from === "Paused" ? "resumed" : from === "Planning" ? "approved the plan" : "started running";
      else if (to === "Planning") text = from === "Draft" ? "opened plan review" : "returned to plan review";
      else if (to === "Synthesising") text = "started synthesising";
      else if (to === "Completed") text = "completed the investigation";
      else if (to === "Stopped") text = "stopped the investigation";
      else text = `changed the state to ${String(to)}`;
      break;
    }
    case "investigation.root_goal_set":
      text = join("set the root goal", quote(d.root_goal));
      break;
    case "premise.extracted":
      text = join("extracted a premise", quote(d.text));
      break;
    case "premise.outcome":
      text = d.outcome === "unverifiable" ? "could not verify the premise" : `${String(d.outcome)} the premise`;
      break;
    case "plan.version_created":
      text = d.instruction_id ? join("re-planned", diffText(d.diff)) : join("drafted the plan", diffText(d.diff));
      break;
    case "plan.reverted":
      text = `reverted the plan to version ${String(d.to_version)}`;
      break;
    case "plan.failed":
      text = join("failed to draft the plan", str(d.reason));
      break;
    case "plan.draft_requested":
      text = "asked for a plan";
      break;
    case "node.proposed":
      text = join(`proposed ${str(d.display_id) ?? self}`, quote(d.question));
      break;
    case "node.approved":
      text = join(`approved ${self}`, node && quote(node.question));
      break;
    case "node.rejected":
      text = join(`rejected ${self}`, node && quote(node.question), str(d.reason), !!d.duplicate_of && `duplicates ${name(d.duplicate_of)}`);
      break;
    case "node.started":
      text = typeof d.attempt === "number" && d.attempt > 1 ? `started · attempt ${d.attempt}` : "started";
      break;
    case "node.activity": {
      const retry = d.retry as { n?: number; m?: number } | null;
      const what = d.activity === "Retrying" && retry ? `retrying ${retry.n} of ${retry.m}` : String(d.activity ?? "").toLowerCase();
      text = join(what, str(d.detail));
      break;
    }
    case "node.step_completed":
      text = join(`finished ${String(d.step)}`, str(d.summary));
      break;
    case "node.waiting_on_children":
      text = "waiting on children";
      break;
    case "node.completed": {
      const v = (d.verdict ?? {}) as { text?: unknown; confidence?: unknown };
      text = join("completed", str(v.text) && `verdict: ${v.text}`, str(v.confidence), node && money(node.spent_usd));
      break;
    }
    case "node.failed":
      text = join("failed", str(d.reason));
      break;
    case "node.reset":
      text = join(`reset ${self}`, RESET_WHY[String(d.reason)]);
      break;
    case "node.off_topic":
      text = join(`marked ${self} off-topic`, str(d.reason));
      break;
    case "node.relevance_checked":
      text = d.reason ? join(`kept the result of ${self}`, str(d.reason)) : join(`kept the result of ${self}`, "no usable answer");
      break;
    case "node.left_failed":
      text = join(`left ${self} Failed`, LEFT_FAILED_WHY[String(d.reason)]);
      break;
    case "node.paused":
    case "node.resumed": {
      const n = ids(d.node_ids);
      text = join(`${ev.type === "node.paused" ? "paused" : "resumed"} branch ${ev.node_id ? self : name(n[0])}`, plural(n.length, "node"));
      break;
    }
    case "node.inclusion_changed": {
      const n = ids(d.node_ids);
      const head = ev.node_id ? self : name(n[0]);
      if (d.inclusion === "Ignored") text = join(`ignored branch ${head}`, plural(n.length, "node"), `${money(spentOf(n))} spent`);
      else if (d.inclusion === "Included") text = join(`restored branch ${head}`, plural(n.length, "node"));
      else text = join(`superseded ${list(n)}`, plural(n.length, "node"));
      break;
    }
    case "node.budget_changed": {
      const b = (d.budget ?? {}) as { sources?: number; child_nodes?: number };
      text = join(`changed the budget of ${self}`, typeof b.sources === "number" && plural(b.sources, "source"),
        typeof b.child_nodes === "number" && plural(b.child_nodes, "child node"));
      break;
    }
    case "focus.changed":
      text = d.node_id ? `ran only branch ${name(d.node_id)}` : "ran everything";
      break;
    case "instruction.queued":
      text = join(ev.node_id ? `instructed ${self}` : "instructed the plan", quote(d.text));
      break;
    case "instruction.applied":
      text = join(ev.node_id ? `applied the instruction to ${self}` : "applied the instruction", diffText(d.diff));
      break;
    case "source.recorded":
      text = join("recorded a source", str(d.title) ?? str(d.url), str(d.credibility));
      break;
    case "page.unobtainable":
      actor = "system";
      text = join("page unobtainable", str(d.url), Array.isArray(d.attempts) && plural(d.attempts.length, "attempt"), ev.node_id && self);
      break;
    case "claim.added":
      text = join("claim added", quote(d.text), str(d.status));
      break;
    case "claim.updated":
      text = join(d.merged_into ? "claim merged" : "claim updated", str(d.status));
      break;
    case "claim.contradiction_recorded":
      text = join("contradiction recorded", plural(ids(d.claim_ids).length, "claim"));
      break;
    case "claim.withdrawn":
      text = join("claims withdrawn", plural(ids(d.claim_ids).length, "claim"), d.cause === "rerun" && "re-run");
      break;
    case "limit.changed":
      text = join("set the spending limit", d.spending_limit_usd != null && money(Number(d.spending_limit_usd)));
      break;
    case "investigation.concluding":
      text = join("decided to conclude", d.cut_short_by === "budget" && "cut short by the budget");
      break;
    case "system.recovered":
      text = join("recovered", ids(d.reset_node_ids).length > 0 && `reset ${plural(ids(d.reset_node_ids).length, "node")}`);
      break;
    case "report.created":
      text = join("wrote the report", d.ended_early === true && "ended early");
      break;
    default:
      text = ev.type;
  }

  if (actor === "user") return { who: "You", actorClass: "you", text };
  if (actor === "orchestrator") return { who: "Orchestrator", actorClass: "orc", text };
  if (actor === "system") return { who: "Netgrip", actorClass: "sys", text };
  return { who: self, actorClass: "", text };
}
