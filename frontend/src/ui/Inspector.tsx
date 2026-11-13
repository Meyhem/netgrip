import { useEffect, useState, type ComponentProps, type ReactNode } from "react";
import type { ClaimStatus as Status, DurableEvent, GraphNode, NodeDetail, Snapshot } from "../api/types";
import { elapsed, money, timeOfDaySeconds } from "../lib/format";
import { lastByNode } from "../state/derive";
import { useInvestigationSlice } from "../state/investigationStore";
import { useNodeDetail } from "../state/useNodeDetail";
import { ActivityLine } from "./ActivityLine";
import { Banner } from "./Banner";
import { Brief, noBriefText } from "./Brief";
import { BudgetMeter } from "./BudgetMeter";
import { ClaimCard, independent } from "./ClaimCard";
import { cx } from "./cx";
import { Instruction, seqLabel } from "./Instruction";
import { Pill, StatusPill } from "./StatusPill";
import { PageSheet } from "./PageSheet";
import { Trail } from "./Trail";
import { asVerdict, Verdict } from "./Verdict";
import { CLAIM_STATUS, KIND_CODE, NODE_PILL } from "./vocab";

export type InspectorTab = "overview" | "claims" | "brief" | "trail" | "instructions";

export interface InspectorProps {
  investigationId: string;
  s: Snapshot;
  /** The board's accumulated durable events (activity details, times, who excluded a node). */
  events: DurableEvent[];
  /** The selected node; null shows the root. */
  nodeId: string | null;
  /** False while the stream is not open: nothing pulses. */
  live?: boolean;
  /** Phase 6: NodeActions, in the header. */
  nodeActions?: ReactNode;
  /** Phase 6: the InstructionComposer, pinned to the bottom. */
  composer?: ReactNode;
}

const NO_CLAIMS = "No claims yet. They appear here as pages are read.";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The current time, ticking each second while `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

/** The node and its descendants, from the snapshot (kept current by the stream). */
function branchOf(s: Snapshot, id: string): GraphNode[] {
  const out: GraphNode[] = [];
  const todo = [id];
  while (todo.length) {
    const cur = todo.pop()!;
    const n = s.nodes.find((x) => x.id === cur);
    if (!n) continue;
    out.push(n);
    for (const c of s.nodes) if (c.parent_id === cur) todo.push(c.id);
  }
  return out;
}

/** The branch's spend and node counts, as the backend's node detail `_branch` defines them, but
 * from the snapshot so they follow every event (a coordinator has few events of its own):
 * `nodes` = approved nodes below the node; `nodesMax` = summed `child_nodes` of the branch's
 * approved nodes. */
export function branchCounts(s: Snapshot, id: string): { spent: number; nodes: number; nodesMax: number } {
  const branch = branchOf(s, id);
  const approved = branch.filter((n) => n.status !== "Proposed" && n.status !== "Rejected");
  return {
    spent: branch.reduce((sum, n) => sum + n.spent_usd, 0),
    nodes: approved.filter((n) => n.id !== id).length,
    nodesMax: approved.reduce((sum, n) => sum + (n.budget?.child_nodes ?? 0), 0),
  };
}

function proposedByText(node: GraphNode, s: Snapshot): string | null {
  const by = node.proposed_by;
  if (!by) return null;
  const parent = s.nodes.find((n) => n.id === by);
  if (parent) return `Proposed by ${parent.display_id}`;
  return `Proposed by ${by === "user" ? "you" : `the ${by}`}`;
}

interface Ctx { s: Snapshot; events: DurableEvent[]; node: GraphNode; detail: NodeDetail; displayIds: Record<string, string>; live: boolean }

/** ScreenNodeDetail / ScreenControlBoard region 4: the selected node, one tab at a time. */
export function Inspector({ investigationId, s, events, nodeId, live: streamLive = true, nodeActions, composer }: InspectorProps) {
  const halted = s.investigation.state === "Paused" || s.investigation.state === "Stopped";
  const rootId = s.nodes.find((n) => n.parent_id === null)?.id ?? null;
  const id = nodeId ?? rootId;
  const { detail, status } = useNodeDetail(investigationId, id);
  const [tab, setTab] = useState<InspectorTab>("overview");
  // The stored page open in the sheet, for this node only.
  const [page, setPage] = useState<{ nodeId: string | null; pageVersionId: string } | null>(null);
  const openPage = page && page.nodeId === id ? page.pageVersionId : null;
  // The row from the snapshot is current to the last applied event; the detail may lag a fetch.
  const node = s.nodes.find((n) => n.id === id) ?? detail?.node ?? null;
  // `live` appears only on running or waiting work: the node is Included, Running or Waiting on
  // children, and the investigation is not Paused or Stopped. Otherwise a node still marked
  // Running or Waiting takes the paused tone. The pulse also needs the stream open.
  const active = node?.status === "Running" || node?.status === "Waiting on children";
  const running = !!node && node.inclusion === "Included" && active && !halted;
  const live = streamLive && running;
  const displayIds = Object.fromEntries(s.nodes.map((n) => [n.id, n.display_id]));
  const instructionCount = detail ? detail.instructions.inherited.length + detail.instructions.own.length : null;

  const tabs: [InspectorTab, string, number | null][] = [
    ["overview", "Overview", null],
    ["claims", "Claims", detail ? detail.claims.length : null],
    ["brief", "Brief", null],
    ["trail", "Trail", null],
    ["instructions", "Instructions", instructionCount],
  ];

  let body: ReactNode;
  if (!node || (status === "error" && !detail)) {
    body = <Banner tone="warn" title="Netgrip cannot reach its service.">Reload to try again. Nothing is lost.</Banner>;
  } else if (!detail) {
    body = <div className="ng-activity"><span className="ng-activity__verb">Loading</span><span className="ng-activity__what">{node.display_id}</span></div>;
  } else {
    const ctx: Ctx = { s, events, node, detail, displayIds, live };
    body =
      tab === "overview" ? <Overview {...ctx} />
      : tab === "claims" ? <ClaimsTab key={node.id} {...ctx} />
      : tab === "brief" ? <Brief brief={detail.brief} node={node} />
      : tab === "trail" ? <LiveTrail investigationId={investigationId} detail={detail} live={live} running={running}
          onOpenPage={(pageVersionId) => setPage({ nodeId: id, pageVersionId })} />
      : <InstructionsTab {...ctx} />;
  }

  return (
    <>
      {node && (
        <div className="ng-col inspector__head">
          <div className="ng-row ng-row--nowrap">
            <span className="ng-tag">{KIND_CODE[node.kind]}</span>
            <span className="ng-mono ng-faint">{node.display_id} · depth {node.depth}</span>
            <Pill spec={active && !running ? { ...NODE_PILL[node.status], tone: NODE_PILL.Paused.tone } : NODE_PILL[node.status]} still={!live} />
            {node.inclusion !== "Included" && <StatusPill kind="inclusion" state={node.inclusion} />}
            {nodeActions != null && <span className="ng-right">{nodeActions}</span>}
          </div>
          <h2 className="ng-heading">{node.question}</h2>
          {node.justification && <p className="ng-small ng-muted"><span className="ng-label">Why </span>{node.justification}</p>}
        </div>
      )}
      <div className="ng-tabs" role="tablist" aria-label="Node detail">
        {tabs.map(([key, label, count]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} className={cx("ng-tab", tab === key && "is-on")} onClick={() => setTab(key)}>
            {label}{count != null && <span className="ng-mono-sm">{count}</span>}
          </button>
        ))}
      </div>
      <div className="ng-pane__scroll ng-col inspector__body" role="tabpanel" data-node-id={id ?? undefined} data-tab={tab}>
        {body}
      </div>
      {composer != null && <div className="inspector__composer">{composer}</div>}
      {openPage && <PageSheet investigationId={investigationId} pageVersionId={openPage} onClose={() => setPage(null)} />}
    </>
  );
}

/** The Trail with the node's streamed model text. Only the trail re-renders on each frame of
 * streamed text, not the inspector around it. */
function LiveTrail({ investigationId, ...props }: Omit<ComponentProps<typeof Trail>, "modelText"> & { investigationId: string }) {
  const id = props.detail.node.id;
  const modelText = useInvestigationSlice(investigationId, (st) => st.modelText[id] ?? null);
  return <Trail {...props} modelText={modelText} />;
}

function Overview(ctx: Ctx) {
  const { node } = ctx;
  if (node.status === "Rejected") return <RejectedOverview {...ctx} />;
  if (node.inclusion !== "Included") return <ExcludedOverview {...ctx} />;
  if (node.status === "Completed") return <CompletedOverview {...ctx} />;
  if (node.status === "Failed") return <Verdict verdict={null} failed={node.failure_reason ?? ""} />;
  return <ActiveOverview {...ctx} />;
}

/** Running, Waiting on children, Pending, Paused or Proposed: what it does now and has so far. */
function ActiveOverview({ s, events, node, detail, displayIds }: Ctx) {
  const running = node.status === "Running";
  const now = useNow(running);
  const proposedBy = node.status === "Proposed" ? proposedByText(node, s) : null;
  const inherited = detail.instructions.inherited.filter((i) => i.state !== "undone");
  return (
    <>
      {running && <NowBlock events={events} node={node} detail={detail} now={now} />}
      {!detail.brief && node.status === "Waiting on children" && <p className="ng-small ng-muted">{noBriefText(node)}</p>}
      {proposedBy && <span className="ng-small ng-muted">{proposedBy}</span>}
      <Verdict verdict={asVerdict(node.verdict)} />
      <div className="ng-col">
        <span className="ng-label">Claims so far</span>
        {detail.claims.length === 0
          ? <span className="ng-small ng-muted">{NO_CLAIMS}</span>
          : detail.claims.map((c) => <ClaimCard key={c.id} claim={c} nodeDisplayIds={displayIds} compact />)}
      </div>
      <BranchMeters s={s} node={node} detail={detail} />
      {inherited.length > 0 && (
        <div className="ng-col">
          <span className="ng-label">{inherited.length === 1 ? "Inherited instruction" : "Inherited instructions"}</span>
          {inherited.map((i) => <Instruction key={i.id} instruction={i} nodeDisplayIds={displayIds} variant="inherited" from={i.from_display_id} />)}
        </div>
      )}
    </>
  );
}

function NowBlock({ events, node, detail, now }: { events: DurableEvent[]; node: GraphNode; detail: NodeDetail; now: number }) {
  const act = lastByNode(events, ["node.activity"]).get(node.id)?.data ?? {};
  const started = lastByNode(events, ["node.started"]).get(node.id)?.at;
  const step = detail.trail.length ? detail.trail[detail.trail.length - 1].step : null;
  const read = new Set(detail.trail.map((t) => t.page_version_id).filter(Boolean)).size;
  const limit = node.budget?.sources;
  const meta = [
    step != null ? `step ${step}` : null,
    started ? `${elapsed((now - Date.parse(started)) / 1000)} in this run` : null,
    limit ? `${read} of ${limit} sources read` : `${plural(read, "source")} read`,
  ].filter(Boolean).join(" · ");
  return (
    <div className="ng-col">
      <span className="ng-label">Now</span>
      <div className="ng-well">
        {node.activity && (
          <ActivityLine activity={node.activity} detail={typeof act.detail === "string" ? act.detail : ""}
            retry={(act.retry as { n: number; m: number } | null | undefined) ?? null} />
        )}
        <div className="ng-faint inspector__now-meta">{meta}</div>
      </div>
    </div>
  );
}

/** The branch's own Spend, Nodes (when it may have any) and the node's Sources. */
function BranchMeters({ s, node, detail }: { s: Snapshot; node: GraphNode; detail: NodeDetail }) {
  const b = branchCounts(s, node.id);
  const read = new Set(detail.trail.map((t) => t.page_version_id).filter(Boolean)).size;
  return (
    <div className="ng-row inspector__meters">
      <div className="inspector__meter--wide"><BudgetMeter label="Spend" value={b.spent} max={s.investigation.spending_limit_usd} format="money" approximate={s.investigation.spend_approximate} /></div>
      {(b.nodesMax > 0 || b.nodes > 0) && <div className="inspector__meter"><BudgetMeter label="Nodes" value={b.nodes} max={b.nodesMax} format="count" /></div>}
      {node.budget?.sources ? <div className="inspector__meter"><BudgetMeter label="Sources" value={read} max={node.budget.sources} format="count" /></div> : null}
    </div>
  );
}

function countsLine({ events, node, detail }: Ctx): string {
  const sources = detail.claims.flatMap((c) => [...c.supporting, ...c.contradicting]).filter((x) => x.page_version_id);
  const lost = events.filter((e) => e.type === "page.unobtainable" && e.node_id === node.id).length;
  return [
    plural(detail.claims.length, "claim"),
    `${independent(sources)} independent ${independent(sources) === 1 ? "source" : "sources"}`,
    money(node.spent_usd),
    lost > 0 ? `${plural(lost, "page")} unobtainable` : null,
  ].filter(Boolean).join(" · ");
}

function CompletedOverview(ctx: Ctx) {
  const { s, node, detail } = ctx;
  return (
    <>
      <Verdict verdict={asVerdict(node.verdict) ?? asVerdict(detail.node.verdict)} counts={countsLine(ctx)} />
      {detail.open_questions.length > 0 && (
        <div className="ng-col">
          <span className="ng-label">Open questions</span>
          {detail.open_questions.map((q, i) => <span key={i} className="ng-small ng-muted">{q}</span>)}
        </div>
      )}
      {detail.proposals.length > 0 && (
        <div className="ng-col">
          <span className="ng-label">Follow-ups it proposed</span>
          {detail.proposals.map((p) => {
            const row = s.nodes.find((n) => n.id === p.node_id);
            const state = row?.status ?? (p.decision === "pending" ? "Proposed" : p.decision === "rejected" ? "Rejected" : "Pending");
            return (
              <div key={p.node_id} className="ng-col inspector__proposal">
                <div className="ng-row"><span className="ng-small ng-grow">{p.question}</span><StatusPill kind="node" state={state} /></div>
                {p.decision === "rejected" && p.reason && <span className="ng-small ng-muted">{p.reason}</span>}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

/** Rejected: only the proposal, who proposed it and the orchestrator's reason. */
function RejectedOverview({ s, node }: Ctx) {
  const by = proposedByText(node, s);
  return (
    <>
      <div className="ng-col">
        <span className="ng-label">Proposal</span>
        <p>{node.question}</p>
        {node.justification && <p className="ng-small ng-muted">{node.justification}</p>}
      </div>
      {by && <span className="ng-small">{by}</span>}
      <p className="ng-small ng-muted">{node.rejection_reason ? `Rejected by the orchestrator: ${node.rejection_reason}` : "Rejected by the orchestrator."}</p>
    </>
  );
}

/** Ignored or Superseded: who excluded it and when, and what is kept. */
function ExcludedOverview({ s, events, node, detail }: Ctx) {
  const inclusion = node.inclusion as "Ignored" | "Superseded";
  const ev = lastByNode(events, ["node.inclusion_changed"]).get(node.id);
  const fromEvent = ev && ev.data.inclusion === inclusion ? ev : null;
  const by = node.excluded_by ?? (fromEvent?.data.by as "user" | "replan" | undefined) ?? null;
  const at = node.excluded_at ?? fromEvent?.at ?? null;
  const instructionId = node.excluded_instruction_id ?? (fromEvent?.data.instruction_id as string | null | undefined) ?? null;
  let who: string | null = null;
  if (by === "replan") {
    const instruction = s.instructions.find((i) => i.id === instructionId);
    const on = instruction?.node_id ? s.nodes.find((n) => n.id === instruction.node_id)?.display_id : null;
    who = instruction ? `${inclusion} by your instruction${on ? ` on ${on}` : ""}` : `${inclusion} by a re-plan`;
  } else if (by === "user" && inclusion !== "Ignored") {
    who = `${inclusion} by you`;
  }
  const mono = [who, at ? timeOfDaySeconds(at) : null, fromEvent ? seqLabel(fromEvent.seq) : null].filter(Boolean).join(" · ");
  const n = detail.claims.length;
  const b = branchCounts(s, node.id);
  return (
    <>
      <div className="ng-row"><StatusPill kind="inclusion" state={inclusion} />{mono && <span className="ng-mono ng-faint">{mono}</span>}</div>
      <p className="ng-small ng-muted">
        {n === 0
          ? "This branch is stopped. It found no claims, and the report will list the branch as excluded."
          : `This branch is stopped. Its ${plural(n, "claim")} ${n === 1 ? "is" : "are"} kept out of the report, and the report will list the branch as excluded.`}
      </p>
      <div className="ng-well">{plural(b.nodes + 1, "node")} · {money(b.spent)} spent · {plural(n, "claim")} kept in storage</div>
    </>
  );
}

const STATUS_ORDER = Object.keys(CLAIM_STATUS) as Status[];

function ClaimsTab({ detail, displayIds }: Ctx) {
  const [filter, setFilter] = useState<Status | null>(null);
  const claims = detail.claims;
  if (claims.length === 0) return <span className="ng-small ng-muted">{NO_CLAIMS}</span>;
  const present = STATUS_ORDER.filter((st) => claims.some((c) => c.status === st));
  const shown = filter ? claims.filter((c) => c.status === filter) : claims;
  const tag = (on: boolean, label: string, onClick: () => void) => (
    <button key={label} type="button" className={cx("ng-tag", "inspector__filter", on && "ng-tag--solid")} aria-pressed={on} onClick={onClick}>{label}</button>
  );
  return (
    <>
      <div className="ng-row ng-row--tight">
        {tag(filter === null, `All ${claims.length}`, () => setFilter(null))}
        {present.map((st) => tag(filter === st, `${st} ${claims.filter((c) => c.status === st).length}`, () => setFilter(st)))}
      </div>
      {shown.map((c) => <ClaimCard key={c.id} claim={c} nodeDisplayIds={displayIds} />)}
    </>
  );
}

/** Inherited from the root down, then the node's own, oldest first: the order the agent reads them. */
function InstructionsTab({ node, detail, displayIds }: Ctx) {
  const { inherited, own } = detail.instructions;
  return (
    <>
      <span className="ng-label">In the order the agent reads them</span>
      {inherited.map((i) => <Instruction key={i.id} instruction={i} nodeDisplayIds={displayIds} variant="inherited" from={i.from_display_id} />)}
      {own.map((i) => <Instruction key={i.id} instruction={i} nodeDisplayIds={displayIds} variant={i.state === "queued" ? "queued" : "applied"} />)}
      {own.length === 0 && <span className="ng-small ng-muted">No instruction has been given to {node.display_id} itself.</span>}
    </>
  );
}
