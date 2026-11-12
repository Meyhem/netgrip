// Graph layout for GraphCanvas (dagre). Depth runs left to right, as the GraphCanvas README
// says: the root goal sits at the left edge. Positions are box top-left corners.
import dagre from "@dagrejs/dagre";

/** GraphNode box: 172 wide; three lines (top 16 + question 2×17 + sub 16, gaps, padding, border). */
export const NODE_W = 172;
export const NODE_H = 84;
/** Without line 3. */
export const NODE_H_SHORT = 66;
/** Gaps taken from the GraphCanvas preview: 16 between boxes in a column, 48 between columns. */
const NODE_SEP = 16;
const RANK_SEP = 48;
const MARGIN = 16;
/** Dependency edges stop short so the arrowhead meets the box edge. */
const ARROW_GAP = 2;

export interface LayoutInput {
  id: string;
  parentId: string | null;
  dependsOn: string[];
  /** Box height; NODE_H when left out. */
  height?: number;
}

export type EdgeKind = "decomposition" | "dependency";
export interface Point { x: number; y: number }
export interface LayoutEdge { from: string; to: string; kind: EdgeKind; points: Point[] }

export interface Layout {
  positions: Record<string, Point>;
  edges: LayoutEdge[];
  width: number;
  height: number;
  /** For each visible collapsed node, how many descendants its fold hides. */
  hiddenCount: Record<string, number>;
}

export function layoutGraph(nodes: LayoutInput[], opts: { collapsed?: Set<string> } = {}): Layout {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const children = new Map<string, string[]>();
  for (const n of nodes) {
    if (n.parentId && byId.has(n.parentId)) children.set(n.parentId, [...(children.get(n.parentId) ?? []), n.id]);
  }
  const collapsed = opts.collapsed ?? new Set<string>();
  const hidden = new Set<string>();
  const hiddenCount: Record<string, number> = {};
  const hide = (id: string): number =>
    (children.get(id) ?? []).reduce((sum, c) => (hidden.add(c), sum + 1 + hide(c)), 0);
  // Roots first so an outer collapse wins over one nested inside it.
  for (const n of nodes) {
    if (collapsed.has(n.id) && !hidden.has(n.id) && !isUnder(n.id, collapsed, byId)) {
      const count = hide(n.id);
      if (count > 0) hiddenCount[n.id] = count;
    }
  }
  const visible = nodes.filter((n) => !hidden.has(n.id));
  if (visible.length === 0) return { positions: {}, edges: [], width: 0, height: 0, hiddenCount };

  const g = new dagre.graphlib.Graph({ multigraph: true });
  g.setGraph({ rankdir: "LR", nodesep: NODE_SEP, ranksep: RANK_SEP, marginx: MARGIN, marginy: MARGIN });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of visible) g.setNode(n.id, { width: NODE_W, height: n.height ?? NODE_H });

  const wanted: { from: string; to: string; kind: EdgeKind }[] = [];
  for (const n of visible) {
    if (n.parentId && byId.has(n.parentId)) wanted.push({ from: n.parentId, to: n.id, kind: "decomposition" });
    for (const d of n.dependsOn) {
      if (byId.has(d) && !hidden.has(d) && d !== n.id) wanted.push({ from: d, to: n.id, kind: "dependency" });
    }
  }
  for (const e of wanted) {
    g.setEdge(e.from, e.to, { minlen: 1, weight: e.kind === "decomposition" ? 2 : 1 }, e.kind);
  }
  dagre.layout(g);

  const positions: Record<string, Point> = {};
  const boxes = new Map<string, { x: number; y: number; w: number; h: number }>();
  for (const n of visible) {
    const v = g.node(n.id);
    const box = { x: v.x - v.width / 2, y: v.y - v.height / 2, w: v.width, h: v.height };
    boxes.set(n.id, box);
    positions[n.id] = { x: box.x, y: box.y };
  }
  const columns = [...new Set([...boxes.values()].map((b) => b.x))];

  const edges = wanted.map((e): LayoutEdge => {
    const a = boxes.get(e.from)!;
    const b = boxes.get(e.to)!;
    const start = { x: a.x + a.w, y: a.y + a.h / 2 };
    const end = { x: b.x - (e.kind === "dependency" ? ARROW_GAP : 0), y: b.y + b.h / 2 };
    // Adjacent columns get one clean curve; longer edges keep dagre's bends between columns.
    const spans = columns.some((x) => x > a.x && x < b.x);
    const inner = spans
      ? ((g.edge({ v: e.from, w: e.to, name: e.kind })?.points ?? []) as Point[]).slice(1, -1).filter((p) => p.x > start.x && p.x < end.x)
      : [];
    return { ...e, points: [start, ...inner.map((p) => ({ x: p.x, y: p.y })), end] };
  });

  const { width = 0, height = 0 } = g.graph();
  return { positions, edges, width, height, hiddenCount };
}

function isUnder(id: string, collapsed: Set<string>, byId: Map<string, LayoutInput>): boolean {
  const seen = new Set<string>();
  for (let p = byId.get(id)?.parentId; p && !seen.has(p); p = byId.get(p)?.parentId) {
    if (collapsed.has(p)) return true;
    seen.add(p);
  }
  return false;
}

/** An SVG path through the points with horizontal tangents, as in the GraphCanvas preview. */
export function edgePath(points: Point[]): string {
  const f = (n: number) => Math.round(n * 10) / 10;
  let d = `M${f(points[0].x)} ${f(points[0].y)}`;
  for (let i = 1; i < points.length; i++) {
    const p = points[i - 1];
    const q = points[i];
    const m = (p.x + q.x) / 2;
    d += `C${f(m)} ${f(p.y)} ${f(m)} ${f(q.y)} ${f(q.x)} ${f(q.y)}`;
  }
  return d;
}
