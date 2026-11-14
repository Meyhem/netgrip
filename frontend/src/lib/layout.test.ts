import { describe, expect, it } from "vitest";
import { layoutGraph, NODE_H, NODE_W, type LayoutInput } from "./layout";

/** A plan of 40 nodes: root, 2 premise checks, 8 divergent children (each waiting on both
 * premise checks, as I2 adds), 28 grandchildren and a verification that waits on D3. */
function fortyNodes(): LayoutInput[] {
  const out: LayoutInput[] = [
    { id: "R", parentId: null, dependsOn: [] },
    { id: "P1", parentId: "R", dependsOn: [] },
    { id: "P2", parentId: "R", dependsOn: [] },
  ];
  for (let i = 1; i <= 8; i++) out.push({ id: `D${i}`, parentId: "R", dependsOn: ["P1", "P2"] });
  const letters = "abcd";
  let n = 0;
  for (let i = 1; i <= 8 && n < 28; i++) {
    for (let j = 0; j < 4 && n < 28; j++, n++) out.push({ id: `D${i}${letters[j]}`, parentId: `D${i}`, dependsOn: [] });
  }
  out.push({ id: "V1", parentId: "R", dependsOn: ["D3"] });
  return out;
}

const overlaps = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  a.x < b.x + NODE_W && b.x < a.x + NODE_W && a.y < b.y + NODE_H && b.y < a.y + NODE_H;

describe("layoutGraph", () => {
  it("puts the root in the middle, deeper nodes on wider rings, and no two boxes overlap", () => {
    const nodes = fortyNodes();
    expect(nodes).toHaveLength(40);
    const { positions, width, height } = layoutGraph(nodes);
    expect(Object.keys(positions)).toHaveLength(40);
    const centre = (id: string) => ({ x: positions[id].x + NODE_W / 2, y: positions[id].y + NODE_H / 2 });
    const dist = (id: string) => Math.hypot(centre(id).x - centre("R").x, centre(id).y - centre("R").y);
    for (const n of nodes) {
      if (n.parentId) expect(dist(n.parentId)).toBeLessThan(dist(n.id));
    }
    expect(dist("P1")).toBeCloseTo(dist("D1"));
    const ids = nodes.map((n) => n.id);
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        expect(overlaps(positions[ids[i]], positions[ids[j]]), `${ids[i]} overlaps ${ids[j]}`).toBe(false);
      }
    }
    for (const p of Object.values(positions)) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.x + NODE_W).toBeLessThanOrEqual(width);
      expect(p.y + NODE_H).toBeLessThanOrEqual(height);
    }
  });

  it('dependency edges get kind "dependency"', () => {
    const { edges } = layoutGraph(fortyNodes());
    const dep = edges.find((e) => e.from === "D3" && e.to === "V1");
    expect(dep?.kind).toBe("dependency");
    expect(edges.find((e) => e.from === "R" && e.to === "V1")?.kind).toBe("decomposition");
    expect(edges.filter((e) => e.kind === "dependency")).toHaveLength(17);
    expect(edges.filter((e) => e.kind === "decomposition")).toHaveLength(39);
    for (const e of edges) expect(e.points.length).toBeGreaterThanOrEqual(2);
  });

  it("collapsed branches hide their descendants and count them", () => {
    const { positions, edges, hiddenCount } = layoutGraph(fortyNodes(), { collapsed: new Set(["D1"]) });
    expect(positions.D1).toBeDefined();
    expect(positions.D1a).toBeUndefined();
    expect(hiddenCount.D1).toBe(4);
    expect(edges.some((e) => e.to === "D1a")).toBe(false);
  });

  it("an empty graph has no size", () => {
    expect(layoutGraph([])).toEqual({ positions: {}, edges: [], width: 0, height: 0, hiddenCount: {} });
  });
});
