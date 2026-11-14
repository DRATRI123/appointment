import { devices, expect, test, type Page } from "@playwright/test";
import { bookAsGuest, fillDetailsAndVerify, pickFirstSlot, randomMobile, sendCode } from "./guest-booking";

interface Clinic { slug: string; orgId: string; services: Record<string, string>; branches: Record<string, string>; pros: Record<string, string> }

/** Two locations, two services (one paid by UPI), two doctors: enough for every step of the booking page to appear. */
async function seedClinic(page: Page): Promise<Clinic> {
  const email = `pb-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Clinic Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Public Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  return page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    const call = (path: string, body: unknown, method = "POST") => fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) }).then((r) => r.json());
    const main = await call("/branches", { name: "Main Road", code: "MAIN" });
    const east = await call("/branches", { name: "East Side", code: "EAST" });
    const consult = await call("/services", { name: "Consultation", duration_minutes: 30, price_paise: 60000, payment_mode: "full_advance" });
    const therapy = await call("/services", { name: "Therapy", duration_minutes: 60, price_paise: 150000, payment_mode: "pay_at_clinic" });
    const both = [{ branch_id: main.id }, { branch_id: east.id }];
    const asha = await call("/professionals", { display_name: "Dr. Asha Rao", specialization: "Ayurveda", qualification: "BAMS, MD", experience_years: 12, branches: both, services: [{ service_id: consult.id }, { service_id: therapy.id }] });
    const vikram = await call("/professionals", { display_name: "Dr. Vikram Iyer", specialization: "Panchakarma", branches: both, services: [{ service_id: consult.id }] });
    for (const pro of [asha, vikram]) for (const branch of [main, east]) {
      await call("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: branch === main ? "09:00:00" : "14:00:00", end_time: branch === main ? "13:00:00" : "19:00:00" })) }, "PUT");
    }
    await call("/upi-accounts", { display_name: "Main", upi_id: "public.clinic@okhdfcbank", merchant_name: "Public Clinic" });
    return {
      slug: org.slug, orgId: org.id,
      services: { consult: consult.slug, therapy: therapy.slug },
      branches: { main: main.slug, east: east.slug },
      pros: { asha: asha.slug, vikram: vikram.slug },
    };
  });
}

async function allowEmbedding(page: Page, clinic: Clinic, origins: string[]) {
  const status = await page.evaluate(async ({ orgId, origins }) => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const r = await fetch(`/api/v1/organizations/${orgId}/settings/embed`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": orgId }, body: JSON.stringify({ values: { allowed_origins: origins } }) });
    return r.status;
  }, { orgId: clinic.orgId, origins });
  expect(status).toBe(200);
}

test("every step appears in order and the visitor can go back and change a choice", async ({ page, browser }) => {
  const clinic = await seedClinic(page);
  const guest = await (await browser.newContext()).newPage();
  await guest.goto(`/${clinic.slug}`);
  await expect(guest.getByRole("heading", { level: 2, name: "What would you like to book?" })).toBeVisible();
  await expect(guest.getByTestId("pick-service")).toHaveCount(2);
  await guest.getByTestId("pick-service").filter({ hasText: "Consultation" }).click();
  await expect(guest.getByRole("heading", { name: "Choose a location" })).toBeVisible();
  await guest.getByTestId("pick-branch").filter({ hasText: "East Side" }).click();
  await expect(guest.getByRole("heading", { name: "Choose your doctor" })).toBeVisible();
  await expect(guest.getByTestId("pick-professional")).toHaveCount(2);
  await expect(guest.getByText("BAMS, MD")).toBeVisible();
  await expect(guest.getByText("12+ yrs experience")).toBeVisible();
  await guest.getByTestId("pick-any").click();
  await expect(guest.getByRole("heading", { name: "Pick a date and time" })).toBeVisible();
  // Back goes to the doctor step with the choice kept editable.
  await guest.getByRole("button", { name: "Back" }).click();
  await expect(guest.getByRole("heading", { name: "Choose your doctor" })).toBeVisible();
  await guest.getByTestId("pick-professional").filter({ hasText: "Dr. Asha Rao" }).click();
  await pickFirstSlot(guest);
  const summary = guest.getByRole("complementary", { name: "Booking summary" });
  await expect(summary).toContainText("East Side");
  await expect(summary).toContainText("Dr. Asha Rao");
  await expect(summary.getByTestId("summary-total")).toHaveText("₹600.00");
  await guest.context().close();
});

test("URL parameters preselect real choices and are ignored when they do not match", async ({ page, browser }) => {
  const clinic = await seedClinic(page);
  const guest = await (await browser.newContext()).newPage();

  // Service, branch and doctor preselected: straight to the calendar.
  await guest.goto(`/${clinic.slug}?service=${clinic.services.consult}&branch=${clinic.branches.main}&doctor=${clinic.pros.vikram}`);
  await expect(guest.getByRole("heading", { name: "Pick a date and time" })).toBeVisible();
  const summary = guest.getByRole("complementary", { name: "Booking summary" });
  await expect(summary).toContainText("Consultation");
  await expect(summary).toContainText("Main Road");
  await expect(summary).toContainText("Dr. Vikram Iyer");

  // Aliases work too.
  await guest.goto(`/${clinic.slug}?service=${clinic.services.therapy}&location=${clinic.branches.east}`);
  await expect(guest.getByRole("heading", { name: "Pick a date and time" })).toBeVisible(); // only Dr. Asha offers therapy
  await expect(summary).toContainText("Dr. Asha Rao");

  // Unknown, malformed and price-like parameters change nothing.
  await guest.goto(`/${clinic.slug}?service=does-not-exist&branch=%3Cscript%3E&doctor=x&price=1&amount=1`);
  await expect(guest.getByRole("heading", { name: "What would you like to book?" })).toBeVisible();
  await expect(guest.getByTestId("pick-service")).toHaveCount(2);

  // A preselected paid service still costs what the clinic charges, whatever the link says.
  const reference = await bookAsGuest(guest, clinic.slug, {
    name: "Link Visitor", mobile: randomMobile(), servicePreselected: true,
    query: `?service=${clinic.services.consult}&branch=${clinic.branches.main}&doctor=${clinic.pros.asha}&price=1&total_amount_paise=1`,
    onReview: async (p) => { await expect(p.getByTestId("pay-now")).toHaveText("Pay ₹600.00 now"); },
  });
  expect(reference).toMatch(/^APT-/);
  await expect(guest.getByTestId("booking-status")).toHaveAttribute("data-tone", "action");
  await expect(guest.getByTestId("upi-checkout").getByText("Pay ₹600.00 by UPI")).toBeVisible();
  await guest.context().close();
  // The status page is private: on another device the reference alone is not enough.
  const stranger = await (await browser.newContext()).newPage();
  await stranger.goto(`/${clinic.slug}/appointments/${reference}`);
  await expect(stranger.getByTestId("booking-heading")).toHaveText("We couldn't open this booking");
  await stranger.context().close();
});

test("a wrong code is refused and the booking cannot continue until the number is verified", async ({ page, browser }) => {
  const clinic = await seedClinic(page);
  const guest = await (await browser.newContext()).newPage();
  await guest.goto(`/${clinic.slug}?service=${clinic.services.therapy}&branch=${clinic.branches.main}`);
  await pickFirstSlot(guest);
  await guest.getByLabel("Patient's full name").fill("Careful Visitor");
  await guest.getByLabel("Mobile number").fill(randomMobile());
  await expect(guest.getByTestId("details-continue")).toBeDisabled();
  const code = await sendCode(guest);
  const wrong = code === "000000" ? "111111" : "000000";
  await guest.getByTestId("otp-input").fill(wrong);
  await expect(guest.getByTestId("otp-error")).toContainText("Incorrect code");
  await expect(guest.getByTestId("details-continue")).toBeDisabled();
  await guest.getByTestId("otp-input").fill(code);
  await expect(guest.getByTestId("mobile-verified")).toBeVisible();
  await expect(guest.getByTestId("details-continue")).toBeEnabled();
  await guest.context().close();
});

test.describe("on a phone", () => {
  // Everything about an iPhone 13 except its browser engine (the suite runs Chromium).
  const { viewport, userAgent, deviceScaleFactor, isMobile, hasTouch } = devices["iPhone 13"];
  const iphone = { viewport, userAgent, deviceScaleFactor, isMobile, hasTouch };
  test.use(iphone);

  test("books end to end with the bottom summary bar and no sideways scrolling", async ({ page, browser }) => {
    const clinic = await seedClinic(page);
    const guest = await (await browser.newContext(iphone)).newPage();
    await guest.goto(`/${clinic.slug}`);
    const noSideScroll = () => guest.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    expect(await noSideScroll()).toBe(true);
    await expect(guest.getByTestId("mobile-summary")).toBeVisible();
    await guest.getByTestId("pick-service").filter({ hasText: "Consultation" }).click();
    await guest.getByTestId("pick-branch").first().click();
    await guest.getByTestId("pick-professional").first().click();
    await pickFirstSlot(guest);
    expect(await noSideScroll()).toBe(true);
    await fillDetailsAndVerify(guest, { name: "Phone Visitor", mobile: randomMobile() });
    await expect(guest.getByTestId("review")).toBeVisible();
    await guest.getByTestId("mobile-summary").getByRole("button").click();
    await expect(guest.getByTestId("mobile-summary")).toContainText("₹600.00");
    await guest.getByTestId("confirm-booking").click();
    await guest.waitForURL(/\/appointments\/APT-/);
    await expect(guest.getByTestId("upi-qr")).toBeVisible();
    expect(await noSideScroll()).toBe(true);
    await guest.context().close();
  });
});

test.describe("embedding", () => {
  test("normal pages cannot be framed; the embed page only by the clinic's allowed websites", async ({ page, request }) => {
    const clinic = await seedClinic(page);
    const normal = await request.get(`/${clinic.slug}`);
    expect(normal.headers()["x-frame-options"]).toBe("DENY");
    expect(normal.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");

    await allowEmbedding(page, clinic, ["https://shop.example.com", "https://www.shop.example.com/"]);
    const embed = await request.get(`/embed/${clinic.slug}`);
    expect(embed.status()).toBe(200);
    expect(embed.headers()["x-frame-options"]).toBeUndefined();
    expect(embed.headers()["content-security-policy"]).toContain("frame-ancestors 'self' https://shop.example.com https://www.shop.example.com;");
    expect(embed.headers()["x-robots-tag"] ?? (await embed.text())).toMatch(/noindex/);

    // A clinic that allowed nothing (or does not exist) cannot be framed at all.
    const unknown = await request.get("/embed/no-such-clinic-anywhere");
    expect(unknown.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");
  });

  test("an allowed store shows the booking page in an iframe that resizes itself; other sites are refused", async ({ page, browser, baseURL }) => {
    const clinic = await seedClinic(page);
    await allowEmbedding(page, clinic, ["http://shop.localhost:4999"]); // plain http is accepted only in development and test
    const bookingOrigin = new URL(baseURL!).origin;
    const parentHtml = `<!doctype html><title>Store</title><h1>Store page</h1>
      <iframe id="booking" src="${bookingOrigin}/embed/${clinic.slug}?service=${clinic.services.consult}" style="width:100%;height:320px;border:0"></iframe>
      <script>window.addEventListener("message", function (e) {
        if (e.origin !== ${JSON.stringify(bookingOrigin)} || !e.data || e.data.type !== "appointment-booking:resize") return;
        var h = parseInt(e.data.height, 10); if (h > 300 && h < 8000) document.getElementById("booking").style.height = h + "px";
      });</script>`;

    const ctx = await browser.newContext();
    // Chromium blocks pages on other hosts from framing localhost unless allowed; real stores and booking sites are
    // both public, so this only matters for the test.
    await ctx.grantPermissions(["local-network-access"]);
    await ctx.route(/^http:\/\/(shop|evil)\.localhost:4999\//, (route) => route.fulfill({ contentType: "text/html", body: parentHtml }));
    const store = await ctx.newPage();
    await store.goto("http://shop.localhost:4999/pages/book");
    const frame = store.frameLocator("#booking");
    await expect(frame.getByRole("heading", { name: "Choose a location" })).toBeVisible({ timeout: 15_000 });
    await expect(frame.getByTestId("booking-shell")).toBeVisible();
    await expect(frame.getByRole("heading", { level: 1 })).toHaveCount(0); // no clinic hero/header inside the frame
    await expect.poll(async () => store.locator("#booking").evaluate((el) => el.getBoundingClientRect().height)).toBeGreaterThan(320);

    const evil = await ctx.newPage();
    const blocked = evil.waitForEvent("console", { predicate: (m) => /frame-ancestors/.test(m.text()), timeout: 15_000 });
    await evil.goto("http://evil.localhost:4999/");
    await blocked;
    await expect(evil.frameLocator("#booking").getByTestId("booking-shell")).toHaveCount(0);
    await ctx.close();
  });
});

test("the admin screen builds links and code and saves allowed websites", async ({ page, context }) => {
  const clinic = await seedClinic(page);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/admin/booking-page");
  const link = page.getByTestId("booking-link");
  await expect(link).toHaveValue(new RegExp(`/${clinic.slug}$`));
  await page.getByLabel("Preselect service").selectOption({ label: "Therapy" });
  await expect(link).toHaveValue(new RegExp(`/${clinic.slug}\\?service=${clinic.services.therapy}$`));
  await expect(page.getByTestId("liquid-code")).toContainText(`clinic: '${clinic.slug}'`);
  await expect(page.getByTestId("liquid-code")).toContainText(`service: '${clinic.services.therapy}'`);
  await page.getByTestId("liquid-code-copy").click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("{% render 'appointment-booking-button'");
  await page.getByRole("tab", { name: "Embed (iframe)" }).click();
  await expect(page.getByTestId("iframe-code")).toContainText(`/embed/${clinic.slug}?service=${clinic.services.therapy}`);

  const snippet = await page.request.get("/integrations/shopify/appointment-booking-button.liquid");
  expect(snippet.status()).toBe(200);
  expect(await snippet.text()).toContain("ab-button");

  // Allowed websites: bad input is explained, good input is normalized and saved.
  await page.getByTestId("origin-input").fill("http://insecure.example.com");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "https://" })).toBeVisible();
  await page.getByTestId("origin-input").fill("MyStore.com/pages/book");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByTestId("allowed-websites")).toContainText("https://mystore.com");
  await page.getByTestId("save-origins").click();
  await expect(page.getByText(/Allowed websites saved/)).toBeVisible();
  const policy = await page.request.get(`/api/v1/public/organizations/${clinic.slug}/embed-policy`).then((r) => r.json());
  expect(policy.allowed_origins).toEqual(["https://mystore.com"]);
});
