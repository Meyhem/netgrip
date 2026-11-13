import { expect, test, type Page } from "@playwright/test";
import { clearInvestigations, snapshotOf, startedRun } from "./helpers";

// The slowed fake server (project "steering"): the run lasts long enough to steer it, then the
// report is read.

test.beforeEach(async ({ request }) => {
  await clearInvestigations(request);
});

const row = (page: Page, display: string) => page.locator(".ng-qrow", { hasText: new RegExp(`^\\s*\\S*\\s*${display} `) }).first();

test("S3 + S8: ignore a branch, Finish now: the report lists it and says it ended early", async ({ page, request }) => {
  test.setTimeout(180_000);
  const id = await startedRun(request);
  await page.goto(`/investigations/${id}`);
  await expect(row(page, "D1")).toBeVisible({ timeout: 30_000 });
  await row(page, "D1").click();
  await page.locator('[data-slot="execution-order"] [role="listbox"]').focus();
  await page.keyboard.press("x");
  await expect(page.locator('.ng-qrow[data-section="not-running"]', { hasText: /^\s*\S*\s*D1 / })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Finish now" }).click();
  await expect.poll(async () => (await snapshotOf(request, id)).investigation.state, { timeout: 90_000 }).toBe("Completed");

  await page.goto(`/investigations/${id}`);
  await expect(page.locator(".ng-board__head")).toContainText("ended early by you");
  const limits = page.locator("#report-limits");
  await expect(limits).toContainText("Ended early by you");
  const excluded = limits.locator(".ng-instr", { hasText: "You excluded · D1" });
  await expect(excluded).toBeVisible();
  await expect(excluded).toContainText("Ignored branch");
});

test("S8: a Stopped investigation is finished into a report from the list", async ({ page, request }) => {
  test.setTimeout(180_000);
  const id = await startedRun(request);
  await page.goto(`/investigations/${id}`);
  await expect(page.locator('.ng-qrow[data-section="now"]').first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect.poll(async () => (await snapshotOf(request, id)).investigation.state, { timeout: 60_000 }).toBe("Stopped");

  await page.goto("/");
  await page.getByRole("row", { name: /Great Wall/ }).getByRole("button", { name: "Finish into a report" }).click();
  await expect.poll(async () => (await snapshotOf(request, id)).investigation.state, { timeout: 90_000 }).toBe("Completed");
  await page.goto(`/investigations/${id}`);
  await expect(page.locator(".ng-report")).toBeVisible();
  await expect(page.locator("h2.ng-display")).toBeVisible();
  await expect(page.locator("#report-limits")).toContainText("ended early by you");
});
