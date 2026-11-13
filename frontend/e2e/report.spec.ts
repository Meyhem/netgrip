import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { clearInvestigations, completedRun, storageTotal } from "./helpers";

// The fast fake server (project "app"): a run reaches its report in seconds.

test.beforeEach(async ({ request }) => {
  await clearInvestigations(request);
});

test("the report opens on the answer; the premise was wrong; a citation opens its evidence; show on the board", async ({ page, request }) => {
  test.setTimeout(120_000);
  const id = await completedRun(request);
  await page.goto(`/investigations/${id}`);
  await expect(page.locator(".ng-report")).toBeVisible();
  await expect(page.locator("h2.ng-display")).toContainText("wrong");
  const banner = page.locator(".ng-banner--danger");
  await expect(banner).toContainText("Where you were wrong");
  await expect(banner.getByRole("button", { name: "P1" })).toBeVisible();
  await expect(page.locator(".report-evidence")).toHaveCount(0);

  const chip = page.locator("h2.ng-display .ng-cite").first();
  await chip.click();
  const pane = page.locator(".report-evidence");
  await expect(pane).toBeVisible();
  await expect(chip).toHaveClass(/is-open/);
  await expect(pane).toContainText("How it got here");
  await expect(pane.locator(".ng-src").first()).toBeVisible();

  await pane.getByRole("link", { name: "show on the board" }).click();
  await expect(page).toHaveURL(new RegExp(`/investigations/${id}/board$`));
  await expect(page.locator(".control-board")).toBeVisible();
  await expect(page.locator('[data-slot="inspector"] [data-node-id]')).toBeVisible();
  // The board of a finished run is history: nothing on it steers.
  await expect(page.locator(".ng-btn--steer")).toHaveCount(0);
});

test("Export Markdown downloads the sections with footnotes", async ({ page, request }) => {
  test.setTimeout(120_000);
  const id = await completedRun(request);
  await page.goto(`/investigations/${id}`);
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Export Markdown" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^[a-z0-9-]+\.md$/);
  const text = readFileSync(await download.path(), "utf8");
  for (const h of ["The answer", "Where you were wrong", "Key findings", "What could not be verified", "Limits of this investigation"]) {
    expect(text).toContain(`## ${h}`);
  }
  expect(text).toMatch(/^\[\^c1\]: /m);
  expect(text).not.toMatch(/spending_limit|effort_budget|sources_to_confirm/);
});

test("delete from the list: the dialog names the prompt and the space; the row goes and storage shrinks", async ({ page, request }) => {
  test.setTimeout(120_000);
  const id = await completedRun(request);
  const before = await storageTotal(request);
  await page.goto("/");
  const row = page.getByRole("row", { name: /Great Wall/ });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: /Delete investigation/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Is the Great Wall of China visible from space with the naked eye?");
  await expect(dialog).toContainText(/Frees \d[\d.]* (MB|GB)/);
  await dialog.getByRole("button", { name: "Delete investigation" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("row", { name: /Great Wall/ })).toHaveCount(0);
  expect((await request.get(`/api/investigations/${id}`)).status()).toBe(404);
  expect(await storageTotal(request)).toBeLessThan(before);
});
