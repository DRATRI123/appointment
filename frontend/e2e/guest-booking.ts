import { expect, type Page } from "@playwright/test";

export interface GuestBooking {
  name: string;
  mobile: string; // 10 digits, as a visitor types it
  email?: string;
  coupon?: string;
  /** Query string for preselection, e.g. "?service=consultation". */
  query?: string;
  /** Skip clicking a service card (it was preselected by the URL). */
  servicePreselected?: boolean;
  /** Called on the review step before confirming (assert prices, apply coupons, …). */
  onReview?: (page: Page) => Promise<void>;
  base?: string; // "" (default) or "/embed"
}

/**
 * Book as a guest through the public booking page: doctor → (service, location) → date and time → details + code →
 * review → confirm. The code is read from the development outbox; the page and the API never show it.
 */
export async function bookAsGuest(page: Page, slug: string, b: GuestBooking): Promise<string> {
  // The booking steps live at /{clinic}/book (the clinic website is /{clinic}); the frame page is /embed/{clinic}.
  await page.goto(b.base ? `${b.base}/${slug}${b.query ?? ""}` : `/${slug}/book${b.query ?? ""}`);
  await pickFirstSlot(page);
  await fillDetailsAndVerify(page, b);
  await expect(page.getByTestId("review")).toBeVisible();
  if (b.coupon) {
    await page.getByLabel("Coupon code").fill(b.coupon);
    await page.getByRole("button", { name: "Apply" }).click();
  }
  if (b.onReview) await b.onReview(page);
  await page.getByTestId("confirm-booking").click();
  await page.waitForURL(/\/appointments\/APT-/);
  return page.url().match(/APT-[A-Z0-9-]+/)![0];
}

/**
 * From the doctor list or a doctor's page: pick the first doctor (if the list is shown), the first service and location
 * (if there is a choice), the first free time, then "Book appointment".
 */
export async function pickFirstSlot(page: Page) {
  const detail = page.getByTestId("doctor-detail");
  const doctor = page.getByTestId("pick-professional").first();
  await expect(detail.or(doctor)).toBeVisible({ timeout: 15_000 });
  if (!(await detail.isVisible())) await doctor.click();
  await expect(detail).toBeVisible();
  const services = detail.getByTestId("pick-service");
  if ((await services.count()) && !(await detail.locator('[data-testid="pick-service"][aria-checked="true"]').count())) await services.first().click();
  const branches = detail.getByTestId("pick-branch");
  if ((await branches.count()) && !(await detail.locator('[data-testid="pick-branch"][aria-checked="true"]').count())) await branches.first().click();
  const slot = page.getByTestId("slot").first();
  await expect(slot).toBeVisible({ timeout: 15_000 });
  await slot.click();
  await page.getByTestId("book-slot").click();
  await expect(page.getByTestId("details-form")).toBeVisible();
  await expect(page.getByTestId("hold-countdown")).toBeVisible();
}

export async function fillDetailsAndVerify(page: Page, b: Pick<GuestBooking, "name" | "mobile" | "email">) {
  await page.getByLabel("Patient's full name").fill(b.name);
  await page.getByLabel("Mobile number").fill(b.mobile);
  if (b.email) await page.getByLabel("Email (optional)").fill(b.email);
  const code = await sendCode(page);
  await page.getByTestId("otp-input").fill(code); // six digits submit by themselves
  await expect(page.getByTestId("contact-verified")).toBeVisible();
  await page.getByTestId("details-continue").click();
}

/**
 * Press "Send code" and return the code. The API never returns codes; in development and test the console delivery
 * provider keeps them in memory and /api/v1/dev/outbox/latest-code hands the latest one to automated tests.
 */
export async function sendCode(page: Page, destination?: string): Promise<string> {
  const sent = page.waitForResponse((r) => r.url().endsWith("/verification/start") && r.request().method() === "POST");
  await page.getByTestId("send-code").click();
  const response = await sent;
  expect(response.status(), await response.text()).toBe(200);
  const body = await response.json();
  expect(JSON.stringify(body)).not.toMatch(/"code":"\d+"/);
  const to = destination ?? `+91${(await page.getByLabel("Mobile number").inputValue()).replace(/\D/g, "").slice(-10)}`;
  const r = await page.request.get(`/api/v1/dev/outbox/latest-code?destination=${encodeURIComponent(to)}`);
  expect(r.status(), "the test API must run with APP_ENV=development or test").toBe(200);
  return (await r.json()).code as string;
}

/** A fresh Indian mobile number, so per-number code limits never carry over between test runs. */
export function randomMobile(): string {
  return `9${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
}
