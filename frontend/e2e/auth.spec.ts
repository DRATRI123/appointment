import { expect, test } from "@playwright/test";

/**
 * Full Phase 2 flow against the real backend (console OTP provider shows the code in development):
 * OTP sign-in -> onboarding (create organization) -> admin overview -> invite staff -> settings -> sign out.
 */
test("otp sign-in, create organization, invite staff, update settings", async ({ page }) => {
  const mobile = `9${Math.floor(100000000 + Math.random() * 899999999)}`;
  await page.goto("/login");
  await page.getByLabel("Mobile number or email").fill(mobile);
  await page.getByRole("button", { name: "Send code" }).click();

  const debug = page.getByTestId("debug-code");
  await expect(debug).toBeVisible();
  const code = (await debug.locator("strong").textContent())!.trim();
  await page.getByLabel("One-time code").fill(code);
  await page.getByLabel(/Your name/).fill("E2E Owner");
  await page.getByRole("button", { name: /Verify/ }).click();

  // New user without memberships lands on the customer dashboard; go create an organization.
  await page.waitForURL(/\/customer/);
  await page.goto("/onboarding");
  await page.getByLabel("Organization name").fill("E2E Clinic");
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "E2E Clinic" })).toBeVisible();

  // Staff: invite a receptionist.
  await page.goto("/admin/staff");
  await expect(page.getByTestId("member-row")).toHaveCount(1);
  await page.getByRole("button", { name: "Add staff" }).click();
  await page.getByLabel("Full name").fill("Front Desk");
  await page.getByLabel("Mobile number or email").fill(`8${Math.floor(100000000 + Math.random() * 899999999)}`);
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByTestId("member-row")).toHaveCount(2);
  await expect(page.getByText("invited")).toBeVisible();

  // Settings: flip a booking switch and save.
  await page.goto("/admin/settings");
  await page.getByRole("tab", { name: "Booking" }).click();
  const guest = page.locator("#booking\\.allow_guest_booking");
  await guest.click();
  await page.getByTestId("settings-booking").getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Booking settings saved")).toBeVisible();

  // Audit log shows the change.
  await page.goto("/admin/audit-logs");
  await expect(page.getByText("organization.settings_updated").first()).toBeVisible();

  // Sign out returns to login and protected pages redirect.
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.waitForURL(/\/login/);
  await page.goto("/admin");
  await page.waitForURL(/\/login\?next=/);
});

test("email registration leads to onboarding", async ({ page }) => {
  const email = `owner-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Reg Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await expect(page.getByText("Set up your organization")).toBeVisible();
});

test("super admin area is denied to ordinary users", async ({ page }) => {
  const email = `plain-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Plain User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.goto("/super-admin");
  await expect(page.getByText("You don't have access to this area")).toBeVisible();
});
