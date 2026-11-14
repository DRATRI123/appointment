import { expect, test, type Page } from "@playwright/test";

/** Clinic with today's outcomes: booked, cancelled, completed + cash paid, no-show. */
async function seed(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Dashboard Owner");
  await page.getByLabel("Email").fill(`dash-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Dashboard Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  await page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    const call = async (path: string, body: unknown, method = "POST") => {
      const r = await fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) });
      const data = await r.json();
      if (!r.ok) throw new Error(`${path}: ${JSON.stringify(data)}`);
      return data;
    };
    const branch = await call("/branches", { name: "Main", code: "MAIN" });
    const service = await call("/services", { name: "Consultation", duration_minutes: 30, price_paise: 50000, payment_mode: "pay_at_clinic" });
    const pro = await call("/professionals", { display_name: "Dr. Dash", branches: [{ branch_id: branch.id }], services: [{ service_id: service.id }] });
    await call("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: "06:00:00", end_time: "22:00:00" })) }, "PUT");
    const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
    const book = (hhmm: string, name: string, mobile: string) => call("/appointments", { professional_id: pro.id, branch_id: branch.id, service_id: service.id, start_at: `${today}T${hhmm}:00+05:30`, customer: { full_name: name, mobile }, source: "reception" });
    await book("07:00", "Asha Booked", "9811000001");
    const b = await book("07:30", "Ravi Cancelled", "9811000002");
    const c = await book("08:00", "Meera Completed", "9811000003");
    const d = await book("08:30", "Kiran NoShow", "9811000004");
    await call(`/appointments/${b.id}/status`, { action: "cancel" });
    await call(`/appointments/${c.id}/status`, { action: "complete" });
    await call("/payments", { appointment_id: c.id, kind: "full", method: "cash" });
    await call(`/appointments/${d.id}/status`, { action: "no_show" });
  });
}

test("dashboard shows KPIs and charts with table views; reports preview and download", async ({ page }) => {
  await seed(page);
  await page.goto("/admin");
  const tiles = page.getByTestId("stat-tile");
  await expect(tiles.filter({ hasText: "Money received" })).toContainText("₹500");
  await expect(tiles.filter({ hasText: "Appointments" }).first()).toContainText("4");
  await expect(tiles.filter({ hasText: "Cancellation rate" })).toContainText("25%");
  await expect(tiles.filter({ hasText: "No-show rate" })).toContainText("50%");
  await expect(page.getByTestId("today")).toContainText("1 done · 1 no-show"); // the cancelled visit is not on today's agenda
  const outcomes = page.getByTestId("chart-frame").filter({ hasText: "Appointments by day" });
  await expect(outcomes.locator(".recharts-bar-rectangle").first()).toBeVisible();
  await outcomes.getByRole("button", { name: "Table" }).click();
  await expect(outcomes.getByRole("row").filter({ hasText: /\d/ }).last()).toContainText(/2\s*1\s*1/);
  await expect(page.getByTestId("setup-checklist")).toHaveCount(0);

  await page.getByRole("link", { name: "Reports" }).first().click();
  await page.waitForURL(/\/admin\/reports/);
  await page.getByTestId("report-list").getByRole("button", { name: "Appointments" }).click();
  const table = page.getByTestId("report-table");
  await expect(table.getByRole("row")).toHaveCount(6); // header + 4 rows + totals
  await expect(table).toContainText("Meera Completed");
  await expect(page.getByText("Contains patients' personal details")).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-xlsx").click()]);
  expect(download.suggestedFilename()).toMatch(/^appointments_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}\.xlsx$/);
  await page.getByTestId("report-list").getByRole("button", { name: "Daily summary" }).click();
  await expect(page.getByTestId("report-table")).toContainText("₹500.00");
});
