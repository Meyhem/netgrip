// Graph layout for GraphCanvas: a radial tree. The root goal sits in the middle and depth runs
// outward in rings. Positions are box top-left corners.

/** GraphNode box: 172 wide; three lines (top 16 + question 2×17 + sub 16, gaps, padding, border). */
export const NODE_W = 172;
export const NODE_H = 84;
/** Without line 3. */
export const NODE_H_SHORT = 66;
/** Ring spacing: boxes on neighbouring rings stay clear in any direction. */
const RING_STEP = 220;
/** Least distance between two box centres on one ring (clears a box's diagonal, 191). */
const SEPARATION = 200;
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

  // Radial tree: the first root sits in the middle, depth runs outward in rings. Every other root
  // hangs off it. Each node takes an angular slice proportional to its leaves.
  const centre = visible.find((n) => !n.parentId || !byId.has(n.parentId)) ?? visible[0];
  const kids = (id: string): string[] =>
    visible.filter((n) => n.id !== centre.id && (n.parentId === id || (id === centre.id && (!n.parentId || !byId.has(n.parentId))))).map((n) => n.id);
  const leaves = new Map<string, number>();
  const seen = new Set<string>();
  const count = (id: string): number => {
    seen.add(id);
    const ks = kids(id).filter((k) => !seen.has(k));
    const total = ks.length ? ks.reduce((sum, k) => sum + count(k), 0) : 1;
    leaves.set(id, total);
    return total;
  };
  count(centre.id);

  const angle = new Map<string, number>();
  const depth = new Map<string, number>();
  const rings: string[][] = [];
  const placed = new Set<string>();
  const spread = (id: string, from: number, to: number, d: number) => {
    placed.add(id);
    angle.set(id, (from + to) / 2);
    depth.set(id, d);
    (rings[d] ??= []).push(id);
    const ks = kids(id).filter((k) => !placed.has(k) && leaves.has(k));
    const sum = ks.reduce((t, k) => t + leaves.get(k)!, 0);
    let at = from;
    for (const k of ks) {
      const span = ((to - from) * leaves.get(k)!) / sum;
      spread(k, at, at + span, d + 1);
      at += span;
    }
  };
  spread(centre.id, -Math.PI / 2, (3 * Math.PI) / 2, 0);

  // A ring is as far out as the last one plus a step, and far enough that its neighbours clear each other.
  const radius: number[] = [0];
  for (let d = 1; d < rings.length; d++) {
    let r = radius[d - 1] + RING_STEP;
    const ring = rings[d];
    for (let i = 0; i < ring.length && ring.length > 1; i++) {
      let gap = angle.get(ring[(i + 1) % ring.length])! - angle.get(ring[i])!;
      if (gap <= 0) gap += 2 * Math.PI;
      if (gap < Math.PI) r = Math.max(r, SEPARATION / (2 * Math.sin(gap / 2)));
    }
    radius[d] = r;
  }

  const boxes = new Map<string, { x: number; y: number; w: number; h: number }>();
  for (const n of visible) {
    if (!depth.has(n.id)) continue;
    const r = radius[depth.get(n.id)!];
    const a = angle.get(n.id)!;
    const h = n.height ?? NODE_H;
    boxes.set(n.id, { x: r * Math.cos(a) - NODE_W / 2, y: r * Math.sin(a) - h / 2, w: NODE_W, h });
  }
  const minX = Math.min(...[...boxes.values()].map((b) => b.x)) - MARGIN;
  const minY = Math.min(...[...boxes.values()].map((b) => b.y)) - MARGIN;
  const width = Math.max(...[...boxes.values()].map((b) => b.x + b.w)) + MARGIN - minX;
  const height = Math.max(...[...boxes.values()].map((b) => b.y + b.h)) + MARGIN - minY;

  const wanted: { from: string; to: string; kind: EdgeKind }[] = [];
  for (const n of visible) {
    if (n.parentId && byId.has(n.parentId) && boxes.has(n.parentId) && boxes.has(n.id)) wanted.push({ from: n.parentId, to: n.id, kind: "decomposition" });
    for (const d of n.dependsOn) {
      if (boxes.has(d) && boxes.has(n.id) && !hidden.has(d) && d !== n.id) wanted.push({ from: d, to: n.id, kind: "dependency" });
    }
  }

  // Edges run box to box. Decompositions are straight; dependencies bow towards the middle so they
  // do not run along the rings' neighbours.
  const mid = { x: -minX, y: -minY };
  const edges = wanted.map((e): LayoutEdge => {
    const a = boxes.get(e.from)!;
    const b = boxes.get(e.to)!;
    const ca = { x: a.x + a.w / 2 - minX, y: a.y + a.h / 2 - minY };
    const cb = { x: b.x + b.w / 2 - minX, y: b.y + b.h / 2 - minY };
    if (e.kind === "decomposition") {
      return { ...e, points: [clip(ca, cb, a.w, a.h, 0), clip(cb, ca, b.w, b.h, 0)] };
    }
    const m = { x: (ca.x + cb.x) / 2, y: (ca.y + cb.y) / 2 };
    const ctrl = { x: mid.x + (m.x - mid.x) * 0.7, y: mid.y + (m.y - mid.y) * 0.7 };
    return { ...e, points: [clip(ca, ctrl, a.w, a.h, 0), ctrl, clip(cb, ctrl, b.w, b.h, ARROW_GAP)] };
  });

  const positions: Record<string, Point> = {};
  for (const [id, b] of boxes) positions[id] = { x: b.x - minX, y: b.y - minY };
  return { positions, edges, width, height, hiddenCount };
}

/** Where the line from a box's centre towards `to` leaves the box, `gap` short of the edge. */
function clip(c: Point, to: Point, w: number, h: number, gap: number): Point {
  const dx = to.x - c.x;
  const dy = to.y - c.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return c;
  const t = Math.min(dx === 0 ? Infinity : w / 2 / Math.abs(dx), dy === 0 ? Infinity : h / 2 / Math.abs(dy));
  const d = t * len + gap;
  return { x: c.x + (dx / len) * d, y: c.y + (dy / len) * d };
}

function isUnder(id: string, collapsed: Set<string>, byId: Map<string, LayoutInput>): boolean {
  const seen = new Set<string>();
  for (let p = byId.get(id)?.parentId; p && !seen.has(p); p = byId.get(p)?.parentId) {
    if (collapsed.has(p)) return true;
    seen.add(p);
  }
  return false;
}

/** An SVG path: straight for two points, a quadratic curve through the middle one for three. */
export function edgePath(points: Point[]): string {
  const f = (n: number) => Math.round(n * 10) / 10;
  const [a, b, c] = points;
  if (points.length === 3) return `M${f(a.x)} ${f(a.y)}Q${f(b.x)} ${f(b.y)} ${f(c.x)} ${f(c.y)}`;
  return `M${f(a.x)} ${f(a.y)}L${f(b.x)} ${f(b.y)}`;
}
