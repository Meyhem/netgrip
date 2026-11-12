import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import type { GraphNode as Node } from "../api/types";
import { edgePath, layoutGraph, NODE_H, NODE_H_SHORT, type LayoutEdge } from "../lib/layout";
import { Button } from "./Button";
import { cx } from "./cx";
import { GraphNode, nodeSub, type GraphMode } from "./GraphNode";

/** What a screen adds to a node beyond its snapshot data (plan review: "new", "− Removed"). */
export interface NodeExtra {
  sub?: string | null;
  mark?: string | null;
  removed?: boolean;
}

export interface GraphCanvasProps {
  nodes: Node[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  mode: GraphMode;
  /** Toolbar content before "Fit". */
  toolbar?: ReactNode;
  /** Toolbar content after "Fit". */
  toolbarEnd?: ReactNode;
  extras?: Record<string, NodeExtra>;
}

interface View { x: number; y: number; k: number }

const NO_EXTRAS: Record<string, NodeExtra> = {};

const MIN_K = 0.2;
const MAX_K = 2;
const FIT_PAD = 8;
/** The first view of a large plan stays readable rather than shrinking to fit. */
const AUTO_FIT_MIN_K = 0.6;
/** Movement below this is a click, not a drag. */
const DRAG_SLOP = 3;

/**
 * The task graph: an `ng-toolbar` row with Fit, then the `ng-canvas`. Returned as two siblings so
 * they fill the toolbar and canvas rows of `ng-center`. Drag pans, the wheel zooms, a click
 * selects, a double-click folds a branch.
 */
export function GraphCanvas({ nodes, selectedId, onSelect, mode, toolbar, toolbarEnd, extras = NO_EXTRAS }: GraphCanvasProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  const canvasRef = useRef<HTMLDivElement>(null);
  const dragged = useRef(false);
  const arrowId = `graph-arrow${useId().replace(/:/g, "")}`;

  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const subs = useMemo(() => {
    const out: Record<string, string | null> = {};
    for (const n of nodes) {
      const extra = extras[n.id];
      out[n.id] = extra && extra.sub !== undefined ? extra.sub : nodeSub(n) ?? plannedSub(n, byId);
    }
    return out;
  }, [nodes, extras, byId]);

  const layout = useMemo(
    () =>
      layoutGraph(
        nodes.map((n) => ({
          id: n.id,
          parentId: n.parent_id,
          // Every child of the root waits on every premise check (I2). Those waits are said once,
          // as "runs first" on the premise check, instead of an arrow into every node.
          dependsOn: n.depends_on.filter((d) => byId.get(d)?.kind !== "Premise check"),
          height: subs[n.id] ? NODE_H : NODE_H_SHORT,
        })),
        { collapsed },
      ),
    [nodes, byId, subs, collapsed],
  );

  const parents = useMemo(() => new Set(nodes.map((n) => n.parent_id).filter((p): p is string => !!p)), [nodes]);

  const off = (id: string) => byId.get(id)?.inclusion !== "Included" || !!extras[id]?.removed;
  // The chain from the root to each running node (board mode only; nothing is live in a plan).
  const live = useMemo(() => {
    const out = new Set<string>();
    if (mode !== "board") return out;
    for (const n of nodes) {
      if (n.status !== "Running" || n.inclusion !== "Included") continue;
      for (let cur: Node | undefined = n; cur && !out.has(cur.id); cur = cur.parent_id ? byId.get(cur.parent_id) : undefined) out.add(cur.id);
    }
    return out;
  }, [nodes, byId, mode]);

  const edgeClass = (e: LayoutEdge) => {
    const isOff = off(e.from) || off(e.to);
    return cx(
      "ng-edge",
      e.kind === "dependency" && "ng-edge--dep",
      isOff && "ng-edge--off",
      !isOff && e.kind === "decomposition" && live.has(e.to) && "ng-edge--live",
    );
  };

  const rootId = nodes.find((n) => !n.parent_id || !byId.has(n.parent_id))?.id;
  /** Scales the whole graph into view. `minK` keeps it readable: a taller graph is then centred
   * on the root. Returns false while the canvas has no size yet. */
  const fit = useCallback(
    (minK = MIN_K) => {
      const el = canvasRef.current;
      const cw = el?.clientWidth ?? 0;
      const ch = el?.clientHeight ?? 0;
      if (!cw || !ch || !layout.width) {
        setView((v) => (v.x === 0 && v.y === 0 && v.k === 1 ? v : { x: 0, y: 0, k: 1 }));
        return false;
      }
      const k = clamp(Math.max(minK, Math.min(1, (cw - 2 * FIT_PAD) / layout.width, (ch - 2 * FIT_PAD) / layout.height)));
      const root = rootId ? layout.positions[rootId] : undefined;
      const y = layout.height * k <= ch - 2 * FIT_PAD || !root
        ? Math.max(FIT_PAD, (ch - layout.height * k) / 2)
        : ch / 2 - (root.y + NODE_H / 2) * k;
      setView({ x: FIT_PAD, y, k });
      return true;
    },
    [layout, rootId],
  );

  // Fit once, when the graph first has nodes and the canvas has a size. Later redraws keep the
  // user's pan and zoom; "Fit" is always there.
  const fitted = useRef(false);
  const autoFit = useRef(() => {});
  autoFit.current = () => {
    if (!fitted.current && nodes.length > 0) fitted.current = fit(AUTO_FIT_MIN_K);
  };
  useLayoutEffect(() => autoFit.current(), [nodes.length, fit]);
  useEffect(() => {
    const el = canvasRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => autoFit.current());
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const px = e.clientX - r.left;
      const py = e.clientY - r.top;
      setView((v) => {
        const k = clamp(v.k * Math.exp(-e.deltaY * 0.001));
        return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const onMouseDown = (e: ReactMouseEvent) => {
    if (e.button !== 0) return;
    dragged.current = false;
    const sx = e.clientX;
    const sy = e.clientY;
    let last = { x: sx, y: sy };
    const move = (m: MouseEvent) => {
      if (Math.abs(m.clientX - sx) > DRAG_SLOP || Math.abs(m.clientY - sy) > DRAG_SLOP) dragged.current = true;
      const dx = m.clientX - last.x;
      const dy = m.clientY - last.y;
      last = { x: m.clientX, y: m.clientY };
      setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const toggleFold = (id: string) =>
    setCollapsed((c) => {
      const next = new Set(c);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <>
      <div className="ng-toolbar">
        {toolbar}
        <Button variant="quiet" size="sm" className="ng-right" onClick={() => fit()}>Fit</Button>
        {toolbarEnd}
      </div>
      <div
        ref={canvasRef}
        className="ng-canvas"
        style={{ cursor: "grab", backgroundPosition: `${view.x}px ${view.y}px` }}
        onMouseDown={onMouseDown}
        onClickCapture={(e) => {
          // The click that ends a drag does not select.
          if (dragged.current) {
            dragged.current = false;
            e.stopPropagation();
          }
        }}
      >
        <div
          style={{
            position: "absolute", left: 0, top: 0, width: layout.width, height: layout.height,
            transformOrigin: "0 0", transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`,
          }}
        >
          <svg style={{ overflow: "visible" }}>
            <defs>
              <marker id={arrowId} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
                <path className="ng-edge-arrow" d="M0 0L8 4L0 8z" />
              </marker>
            </defs>
            {layout.edges.map((e) => (
              <path
                key={`${e.kind}:${e.from}>${e.to}`}
                data-edge={`${e.from}>${e.to}`}
                className={edgeClass(e)}
                d={edgePath(e.points)}
                markerEnd={e.kind === "dependency" ? `url(#${arrowId})` : undefined}
              />
            ))}
          </svg>
          {nodes.map((n) => {
            const pos = layout.positions[n.id];
            if (!pos) return null;
            const extra = extras[n.id] ?? {};
            const hidden = layout.hiddenCount[n.id];
            return (
              <GraphNode
                key={n.id}
                node={n}
                mode={mode}
                selected={n.id === selectedId}
                onSelect={onSelect}
                sub={subs[n.id]}
                mark={extra.mark}
                removed={extra.removed}
                fold={hidden ? `+${hidden}` : parents.has(n.id) ? "−" : null}
                onFold={parents.has(n.id) ? toggleFold : undefined}
                style={{ left: pos.x, top: pos.y, height: subs[n.id] ? NODE_H : NODE_H_SHORT }}
              />
            );
          })}
        </div>
      </div>
    </>
  );
}

const clamp = (k: number) => Math.min(MAX_K, Math.max(MIN_K, k));

/** Before a node runs, line 3 says what it waits for: premise checks run first (I2). */
function plannedSub(n: Node, byId: Map<string, Node>): string | null {
  if (n.status !== "Proposed" && n.status !== "Pending") return null;
  if (n.kind === "Premise check") return "runs first";
  const after = n.depends_on.map((d) => byId.get(d)).filter((d): d is Node => !!d && d.kind !== "Premise check");
  return after.length ? `after ${after.map((d) => d.display_id).join(", ")}` : null;
}
