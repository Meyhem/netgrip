import { useEffect, useRef, useState, type ReactNode } from "react";
import type { GraphNode, InvestigationState, Snapshot } from "../api/types";
import type { useCommand } from "../state/useCommand";
import { Banner } from "./Banner";
import { Button } from "./Button";

type Command = ReturnType<typeof useCommand>;

export type ActionType =
  | "instruct" | "go_deeper" | "run_only" | "run_everything"
  | "pause_branch" | "resume_branch" | "ignore_branch" | "restore_branch" | "rerun_node";

export interface Action {
  type: ActionType;
  label: string;
  /** The shortcut shown beside it. */
  key: string;
  enabled: boolean;
  /** One line: scope and effect when enabled, the reason when not. */
  consequence: string;
}

/** The label while the command is in flight (`is-sent`), until its event arrives. */
export const SENT_LABEL: Record<ActionType, string> = {
  instruct: "Instructing…", go_deeper: "Going deeper…", run_only: "Focusing…", run_everything: "Running everything…",
  pause_branch: "Pausing…", resume_branch: "Resuming…", ignore_branch: "Ignoring…",
  restore_branch: "Restoring…", rerun_node: "Re-running…",
};

/** The command each action sends (instruct opens the composer; re-run asks first). */
export const COMMAND: Partial<Record<ActionType, string>> = {
  go_deeper: "go_deeper", run_only: "run_only_branch", run_everything: "run_everything",
  pause_branch: "pause_branch", resume_branch: "resume_branch", ignore_branch: "ignore_branch",
  restore_branch: "restore_branch", rerun_node: "rerun_node",
};

export function descendants(s: Snapshot, id: string): number {
  let n = 0;
  const todo = [id];
  while (todo.length) {
    const cur = todo.pop()!;
    for (const c of s.nodes) if (c.parent_id === cur) { n++; todo.push(c.id); }
  }
  return n;
}

const scope = (n: number) => (n === 0 ? "this node" : `this node and its ${n} ${n === 1 ? "descendant" : "descendants"}`);
const STEERABLE: InvestigationState[] = ["Running", "Paused", "Stopped"];

/** The node whose composer an Add instruction aims at: a Rejected node has none of its own, so
 * its parent (ScreenNodeDetail). */
export function instructTarget(s: Snapshot, node: GraphNode): GraphNode {
  return node.status === "Rejected" ? s.nodes.find((n) => n.id === node.parent_id) ?? node : node;
}

/** What the user can do to `node` now (NodeActions README, "Applies when"). Items that do not
 * apply stay, disabled, with the reason as their consequence. */
export function actionsFor(node: GraphNode, s: Snapshot): Action[] {
  const inv = s.investigation;
  const n = descendants(s, node.id);
  const isRoot = node.parent_id === null;
  const included = node.inclusion === "Included";
  const rejected = node.status === "Rejected";
  const steerable = STEERABLE.includes(inv.state);
  const lock = steerable ? null : `Not possible while the investigation is ${inv.state}.`;
  const make = (type: ActionType, label: string, key: string, reason: string | null, effect: string): Action =>
    ({ type, label, key, enabled: reason === null, consequence: reason ?? effect });

  const target = instructTarget(s, node);
  const targetN = descendants(s, target.id);
  const instructReason =
    target.parent_id === null && inv.state !== "Planning" ? "The root goal cannot be re-planned once research is running. Instruct a branch."
    : inv.state !== "Running" && inv.state !== "Paused" ? `Instructions are locked while the investigation is ${inv.state}.`
    : null;
  const instruct = make("instruct", "Add instruction", "I", instructReason,
    rejected
      ? `Guide ${target.display_id}, the parent that proposed it.`
      : targetN === 0 ? "Takes effect at the node's next step." : `Guide ${scope(targetN)}. Takes effect at the next step.`);

  if (rejected) {
    const off = (type: ActionType, label: string, key: string) => make(type, label, key, "A rejected node never ran.", "");
    return [instruct, off("go_deeper", "Go deeper", "D"), off("run_only", "Run only this branch", "F"),
      off("pause_branch", "Pause branch", "Space"), off("ignore_branch", "Ignore branch", "X"), off("rerun_node", "Re-run node", "R")];
  }

  const rootReason = isRoot ? "Use the investigation's own controls." : null;
  const focused = s.focus_node_id === node.id;
  const pausable = ["Pending", "Running", "Waiting on children"].includes(node.status);
  const pauseAction = node.status === "Paused"
    ? make("resume_branch", "Resume branch", "Space", lock ?? rootReason, `Continues ${scope(n)}.`)
    : make("pause_branch", "Pause branch", "Space", lock ?? rootReason ?? (pausable ? null : "Nothing here is waiting or running."),
        `Suspends ${scope(n)}. Running steps finish first.`);
  return [
    instruct,
    make("go_deeper", "Go deeper", "D", lock ?? rootReason ?? (included ? null : "Restore the branch first."),
      `Grants ${scope(n)} more budget: one level, 1.5 times the child nodes and sources.`),
    focused
      ? make("run_everything", "Run everything", "F", lock, "The rest of the graph runs again.")
      : make("run_only", "Run only this branch", "F",
          inv.state !== "Running" ? "Available while the investigation is running." : rootReason ?? (included ? null : "Restore the branch first."),
          `The rest of the graph waits. Reaches ${n + 1} ${n === 0 ? "node" : "nodes"}.`),
    pauseAction,
    included
      ? make("ignore_branch", "Ignore branch", "X", lock ?? rootReason,
          `Stops ${scope(n)} and keeps its findings out of the report. You can restore it.`)
      : make("restore_branch", "Restore branch", "X", lock ?? rootReason,
          `Brings back ${scope(n)} with the results it already had.`),
    make("rerun_node", "Re-run node", "R",
      lock ?? rootReason ?? (included ? (["Completed", "Failed"].includes(node.status) ? null : "Available once the node has completed or failed.") : "Restore the branch first."),
      "Discards its verdict and claims and runs it again. Fetched pages are reused."),
  ];
}

export interface NodeActionState {
  actions: Action[];
  /** Run the action by type (what a key or a click does). */
  run: (type: ActionType) => void;
  /** By shortcut: the first enabled action of that key (X, Space, F, ...). */
  runKey: (key: string) => void;
  isSent: (type: ActionType) => boolean;
  rerunAsk: boolean;
  confirmRerun: () => void;
  cancelRerun: () => void;
  menu: boolean;
  setMenu: (open: boolean | ((o: boolean) => boolean)) => void;
}

/** The actions of the selected node with their state: what is in flight, the menu, and the
 * inline re-run question. `onInstruct` opens the composer. */
export function useNodeActions(s: Snapshot | null, node: GraphNode | null, command: Command, onInstruct: () => void): NodeActionState {
  const [menu, setMenu] = useState(false);
  const [askFor, setAskFor] = useState<string | null>(null);
  const id = node?.id ?? null;
  // The question belongs to one node: selecting another closes it.
  useEffect(() => { setAskFor(null); setMenu(false); }, [id]);
  const actions = node && s ? actionsFor(node, s) : [];
  const sentKey = (type: ActionType) => `${type}:${id}`;
  const send = (type: ActionType) => {
    const c = COMMAND[type];
    if (c && id) void command.send(c, { key: sentKey(type), nodeId: id });
  };
  const run = (type: ActionType) => {
    const a = actions.find((x) => x.type === type);
    if (!a || !a.enabled || !id) return;
    setMenu(false);
    if (type === "instruct") onInstruct();
    else if (type === "rerun_node") setAskFor(id);
    else send(type);
  };
  return {
    actions,
    run,
    runKey: (key) => { const a = actions.find((x) => x.key === key && x.enabled); if (a) run(a.type); },
    isSent: (type) => command.isSent(sentKey(type)),
    rerunAsk: askFor !== null && askFor === id,
    confirmRerun: () => { setAskFor(null); send("rerun_node"); },
    cancelRerun: () => setAskFor(null),
    menu,
    setMenu,
  };
}

/** The four most used actions as the inspector's action row, the rest in the node menu
 * (`ng-menu`, opened by `.` or the overflow). Everything applies at once; only re-run asks. */
export function NodeActions({ state }: { state: NodeActionState }): ReactNode {
  const { actions, run, isSent, menu, setMenu } = state;
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setMenu(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu, setMenu]);
  if (actions.length === 0) return null;
  const row = actions.filter((a) => ["instruct", "go_deeper", "pause_branch", "resume_branch", "ignore_branch", "restore_branch"].includes(a.type));
  return (
    <div className="ng-row ng-row--tight" ref={ref} style={{ position: "relative" }}>
      {row.map((a) => (
        <Button key={a.type} size="sm" variant="quiet" title={a.consequence} disabled={!a.enabled}
          sent={isSent(a.type)} sentLabel={SENT_LABEL[a.type]} onClick={() => run(a.type)}>
          {a.label}
        </Button>
      ))}
      <Button size="sm" variant="quiet" aria-label="Node menu" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((o) => !o)}>⋯</Button>
      {menu && (
        <div className="ng-menu row-menu" role="menu" aria-label="Node actions">
          {actions.map((a, i) => (
            <div key={a.type}>
              {(a.type === "ignore_branch" || a.type === "restore_branch") && i > 0 && <div className="ng-menu__sep" />}
              <div className={`ng-menu__item${a.enabled ? "" : " is-disabled"}`} role="menuitem" tabIndex={a.enabled ? 0 : -1}
                aria-disabled={!a.enabled} onClick={() => run(a.type)}
                onKeyDown={(e) => { if (e.key === "Enter") run(a.type); }}>
                <b>{isSent(a.type) ? SENT_LABEL[a.type] : a.label}</b>
                <span className="ng-kbd">{a.key}</span>
                <small>{a.consequence}</small>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Re-run asks once, inline in the inspector, with a danger banner. No modal. */
export function RerunQuestion({ node, state }: { node: GraphNode; state: NodeActionState }) {
  if (!state.rerunAsk) return null;
  return (
    <Banner tone="danger" glyph="!" title={`Re-run ${node.display_id}?`}>
      Its verdict and its claims are discarded. Fetched pages are reused.
      <span className="ng-row">
        <Button size="sm" variant="danger" onClick={state.confirmRerun}>Re-run node</Button>
        <Button size="sm" variant="quiet" onClick={state.cancelRerun}>Keep result</Button>
      </span>
    </Banner>
  );
}
