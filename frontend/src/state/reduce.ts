// Folds durable events into a snapshot. Mirrors the backend projectors
// (backend/src/netgrip/store/projections.py) and the snapshot builder
// (backend/src/netgrip/api/investigations.py); contract/plan_review.json checks the two agree.

import type {
  DurableEvent, GraphNode, Instruction, InvestigationSettings, NodeBudget, PlanDiff, Snapshot,
} from "../api/types";

/** The starting point before `investigation.created`: nothing known but the id. */
export function emptySnapshot(id: string): Snapshot {
  return {
    seq: 0,
    investigation: {
      id, prompt: "", state: "Draft", pause_cause: null, pause_detail: null, effort: null,
      nodes_total: 0, nodes_max: 0, running_count: 0, spent_usd: 0, spend_approximate: false,
      spending_limit_usd: 5, disk_bytes: 0, run_seconds: 0, last_activity_at: "", summary: null,
      settings: {} as InvestigationSettings, root_goal: null,
    },
    nodes: [],
    instructions: [],
    premises: [],
    plan_failed: null,
    schedule: { order: [], reasons: {}, slots: 0 },
    focus_node_id: null,
    plan_version: 0,
  };
}

// Event data shapes are checked by the backend (boundary/events.py); read them loosely here.
type Data = Record<string, any>;
type Case = (s: Snapshot, ev: DurableEvent, d: Data) => Snapshot;

const mapNodes = (s: Snapshot, ids: Iterable<string>, fn: (n: GraphNode) => GraphNode): Snapshot => {
  const set = new Set(ids);
  return { ...s, nodes: s.nodes.map((n) => (set.has(n.id) ? fn(n) : n)) };
};

const mapInstruction = (s: Snapshot, id: string, fn: (i: Instruction) => Instruction): Snapshot => ({
  ...s, instructions: s.instructions.map((i) => (i.id === id ? fn(i) : i)),
});

const rootId = (s: Snapshot) => s.nodes.find((n) => n.parent_id === null)?.id ?? null;

const cases: Record<string, Case> = {
  "investigation.created": (s, ev, d) => {
    const settings = d.settings as InvestigationSettings;
    return {
      ...s,
      investigation: {
        ...s.investigation,
        prompt: d.prompt,
        state: "Draft",
        settings,
        effort: settings.effort ?? null,
        nodes_max: settings.effort_budget?.max_nodes ?? 0,
        spending_limit_usd: Number(settings.spending_limit_usd ?? 5),
        last_activity_at: ev.at,
      },
    };
  },

  "investigation.state_changed": (s, _ev, d) => {
    const paused = d.to === "Paused";
    return {
      ...s,
      investigation: {
        ...s.investigation,
        state: d.to,
        pause_cause: paused ? d.cause ?? null : null,
        pause_detail: paused ? d.detail ?? null : null,
      },
    };
  },

  "spend.recorded": (s, ev, d) => {
    const amount = Number(d.amount_usd);
    const next = {
      ...s,
      investigation: {
        ...s.investigation,
        spent_usd: s.investigation.spent_usd + amount,
        spend_approximate: s.investigation.spend_approximate || Boolean(d.approximate),
      },
    };
    return ev.node_id ? mapNodes(next, [ev.node_id], (n) => ({ ...n, spent_usd: n.spent_usd + amount })) : next;
  },

  "investigation.root_goal_set": (s, _ev, d) => ({
    ...s, investigation: { ...s.investigation, root_goal: d.root_goal },
  }),

  "premise.extracted": (s, _ev, d) => ({
    ...s,
    premises: [...s.premises, { id: d.premise_id, text: d.text, node_id: d.node_id ?? null, outcome: null }],
  }),

  "node.proposed": (s, ev, d) => {
    const node: GraphNode = {
      id: ev.node_id as string,
      display_id: d.display_id,
      parent_id: d.parent_id ?? null,
      kind: d.kind,
      question: d.question,
      justification: d.justification ?? null,
      out_of_scope: d.out_of_scope ?? null,
      done_when: d.done_when ?? null,
      depth: d.depth ?? 0,
      status: "Proposed",
      inclusion: "Included",
      budget: null,
      activity: null,
      verdict: null,
      brief: null,
      spent_usd: 0,
      instruction_count: 0,
      // Provisional: the version this node lands in; plan.version_created confirms it.
      plan_version_added: s.plan_version + 1,
      proposed_by: d.proposed_by ?? null,
      depends_on: [...((d.depends_on as string[] | undefined) ?? [])].sort(),
    };
    return { ...s, nodes: [...s.nodes, node] };
  },

  "node.approved": (s, ev, d) =>
    mapNodes(s, [ev.node_id as string], (n) => ({ ...n, status: "Pending", budget: d.budget as NodeBudget })),

  "node.inclusion_changed": (s, _ev, d) =>
    mapNodes(s, d.node_ids as string[], (n) => ({ ...n, inclusion: d.inclusion })),

  "instruction.queued": (s, ev, d) => ({
    ...s,
    instructions: [
      ...s.instructions,
      {
        id: d.instruction_id, node_id: ev.node_id ?? rootId(s), text: d.text, state: "queued",
        queued_seq: ev.seq, applied_seq: null, diff: null, undone: false,
      },
    ],
  }),

  "instruction.applied": (s, ev, d) => {
    const instruction = s.instructions.find((i) => i.id === d.instruction_id);
    const next = mapInstruction(s, d.instruction_id, (i) => ({
      ...i, state: "applied", applied_seq: ev.seq, diff: d.diff as PlanDiff,
    }));
    const nodeId = instruction?.node_id;
    return nodeId ? mapNodes(next, [nodeId], (n) => ({ ...n, instruction_count: n.instruction_count + 1 })) : next;
  },

  "plan.version_created": (s, _ev, d) => {
    const version = d.version as number;
    const next = mapNodes(s, (d.diff as PlanDiff).proposed ?? [], (n) => ({ ...n, plan_version_added: version }));
    return { ...next, plan_version: Math.max(s.plan_version, version), plan_failed: null };
  },

  // The versions above `to_version` are deleted, so the current version drops to it.
  "plan.reverted": (s, _ev, d) => ({
    ...mapInstruction(s, d.instruction_id, (i) => ({ ...i, state: "undone", undone: true })),
    plan_version: Math.min(s.plan_version, d.to_version as number),
  }),

  "plan.failed": (s, _ev, d) => ({ ...s, plan_failed: d.reason }),

  // A new draft is under way (first time or again after plan.failed): the failure no longer stands.
  "plan.draft_requested": (s) => ({ ...s, plan_failed: null }),
};

/** Apply one durable event. Events at or below `state.seq` are ignored (returns `state`
 * itself); unknown types only advance `seq`. Every event stamps `last_activity_at`. */
export function reduce(state: Snapshot, ev: DurableEvent): Snapshot {
  if (ev.seq <= state.seq) return state;
  const fn = cases[ev.type];
  if (!fn) return { ...state, seq: ev.seq };
  const next = fn(state, ev, ev.data as Data);
  return { ...next, seq: ev.seq, investigation: { ...next.investigation, last_activity_at: ev.at } };
}
