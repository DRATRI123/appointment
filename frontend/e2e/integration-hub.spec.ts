import { expect, test, type Page } from "@playwright/test";
import { audit, watch } from "./audit";

// Only integrations that need no outside service are exercised here (Tally, Google Analytics IDs): the browser tests
// never contact Google, Zoho, HubSpot or n8n. Those are covered by the API tests with simulated providers.

async function ownerWithOrg(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Hub Owner");
  await page.getByLabel("Email").fill(`hub-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Hub Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  return page.evaluate(async () => (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0].slug as string);
}

test("the hub lists every integration by category; Tally and Google Analytics are set up and work", async ({ page }) => {
  const slug = await ownerWithOrg(page);
  await page.goto("/admin/integrations");
  await expect(page.getByTestId("hub-summary")).toBeVisible();
  await expect(page.getByTestId("hub-card-hubspot")).toContainText("Not set up");
  await expect(page.getByTestId("hub-card-google_calendar")).toBeVisible();
  await page.getByRole("tab", { name: "Accounting" }).click();
  await expect(page.getByTestId("hub-card-hubspot")).toHaveCount(0);
  await expect(page.getByTestId("hub-card-zoho_books")).toBeVisible();

  // Tally: ledgers filled in by default; save, test, download the import file.
  await page.getByTestId("hub-card-tally").getByRole("link", { name: /Set up|Configure/ }).click();
  await expect(page.getByRole("heading", { name: "Tally (XML export)" })).toBeVisible();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  await page.getByTestId("hub-test").click();
  await expect(page.getByTestId("status-pill").first()).toHaveText(/Connected/);
  const [file] = await Promise.all([page.waitForEvent("download"), page.getByTestId("tally-export").click()]);
  expect(file.suggestedFilename()).toMatch(/^tally-.*\.xml$/);

  // Google Analytics: a wrong ID is refused, a right one becomes Active and the public page asks for consent.
  await page.goto("/admin/integrations/ga4");
  await page.getByLabel("GA4 measurement ID").fill("UA-123");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/looks like G-/)).toBeVisible();
  await page.getByLabel("GA4 measurement ID").fill("G-TEST12345");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  await page.getByTestId("hub-test").click();
  await expect(page.getByTestId("status-pill").first()).toHaveText(/Active/);

  // Levels: Google connections need the clinic's own Google Cloud app; the platform's key is only for sign-in.
  await page.goto("/admin/integrations/google_contacts");
  await expect(page.getByText("First add your clinic's own Google Cloud app")).toBeVisible();
  await expect(page.getByTestId("hub-connect")).toBeDisabled();
  await page.goto("/admin/integrations/google_app");
  await expect(page.getByText("Authorized redirect URI (add it to your Google OAuth client)")).toBeVisible();
  // A clinic may keep its private files in its own bucket; until then the platform storage is used.
  await page.goto("/admin/integrations/own_storage");
  await expect(page.getByTestId("clinic-storage-where")).toHaveText("Platform storage");
  await expect(page.getByTestId("clinic-storage-switch")).toBeDisabled();
  await page.goto("/admin/integrations");
  await expect(page.getByTestId("hub-card-google_signin")).toHaveCount(0); // a platform setting, not on the clinic page

  await page.goto(`/${slug}`);
  const banner = page.getByTestId("analytics-consent");
  await expect(banner).toBeVisible();
  await banner.getByRole("button", { name: "No, thanks" }).click();
  await expect(banner).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("analytics-consent")).toHaveCount(0); // the answer is remembered
  const loaded = await page.evaluate(() => Array.from(document.scripts).some((s) => s.src.includes("googletagmanager")));
  expect(loaded).toBe(false); // nothing loads without consent
});

test("calendar & video page and integration pages pass accessibility and CSP checks", async ({ page }) => {
  const problems = await watch(page);
  await ownerWithOrg(page);
  for (const path of ["/admin/integrations", "/admin/integrations/calendar", "/admin/integrations/n8n", "/admin/integrations/zoho_crm"]) await audit(page, path, problems);
  await expect(page.getByText("Authorized redirect URI (Zoho API Console)")).toBeVisible();
});

const email = process.env.E2E_PLATFORM_ADMIN_EMAIL;
const password = process.env.E2E_PLATFORM_ADMIN_PASSWORD;

test("super admin sets Google from the panel, sees where values come from and downloads .env lines", async ({ page }) => {
  test.skip(!email || !password, "set E2E_PLATFORM_ADMIN_EMAIL and E2E_PLATFORM_ADMIN_PASSWORD");
  const problems = await watch(page);
  await page.goto("/login");
  await page.getByRole("tab", { name: "Email & password" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email!);
  await page.getByLabel("Password", { exact: true }).fill(password!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/super-admin/);
  await audit(page, "/super-admin/integrations", problems);
  await expect(page.getByTestId("integration-summary")).toBeVisible();
  const google = page.getByTestId("section-google");
  await google.getByRole("button", { name: "Configure" }).click();
  await google.locator("#google_google_client_id").fill("123-e2e.apps.googleusercontent.com");
  await google.locator("#google_google_client_secret").fill("GOCSPX-e2e-only-not-real");
  await google.getByRole("button", { name: "Save" }).click();
  await expect(google.getByTestId("status-pill")).toHaveText(/Not tested yet/);
  await expect(google.getByText("saved here").first()).toBeVisible();
  await expect(google.locator("#google_google_client_secret")).toHaveValue(""); // never shown again
  const [file] = await Promise.all([page.waitForEvent("download"), page.getByTestId("env-download").click()]);
  expect(file.suggestedFilename()).toBe("integrations.env");
  // Undo: back to the .env values so other tests see a clean platform.
  await google.getByRole("button", { name: "Use the .env value for OAuth client ID" }).click();
  await google.getByRole("button", { name: "Use the .env value for OAuth client secret" }).click();
  await google.getByRole("button", { name: "Save" }).click();
  await expect(google.getByTestId("status-pill")).toHaveText(/Not set up/);
});
