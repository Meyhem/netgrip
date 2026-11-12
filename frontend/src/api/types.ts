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

export interface Snapshot {
  seq: number;
  investigation: InvestigationRow & { settings: InvestigationSettings; root_goal: string | null };
  nodes: unknown[];
  instructions: unknown[];
  premises: unknown[];
  schedule: { order: string[]; reasons: Record<string, string>; slots: number };
  focus_node_id: string | null;
  plan_version: number;
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
