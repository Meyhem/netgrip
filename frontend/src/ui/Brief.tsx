import type { GraphNode, NodeBrief } from "../api/types";
import { money } from "../lib/format";

/** What a node shows instead of a brief before it has started. */
export function noBriefText(node: GraphNode): string {
  return node.status === "Waiting on children"
    ? "This node has not started its own work; it waits on its children."
    : "This node has not started. Its brief is written when it starts.";
}

/** The brief as the agent received it, read-only (Brief README): Root goal, Path, Why, Task,
 * Out of scope, Done when, Known, Budget; then the instructions it was given. */
export function Brief({ brief, node }: { brief: NodeBrief | null; node: GraphNode }) {
  if (!brief) return <p className="ng-small ng-muted">{noBriefText(node)}</p>;
  const t = brief.task;
  const known = [
    brief.known.claims.map((c) => c.id).join(", "),
    ...brief.known.dependency_results.map((d) => (d.failed ? `${d.display_id} failed` : `result of ${d.display_id}`)),
  ].filter(Boolean).join(" · ");
  const budget = [
    `${money(node.spent_usd)} spent`,
    t.budget.sources != null ? `up to ${t.budget.sources} sources` : null,
    t.budget.child_nodes != null ? `up to ${t.budget.child_nodes} child nodes` : null,
  ].filter(Boolean).join(" · ");
  return (
    <div className="ng-col ng-col--loose">
      <dl className="ng-brief brief">
        <dt>Root goal</dt><dd>{brief.root_goal}</dd>
        <dt>Path</dt>
        <dd className="ng-col brief__path">
          {brief.path.map((p, i) => <span key={i} className="ng-muted">{p.display_id} → {p.question}</span>)}
          <span>{node.display_id} → {t.question}</span>
        </dd>
        <dt>Why</dt><dd>{node.justification ?? <span className="ng-muted">Not given.</span>}</dd>
        <dt>Task</dt><dd>{t.question}</dd>
        <dt>Out of scope</dt><dd className="ng-muted">{t.out_of_scope ?? "Not given."}</dd>
        <dt>Done when</dt><dd className="ng-muted">{t.done_when ?? "Not given."}</dd>
        <dt>Known</dt><dd><span className="ng-mono ng-muted">{known || "Nothing yet."}</span></dd>
        <dt>Budget</dt><dd><span className="ng-mono">{budget}</span></dd>
      </dl>
      {brief.known.instructions.length > 0 && (
        <div className="ng-col">
          <span className="ng-label">Instructions it was given</span>
          {brief.known.instructions.map((i, k) => (
            <div key={k} className="ng-instr ng-instr--inherited">
              <div className="ng-instr__meta"><span>From {i.from_display_id}</span></div>
              <div className="ng-instr__text">{i.text}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
