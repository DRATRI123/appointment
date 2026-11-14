import { expect, test, type Page } from "@playwright/test";

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

test("guest books through the wizard, sees the status page, staff sees it on the calendar", async ({ page, context }) => {
  const { slug } = await seedClinic(page);

  // Guest in a fresh context (no cookies).
  const guest = await context.browser()!.newContext();
  const g = await guest.newPage();
  await g.goto(`/o/${slug}`);
  await g.getByTestId("book-now").click();
  await g.getByTestId("pick-service").first().click();
  // single branch auto-selected → professional step
  await g.getByTestId("pick-professional").first().click();
  await expect(g.getByTestId("slot-picker")).toBeVisible();
  // pick first available day with slots then first slot
  const slot = g.getByTestId("slot").first();
  await expect(slot).toBeVisible({ timeout: 10_000 });
  await slot.click();
  await expect(g.getByTestId("hold-countdown")).toBeVisible();
  await expect(g.getByTestId("pay-now")).toContainText("Nothing");
  await g.getByLabel("Full name").fill("Guest Patient");
  await g.getByLabel("Mobile number").fill("9898989898");
  await g.getByRole("button", { name: "Confirm booking" }).click();
  await g.waitForURL(/\/appointments\/APT-/);
  await expect(g.getByTestId("booking-heading")).toContainText("confirmed");
  await expect(g.getByText("Dr. E2E")).toBeVisible();
  const reference = g.url().match(/APT-[A-Z0-9-]+/)![0];
  await guest.close();

  // Staff sees the appointment in the list and can check it in.
  await page.goto("/admin/appointments");
  await page.getByLabel("To date").fill(new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10));
  await expect(page.getByTestId("appointment-row")).toHaveCount(1);
  await page.getByTestId("appointment-row").click();
  await expect(page.getByText(reference)).toBeVisible();
  await page.getByTestId("action-check_in").click();
  await expect(page.getByTestId("appointment-status")).toHaveText("Checked in");

  // Calendar renders the event.
  await page.goto("/admin/calendar");
  await expect(page.getByTestId("calendar")).toBeVisible();
  await expect(page.getByTestId("calendar").getByRole("button", { name: "Today", exact: true })).toBeVisible();
});

test("the same slot cannot be held twice", async ({ page, request }) => {
  const { slug } = await seedClinic(page);
  const info = await page.evaluate(async (slug) => {
    const org = await fetch(`/api/v1/public/organizations/${slug}`).then((r) => r.json());
    const services = await fetch(`/api/v1/public/organizations/${slug}/services`).then((r) => r.json());
    const pros = await fetch(`/api/v1/public/organizations/${slug}/professionals`).then((r) => r.json());
    const date = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
    const day = await fetch(`/api/v1/public/organizations/${slug}/availability?service_id=${services[0].id}&branch_id=${org.branches[0].id}&date=${date}`).then((r) => r.json());
    return { branch: org.branches[0].id, service: services[0].id, pro: pros[0].id, start: day.professionals[0].slots[0].start_at };
  }, slug);
  const body = { professional_id: info.pro, branch_id: info.branch, service_id: info.service, start_at: info.start };
  const first = await request.post(`/api/v1/public/organizations/${slug}/holds`, { data: { ...body, session_key: "a" } });
  expect(first.status()).toBe(201);
  const second = await request.post(`/api/v1/public/organizations/${slug}/holds`, { data: { ...body, session_key: "b" } });
  expect(second.status()).toBe(409);
  expect((await second.json()).code).toBe("slot_unavailable");
});
