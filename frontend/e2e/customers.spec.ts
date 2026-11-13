import { expect, test, type Page } from "@playwright/test";

async function ownerWithOrg(page: Page) {
  const email = `cu-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Customer Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Cust Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
}

test("staff add a customer, a family member and an encrypted note", async ({ page }) => {
  await ownerWithOrg(page);
  await page.goto("/admin/customers");
  await page.getByRole("button", { name: "Add customer" }).click();
  await page.getByLabel("Full name").fill("Asha Patel");
  await page.getByLabel("Mobile").fill("9811111111");
  await page.getByLabel("Tags").fill("vip");
  await page.getByRole("button", { name: "Add customer" }).last().click();
  await expect(page.getByTestId("customer-row")).toHaveCount(1);
  await page.getByRole("link", { name: "Asha Patel" }).click();
  await expect(page.getByRole("heading", { name: "Asha Patel" })).toBeVisible();

  await page.getByRole("tab", { name: "Family" }).click();
  await page.getByLabel("Name").fill("Dev Patel");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("Dev Patel")).toBeVisible();

  await page.getByRole("tab", { name: "Notes" }).click();
  await page.getByPlaceholder("Write a note…").fill("Allergic to penicillin");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByTestId("note")).toContainText("Allergic to penicillin");
});

test("a published booking form is required during public booking", async ({ page, context }) => {
  await ownerWithOrg(page);
  const slug = await page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    const post = (path: string, body: unknown, method = "POST") => fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) }).then((r) => r.json());
    const branch = await post("/branches", { name: "Main", code: "MAIN" });
    const service = await post("/services", { name: "Consult", duration_minutes: 30, price_paise: 0, payment_mode: "free" });
    const pro = await post("/professionals", { display_name: "Dr. Form", branches: [{ branch_id: branch.id }], services: [{ service_id: service.id }] });
    await post("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: "09:00:00", end_time: "18:00:00" })) }, "PUT");
    return org.slug as string;
  });

  // Build and publish a form from the template through the UI.
  await page.goto("/admin/booking-forms");
  await page.getByRole("button", { name: "New form" }).click();
  await page.getByLabel("Name").fill("Intake");
  await page.getByLabel("Start from").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Create" }).click();
  await page.waitForURL(/\/admin\/booking-forms\//);
  await expect(page.getByTestId("builder-field").first()).toBeVisible();
  await page.getByTestId("publish-form").click();
  await expect(page.getByText("published", { exact: false }).first()).toBeVisible();

  // Guest sees the form; submitting without required answers shows field errors.
  const guest = await (await context.browser()!.newContext()).newPage();
  await guest.goto(`/o/${slug}/book`);
  await guest.getByTestId("pick-service").first().click();
  await guest.getByTestId("pick-professional").first().click();
  await guest.getByTestId("slot").first().click();
  await expect(guest.getByTestId("booking-form-section")).toBeVisible();
  await guest.getByLabel("Full name").fill("Form Guest");
  await guest.getByLabel("Mobile number").fill("9822222222");
  await guest.getByRole("button", { name: "Confirm booking" }).click();
  await expect(guest.getByText("Reason for visit is required.")).toBeVisible();
  await guest.getByLabel(/Reason for visit/).fill("Persistent cough");
  await guest.getByText("No", { exact: true }).click();
  await guest.getByRole("button", { name: "Confirm booking" }).click();
  await guest.waitForURL(/\/appointments\/APT-/);
  await guest.context().close();

  // Staff see the answers on the appointment.
  await page.goto("/admin/appointments");
  await page.getByLabel("To date").fill(new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10));
  await page.getByTestId("appointment-row").first().click();
  await expect(page.getByTestId("form-answers")).toContainText("Persistent cough");
});
