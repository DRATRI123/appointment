import { expect, test } from "@playwright/test";

test("homepage renders hero, navigation and API status card", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("UPI account");
  await expect(page.getByTestId("system-status")).toBeVisible();
  await expect(page.getByRole("link", { name: /open admin dashboard/i })).toBeVisible();
});

test("dashboard shells are reachable", async ({ page }) => {
  for (const path of ["/admin", "/customer", "/professional", "/super-admin", "/login"]) {
    const response = await page.goto(path);
    expect(response?.ok()).toBeTruthy();
  }
});
