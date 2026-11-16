import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "Str0ngPass123";

async function ownerWithOrg(page: Page) {
  const email = `pv-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Privacy Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Privacy Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
}

test("contact details are hidden until shown, staff screens carry a watermark and lock", async ({ page }) => {
  await ownerWithOrg(page);

  // Watermark (references only, no personal data) and the confidentiality notice; the watermark never takes clicks.
  const watermark = page.getByTestId("watermark");
  await expect(watermark).toHaveAttribute("data-text", /^U-[0-9A-F]{8} · .+ · \d{4}-\d{2}-\d{2} \d{2}:\d{2} · S-[0-9A-F]{6}$/);
  await expect(watermark).toHaveAttribute("aria-hidden", "true");
  await expect(watermark).toHaveCSS("pointer-events", "none");
  await expect(page.getByTestId("confidential-notice")).toBeVisible();

  await page.goto("/admin/customers");
  await page.getByRole("button", { name: "Add customer" }).click();
  await page.getByLabel("Full name").fill("Asha Patel");
  await page.getByLabel("Mobile").fill("9811111111");
  await page.getByLabel("Email").fill("asha.patel@example.com");
  await page.getByRole("button", { name: "Add customer" }).last().click();

  // The list shows hidden values only.
  const row = page.getByTestId("customer-row");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("XXXXX");
  await expect(row).toContainText("ash***@example.com");
  await expect(row).not.toContainText("9811111111");

  // The record: hidden until "Show" (just signed in, so no confirmation is asked yet); then call/email links appear.
  await page.getByRole("link", { name: "Asha Patel" }).click();
  const contact = page.getByTestId("masked-contact");
  await expect(contact).toContainText("XXXXX");
  await expect(contact.getByRole("link")).toHaveCount(0);
  await page.getByTestId("reveal-contact").click();
  await expect(contact.getByRole("link", { name: "+919811111111" })).toHaveAttribute("href", "tel:+919811111111");
  await expect(contact.getByRole("link", { name: "asha.patel@example.com" })).toBeVisible();

  // Watermarked PDF summary.
  const [pdf] = await Promise.all([page.waitForEvent("download"), page.getByTestId("summary-pdf").click()]);
  expect(pdf.suggestedFilename()).toMatch(/summary\.pdf$/);

  // Screen lock: the API refuses everything until the person confirms it is them; the page content is removed.
  await page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    await fetch("/api/v1/auth/lock", { method: "POST", credentials: "include", headers: { "X-CSRF-Token": csrf } });
  });
  await page.getByRole("tab", { name: "Appointments" }).click();
  await page.reload();
  const lock = page.getByTestId("lock-screen");
  await expect(lock).toBeVisible();
  await expect(page.getByRole("heading", { name: "Asha Patel" })).toHaveCount(0);
  await lock.getByLabel("Your password").fill("wrong-password-1");
  await lock.getByRole("button", { name: "Unlock" }).click();
  await expect(lock.getByRole("alert")).toBeVisible();
  await lock.getByLabel("Your password").fill(PASSWORD);
  await lock.getByRole("button", { name: "Unlock" }).click();
  await expect(lock).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Asha Patel" })).toBeVisible();
});

test("administrators change privacy rules on one page; values outside the range are refused", async ({ page }) => {
  await ownerWithOrg(page);
  await page.goto("/admin/settings/privacy");
  const form = page.getByTestId("privacy-settings-form");
  await expect(form.getByLabel("Hide patients' mobile numbers and emails")).toBeChecked();
  await form.getByLabel("Printing staff screens").selectOption("block");
  await form.getByLabel("Receptionist").fill("5");
  await page.getByTestId("privacy-save").click();
  await expect(page.getByText("Privacy settings saved")).toBeVisible();
  await page.reload();
  await expect(form.getByLabel("Printing staff screens")).toHaveValue("block");
  await expect(page.locator("html")).toHaveAttribute("data-print-policy", "block");

  await form.getByLabel("Lock the screen after").fill("999");
  await page.getByTestId("privacy-save").click();
  await expect(page.getByText(/lock_after_minutes|between|at most|range/i).first()).toBeVisible();
});
