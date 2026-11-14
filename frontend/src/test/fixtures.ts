import type { Claim, ClaimSource, GraphNode, InvestigationRow, NodeDetail, Pools, Settings } from "../api/types";

export const POOLS: Pools = {
  models: { in_use: 5, limit: 8 },
  search: { in_use: 1, limit: 4 },
  browsers: { in_use: 4, limit: 6, restarts_today: 2, timed_out_today: 7 },
  today_usd: 3.12,
};

export function row(over: Partial<InvestigationRow> = {}): InvestigationRow {
  return {
    id: "inv-1", prompt: "Why is the Great Wall of China visible from space with the naked eye?",
    state: "Draft", pause_cause: null, pause_detail: null, effort: "Medium",
    nodes_total: 0, nodes_max: 40, running_count: 0, spent_usd: 0, spend_approximate: false,
    spending_limit_usd: 5, disk_bytes: 0, run_seconds: 0, last_activity_at: "2026-11-12T10:00:00Z", summary: null,
    ...over,
  };
}

const OPUS = "anthropic/claude-opus-5.5", SONNET = "anthropic/claude-sonnet-5.5", HAIKU = "anthropic/claude-haiku-5.5", GPT = "openai/gpt-5.2";

export function settings(over: Partial<Settings> = {}): Settings {
  return {
    effort: {
      Low: { max_depth: 2, max_nodes: 12, sources_per_node: 4, parallel: 2, sources_to_confirm: 1 },
      Medium: { max_depth: 4, max_nodes: 40, sources_per_node: 8, parallel: 4, sources_to_confirm: 2 },
      High: { max_depth: 6, max_nodes: 80, sources_per_node: 12, parallel: 6, sources_to_confirm: 3 },
    },
    default_effort: "Medium",
    spending_limit_usd: 5,
    retry_before_pause_seconds: 300,
    page_reuse: "1d",
    politeness_seconds: 2,
    capacity: { investigations: 5, model_calls: 8, searches: 4, browser_pages: 6 },
    model_endpoint: "https://openrouter.ai/api/v1",
    model_routing: { sort: "default", deny_data_collection: false, zero_retention: false },
    presets: {
      economy: { strong: SONNET, standard: HAIKU, fast: HAIKU, verifier: GPT },
      balanced: { strong: OPUS, standard: SONNET, fast: HAIKU, verifier: GPT },
      maximum: { strong: OPUS, standard: OPUS, fast: SONNET, verifier: GPT },
    },
    default_preset: "balanced",
    models: [
      { id: OPUS, price_in_per_m: 15, price_out_per_m: 75, price_source: "provider" },
      { id: SONNET, price_in_per_m: 3, price_out_per_m: 15, price_source: "provider" },
      { id: HAIKU, price_in_per_m: 1, price_out_per_m: 5, price_source: "provider" },
      { id: GPT, price_in_per_m: null, price_out_per_m: null, price_source: null },
    ],
    excluded_domains: [],
    keys: {
      model: { set: true, status: "set", checked_at: null, message: null },
      search: { set: false, status: "none", checked_at: null, message: null },
    },
    ...over,
  };
}

/** A snapshot node; `id` doubles as the display id unless given. */
export function graphNode(over: Partial<GraphNode> & { id: string }): GraphNode {
  return {
    display_id: over.id, parent_id: null, kind: "Deep-dive", question: `Question of ${over.id}`,
    justification: null, out_of_scope: null, done_when: null, depth: 0,
    status: "Proposed", inclusion: "Included", budget: null, activity: null, verdict: null, brief: null,
    spent_usd: 0, instruction_count: 0, plan_version_added: 1, proposed_by: "planner", depends_on: [],
    finished_seq: null, finished_at: null, failure_reason: null, rejection_reason: null,
    excluded_by: null, excluded_at: null, excluded_instruction_id: null,
    ...over,
  };
}

/** A node detail response for `node`, empty unless given. */
export function nodeDetail(node: GraphNode, over: Partial<NodeDetail> = {}): NodeDetail {
  return {
    node, brief: null, claims: [], trail: [], instructions: { inherited: [], own: [] }, open_questions: [], proposals: [],
    branch: { spent_usd: node.spent_usd, nodes: 0, nodes_max: 0, depth: node.depth, depth_max: 4, reach: 0 },
    ...over,
  };
}

export function claimSource(over: Partial<ClaimSource> & { id: string }): ClaimSource {
  return {
    url: `https://example.org/${over.id}`, title: null, page_version_id: `pv-${over.id}`, credibility: "Reputable",
    published_at: "2005-05-09", origin_key: `origin-${over.id}`, ...over,
  };
}

export function claim(over: Partial<Claim> & { id: string }): Claim {
  return { node_id: null, text: `Text of ${over.id}`, status: "Unverified", supporting: [], contradicting: [], ...over };
}
