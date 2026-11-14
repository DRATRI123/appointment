import { expect, test, type Page } from "@playwright/test";
import { bookAsGuest, randomMobile } from "./guest-booking";

/** Owner with a branch, a full-advance service, a scheduled professional and a UPI account. */
async function seedClinic(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Payments Owner");
  await page.getByLabel("Email").fill(`pay-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`UPI Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  return page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    const call = (path: string, body: unknown, method = "POST") => fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) }).then((r) => r.json());
    const branch = await call("/branches", { name: "Main", code: "MAIN" });
    const service = await call("/services", { name: "Consultation", duration_minutes: 30, price_paise: 50000, payment_mode: "full_advance" });
    const pro = await call("/professionals", { display_name: "Dr. Pay", branches: [{ branch_id: branch.id }], services: [{ service_id: service.id }] });
    await call("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: "09:00:00", end_time: "18:00:00" })) }, "PUT");
    await call("/coupons", { code: "TENOFF", discount_type: "percent", discount_value: 10 });
    return { slug: org.slug as string };
  });
}

test("UPI accounts page adds an account and previews a test QR", async ({ page }) => {
  await seedClinic(page);
  await page.goto("/admin/upi-accounts");
  await page.getByRole("button", { name: "Add UPI account" }).first().click();
  await page.getByLabel("Display name").fill("Main counter");
  await page.getByLabel("UPI ID").fill("sunrise.clinic@okhdfcbank");
  await page.getByLabel("Merchant name (payee)").fill("Sunrise Ayurveda");
  await page.getByRole("button", { name: "Add account" }).click();
  await expect(page.getByTestId("upi-account")).toHaveCount(1);
  await expect(page.getByTestId("upi-account").getByText("default", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Test QR" }).click();
  await expect(page.getByAltText("Test UPI QR")).toBeVisible();
  await expect(page.getByText(/upi:\/\/pay\?pa=sunrise\.clinic@okhdfcbank/)).toBeVisible();
});

test("guest pays by UPI, submits the UTR, staff verify and the booking is confirmed", async ({ page, context }) => {
  const { slug } = await seedClinic(page);
  await page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    await fetch("/api/v1/upi-accounts", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify({ display_name: "Main", upi_id: "clinic@okhdfcbank", merchant_name: "UPI Clinic" }) });
  });

  const guest = await (await context.browser()!.newContext()).newPage();
  await bookAsGuest(guest, slug, {
    name: "Paying Guest", mobile: randomMobile(), coupon: "tenoff",
    onReview: async (p) => {
      await expect(p.getByTestId("pay-now")).toHaveText("Pay ₹450.00 now");
      await expect(p.getByTestId("summary-total").first()).toHaveText("₹450.00");
    },
  });

  // Checkout: QR, UPI ID, amount.
  await expect(guest.getByTestId("upi-checkout")).toBeVisible();
  await expect(guest.getByTestId("upi-qr")).toBeVisible();
  await expect(guest.getByTestId("upi-id")).toContainText("clinic@okhdfcbank");
  await expect(guest.getByTestId("upi-checkout").getByText("Pay ₹450.00 by UPI")).toBeVisible();
  await guest.getByLabel("UTR / UPI reference number *").fill("412345678901");
  await guest.getByRole("button", { name: "Submit for verification" }).click();
  await expect(guest.getByTestId("booking-heading")).toContainText("Payment received for checking");
  await expect(guest.getByTestId("payment-status")).toHaveText("Submitted");
  const statusUrl = guest.url();

  // Staff verify from the queue.
  await page.goto("/admin/payments/verification");
  await page.getByTestId("payment-row").first().click();
  await expect(page.getByTestId("submission")).toContainText("412345678901");
  await expect(page.getByTestId("approve-payment")).toBeDisabled();
  await page.getByTestId("bank-credit").click();
  await page.getByTestId("approve-payment").click();
  await expect(page.getByTestId("payment-history")).toContainText("verified");

  await guest.goto(statusUrl);
  await expect(guest.getByTestId("booking-heading")).toContainText("confirmed");
  await guest.context().close();
});
