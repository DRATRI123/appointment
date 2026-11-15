import { expect, test, type Page } from "@playwright/test";
import { fillDetailsAndVerify, pickFirstSlot, randomMobile } from "./guest-booking";

async function seedClinic(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Notify Owner");
  await page.getByLabel("Email").fill(`notify-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Notify Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  return page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    const call = (path: string, body: unknown, method = "POST") => fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) }).then((r) => r.json());
    const branch = await call("/branches", { name: "Main", code: "MAIN" });
    const service = await call("/services", { name: "Consultation", duration_minutes: 30, price_paise: 50000, payment_mode: "full_advance" });
    const pro = await call("/professionals", { display_name: "Dr. Recon", branches: [{ branch_id: branch.id }], services: [{ service_id: service.id }] });
    await call("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: "09:00:00", end_time: "18:00:00" })) }, "PUT");
    await call("/upi-accounts", { display_name: "Main", upi_id: "clinic@okhdfcbank", merchant_name: "Recon Clinic" });
    return { slug: org.slug as string };
  });
}


test("admin turns on WhatsApp, a guest opts in, staff see the bell and the outbox, and edit a template", async ({ page, context }) => {
  const { slug } = await seedClinic(page);

  await page.goto("/admin/notifications");
  await page.getByRole("tab", { name: "Settings" }).click();
  await page.getByTestId("toggle-whatsapp_enabled").click();
  await page.getByTestId("save-notification-settings").click();
  await expect(page.getByText("Notification settings saved")).toBeVisible();
  await expect(page.getByTestId("reminder-chip")).toHaveCount(2);

  const guest = await (await context.browser()!.newContext()).newPage();
  await guest.goto(`/${slug}/book`);
  await guest.getByTestId("pick-service").first().click();
  await pickFirstSlot(guest);
  await guest.getByTestId("whatsapp-opt-in").check();
  await fillDetailsAndVerify(guest, { name: "Opted In Guest", mobile: randomMobile(), email: "optin@example.com" });
  await guest.getByTestId("confirm-booking").click();
  await guest.waitForURL(/\/appointments\/APT-/);
  await guest.context().close();

  // Bell shows the new booking (polled every minute; reload to fetch now).
  await page.reload();
  await expect(page.getByTestId("unread-count")).toHaveText("1");
  await page.getByTestId("notification-bell").click();
  await expect(page.getByTestId("inbox-item").first()).toContainText("New booking: Opted In Guest");
  await page.getByTestId("inbox-item").first().click();
  await page.waitForURL(/\/admin\/appointments/);
  await expect(page.getByTestId("unread-count")).toHaveCount(0);

  // Outbox: the payment-due message went to email and WhatsApp (SMS is off by default).
  await page.goto("/admin/notifications");
  const rows = page.getByTestId("outbox-row").filter({ hasText: "Booking received, payment due" });
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: "WhatsApp" })).toHaveCount(1);
  await rows.filter({ hasText: "Email" }).click();
  await expect(page.getByTestId("outbox-message")).toContainText("₹500.00");
  await page.keyboard.press("Escape");

  // Template editor: live preview, then save a custom subject.
  await page.getByRole("tab", { name: "Templates" }).click();
  await page.getByTestId("template-card").filter({ hasText: "Appointment confirmed" }).click();
  await page.getByLabel("Subject").fill("See you on {{appointment_date}}, {{customer_name}}");
  await expect(page.frameLocator("[data-testid=email-preview]").getByText("Asha Patel").first()).toBeVisible();
  await page.getByTestId("save-template").click();
  await expect(page.getByText("Customised for your clinic")).toBeVisible();
  await page.getByRole("button", { name: "SMS", exact: true }).click();
  await expect(page.getByTestId("text-preview")).toContainText("SMS part");
});
