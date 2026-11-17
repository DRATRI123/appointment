import { expect, test, type Page } from "@playwright/test";

// The clinic's own app (here a stand-in page on another address) shows the admin panel in an iframe. People sign in
// inside the frame; only the listed app may show it; the ordinary sign-in in the same browser is not touched.

const PASSWORD = "Str0ngPass123";
const CLINIC_APP = "http://clinic.localhost:4998";
const OTHER_APP = "http://other.localhost:4998";

async function ownerWithOrg(page: Page) {
  const email = `panel-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Panel Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Panel Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  const slug = await page.evaluate(async () => (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0].slug as string);
  return { email, slug };
}

test("the clinic app shows the admin panel after signing in inside it; other apps are refused", async ({ page, baseURL }) => {
  const { email, slug } = await ownerWithOrg(page);
  const site = new URL(baseURL!).origin;

  // Switch it on and list the clinic app's address.
  await page.goto("/admin/settings/panel");
  await expect(page.getByTestId("panel-link")).toHaveText(`${site}/panel/${slug}`);
  await page.getByTestId("panel-origin-input").fill("ftp://nope");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.locator("#panel-origin-error")).toContainText("Enter the address of your clinic app");
  await page.getByTestId("panel-origin-input").fill(CLINIC_APP);
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByTestId("panel-enabled").click();
  await page.getByTestId("panel-save").click();
  await expect(page.getByText("Saved. Browsers pick up the change within a minute.")).toBeVisible();

  const parent = (src: string) => `<!doctype html><title>Clinic app</title><h1>Case paper</h1>
    <iframe id="panel" src="${src}" style="width:1280px;height:800px;border:0"></iframe>`;
  const ctx = page.context(); // the same browser as the owner's ordinary sign-in
  await ctx.grantPermissions(["local-network-access"]);
  await ctx.route(/^http:\/\/(clinic|other)\.localhost:4998\/admin-direct/, (route) => route.fulfill({ contentType: "text/html", body: parent(`${site}/admin`) }));
  await ctx.route(/^http:\/\/(clinic|other)\.localhost:4998\/$/, (route) => route.fulfill({ contentType: "text/html", body: parent(`${site}/panel/${slug}`) }));

  const app = await ctx.newPage();
  await app.setViewportSize({ width: 1400, height: 900 });
  await app.goto(`${CLINIC_APP}/`);
  const frame = app.frameLocator("#panel");
  // The browser's ordinary sign-in is not used inside the frame: it asks to sign in.
  await expect(frame.getByTestId("panel-sign-in")).toBeVisible({ timeout: 15_000 });
  await frame.getByLabel("Email").fill(email);
  await frame.getByLabel("Password").fill("wrong-password");
  await frame.getByRole("button", { name: "Sign in" }).click();
  await expect(frame.getByTestId("panel-error")).toBeVisible();
  await frame.getByLabel("Password").fill(PASSWORD);
  await frame.getByRole("button", { name: "Sign in" }).click();
  await expect(frame.getByTestId("panel-badge")).toBeVisible({ timeout: 15_000 });
  await frame.getByRole("link", { name: "Appointments" }).first().click();
  await expect(frame.getByRole("heading", { name: "Appointments" }).first()).toBeVisible();
  await expect(frame.getByTestId("panel-new-tab")).toHaveAttribute("target", "_blank");

  // Signing out of the panel goes back to its sign-in and leaves the ordinary sign-in alone.
  await frame.getByRole("button", { name: /account menu/ }).click();
  await frame.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(frame.getByTestId("panel-sign-in")).toBeVisible();
  await page.goto("/admin");
  await expect(page.getByTestId("role-label")).toBeVisible();

  // Another app may not show the panel, and no app may frame the admin screens directly.
  for (const url of [`${OTHER_APP}/`, `${CLINIC_APP}/admin-direct`]) {
    const other = await ctx.newPage();
    const blocked = other.waitForEvent("console", { predicate: (m) => /frame-ancestors|X-Frame-Options/.test(m.text()), timeout: 15_000 });
    await other.goto(url);
    await blocked;
    await expect(other.frameLocator("#panel").getByTestId("panel-sign-in")).toHaveCount(0);
    await expect(other.frameLocator("#panel").getByTestId("role-label")).toHaveCount(0);
    await other.close();
  }
  await app.close();
});

test("the panel page opened on its own explains itself, and is off until the clinic switches it on", async ({ page }) => {
  const { slug } = await ownerWithOrg(page);
  await page.goto(`/panel/${slug}`);
  await expect(page.getByTestId("panel-not-framed")).toBeVisible();
  const ctx = page.context();
  await ctx.grantPermissions(["local-network-access"]);
  await ctx.route(/^http:\/\/clinic\.localhost:4998\/off/, (route) => route.fulfill({ contentType: "text/html", body: `<iframe id="panel" src="${new URL(page.url()).origin}/panel/${slug}"></iframe>` }));
  const app = await ctx.newPage();
  const blocked = app.waitForEvent("console", { predicate: (m) => /frame-ancestors/.test(m.text()), timeout: 15_000 });
  await app.goto(`${CLINIC_APP}/off`);
  await blocked; // off: no app may show it
});
