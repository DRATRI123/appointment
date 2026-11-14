import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** Collect CSP violations and console errors for a page. */
async function watch(page: Page) {
  const problems: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      (window as unknown as { __csp: string[] }).__csp = [...((window as unknown as { __csp?: string[] }).__csp ?? []), `${e.violatedDirective} ${e.blockedURI}`];
    });
  });
  return problems;
}

async function audit(page: Page, path: string, problems: string[]) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  const csp = await page.evaluate(() => (window as unknown as { __csp?: string[] }).__csp ?? []);
  expect(csp, `CSP violations on ${path}`).toEqual([]);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} × ${v.nodes[0]?.target.join(" ")} — ${v.help}`), `Accessibility on ${path}`).toEqual([]);
  expect(problems.filter((p) => !p.includes("Failed to load resource")), `Console errors on ${path}`).toEqual([]);
}

test("public, auth, booking and admin pages: no CSP violations, no console errors, no serious accessibility issues", async ({ page }) => {
  test.setTimeout(120000);
  const problems = await watch(page);
  for (const path of ["/", "/login", "/register"]) await audit(page, path, problems);

  await page.goto("/register");
  await page.getByLabel("Full name").fill("Quality Owner");
  await page.getByLabel("Email").fill(`quality-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Quality Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  const slug = await page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    const call = (path: string, body: unknown, method = "POST") => fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) }).then((r) => r.json());
    const branch = await call("/branches", { name: "Main", code: "MAIN" });
    const service = await call("/services", { name: "Consultation", duration_minutes: 30, price_paise: 50000, payment_mode: "full_advance" });
    const pro = await call("/professionals", { display_name: "Dr. Quality", branches: [{ branch_id: branch.id }], services: [{ service_id: service.id }] });
    await call("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: "09:00:00", end_time: "18:00:00" })) }, "PUT");
    await call("/upi-accounts", { display_name: "Main", upi_id: "clinic@okhdfcbank", merchant_name: "Quality Clinic" });
    return org.slug as string;
  });
  for (const path of ["/admin", "/admin/appointments", "/admin/calendar", "/admin/payments/verification", "/admin/reports", "/admin/notifications", "/admin/developers", "/admin/settings", `/o/${slug}`, `/o/${slug}/book`]) {
    await audit(page, path, problems);
  }
});
