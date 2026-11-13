import type { APIRequestContext, Page, Response } from "@playwright/test";

export async function clearInvestigations(request: APIRequestContext) {
  const rows = (await (await request.get("/api/investigations")).json()) as { id: string }[];
  for (const r of rows) await request.delete(`/api/investigations/${r.id}`);
}

/** Collect the body of every /api response the page receives. */
export function collectApiBodies(page: Page): () => Promise<string[]> {
  const pending: Promise<string>[] = [];
  page.on("response", (res: Response) => {
    if (new URL(res.url()).pathname.startsWith("/api/") && !res.url().includes("/stream")) {
      pending.push(res.text().catch(() => ""));
    }
  });
  return () => Promise.all(pending);
}

type SnapshotLite = { seq: number; investigation: { state: string }; nodes: { id: string; status: string }[]; plan_version: number };

export async function snapshotOf(request: APIRequestContext, id: string): Promise<SnapshotLite> {
  return (await (await request.get(`/api/investigations/${id}`)).json()) as SnapshotLite;
}

export async function command(request: APIRequestContext, id: string, type: string, payload: Record<string, unknown> = {}) {
  const res = await request.post(`/api/investigations/${id}/commands`, { data: { id: crypto.randomUUID(), type, node_id: null, payload } });
  if (res.status() !== 202) throw new Error(`${type}: ${res.status()} ${await res.text()}`);
}

async function until(fn: () => Promise<boolean>, what: string, timeoutMs = 30_000) {
  const end = Date.now() + timeoutMs;
  while (!(await fn())) {
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 100));
  }
}

/** Create an investigation and draft its plan (fake mode); it waits in plan review. */
export async function draftedPlan(request: APIRequestContext, prompt = "Is the Great Wall of China visible from space with the naked eye?"): Promise<string> {
  const id = crypto.randomUUID();
  await request.post("/api/investigations", { data: { id, prompt, settings: {} } });
  await command(request, id, "draft_plan");
  await until(async () => {
    const s = await snapshotOf(request, id);
    return s.investigation.state === "Planning" && s.plan_version >= 1 && s.nodes.length > 1;
  }, "the plan");
  return id;
}

/** A drafted plan, approved: the run has started. */
export async function startedRun(request: APIRequestContext): Promise<string> {
  const id = await draftedPlan(request);
  await command(request, id, "approve_plan");
  await until(async () => (await snapshotOf(request, id)).investigation.state !== "Planning", "the run to start");
  return id;
}
