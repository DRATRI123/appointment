import { expect, test } from "@playwright/test";

// Bug report: leave the app open, come back later, touch it, and it asked to sign in again although the sign-in was
// still valid. The short-lived login cookie had gone; the app must renew it quietly with the long sign-in.
test("after a pause the app renews the sign-in by itself instead of asking to sign in again", async ({ page, context }) => {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Pause Owner");
  await page.getByLabel("Email").fill(`pause-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Pause Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);

  // Sign-ins made before this fix kept the short cookie for 15 minutes only; the browser then drops it.
  await context.clearCookies({ name: "access_token" });
  await page.goto("/admin/appointments");
  await expect(page.getByRole("heading", { name: "Appointments" }).first()).toBeVisible();
  expect(page.url()).toContain("/admin/appointments");
  expect((await context.cookies()).some((c) => c.name === "access_token")).toBe(true); // renewed

  // Signed out on purpose: no long sign-in left, so the sign-in page is right.
  await context.clearCookies();
  await page.goto("/admin/appointments");
  await page.waitForURL(/\/login/);
});
