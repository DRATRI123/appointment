import { expect, test, type Page } from "@playwright/test";
import { bookAsGuest, randomMobile } from "./guest-booking";

// Patient help desk: a patient asks the clinic (with a photo), staff answer (and leave an internal note), the patient
// reads the answer, replies, and rates the help.

const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(64)]);

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

async function signInPatient(p: Page, slug: string, mobile: string) {
  await p.goto(`/${slug}/bookings`);
  await p.getByLabel("Mobile number").fill(mobile);
  await p.getByTestId("patient-send-code").click();
  await expect(p.getByTestId("patient-code-form")).toBeVisible();
  const r = await p.request.get(`/api/v1/dev/outbox/latest-code?destination=${encodeURIComponent(`+91${mobile}`)}`);
  await p.getByTestId("patient-code").fill((await r.json()).code);
  await expect(p.getByTestId("patient-account")).toBeVisible();
}

test("a patient asks a question, staff answer with an internal note, the patient replies and rates", async ({ page, browser }) => {
  const { slug } = await seedClinic(page);
  const mobile = randomMobile();
  const phone = await browser.newContext();
  const p = await phone.newPage();
  const reference = await bookAsGuest(p, slug, { name: "Meera Shah", mobile });

  // From the booking's page: "Need help with this booking?" → sign in → the question form, booking already chosen.
  await p.getByTestId("booking-help").click();
  await p.waitForURL(/tab=help/);
  await signInPatient(p, slug, mobile);
  await p.goto(`/${slug}/bookings?tab=help&booking=${reference}`);
  await expect(p.getByTestId("help-form")).toBeVisible();
  await expect(p.getByLabel("Booking (optional)")).toHaveValue(reference);
  await p.getByText("Payment", { exact: true }).click();
  await p.getByLabel("Title").fill("Paid by UPI but status not updated");
  await p.getByLabel("Your question").fill("I paid at 10am, please check.");
  await p.getByTestId("help-file").setInputFiles({ name: "upi.png", mimeType: "image/png", buffer: PNG });
  await p.getByTestId("help-send").click();
  await expect(p.getByTestId("help-thread")).toBeVisible();
  await expect(p.getByTestId("help-status")).toHaveText("Waiting for clinic");
  await expect(p.getByTestId("help-message")).toContainText("I paid at 10am");

  // The clinic's inbox.
  await page.goto("/admin/helpdesk");
  const row = page.getByTestId("desk-row").filter({ hasText: "Paid by UPI" });
  await expect(row).toContainText("Meera Shah");
  await row.getByRole("link").click();
  await expect(page.getByTestId("ticket-subject")).toHaveText("Paid by UPI but status not updated");
  await expect(page.getByTestId("ticket-message")).toContainText("upi.png");
  await page.getByTestId("desk-internal").click();
  await page.getByTestId("desk-reply").fill("Checked the bank statement: credit found at 10:02.");
  await page.getByTestId("desk-send").click();
  await expect(page.getByTestId("ticket-note")).toContainText("bank statement");
  await page.getByTestId("desk-internal").click();
  await page.getByTestId("desk-reply").fill("We found your payment and confirmed the booking. Thank you!");
  await page.getByTestId("desk-send").click();
  await expect(page.getByTestId("desk-status")).toHaveValue("pending_customer");
  await expect(page.getByTestId("desk-assignee")).not.toHaveValue("");

  // The patient sees the answer (not the note), replies, then marks it answered with a rating.
  await p.reload();
  await expect(p.getByTestId("help-message").filter({ hasText: "confirmed the booking" })).toBeVisible();
  await expect(p.getByText("bank statement")).toHaveCount(0);
  await expect(p.getByRole("tab", { name: "Help" }).getByLabel(/new replies/)).toHaveCount(0); // read: no "new reply" badge
  await p.getByTestId("help-reply").fill("Great, thanks!");
  await p.getByTestId("help-reply-send").click();
  await expect(p.getByTestId("help-status")).toHaveText("Waiting for clinic");
  await p.getByTestId("help-solved").click();
  await expect(p.getByTestId("help-status")).toHaveText("Solved");
  await p.getByTestId("help-rate-5").click();
  await expect(p.getByText("You rated this help 5/5")).toBeVisible();

  await page.goto("/admin/helpdesk");
  await expect(page.getByTestId("desk-summary")).toContainText("5");
  await phone.close();
});
