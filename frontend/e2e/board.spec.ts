import { expect, test, type Locator, type Page } from "@playwright/test";
import { clearInvestigations, command, draftedPlan, snapshotOf, startedRun } from "./helpers";

// Runs against the slowed fake server (playwright.config.ts, project "board"): each fake model
// call takes NETGRIP_FAKE_DELAY_MS, so a run lasts long enough to watch it.

test.beforeEach(async ({ request }) => {
  await clearInvestigations(request);
});

const NOT_LOG_ROWS = new Set(["schedule.updated", "spend.recorded"]);

/** "current to #0419" in the graph toolbar, as a number. */
async function currentTo(page: Page): Promise<number> {
  const text = (await page.locator('[data-slot="center"] .ng-toolbar').textContent()) ?? "";
  const m = /current to #(\d+)/.exec(text);
  return m ? Number(m[1]) : -1;
}

async function logSeqs(page: Page): Promise<number[]> {
  return (await page.locator('[data-slot="event-log"] .ng-log__row[data-seq]').evaluateAll(
    (rows) => rows.map((r) => Number(r.getAttribute("data-seq"))),
  ));
}

function expectUnique(seqs: number[]) {
  expect(seqs.length).toBeGreaterThan(0);
  expect(new Set(seqs).size).toBe(seqs.length);
}

const pill = (page: Page) => page.locator(".ng-board__head .ng-pill").first();
const inspector = (page: Page) => page.locator('[data-slot="inspector"]');
const nowRows = (page: Page) => page.locator('.ng-qrow[data-section="now"]');

async function overlaps(a: Locator, b: Locator): Promise<boolean> {
  const [x, y] = [await a.boundingBox(), await b.boundingBox()];
  return !!x && !!y && x.x < y.x + y.width && y.x < x.x + x.width && x.y < y.y + y.height && y.y < x.y + x.height;
}

test("approve → the board fills and follows the run; trail, stored page, reload, then nothing live", async ({ page, request }) => {
  test.setTimeout(180_000);
  const id = await draftedPlan(request);
  await page.goto(`/investigations/${id}`);
  await page.getByRole("button", { name: "Approve plan and start" }).click();

  // Now fills, nodes run, log rows arrive, "current to #" moves on.
  await expect(page.locator(".control-board")).toBeVisible({ timeout: 15_000 });
  await expect(nowRows(page).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".ng-canvas .ng-node--running").first()).toBeVisible();
  const firstSeq = await currentTo(page);
  const firstRows = (await logSeqs(page)).length;
  await expect.poll(() => currentTo(page)).toBeGreaterThan(firstSeq);
  await expect.poll(async () => (await logSeqs(page)).length).toBeGreaterThan(firstRows);

  // Click a node in the graph: the same node is selected in the left pane and inspected.
  // (Follow active is off by default, so the view holds still.)
  await expect(page.locator('[data-slot="center"] .ng-toggle', { hasText: "Follow active" })).not.toHaveClass(/is-on/);
  const node = page.locator(".ng-canvas .ng-node").nth(1);
  const nodeId = (await node.getAttribute("data-node"))!;
  await node.click();
  await expect(node).toHaveClass(/is-selected/);
  await expect(page.locator(`.ng-qrow[data-node-id="${nodeId}"]`)).toHaveClass(/is-selected/);
  await expect(inspector(page).locator("[data-node-id]")).toHaveAttribute("data-node-id", nodeId);

  // Reload mid-run: the same board, no log row twice, and it keeps following.
  expect(await pill(page).textContent()).toMatch(/Running/);
  const beforeReload = await currentTo(page);
  const nodesBefore = await page.locator(".ng-canvas .ng-node").count();
  await page.reload();
  await expect(page.locator(".control-board")).toBeVisible();
  await expect(pill(page)).toHaveText(/Running/);
  await expect.poll(() => currentTo(page)).toBeGreaterThanOrEqual(beforeReload);
  expect(await page.locator(".ng-canvas .ng-node").count()).toBeGreaterThanOrEqual(nodesBefore);
  expectUnique(await logSeqs(page));
  const afterReload = await currentTo(page);
  await expect.poll(() => currentTo(page)).toBeGreaterThan(afterReload);
  expectUnique(await logSeqs(page));
  const api = await snapshotOf(request, id);
  expect(api.seq).toBeGreaterThanOrEqual(afterReload);

  // Trail: streamed model text shows on the open step of a running node.
  const trailTab = inspector(page).getByRole("tab", { name: /^Trail/ });
  await expect.poll(async () => {
    const live = await inspector(page).locator(".trail__step--open .trail__note").allTextContents();
    if (live.length) return live.join(" ");
    const rows = nowRows(page);
    if (await rows.count()) await rows.first().click({ timeout: 2_000 }).catch(() => {});
    if ((await trailTab.getAttribute("aria-selected")) !== "true") await trailTab.click({ timeout: 2_000 }).catch(() => {});
    return "";
  }, { timeout: 60_000, intervals: [200] }).toContain("This text is not stored");

  // A stored page from some node's trail opens over the inspector, as text.
  let i = 0;
  await expect.poll(async () => {
    if (await inspector(page).locator(".trail__page").count()) return true;
    const rows = page.locator(".ng-qrow");
    const n = await rows.count();
    if (n) await rows.nth(i++ % n).click({ timeout: 2_000 }).catch(() => {});
    if ((await trailTab.getAttribute("aria-selected")) !== "true") await trailTab.click({ timeout: 2_000 }).catch(() => {});
    return false;
  }, { timeout: 60_000, intervals: [500] }).toBe(true);
  await inspector(page).locator(".trail__page").first().click();
  const sheet = page.getByRole("dialog", { name: "Stored page" });
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText("fetched");
  await expect(sheet.locator(".page-sheet__text")).not.toBeEmpty();
  await sheet.getByRole("button", { name: "Close stored page" }).click();
  await expect(sheet).toHaveCount(0);

  // The run ends. A finished graph has no live: not on this page, not on the board as history.
  await expect(pill(page)).toHaveText(/Completed/, { timeout: 120_000 });
  await expect(page.locator("[class*='live']")).toHaveCount(0);
  await page.goto(`/investigations/${id}/board`);
  await expect(page.locator(".ng-canvas .ng-node").first()).toBeVisible();
  await expect(pill(page)).toHaveText(/Completed/);
  await expect(page.locator(".ng-canvas .ng-node--done").first()).toBeVisible();
  await expect(page.locator("[class*='live']")).toHaveCount(0);
  await expect(page.locator(".ng-pulse")).toHaveCount(0);
  expectUnique(await logSeqs(page));
});

test("the stream drops: reconnecting, no pulse; back: the log has no gap", async ({ page, request }) => {
  test.setTimeout(120_000);
  // Keep a handle on each EventSource, so the test can drop the open one.
  await page.addInitScript(() => {
    const Base = window.EventSource;
    const all: EventSource[] = [];
    (window as unknown as { __streams: EventSource[] }).__streams = all;
    window.EventSource = class extends Base {
      constructor(url: string | URL, init?: EventSourceInit) {
        super(url, init);
        all.push(this);
      }
    } as typeof EventSource;
  });
  const id = await startedRun(request);
  await page.goto(`/investigations/${id}/board`);
  await expect(nowRows(page).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".ng-pulse").first()).toBeVisible();

  // Block /stream and drop the open connection: every retry fails while blocked.
  await page.route("**/stream?*", (route) => route.abort());
  await page.evaluate(() => {
    for (const es of (window as unknown as { __streams: EventSource[] }).__streams) {
      if (es.readyState !== EventSource.CLOSED) es.dispatchEvent(new Event("error"));
    }
  });
  await expect(pill(page)).toContainText("· reconnecting");
  await expect(page.locator(".ng-pulse")).toHaveCount(0);
  const blockedAt = await currentTo(page);
  // The run goes on without the page.
  await expect.poll(async () => (await snapshotOf(request, id)).seq, { timeout: 30_000 }).toBeGreaterThan(blockedAt + 5);
  expect(await currentTo(page)).toBe(blockedAt);
  await expect(pill(page)).toContainText("· reconnecting");

  // Unblock: the pill clears and the log catches up with nothing missing.
  await page.unroute("**/stream?*");
  await expect(pill(page)).not.toContainText("reconnecting", { timeout: 15_000 });
  const target = (await snapshotOf(request, id)).seq;
  await expect.poll(() => currentTo(page), { timeout: 15_000 }).toBeGreaterThanOrEqual(target);
  const shown = await logSeqs(page);
  expectUnique(shown);
  const lo = Math.min(...shown);
  const hi = Math.max(...shown);
  expect(lo).toBeLessThan(blockedAt);
  const all = (await (await request.get(`/api/investigations/${id}/events?after=${lo - 1}&limit=10000`)).json()) as { seq: number; type: string }[];
  const expected = all.filter((e) => e.seq <= hi && !NOT_LOG_ROWS.has(e.type)).map((e) => e.seq);
  expect([...shown].sort((a, b) => a - b)).toEqual(expected);
});

test("pause, then stop: nothing runs while paused, and the stopped board is history", async ({ page, request }) => {
  test.setTimeout(120_000);
  const id = await startedRun(request);
  await page.goto(`/investigations/${id}/board`);
  await expect(nowRows(page).first()).toBeVisible({ timeout: 30_000 });
  await command(request, id, "pause");
  await expect(pill(page)).toHaveText(/Paused/, { timeout: 30_000 });
  await expect(page.locator('[data-slot="execution-order"]')).toContainText("Nothing runs while paused");
  await expect(nowRows(page)).toHaveCount(0);
  await expect(page.locator(".ng-pulse")).toHaveCount(0);
  // Paused once nothing is in flight: nothing is live, even on nodes halted mid-work.
  await expect(page.locator("[class*='live']")).toHaveCount(0);
  await command(request, id, "stop");
  await expect(pill(page)).toHaveText(/Stopped/, { timeout: 30_000 });
  await page.reload();
  await expect(pill(page)).toHaveText(/Stopped/);
  await expect(page.locator(".ng-canvas .ng-node").first()).toBeVisible();
  // Nodes it halted mid-work keep the status Running (they continue on Resume), but nothing
  // runs now: none is in Now, nothing pulses and nothing is styled live.
  await expect(nowRows(page)).toHaveCount(0);
  await expect(page.locator(".ng-pulse")).toHaveCount(0);
  await expect(page.locator("[class*='live']")).toHaveCount(0);
});

test("narrow widths: the inspector is a sheet below 1180px; the left pane is a tab below 900px", async ({ page, request }) => {
  test.setTimeout(120_000);
  const id = await startedRun(request);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/investigations/${id}/board`);
  const left = page.locator('[data-slot="execution-order"]');
  const canvas = page.locator(".ng-canvas");
  const tabs = page.getByRole("tablist", { name: "Board" });
  await expect(canvas.locator(".ng-node").first()).toBeVisible({ timeout: 30_000 });
  // Wide: three panes side by side, no tabs, no sheet.
  await expect(inspector(page)).toBeVisible();
  await expect(left).toBeVisible();
  await expect(tabs).toBeHidden();
  expect(await overlaps(inspector(page), canvas)).toBe(false);

  // 1100: the inspector is an overlay sheet over the graph, opened by a selection.
  await page.setViewportSize({ width: 1100, height: 800 });
  await expect(inspector(page)).toBeHidden();
  await expect(left).toBeVisible();
  await expect(tabs).toBeHidden();
  const node = canvas.locator(".ng-node").first();
  const nodeId = (await node.getAttribute("data-node"))!;
  await node.click();
  await expect(inspector(page)).toBeVisible();
  await expect(inspector(page).locator("[data-node-id]")).toHaveAttribute("data-node-id", nodeId);
  expect(await inspector(page).evaluate((e) => getComputedStyle(e).position)).toBe("absolute");
  expect(await overlaps(inspector(page), canvas)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(inspector(page)).toBeHidden();
  await expect(page.locator(`.ng-qrow[data-node-id="${nodeId}"]`)).toHaveClass(/is-selected/);

  // 850: the left pane is a tab beside Graph and Log; the inspector is still a sheet.
  await page.setViewportSize({ width: 850, height: 800 });
  await expect(tabs).toBeVisible();
  await expect(tabs.getByRole("tab")).toHaveText(["Execution order", "Graph", "Log"]);
  await expect(tabs.getByRole("tab", { name: "Graph" })).toHaveAttribute("aria-selected", "true");
  await expect(left).toBeHidden();
  await expect(canvas).toBeVisible();
  await expect(page.locator('[data-slot="event-log"]')).toBeHidden();

  await tabs.getByRole("tab", { name: "Execution order" }).click();
  await expect(left).toBeVisible();
  await expect(canvas).toBeHidden();
  await page.locator(".ng-qrow").first().click();
  await expect(inspector(page)).toBeVisible();
  expect(await inspector(page).evaluate((e) => getComputedStyle(e).position)).toBe("absolute");
  await inspector(page).getByRole("button", { name: "Close inspector" }).click();
  await expect(inspector(page)).toBeHidden();

  await tabs.getByRole("tab", { name: "Log" }).click();
  await expect(page.locator('[data-slot="event-log"] .ng-log')).toBeVisible();
  await expect(left).toBeHidden();
  await expect(canvas).toBeHidden();
  const logBox = await page.locator('[data-slot="event-log"] .ng-log').boundingBox();
  expect(logBox!.height).toBeGreaterThan(300); // the log fills the tab, not the docked 166px

  await tabs.getByRole("tab", { name: "Graph" }).click();
  await expect(canvas).toBeVisible();
  await expect(left).toBeHidden();
});
