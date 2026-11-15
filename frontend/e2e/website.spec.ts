import { expect, test, type Page } from "@playwright/test";
import { pickFirstSlot, randomMobile } from "./guest-booking";

/** A clinic with one branch, one service and one scheduled doctor, owned by the signed-in page. */
async function seedClinic(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Website Owner");
  await page.getByLabel("Email").fill(`site-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  const name = `Site Clinic ${Date.now()}`;
  await page.getByLabel("Organization name").fill(name);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  const slug = await page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    const call = (path: string, body: unknown, method = "POST") => fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) }).then((r) => r.json());
    const branch = await call("/branches", { name: "Main", code: "MAIN" });
    const service = await call("/services", { name: "Consultation", duration_minutes: 30, price_paise: 50000, payment_mode: "pay_at_clinic" });
    const pro = await call("/professionals", { display_name: "Dr. Web", qualification: "BAMS", branches: [{ branch_id: branch.id }], services: [{ service_id: service.id }] });
    await call("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: "09:00:00", end_time: "18:00:00" })) }, "PUT");
    return org.slug as string;
  });
  return { slug, name };
}

async function go(page: Page, label: string) {
  await page.getByRole("navigation", { name: "Website sections" }).getByRole("link", { name: label, exact: true }).click();
}

test("admin edits the website, previews unsaved changes, publishes and can restore", async ({ page, browser }) => {
  test.setTimeout(90_000);
  const { slug, name } = await seedClinic(page);
  // Before anything is published, the clinic already has a starter site built from its own profile.
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto(`/${slug}`);
  await expect(visitor.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(visitor.getByTestId("site-doctor")).toContainText("Dr. Web");

  await page.goto("/admin/website/builder");
  await expect(page.getByTestId("website-toolbar")).toContainText("Draft not published");
  await go(page, "Hero section");
  await page.getByTestId("section-heading").fill("Gentle care, close to home");
  await go(page, "FAQ");
  await page.getByRole("button", { name: "Add question" }).click();
  await page.getByLabel("Question").fill("Is parking available?");
  await page.getByLabel("Answer").fill("Yes, **free parking** behind the clinic.");
  await go(page, "Custom pages");
  await page.getByTestId("add-page").click();
  await page.getByTestId("page-title").fill("Our story");
  await page.getByTestId("page-slug").fill("our-story");
  await page.getByLabel("Show in the menu").click();
  await page.getByRole("textbox", { name: "Content" }).fill("## Since 2009\n\nWe care for families.");
  await expect(page.getByTestId("website-toolbar")).toContainText("Unsaved changes");

  // The preview shows the unsaved draft.
  await go(page, "Preview & publish");
  const preview = page.frameLocator('[data-testid="preview-frame"]');
  await expect(preview.getByText("Gentle care, close to home")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("preview-mobile").click();
  await expect(preview.getByRole("button", { name: "Open menu" })).toBeVisible();
  // …while visitors still see the live site.
  await visitor.reload();
  await expect(visitor.getByText("Gentle care, close to home")).toHaveCount(0);

  await page.getByLabel("What changed (optional)").fill("New headline, FAQ, story page");
  await page.getByTestId("publish-now").click();
  await expect(page.getByTestId("website-toolbar")).toContainText("Live · version 1");

  await visitor.goto(`/${slug}`);
  await expect(visitor.getByRole("heading", { level: 1, name: "Gentle care, close to home" })).toBeVisible();
  await visitor.getByTestId("site-faq").getByText("Is parking available?").click();
  await expect(visitor.getByTestId("site-faq").locator("strong")).toHaveText("free parking");
  await visitor.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Our story" }).click();
  await expect(visitor).toHaveURL(new RegExp(`/${slug}/our-story$`));
  await expect(visitor.getByRole("heading", { level: 1, name: "Our story" })).toBeVisible();
  await expect(visitor.getByRole("heading", { name: "Since 2009" })).toBeVisible();

  // Publish a second version, then restore the first into the draft and publish it again.
  await go(page, "Hero section");
  await page.getByTestId("section-heading").fill("A different headline");
  await page.getByTestId("publish").click();
  await expect(page.getByTestId("website-toolbar")).toContainText("Live · version 2");
  await go(page, "Preview & publish");
  await page.getByTestId("website-version").filter({ hasText: "Version 1" }).getByRole("button", { name: "Restore" }).click();
  await page.getByTestId("confirm-restore").click();
  await page.getByTestId("publish-now").click();
  await expect(page.getByTestId("website-toolbar")).toContainText("Live · version 3");
  await visitor.goto(`/${slug}`);
  await expect(visitor.getByRole("heading", { level: 1, name: "Gentle care, close to home" })).toBeVisible();
  await visitor.context().close();
});

test("unsafe links are refused with a message that says where the problem is", async ({ page }) => {
  await seedClinic(page);
  await page.goto("/admin/website/buttons");
  await page.getByTestId("add-button").click();
  await page.getByTestId("button-label").fill("Partner");
  await page.getByTestId("button-editor").getByLabel("Button type").selectOption({ label: "Custom URL" });
  await page.getByTestId("button-url").fill("javascript:alert(1)");
  await page.getByTestId("save-draft").click();
  await expect(page.getByText("Partner › web address: Links must start with https://")).toBeVisible();
  await page.getByTestId("button-url").fill("https://partner.example.com");
  await page.getByTestId("save-draft").click();
  await expect(page.getByText("Draft saved")).toBeVisible();
});

test("patients can verify by email when the clinic offers it, and analytics count the visit", async ({ page, browser }) => {
  test.setTimeout(90_000);
  const { slug } = await seedClinic(page);
  await page.goto("/admin/settings/verification");
  await page.getByTestId("policy-channel-email").click();
  await page.getByTestId("save-otp-policy").click();
  await expect(page.getByText("Verification settings saved")).toBeVisible();

  const guest = await (await browser.newContext()).newPage();
  await guest.goto(`/${slug}?utm_source=instagram&utm_campaign=spring`);
  await guest.getByRole("link", { name: "Book appointment" }).first().click();
  await guest.waitForURL(new RegExp(`/${slug}/book`));
  await guest.getByTestId("pick-service").first().click();
  await pickFirstSlot(guest);
  const email = `patient${Date.now()}@example.com`;
  await guest.getByLabel("Patient's full name").fill("Email Patient");
  await guest.getByLabel("Mobile number").fill(randomMobile());
  await guest.locator("#bk_email").fill(email);
  await guest.getByTestId("channel-email").click();
  const started = guest.waitForResponse((r) => r.url().endsWith("/verification/start"));
  await guest.getByTestId("send-code").click();
  expect((await started).status()).toBe(200);
  const { code } = await (await guest.request.get(`/api/v1/dev/outbox/latest-code?destination=${encodeURIComponent(email)}`)).json();
  await guest.getByTestId("otp-input").fill(code);
  await expect(guest.getByTestId("email-verified")).toBeVisible();
  await guest.getByTestId("details-continue").click();
  await guest.getByTestId("confirm-booking").click();
  await guest.waitForURL(/\/appointments\/APT-/);
  await guest.context().close();

  await page.goto("/admin/website-analytics");
  const kpis = page.getByTestId("website-kpis");
  await expect(kpis).toContainText("Bookings via website");
  await expect(page.getByText("instagram").first()).toBeVisible();
  await expect(page.getByText("spring")).toBeVisible();
});
