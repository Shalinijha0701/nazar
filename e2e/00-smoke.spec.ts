import { expect, test } from "@playwright/test";

test.describe("smoke", () => {
  test("dashboard loads with replay data and grouped counts", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1", { hasText: "Your market catch-up" })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("text=/Replay connected/").first()).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("text=3 attention")).toBeVisible();
    await expect(page.locator("text=5 normal noise")).toBeVisible();
    await expect(page.locator("text=2 unavailable")).toBeVisible();
  });

  test("health endpoint reports ok", async ({ request }) => {
    const response = await request.get("http://localhost:8000/health");
    expect(response.status()).toBe(200);
    expect(await response.json()).toEqual({ status: "ok" });
  });
});
