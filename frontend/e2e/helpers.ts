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
