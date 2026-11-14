import { expect, test } from "@playwright/test";
import { audit, watch } from "./audit";

// Needs a platform admin (scripts/create_platform_admin.py). CI creates one; locally set both variables to run it.
const email = process.env.E2E_PLATFORM_ADMIN_EMAIL;
const password = process.env.E2E_PLATFORM_ADMIN_PASSWORD;

test("platform admin sees worker, jobs, checks and backups on System health", async ({ page }) => {
  test.skip(!email || !password, "set E2E_PLATFORM_ADMIN_EMAIL and E2E_PLATFORM_ADMIN_PASSWORD");
  const problems = await watch(page);
  await page.goto("/login");
  await page.getByRole("tab", { name: "Email & password" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email!);
  await page.getByLabel("Password", { exact: true }).fill(password!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/super-admin/);

  await audit(page, "/super-admin/health", problems);
  await expect(page.getByRole("heading", { name: "System health" })).toBeVisible();
  const checks = page.getByTestId("health-checks");
  await expect(checks).toContainText("Database");
  await expect(checks).toContainText("Schema migrations");
  await expect(page.getByTestId("health-jobs")).toContainText("Send email, SMS and WhatsApp");
  // Either everything is fine or the page says exactly what is wrong.
  await expect(page.getByTestId("health-ok").or(page.getByTestId("health-attention"))).toBeVisible();
});
