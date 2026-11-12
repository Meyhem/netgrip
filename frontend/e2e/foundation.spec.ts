import { expect, test } from "@playwright/test";
import { clearInvestigations, collectApiBodies } from "./helpers";

test.beforeEach(async ({ request }) => {
  await clearInvestigations(request);
});

test("empty state → type a prompt → Save as draft → row appears as Draft with Continue", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Ask a question or state a claim. Netgrip will check it, including the parts you take for granted.")).toBeVisible();
  await expect(page.locator("table")).toHaveCount(0);
  await page.getByRole("textbox", { name: "Your question or claim" }).fill("Do heat pumps work below −15 °C?");
  await page.getByRole("button", { name: "Save as draft" }).dblclick();
  const row = page.getByRole("row", { name: /Do heat pumps work below/ });
  await expect(row).toBeVisible();
  await expect(row.locator(".ng-pill")).toHaveText("○Draft");
  await expect(row.getByRole("button", { name: "Continue" })).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(2); // header + one investigation
});

test("Settings: change the spending limit to $7.50, reload, it reads $7.50; New investigation defaults to $7.50", async ({ page }) => {
  await page.goto("/settings#spend");
  const limit = page.getByLabel("Default limit");
  await limit.fill("$7.50");
  await limit.press("Enter");
  await expect(page.getByText("Saved")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Default limit")).toHaveValue("$7.50");
  await page.goto("/new");
  await expect(page.getByLabel("Spending limit")).toHaveValue("$7.50");
});

test("Settings: set a model key; the page HTML and every /api response body never contain the key string", async ({ page }) => {
  const secret = "sk-or-e2e-" + Math.random().toString(36).slice(2) + "-do-not-show";
  const bodies = collectApiBodies(page);
  await page.goto("/settings");
  const keys = page.locator("#keys");
  await keys.getByRole("button", { name: "Replace" }).first().click();
  await keys.getByLabel("Model provider key").fill(secret);
  await keys.getByRole("button", { name: "Save key" }).click();
  await expect(keys.getByText("Key set").first()).toBeVisible();
  await expect(keys.getByLabel("Model provider key")).toHaveCount(0);
  await page.reload();
  await expect(keys.getByText("Key set").first()).toBeVisible();
  await page.goto("/new");
  await expect(page.getByRole("button", { name: "Draft the plan" })).toBeVisible();
  expect(await page.content()).not.toContain(secret);
  const all = await bodies();
  expect(all.length).toBeGreaterThan(3);
  for (const b of all) expect(b).not.toContain(secret);
});

test("delete a draft: dialog names the prompt; row disappears", async ({ page, request }) => {
  await request.post("/api/investigations", { data: { id: crypto.randomUUID(), prompt: "Is the 10,000 steps target based on evidence?", settings: {} } });
  await request.post("/api/investigations", { data: { id: crypto.randomUUID(), prompt: "Keep this one", settings: {} } });
  await page.goto("/");
  const row = page.getByRole("row", { name: /10,000 steps/ });
  await row.getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: /Delete investigation/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Is the 10,000 steps target based on evidence?");
  await expect(dialog).toContainText("MB");
  await dialog.getByRole("button", { name: "Delete investigation" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("row", { name: /10,000 steps/ })).toHaveCount(0);
  await expect(page.getByRole("row", { name: /Keep this one/ })).toBeVisible();
});
