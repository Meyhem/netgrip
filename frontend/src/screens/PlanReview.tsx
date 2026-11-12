import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { deleteInvestigation } from "../api/client";
import type { GraphNode, Instruction as InstructionData, Snapshot } from "../api/types";
import { forgetInvestigation, useInvestigation } from "../state/investigationStore";
import { useCommand } from "../state/useCommand";
import { ActivityLine } from "../ui/ActivityLine";
import { Banner } from "../ui/Banner";
import { BudgetMeter } from "../ui/BudgetMeter";
import { Button } from "../ui/Button";
import { DeleteDialog } from "../ui/DeleteDialog";
import { GraphCanvas, type NodeExtra } from "../ui/GraphCanvas";
import { Instruction } from "../ui/Instruction";
import { InstructionComposer } from "../ui/InstructionComposer";
import { StatusPill } from "../ui/StatusPill";
import { NotBuilt, Page } from "./InvestigationRoute";
import { PRESET_WORD } from "./NewInvestigation";

/** A re-plan that produced a version. A failed one is applied with an empty diff and a note. */
const madeVersion = (i: InstructionData) =>
  i.state === "applied" && !!i.diff && i.diff.kept.length + i.diff.superseded.length + i.diff.proposed.length > 0;

/** The instructions behind the current plan, oldest first: instruction k made version k + 2.
 * Undo always takes the latest one off (R8), so the ones not undone are the current chain. */
export function versionChain(s: Snapshot): InstructionData[] {
  return s.instructions.filter(madeVersion).sort((a, b) => (a.applied_seq ?? 0) - (b.applied_seq ?? 0));
}

/** "a", "a and b", "a, b and c". */
const list = (xs: string[]) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

/** The "On approval" note: premise checks first (I2), then the root's other children that wait
 * on nothing else, `parallel` at a time. */
export function approvalNote(nodes: GraphNode[], parallel: number | undefined): string {
  const included = nodes.filter((n) => n.inclusion === "Included");
  const byId = new Map(included.map((n) => [n.id, n]));
  const root = included.find((n) => n.parent_id === null);
  if (!root) return "";
  const children = included.filter((n) => n.parent_id === root.id);
  const premises = children.filter((n) => n.kind === "Premise check").map((n) => n.display_id);
  const first = children
    .filter((n) => n.kind !== "Premise check" && n.depends_on.every((d) => byId.get(d)?.kind === "Premise check" || !byId.has(d)))
    .map((n) => n.display_id);
  const parts: string[] = [];
  if (premises.length) parts.push(`${list(premises)} ${premises.length === 1 ? "runs" : "run"} first.`);
  if (first.length) {
    const lead = premises.length ? "Then " : "";
    const at = parallel ? `, ${parallel} at a time` : "";
    parts.push(first.length === 1 ? `${lead}${first[0]} runs.` : `${lead}${list(first)} run in parallel${at}.`);
  }
  parts.push("The orchestrator may add nodes as it learns; each one appears here with its reason.");
  return parts.join(" ");
}

/** ScreenPlanReview: the Planning state. The user reshapes the plan with instructions and
 * approves it. Everything shown comes from the snapshot and its events. */
export function PlanReview({ id }: { id: string }) {
  const { snapshot, status, error } = useInvestigation(id);
  if (!snapshot) {
    return error ? <Page><Banner tone="warn" title="Netgrip cannot reach its service.">Reload to try again. Nothing is lost.</Banner></Page> : null;
  }
  const state = snapshot.investigation.state;
  if (state !== "Planning" && state !== "Draft") return <NotBuilt state={state} origin={snapshot.investigation.pause_cause} />;
  return <Review id={id} s={snapshot} reconnecting={status === "reconnecting"} />;
}

function Review({ id, s, reconnecting }: { id: string; s: Snapshot; reconnecting: boolean }) {
  const navigate = useNavigate();
  const { send, isSent, error } = useCommand(id);
  const [selected, setSelected] = useState<string | null>(null);
  const [discarding, setDiscarding] = useState(false);
  const inv = s.investigation;
  const v = s.plan_version;

  const chain = useMemo(() => versionChain(s), [s]);
  const last = v > 1 ? chain[chain.length - 1] ?? null : null;
  const versionOf = useMemo(() => new Map(chain.map((i, k) => [i.id, `plan v${k + 1} → v${k + 2}`])), [chain]);

  const root = s.nodes.find((n) => n.parent_id === null) ?? null;
  const removed = useMemo(() => new Set(last?.diff?.superseded ?? []), [last]);
  const visible = useMemo(() => s.nodes.filter((n) => n.inclusion === "Included" || removed.has(n.id)), [s.nodes, removed]);
  const extras = useMemo(() => {
    const out: Record<string, NodeExtra> = {};
    for (const nid of last?.diff?.proposed ?? []) out[nid] = { mark: "new", sub: "added by your instruction" };
    for (const nid of removed) out[nid] = { removed: true };
    // The instructions are listed in the right pane; the root carries no count mark here.
    if (root) out[root.id] = { ...out[root.id], mark: null };
    return out;
  }, [last, removed, root]);
  const displayIds = useMemo(() => Object.fromEntries(s.nodes.map((n) => [n.id, n.display_id])), [s.nodes]);
  const questions = useMemo(() => Object.fromEntries(s.nodes.map((n) => [n.id, n.question])), [s.nodes]);

  const queued = s.instructions.filter((i) => i.state === "queued");
  // Also derived from the snapshot: a re-plan recovered after a restart has no command id.
  const replanning = queued.length > 0 || isSent("instruct");
  const draftFailed = v === 0 && s.plan_failed != null;
  const drafting = v === 0 && (!draftFailed || isSent("draft"));
  const busy = replanning || drafting;
  const canApprove = inv.state === "Planning" && v > 0 && !busy && !isSent("undo");

  const included = s.nodes.filter((n) => n.inclusion === "Included");
  const planned = included.filter((n) => n.parent_id !== null).length;
  const budget = inv.settings?.effort_budget;
  const preset = inv.settings?.preset;
  const meta = [inv.effort, preset ? PRESET_WORD[preset] : null, "no research has run", reconnecting ? "reconnecting" : null]
    .filter(Boolean).join(" · ");

  const planEvent = (ev: { type: string }) => ev.type === "plan.version_created" || ev.type === "plan.failed";
  const instructions = [...s.instructions].sort((a, b) => b.queued_seq - a.queued_seq);

  const toolbar = (
    <>
      <span className="ng-label">{v > 0 ? `Proposed plan · version ${v}` : "Proposed plan"}</span>
      {drafting ? (
        <ActivityLine activity="Planning" detail="Drafting the plan from your prompt" />
      ) : replanning ? (
        <ActivityLine activity="Planning" detail={queued.length ? `Re-planning… "${queued[0].text}"` : "Re-planning…"} />
      ) : last?.diff ? (
        <span className="ng-mono ng-muted">
          changed by your last instruction: {last.diff.superseded.length} removed, {last.diff.proposed.length} added
        </span>
      ) : null}
    </>
  );

  return (
    <div className="ng-board plan-review">
      <div className="ng-board__head">
        <div className="ng-col ng-grow plan-review__title">
          <div className="ng-row ng-row--nowrap">
            <StatusPill kind="investigation" state={inv.state} />
            <span className="ng-mono ng-muted">{meta}</span>
          </div>
          <h1 className="ng-title ng-clip" title={inv.prompt}>{inv.prompt}</h1>
        </div>
        <div className="plan-review__spend">
          <BudgetMeter label="Spend" value={inv.spent_usd} max={inv.spending_limit_usd} format="money" approximate={inv.spend_approximate} />
        </div>
        <div className="plan-review__nodes">
          <BudgetMeter label="Planned nodes" value={planned} max={budget?.max_nodes ?? inv.nodes_max} format="count" />
        </div>
        <div className="ng-row ng-row--nowrap">
          <Button variant="quiet" onClick={() => setDiscarding(true)}>Discard draft</Button>
          <Button variant="steer" disabled={!canApprove} sent={isSent("approve")} sentLabel="Starting…"
            onClick={() => void send("approve_plan", { key: "approve", until: (ev) => ev.type === "investigation.state_changed" })}>
            Approve plan and start
          </Button>
        </div>
      </div>
      <div className="ng-board__body plan-review__body">
        <div className="ng-center">
          <GraphCanvas
            nodes={visible}
            selectedId={selected ?? root?.id ?? null}
            onSelect={setSelected}
            mode="plan"
            extras={extras}
            toolbar={toolbar}
            toolbarEnd={
              <Button size="sm" variant="quiet" disabled={v <= 1 || busy} sent={isSent("undo")} sentLabel="Undoing…"
                onClick={() => void send("undo_plan_instruction", { key: "undo", until: (ev) => ev.type === "plan.reverted" })}>
                Undo last instruction
              </Button>
            }
          />
          <div className="ng-dock ng-col plan-review__dock">
            {error && <p className="ng-small ng-danger">{error.message}</p>}
            {draftFailed && (
              <div className="ng-col">
                <Banner tone="warn" title="Netgrip could not draft the plan.">
                  {s.plan_failed} Nothing was researched. Planning so far is counted in Spend.
                </Banner>
                <div className="ng-row">
                  <Button sent={isSent("draft")} sentLabel="Drafting…"
                    onClick={() => void send("draft_plan", { key: "draft", until: planEvent })}>
                    Draft the plan
                  </Button>
                </div>
              </div>
            )}
            {v > 0 && root && (
              <InstructionComposer
                target={{ id: root.id, display_id: root.display_id, label: "the whole investigation" }}
                reach={included.length}
                hasChildren={included.length > 1}
                plan
                buttonLabel="Re-plan"
                sent={replanning}
                sentLabel="Re-planning…"
                draftKey={id}
                onSend={(text) => send("instruct_plan", { key: "instruct", payload: { text } })}
              />
            )}
          </div>
        </div>
        <aside className="ng-pane ng-pane--right">
          <div className="ng-pane__scroll ng-col ng-col--loose plan-review__pane">
            <div className="ng-col">
              <span className="ng-label">Root goal</span>
              <p>{inv.root_goal ?? (drafting ? "Netgrip is drafting it from your prompt." : "Not drafted yet.")}</p>
              <span className="ng-small ng-muted">Derived from your prompt. Fixed once you approve.</span>
            </div>
            {(v > 0 || s.premises.length > 0) && (
              <div className="ng-col">
                <span className="ng-label">Assumptions in your question · checked first</span>
                {s.premises.map((p) => (
                  <div key={p.id} className="ng-claim">
                    <div className="ng-row"><span className="ng-tag">PRM</span><span className="ng-mono ng-faint">{p.node_id ? displayIds[p.node_id] : ""}</span></div>
                    <span>{p.text}</span>
                  </div>
                ))}
                <span className="ng-small ng-muted">
                  {s.premises.length
                    ? "Your question takes these as given. If they turn out false, the report says so first."
                    : "Netgrip found nothing your question takes as given."}
                </span>
              </div>
            )}
            {v > 0 && (
              <div className="ng-col">
                <span className="ng-label">Your instructions so far</span>
                {instructions.length === 0 && (
                  <span className="ng-small ng-muted">None yet. Each instruction redraws the plan; Undo takes the last one back.</span>
                )}
                {instructions.map((i) => (
                  <Instruction key={i.id} instruction={i} nodeDisplayIds={displayIds} nodeQuestions={questions}
                    variant={i.state === "queued" ? "queued" : "applied"} versionLabel={versionOf.get(i.id)} />
                ))}
              </div>
            )}
            {v > 0 && (
              <div className="ng-col">
                <span className="ng-label">On approval</span>
                <p className="ng-small ng-muted">{approvalNote(s.nodes, budget?.parallel)}</p>
              </div>
            )}
          </div>
        </aside>
      </div>
      {discarding && (
        <DeleteDialog
          prompt={inv.prompt}
          diskBytes={inv.disk_bytes}
          onCancel={() => setDiscarding(false)}
          onDelete={async () => {
            await deleteInvestigation(id);
            forgetInvestigation(id);
            navigate("/");
          }}
        />
      )}
    </div>
  );
}
