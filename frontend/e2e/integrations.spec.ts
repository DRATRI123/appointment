import { expect, test, type Page } from "@playwright/test";
import { bookAsGuest, randomMobile } from "./guest-booking";

async function seedClinic(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Video Owner");
  await page.getByLabel("Email").fill(`video-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Video Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  return page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    const call = (path: string, body: unknown, method = "POST") => fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) }).then((r) => r.json());
    const branch = await call("/branches", { name: "Main", code: "MAIN" });
    const service = await call("/services", { name: "Video Consultation", duration_minutes: 30, price_paise: 50000, payment_mode: "pay_at_clinic", consultation_mode: "online" });
    const pro = await call("/professionals", { display_name: "Dr. Video", branches: [{ branch_id: branch.id }], services: [{ service_id: service.id }] });
    await call("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: "09:00:00", end_time: "18:00:00" })) }, "PUT");
    return { slug: org.slug as string };
  });
}

test("manual video link reaches the customer, feeds and calendar files work, staff can change the link", async ({ page, context }) => {
  const { slug } = await seedClinic(page);

  await page.goto("/admin/integrations/calendar");
  await expect(page.getByText("Add your clinic's Google Cloud app first.")).toBeVisible();
  await expect(page.getByTestId("connect-google")).toBeDisabled();
  await expect(page.getByTestId("zoom-card")).toBeVisible();
  const card = page.getByTestId("professional-connections").filter({ hasText: "Dr. Video" });
  await card.getByLabel("Online consultations use").selectOption("manual");
  await card.getByLabel("Your meeting room link").fill("https://meet.example.com/dr-video");
  await card.getByTestId("save-meeting").click();
  await expect(page.getByText("Video link settings saved")).toBeVisible();
  await expect(card).toContainText("My own meeting link");
  await card.getByTestId("create-feed").click();
  const feedUrl = await card.getByLabel("Calendar feed link").inputValue();
  expect(feedUrl).toMatch(/\/api\/v1\/calendar-feeds\/.+\.ics$/);

  const guest = await (await context.browser()!.newContext()).newPage();
  await bookAsGuest(guest, slug, { name: "Video Guest", mobile: randomMobile() });
  await expect(guest.getByTestId("booking-heading")).toContainText("confirmed");
  await expect(guest.getByTestId("join-meeting")).toHaveAttribute("href", "https://meet.example.com/dr-video");
  const ics = await guest.getByRole("link", { name: "Add to calendar (.ics)" }).getAttribute("href");
  const icsResp = await guest.request.get(ics!);
  expect(icsResp.headers()["content-type"]).toContain("text/calendar");
  expect(await icsResp.text()).toContain("SUMMARY:Video Consultation with Dr. Video");
  await guest.context().close();

  const feed = await page.request.get(new URL(feedUrl).pathname);
  expect(feed.status()).toBe(200);
  expect(await feed.text()).toContain("Video Guest");

  await page.goto("/admin/appointments");
  await page.getByText("Video Guest").first().click();
  await expect(page.getByTestId("meeting-link")).toHaveText(/meet\.example\.com\/dr-video/);
  await page.getByTestId("appointment-meeting").getByRole("button", { name: "Change" }).click();
  await page.getByLabel("Meeting link").fill("https://zoom.us/j/123456789");
  await page.getByTestId("appointment-meeting").getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("meeting-link")).toHaveText(/zoom\.us\/j\/123456789/);
});
