import { expect, test } from "@playwright/test";
import { clearInvestigations, startedRun } from "./helpers";

// Runs against the fake server whose model fails twice on the first node (S10).

test.beforeEach(async ({ request }) => {
  await clearInvestigations(request);
  // Shorten the retry window so the outage pauses after about a second.
  const res = await request.patch("/api/settings", { data: { retry_before_pause_seconds: 1 } });
  expect(res.ok()).toBeTruthy();
});

test("S10: the model stops answering, the banner names the cause, Resume continues to the end", async ({ page, request }) => {
  test.setTimeout(180_000);
  const id = await startedRun(request);
  await page.goto(`/investigations/${id}`);
  const banner = page.locator(".ng-banner--warn");
  await expect(banner).toContainText("Paused: the model service stopped responding", { timeout: 120_000 });
  await expect(banner).toContainText("Nothing is lost.");
  await expect(page.locator(".ng-board__head .ng-pill").first()).toHaveText(/Paused/);
  await banner.getByRole("button", { name: "Show the errors in the log" }).click();
  await expect(page.locator('[data-slot="event-log"] [aria-pressed="true"]', { hasText: "Problems" })).toBeVisible();
  await banner.getByRole("button", { name: "Resume" }).click();
  await expect(page.locator(".ng-board__head .ng-pill").first()).toHaveText(/Running|Completed/, { timeout: 60_000 });
  await expect(page.locator(".ng-banner--warn")).toHaveCount(0);
  await expect(page.locator(".ng-board__head .ng-pill").first()).toHaveText(/Completed/, { timeout: 150_000 });
});
