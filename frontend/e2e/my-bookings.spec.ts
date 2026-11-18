import { expect, test, type Page } from "@playwright/test";
import { bookAsGuest, randomMobile } from "./guest-booking";

// Bug report: patients who booked without signing in could only see their booking's status and payment through the
// private link. Now they sign in with a one-time code to the mobile number they booked with and see every booking.

/** Seed an organization with a scheduled professional through the API from the signed-in browser. */
async function seedClinic(page: Page) {
  const email = `bk-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Booking Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  const orgName = `Booking Clinic ${Date.now()}`;
  await page.getByLabel("Organization name").fill(orgName);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  const slug = await page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const orgs = await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json());
    const org = orgs[0];
    const post = (path: string, body: unknown, method = "POST") => fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) }).then((r) => r.json());
    const branch = await post("/branches", { name: "Main", code: "MAIN" });
    const service = await post("/services", { name: "General consultation", duration_minutes: 30, price_paise: 50000, payment_mode: "pay_at_clinic" });
    const pro = await post("/professionals", { display_name: "Dr. E2E", specialization: "General", branches: [{ branch_id: branch.id }], services: [{ service_id: service.id }] });
    await post("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: "09:00:00", end_time: "18:00:00" })) }, "PUT");
    return org.slug as string;
  });
  return { slug, orgName };
}

test("a guest booking shows up after signing in with a code to the same mobile, on another phone, without the link", async ({ page, browser }) => {
  const { slug } = await seedClinic(page);
  const mobile = randomMobile();
  const firstPhone = await browser.newContext();
  const reference = await bookAsGuest(await firstPhone.newPage(), slug, { name: "Asha Patel", mobile });
  await firstPhone.close();

  // Another phone: nothing stored, no link.
  const otherPhone = await browser.newContext();
  const p = await otherPhone.newPage();
  await p.goto(`/${slug}/bookings`);
  await expect(p.getByTestId("bookings-sign-in")).toBeVisible();
  await expect(p.getByTestId("device-booking")).toHaveCount(0);
  await expect(p.locator("input[type=password]")).toHaveCount(0); // patients never see a password field
  await expect(p.getByText(/your code is/i)).toHaveCount(0); // no code on the screen
  // Sign in right here: mobile number → one-time code (sent through the clinic's channels; never shown on the page).
  await p.getByLabel("Mobile number").fill(mobile);
  await p.getByTestId("patient-send-code").click();
  await expect(p.getByTestId("patient-code-form")).toContainText(/\+91•+/); // masked number
  const r = await p.request.get(`/api/v1/dev/outbox/latest-code?destination=${encodeURIComponent(`+91${mobile}`)}`); // development and test only
  expect(r.status()).toBe(200);
  await p.getByTestId("patient-code").fill((await r.json()).code); // all digits: checks by itself

  // The patient's area on the clinic's page: the booking with status and payment, payments, family, messages.
  const account = p.getByTestId("patient-account");
  await expect(account).toBeVisible();
  expect(p.url()).toMatch(new RegExp(`/${slug}/bookings$`)); // stayed on the clinic's page
  await expect(p.getByTestId("patient-name")).toHaveText("Asha Patel");
  const item = account.getByTestId("device-booking").filter({ hasText: "Dr. E2E" });
  await expect(item).toHaveCount(1);
  await expect(item.getByTestId("booking-status-chip")).toHaveText("Confirmed");
  await expect(item.getByTestId("booking-payment")).toContainText("pay at the clinic");
  await p.getByRole("tab", { name: "Family" }).click();
  await p.getByLabel("Name").fill("Riya Patel");
  await p.getByRole("button", { name: "Add" }).click();
  await expect(p.getByTestId("family-member")).toContainText("Riya Patel");
  await p.getByRole("tab", { name: "Messages" }).click();
  await p.getByTestId("pref-marketing").click();
  await expect(p.getByTestId("pref-marketing")).toHaveAttribute("aria-checked", "true");
  await p.getByRole("tab", { name: "Bookings" }).click();
  await item.getByTestId("booking-open").click();
  await p.waitForURL(new RegExp(`/appointments/${reference}$`));
  await expect(p.getByTestId("booking-status")).toBeVisible();
  // Sign out: back to the sign-in box.
  await p.goto(`/${slug}/bookings`);
  await p.getByTestId("patient-sign-out").click();
  await expect(p.getByTestId("bookings-sign-in")).toBeVisible();
  await otherPhone.close();
});

test("'My bookings' is in the website header on a computer and in the menu on a phone", async ({ page, browser }) => {
  const { slug } = await seedClinic(page);
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const d = await desktop.newPage();
  await d.goto(`/${slug}`);
  await d.getByTestId("header-my-bookings").click();
  await d.waitForURL(new RegExp(`/${slug}/bookings$`));
  await expect(d.getByTestId("bookings-sign-in")).toBeVisible();
  await desktop.close();

  const phone = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const m = await phone.newPage();
  await m.goto(`/${slug}/book`);
  await expect(m.getByTestId("header-my-bookings")).toBeHidden(); // the bottom bar has it on phones
  await m.getByRole("button", { name: "Open menu" }).click();
  await m.getByTestId("menu-my-bookings").click();
  await m.waitForURL(new RegExp(`/${slug}/bookings$`));
  await expect(m.getByTestId("bookings-sign-in")).toBeVisible();
  await phone.close();
});
