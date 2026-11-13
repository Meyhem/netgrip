// Mirrors the Phase 1 API (docs/plans/00-overview.md). State strings are the domain's words.

export type InvestigationState =
  | "Draft" | "Planning" | "Running" | "Paused" | "Synthesising" | "Completed" | "Stopped";
export type NodeState =
  | "Proposed" | "Rejected" | "Pending" | "Running" | "Waiting on children" | "Paused" | "Completed" | "Failed";
export type Inclusion = "Included" | "Ignored" | "Superseded";
export type Kind = "Premise check" | "Divergent" | "Deep-dive" | "Verification" | "Synthesis";
export type ClaimStatus = "Confirmed" | "Supported" | "Unverified" | "Contested" | "Refuted";
export type Credibility = "Primary" | "Reputable" | "Weak";
export type Confidence = "low" | "medium" | "high";
export type PauseCause =
  | "user" | "spending_limit" | "model_unavailable" | "search_unavailable" | "key_rejected" | "credit_exhausted";
export type Activity =
  | "Planning" | "Searching" | "Reading" | "Extracting" | "Reasoning" | "Aggregating" | "Waiting on children" | "Retrying";
export type Actor = "user" | "orchestrator" | "node" | "system";

export type EffortName = "Low" | "Medium" | "High";
export type Tier = "strong" | "standard" | "fast" | "verifier";
export type PresetName = "economy" | "balanced" | "maximum";
export type PageReuse = "1d" | "always_refetch";

export interface EffortBudget {
  max_depth: number;
  max_nodes: number;
  sources_per_node: number;
  parallel: number;
  sources_to_confirm: number;
}

export interface InvestigationSettings {
  effort: EffortName;
  effort_budget?: EffortBudget;
  preset: PresetName;
  tiers: Record<Tier, string>;
  excluded_domains: string[];
  prefer: "none" | "primary";
  page_reuse: PageReuse;
  spending_limit_usd: number;
}

export interface InvestigationRow {
  id: string;
  prompt: string;
  state: InvestigationState;
  pause_cause: PauseCause | null;
  pause_detail: string | null;
  effort: EffortName | null;
  nodes_total: number;
  nodes_max: number;
  running_count: number;
  spent_usd: number;
  spend_approximate: boolean;
  spending_limit_usd: number;
  disk_bytes: number;
  run_seconds: number;
  last_activity_at: string;
  summary: string | null;
}

export interface NodeBudget {
  child_nodes: number;
  sources: number;
  /** Levels past the investigation's depth limit that "Go deeper" allowed. */
  depth_extra?: number;
  tier?: string;
}

/** One node of the investigation graph, as in the snapshot's `nodes`. */
export interface GraphNode {
  id: string;
  display_id: string;
  parent_id: string | null;
  kind: Kind;
  question: string;
  justification: string | null;
  out_of_scope: string | null;
  done_when: string | null;
  depth: number;
  status: NodeState;
  inclusion: Inclusion;
  budget: NodeBudget | null;
  activity: Activity | null;
  verdict: unknown;
  /** The brief the node was last started with (node.started.data.brief). */
  brief: Record<string, unknown> | null;
  spent_usd: number;
  instruction_count: number;
  plan_version_added: number | null;
  proposed_by: string | null;
  depends_on: string[];
  /** Seq and time of the node's last `node.completed`/`node.failed`; cleared when it runs again. */
  finished_seq: number | null;
  finished_at: string | null;
  /** From `node.failed`, while Failed. */
  failure_reason: string | null;
  /** From `node.rejected`. */
  rejection_reason: string | null;
  /** From the `node.inclusion_changed` that excluded it; cleared on restore. */
  excluded_by: "user" | "replan" | null;
  excluded_at: string | null;
  excluded_instruction_id: string | null;
  /** The status a branch pause interrupted; set while Paused. */
  paused_from?: NodeState | null;
}

/** kept / superseded / proposed node ids of one plan version or applied instruction. */
export interface PlanDiff { kept: string[]; superseded: string[]; proposed: string[]; notes: string[] }

export interface Instruction {
  id: string;
  node_id: string | null;
  text: string;
  state: "queued" | "applied" | "undone";
  queued_seq: number;
  applied_seq: number | null;
  diff: PlanDiff | null;
  undone: boolean;
  /** What a queued instruction waits for ("D2b finishes READING"), or null. */
  waiting_for?: string | null;
}

export interface Premise { id: string; text: string; node_id: string | null; outcome: string | null }

export interface Snapshot {
  seq: number;
  investigation: InvestigationRow & { settings: InvestigationSettings; root_goal: string | null; ended_early?: boolean };
  nodes: GraphNode[];
  instructions: Instruction[];
  premises: Premise[];
  plan_failed: string | null;
  schedule: { order: string[]; reasons: Record<string, string>; slots: number };
  focus_node_id: string | null;
  plan_version: number;
  /** The newest durable events (up to 200, oldest first) up to `seq`. Sent by the snapshot
   * endpoint only; the reducer leaves it as loaded. */
  recent_events?: DurableEvent[];
  /** The claims synthesis may use ("Writing the report from N claims"). Snapshot endpoint
   * only; the reducer leaves it as loaded. */
  synthesis_claims?: number;
}

/** Streamed model text and similar: no seq, never stored or replayed (D-11). */
export interface EphemeralEvent {
  investigation_id: string;
  node_id: string | null;
  kind: string;
  data: Record<string, unknown>;
}

export interface DurableEvent {
  seq: number;
  investigation_id: string;
  type: string;
  v: number;
  at: string;
  actor: Actor;
  node_id: string | null;
  command_id: string | null;
  data: Record<string, unknown>;
}

export interface KeyStatus {
  set: boolean;
  status: "none" | "set" | "rejected";
  checked_at: string | null;
  message: string | null;
}

export interface ModelPrice {
  id: string;
  price_in_per_m: number | null;
  price_out_per_m: number | null;
  price_source: string | null;
}

export interface Capacity {
  investigations: number;
  model_calls: number;
  searches: number;
  browser_pages: number;
}

export interface Settings {
  effort: Record<EffortName, EffortBudget>;
  default_effort: EffortName;
  spending_limit_usd: number;
  retry_before_pause_seconds: number;
  page_reuse: PageReuse;
  politeness_seconds: number;
  capacity: Capacity;
  model_endpoint: string;
  presets: Record<PresetName, Record<Tier, string>>;
  default_preset: PresetName;
  models: ModelPrice[];
  excluded_domains: string[];
  keys: Record<"model" | "search", KeyStatus>;
}

export interface Pool { in_use: number; limit: number }
export interface Pools { models: Pool; search: Pool; browsers: Pool; today_usd: number }
export interface Storage { total_bytes: number; investigations: number; pages: number; data_dir: string }

export interface Range { low_usd: number; high_usd: number }
export interface Estimate extends Range {
  per_tier: Record<Tier, Range & { share: number }>;
  unpriced_models: string[];
}

export interface CommandAck { recorded: boolean; duplicate: boolean }

/** A node's verdict (`node.completed.data.verdict`): the agent's text and its confidence. */
export interface Verdict { text: string; confidence: Confidence }

/** A source for or against a claim. A page that could not be obtained has no page version. */
export interface ClaimSource {
  id: string;
  url: string;
  title: string | null;
  page_version_id: string | null;
  credibility: Credibility;
  published_at: string | null;
  origin_key: string;
}

export interface Claim {
  id: string;
  node_id: string | null;
  text: string;
  status: ClaimStatus;
  supporting: ClaimSource[];
  contradicting: ClaimSource[];
}

/** The brief as a node received it in its last `node.started` (backend engine/brief.py). */
export interface NodeBrief {
  root_goal: string;
  path: { display_id: string; question: string; justification: string | null }[];
  task: { question: string; out_of_scope: string | null; done_when: string | null; budget: Partial<NodeBudget>; hint?: string | null };
  known: {
    claims: { id: string; text: string; status: ClaimStatus }[];
    dependency_results: { display_id: string; verdict: Partial<Verdict> | null; failed?: string | null }[];
    instructions: { text: string; from_display_id: string }[];
  };
}

/** One step of a node's trail. `ended_at` is null while the step is open. */
export interface TrailStep {
  step: number;
  name: string;
  kind: string | null;
  activity: Activity | null;
  detail: string | null;
  summary: string | null;
  started_at: string;
  ended_at: string | null;
  route: string | null;
  page_version_id: string | null;
  retry: { n: number; m: number } | null;
  instruction_applied: string[];
}

export interface Proposal { node_id: string; display_id: string; question: string; decision: "approved" | "rejected" | "pending"; reason: string | null }

/** The node with its descendants (node detail `branch`). */
export interface Branch { spent_usd: number; nodes: number; nodes_max: number; depth: number; depth_max: number; reach: number }

/** `GET /api/investigations/{id}/nodes/{node_id}`: everything about one node. */
export interface NodeDetail {
  node: GraphNode;
  /** Null for a node that never started (a coordinator from the plan waits on its children). */
  brief: NodeBrief | null;
  claims: Claim[];
  trail: TrailStep[];
  instructions: { inherited: (Instruction & { from_display_id: string })[]; own: Instruction[] };
  open_questions: string[];
  proposals: Proposal[];
  branch: Branch;
}
