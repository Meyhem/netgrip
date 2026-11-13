import { expect, test, type Page } from "@playwright/test";
import { clearInvestigations, command, draftedPlan, snapshotOf, startedRun } from "./helpers";

// Runs against the slowed fake server (playwright.config.ts, project "steering"). Each test
// starts its own run and steers it from the board.

test.beforeEach(async ({ request }) => {
  await clearInvestigations(request);
});

const pill = (page: Page) => page.locator(".ng-board__head .ng-pill").first();
const inspector = (page: Page) => page.locator('[data-slot="inspector"]');
const row = (page: Page, display: string) => page.locator(".ng-qrow", { hasText: new RegExp(`^\\s*\\S*\\s*${display} `) }).first();

async function openBoard(page: Page, id: string) {
  await page.goto(`/investigations/${id}`);
  await expect(page.locator(".control-board")).toBeVisible();
}

/** Select the queue row of node `display` and wait for the inspector to show it. */
async function pick(page: Page, display: string) {
  await expect(row(page, display)).toBeVisible({ timeout: 30_000 });
  await row(page, display).click();
  await expect(inspector(page).locator(".inspector__head, .ng-heading").first()).toBeVisible();
  await expect(inspector(page)).toContainText(display);
}

test("S3: ignore a branch with X, it greys and lands in Not running, the log has a You row; Restore brings it back", async ({ page, request }) => {
  test.setTimeout(120_000);
  const id = await startedRun(request);
  await openBoard(page, id);
  await pick(page, "D1");
  await page.locator('[data-slot="execution-order"] [role="listbox"]').focus();
  await page.keyboard.press("x");
  const off = page.locator('.ng-qrow[data-section="not-running"]', { hasText: /^\s*\S*\s*D1 / });
  await expect(off).toBeVisible({ timeout: 15_000 });
  await expect(off).toContainText("Ignored by you");
  await expect(page.locator(".ng-canvas .ng-node--excluded").first()).toBeVisible();
  await expect(page.locator('[data-slot="event-log"] .ng-log__row--you').first()).toBeVisible();
  await off.getByRole("button", { name: "Restore" }).click();
  await expect(page.locator('.ng-qrow[data-section="not-running"]', { hasText: /^\s*\S*\s*D1 / })).toHaveCount(0, { timeout: 15_000 });
});

test("S4: instruct a coordinator: queued, then applied with a diff; superseded children hatched", async ({ page, request }) => {
  test.setTimeout(180_000);
  const id = await startedRun(request);
  await openBoard(page, id);
  // The coordinator D1 splits into D1a and D1b while it runs.
  await expect(row(page, "D1a")).toBeVisible({ timeout: 120_000 });
  await pick(page, "D1");
  await inspector(page).getByRole("textbox").fill("Concentrate on official space agency statements.");
  await inspector(page).getByRole("button", { name: "Send instruction" }).click();
  const diff = inspector(page).locator(".ng-instr .ng-diff");
  await expect(diff).toBeVisible({ timeout: 60_000 });
  await expect(diff).toContainText("superseded");
  await expect(diff).toContainText("proposed");
  await expect(page.locator(".ng-canvas .ng-node--excluded").first()).toBeVisible();
  await expect(diff.getByRole("button", { name: "Restore" }).first()).toBeVisible();
});

test("S5: F runs only this branch, the others say why, Run everything clears it", async ({ page, request }) => {
  test.setTimeout(120_000);
  const id = await startedRun(request);
  await openBoard(page, id);
  await pick(page, "D1");
  await page.locator('[data-slot="execution-order"] [role="listbox"]').focus();
  await page.keyboard.press("f");
  await expect(page.locator(".ng-board__head")).toContainText("Running only D1", { timeout: 15_000 });
  await expect(page.locator(".ng-qrow", { hasText: "waits: you are running only D1" }).first()).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Run everything" }).click();
  await expect(page.locator(".ng-board__head")).not.toContainText("Running only", { timeout: 15_000 });
});

test("S8: Finish now ends the research early: Synthesising, then a report; composers are locked", async ({ page, request }) => {
  test.setTimeout(120_000);
  const id = await startedRun(request);
  await openBoard(page, id);
  await expect(page.locator('.ng-qrow[data-section="now"]').first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Finish now" }).click();
  await expect(pill(page)).toHaveText(/Synthesising|Completed/, { timeout: 60_000 });
  await expect(pill(page)).toHaveText(/Completed/, { timeout: 60_000 });
  await expect(inspector(page).locator(".ng-composer")).toHaveClass(/is-locked/);
  expect((await snapshotOf(request, id)).investigation.state).toBe("Completed");
});

test("spending limit: the banner appears, raise the limit and the run continues", async ({ page, request }) => {
  test.setTimeout(180_000);
  const id = crypto.randomUUID();
  await request.post("/api/investigations", { data: { id, prompt: "Is the Great Wall visible from space?", settings: { spending_limit_usd: 0.05 } } });
  await command(request, id, "draft_plan");
  await expect.poll(async () => (await snapshotOf(request, id)).plan_version, { timeout: 30_000 }).toBeGreaterThanOrEqual(1);
  await command(request, id, "approve_plan");
  await openBoard(page, id);
  const banner = page.locator(".ng-banner--warn");
  await expect(banner).toContainText("Paused: the spending limit of $0.05 was reached", { timeout: 120_000 });
  await expect(pill(page)).toHaveText(/Paused/);
  await expect(page.locator(".ng-btn--steer")).toHaveCount(1);
  await banner.getByLabel("New spending limit").fill("5");
  await banner.getByRole("button", { name: "Raise limit and resume" }).click();
  await expect(pill(page)).toHaveText(/Running|Completed/, { timeout: 60_000 });
  await expect(page.locator(".ng-banner--warn")).toHaveCount(0);
});

test("pause, then reload: still Paused by you, Now empty with Nothing runs while paused", async ({ page, request }) => {
  test.setTimeout(120_000);
  const id = await startedRun(request);
  await openBoard(page, id);
  await expect(page.locator('.ng-qrow[data-section="now"]').first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "‖ Pause" }).click();
  await expect(pill(page)).toHaveText(/Paused/, { timeout: 60_000 });
  await page.reload();
  await expect(pill(page)).toHaveText(/Paused.*by you/i);
  await expect(page.locator('[data-slot="execution-order"]')).toContainText("Nothing runs while paused");
  await expect(page.locator('.ng-qrow[data-section="now"]')).toHaveCount(0);
  await expect(page.locator(".ng-banner")).toHaveCount(0);
});

test("a drafted plan is not steerable: finish_now answers 409", async ({ request }) => {
  const id = await draftedPlan(request);
  const res = await request.post(`/api/investigations/${id}/commands`, { data: { id: crypto.randomUUID(), type: "finish_now", node_id: null, payload: {} } });
  expect(res.status()).toBe(409);
});
