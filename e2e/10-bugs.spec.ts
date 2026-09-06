import { expect, test, type Page } from "@playwright/test";

async function loadDashboard(page: Page) {
  await page.goto("/");
  await expect(page.locator("h1", { hasText: "Your market catch-up" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("text=/Replay connected/").first()).toBeVisible({ timeout: 20_000 });
}

async function openRuleDialog(page: Page, companyText: string) {
  await page
    .locator("article", { hasText: companyText })
    .first()
    .locator("button", { hasText: "Add personal rule" })
    .click();
  await expect(page.locator("[data-slot=dialog-content]")).toBeVisible();
}

test.describe("bug fixes", () => {
  test("BUG-1: invalid threshold shows a readable error", async ({ page }) => {
    await loadDashboard(page);
    await page.locator("button", { hasText: "stocks moved inside their expected range" }).click();

    // Client-side: zero threshold rejected before any request
    await openRuleDialog(page, "Tata Motors");
    await page.locator("#rule-value").fill("0");
    await page.locator("button", { hasText: "Save rule" }).click();
    await expect(page.locator("[data-sonner-toast]", { hasText: "greater than zero" })).toBeVisible();

    // Server-side 422 (over the upper bound): detail array rendered as readable text
    await page.locator("#rule-value").fill("20000000");
    await page.locator("button", { hasText: "Save rule" }).click();
    const serverToast = page.locator("[data-sonner-toast]", { hasText: /less than or equal/ });
    await expect(serverToast).toBeVisible();
    await expect(page.locator("[data-sonner-toast]", { hasText: "[object Object]" })).toHaveCount(0);
    await page.keyboard.press("Escape");
  });

  test("BUG-3: header reports the API review interval", async ({ page }) => {
    await loadDashboard(page);
    await expect(
      page.locator("header p", { hasText: "165 trading minutes of market activity" }),
    ).toBeVisible();
  });

  test("BUG-4: volume rule reports it was not evaluated in replay", async ({ page }) => {
    await loadDashboard(page);
    await page.locator("button", { hasText: "stocks moved inside their expected range" }).click();
    await openRuleDialog(page, /^ITC/);

    // Dialog warns before saving
    await page.getByRole("combobox").click();
    await page.getByRole("option", { name: "Volume pace exceeds" }).click();
    await expect(
      page.locator("[data-slot=dialog-content]", { hasText: "only includes volume history for HDFCBANK" }),
    ).toBeVisible();

    // Card narrative names the unevaluated rule after saving
    await page.locator("#rule-value").fill("1.5");
    await page.locator("button", { hasText: "Save rule" }).click();
    await expect(page.locator("[data-sonner-toast]", { hasText: "Rule saved" })).toBeVisible();
    await page.locator("article button", { hasText: "ITC" }).first().click();
    await expect(
      page.locator("[data-slot=sheet-content]", { hasText: "volume-pace rule was not evaluated" }),
    ).toBeVisible({ timeout: 20_000 });
    await page.keyboard.press("Escape");
  });

  test("BUG-5: never-triggerable price rule warns on save", async ({ page }) => {
    await loadDashboard(page);
    await page.locator("button", { hasText: "stocks moved inside their expected range" }).click();
    await openRuleDialog(page, "Tata Motors");
    await page.locator("#rule-value").fill("100");
    await page.locator("button", { hasText: "Save rule" }).click();
    await expect(
      page.locator("[data-sonner-toast]", { hasText: "can never trigger" }),
    ).toBeVisible();
  });

  test("BUG-7: sidebar lists every tracked stock", async ({ page }) => {
    await loadDashboard(page);
    const sidebarButtons = page.locator("aside .overflow-y-auto button");
    await expect(sidebarButtons).toHaveCount(10);
  });

  test("BUG-2: no horizontal scroll on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    await expect(page.locator("h1", { hasText: "Your market catch-up" })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("article").first()).toBeVisible({ timeout: 20_000 });
    await page.waitForTimeout(1000);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
