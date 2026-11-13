import { expect, test } from "@playwright/test";
import { clearInvestigations } from "./helpers";

test.beforeEach(async ({ request }) => {
  await clearInvestigations(request);
});

test("S9: prompt → Draft the plan → re-plan by instruction → undo → approve; pill becomes Running, then Completed", async ({ page }) => {
  await page.goto("/new");
  await page.getByRole("textbox", { name: "Your question or claim" }).fill("Why is the Great Wall of China visible from space with the naked eye?");
  await page.getByRole("button", { name: "Draft the plan" }).click();

  await expect(page).toHaveURL(/\/investigations\/[0-9a-f-]+$/);
  const toolbar = page.locator(".ng-toolbar");
  await expect(toolbar).toContainText("Proposed plan · version 1");
  const nodes = page.locator(".ng-canvas .ng-node");
  await expect(nodes.first()).toBeVisible();
  const count = await nodes.count();
  expect(count).toBeGreaterThan(3);
  await expect(page.locator(".ng-canvas .ng-node--proposed")).toHaveCount(count);
  await expect(page.locator(".ng-canvas .ng-node__state").filter({ hasText: "◌ Planned" })).toHaveCount(count);
  await expect(page.locator("[class*='live']")).toHaveCount(0);
  await expect(page.locator(".ng-board__head .ng-pill")).toHaveText(/Plan review/);
  await expect(page.locator(".ng-btn--steer")).toHaveCount(1);
  await expect(page.locator(".ng-pane--right")).toContainText("Assumptions in your question · checked first");
  await expect(page.locator(".ng-pane--right .ng-claim").first()).toContainText("P1");

  // Mark the document: a reload would lose it.
  await page.evaluate(() => { (window as unknown as { __s9: number }).__s9 = 1; });
  const before = await page.locator(".ng-canvas .ng-node__top").allTextContents();

  await page.getByRole("textbox", { name: "Instruction for R" }).fill("Leave out tourism marketing. Include where the claim came from.");
  await page.getByRole("button", { name: "Re-plan" }).click();
  await expect(toolbar).toContainText("Proposed plan · version 2");
  await expect(toolbar).toContainText("changed by your last instruction:");
  await expect(page.locator(".ng-canvas .ng-node__mark").filter({ hasText: "new" }).first()).toBeVisible();
  await expect(page.locator(".ng-canvas .ng-node--excluded").first()).toContainText("− Removed");
  const instr = page.locator(".ng-pane--right .ng-instr").first();
  await expect(instr).toContainText("Leave out tourism marketing. Include where the claim came from.");
  await expect(instr.locator(".ng-diff")).toBeVisible();
  await expect(instr.locator(".ng-diff__n").first()).toContainText("+ proposed");
  expect(await page.locator(".ng-canvas .ng-node__top").allTextContents()).not.toEqual(before);
  expect(await page.evaluate(() => (window as unknown as { __s9?: number }).__s9)).toBe(1);

  await page.getByRole("button", { name: "Undo last instruction" }).click();
  await expect(toolbar).toContainText("Proposed plan · version 1");
  await expect(page.locator(".ng-canvas .ng-node--excluded")).toHaveCount(0);
  await expect(page.locator(".ng-canvas .ng-node")).toHaveCount(count);
  await expect(instr.locator(".ng-instr__meta")).toContainText("undone");

  await page.getByRole("button", { name: "Approve plan and start" }).click();
  // Fake mode runs the approved plan to the end on the scripted web (Phase 4), and fast:
  // the pill may already have moved past Running when it is first read.
  const pill = page.locator(".ng-pill").first();
  await expect(pill).toHaveText(/Running|Synthesising|Completed/);
  await expect(pill).toHaveText(/Completed/, { timeout: 30_000 });
  expect(await page.evaluate(() => (window as unknown as { __s9?: number }).__s9)).toBe(1);
});
