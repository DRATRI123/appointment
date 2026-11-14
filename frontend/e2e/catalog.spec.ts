import { expect, test, type Page } from "@playwright/test";

async function signInAndCreateOrg(page: Page, orgName: string) {
  const email = `cat-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Catalog Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(orgName);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
}

test("branch, category, service and professional appear on the public page", async ({ page }) => {
  const orgName = `Lotus Clinic ${Date.now()}`;
  await signInAndCreateOrg(page, orgName);

  // Branch
  await page.goto("/admin/branches");
  await page.getByRole("button", { name: "Add branch" }).first().click();
  await page.getByLabel("Name", { exact: true }).fill("Koramangala");
  await page.getByLabel("Code", { exact: true }).fill("KOR");
  await page.getByLabel("City", { exact: true }).fill("Bengaluru");
  await page.getByRole("button", { name: "Create branch" }).click();
  await expect(page.getByTestId("branch-card")).toHaveCount(1);
  await expect(page.getByText("default")).toBeVisible();

  // Category
  await page.goto("/admin/categories");
  await page.getByRole("button", { name: "Add category" }).first().click();
  await page.getByLabel("Name", { exact: true }).fill("Skin consultation");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByTestId("category-row")).toHaveCount(1);

  // Service
  await page.goto("/admin/services");
  await page.getByRole("button", { name: "Add service" }).first().click();
  await page.getByLabel("Name", { exact: true }).fill("Acne consultation");
  await page.getByLabel("Category", { exact: true }).selectOption({ label: "Skin consultation" });
  await page.getByRole("tab", { name: /Pricing/ }).click();
  await page.locator("#s_price").fill("800");
  await page.getByRole("button", { name: "Create service" }).click();
  await expect(page.getByTestId("service-row")).toHaveCount(1);
  await expect(page.getByText("₹800.00")).toBeVisible();

  // Professional with branch + service
  await page.goto("/admin/professionals");
  await page.getByRole("button", { name: "Add professional" }).first().click();
  await page.getByLabel("Display name", { exact: true }).fill("Dr. Kavya Nair");
  await page.getByLabel("Specialization", { exact: true }).fill("Dermatology");
  await page.getByRole("tab", { name: /Branches/ }).click();
  await page.getByText("Koramangala", { exact: true }).click();
  await page.getByRole("tab", { name: "Services" }).click();
  await page.getByText("Acne consultation", { exact: true }).click();
  await page.getByRole("button", { name: "Add professional" }).last().click();
  await expect(page.getByTestId("professional-card")).toHaveCount(1);
  await expect(page.getByText("1 branch · 1 service")).toBeVisible();

  // Public page
  const slug = await page.evaluate(() => fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()).then((o) => o[0].slug));
  await page.goto(`/${slug}`);
  await expect(page.getByRole("heading", { level: 1, name: orgName })).toBeVisible();
  await expect(page.getByTestId("pick-service")).toHaveCount(1);
  await expect(page.getByTestId("pick-service")).toContainText("Acne consultation");
  await page.getByTestId("pick-service").click();
  // One branch and one doctor: both are chosen automatically and shown in the summary.
  const summary = page.getByRole("complementary", { name: "Booking summary" });
  await expect(summary.getByText("Dr. Kavya Nair")).toBeVisible();
  await expect(summary.getByText("Koramangala")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Pick a date and time" })).toBeVisible();

  // Old links keep working.
  await page.goto(`/o/${slug}/book`);
  await expect(page).toHaveURL(new RegExp(`/${slug}$`));
});

test("unknown organization slug shows a not-found state", async ({ page }) => {
  await page.goto("/this-org-does-not-exist");
  await expect(page.getByText("We couldn't find this booking page")).toBeVisible();
});
