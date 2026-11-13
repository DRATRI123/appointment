import { expect, test, type Page } from "@playwright/test";

async function seedClinic(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Recon Owner");
  await page.getByLabel("Email").fill(`recon-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Recon Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);
  return page.evaluate(async () => {
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)![1];
    const org = (await fetch("/api/v1/organizations", { credentials: "include" }).then((r) => r.json()))[0];
    const call = (path: string, body: unknown, method = "POST") => fetch(`/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Organization-Id": org.id }, body: JSON.stringify(body) }).then((r) => r.json());
    const branch = await call("/branches", { name: "Main", code: "MAIN" });
    const service = await call("/services", { name: "Consultation", duration_minutes: 30, price_paise: 50000, payment_mode: "full_advance" });
    const pro = await call("/professionals", { display_name: "Dr. Recon", branches: [{ branch_id: branch.id }], services: [{ service_id: service.id }] });
    await call("/schedules", { professional_id: pro.id, branch_id: branch.id, windows: [0, 1, 2, 3, 4, 5, 6].map((wd) => ({ weekday: wd, start_time: "09:00:00", end_time: "18:00:00" })) }, "PUT");
    await call("/upi-accounts", { display_name: "Main", upi_id: "clinic@okhdfcbank", merchant_name: "Recon Clinic" });
    return { slug: org.slug as string };
  });
}

function istToday() {
  const d = new Date(Date.now() + 5.5 * 3600 * 1000);
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${String(d.getUTCFullYear()).slice(2)}`;
}

test("statement import suggests a match, staff verify with bank evidence, then refund it", async ({ page, context }) => {
  const { slug } = await seedClinic(page);
  const utr = String(400000000000 + Math.floor(Math.random() * 99999999999));

  const guest = await (await context.browser()!.newContext()).newPage();
  await guest.goto(`/o/${slug}/book`);
  await guest.getByTestId("pick-service").first().click();
  await guest.getByTestId("pick-professional").first().click();
  await guest.getByTestId("slot").first().click();
  await guest.getByLabel("Full name").fill("Statement Guest");
  await guest.getByLabel("Mobile number").fill("9812300001");
  await guest.getByRole("button", { name: "Confirm booking" }).click();
  await guest.waitForURL(/\/appointments\/APT-/);
  await guest.getByLabel("UTR / UPI reference number *").fill(utr);
  await guest.getByRole("button", { name: "Submit for verification" }).click();
  await expect(guest.getByTestId("payment-status")).toHaveText("Submitted");
  await guest.context().close();

  // Import today's statement (HDFC layout is detected from the header).
  const today = istToday();
  const csv = [
    "HDFC BANK Ltd.,,,,,,",
    "Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance",
    `${today},UPI-STATEMENT GUEST-guest@okicici-ICIC0000001-${utr}-PAYMENT,0000${utr},${today},,500.00,"1,00,500.00"`,
    `${today},NEFT CR-SUPPLIER REFUND,HDFCN5202611139${String(Date.now()).slice(-4)},${today},,"1,234.00","1,01,734.00"`,
  ].join("\n");
  await page.goto("/admin/reconciliation");
  await page.getByRole("tab", { name: "Import statement" }).click();
  await page.getByLabel("Statement file (CSV)").setInputFiles({ name: "hdfc.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByLabel("Bank format")).toHaveValue("hdfc");
  await page.getByTestId("import-statement").click();

  const row = page.getByTestId("bank-row").filter({ hasText: utr });
  await expect(row).toContainText("Suggested");
  await expect(row).toContainText("Statement Guest");
  await row.getByTestId("confirm-suggestion").click();
  await page.getByRole("tab", { name: "All" }).click();
  await expect(page.getByTestId("bank-row").filter({ hasText: utr })).toContainText("Matched");

  // The unrelated credit can be ignored with a reason.
  const supplier = page.getByTestId("bank-row").filter({ hasText: "SUPPLIER REFUND" });
  await supplier.getByRole("button", { name: "Ignore" }).click();
  await page.getByLabel("Reason").fill("Supplier refund, not a booking");
  await page.getByRole("button", { name: "Ignore", exact: true }).last().click();
  await expect(supplier).toContainText("Ignored");

  // Matching is evidence only: the payment is still waiting until a verifier approves it.
  await page.getByTestId("bank-row").filter({ hasText: utr }).getByRole("button", { name: "Open payment" }).click();
  await expect(page.getByTestId("payment-status").first()).toHaveText("Submitted");
  await expect(page.getByTestId("bank-evidence")).toContainText("Matched to this payment");
  await page.getByTestId("bank-credit").click();
  await page.getByTestId("approve-payment").click();
  await expect(page.getByTestId("payment-history")).toContainText("verified");

  // Request a refund from the payment, then approve and record it on the refunds page.
  await page.getByRole("button", { name: "Request refund" }).click();
  await page.getByLabel("Reason").fill("Doctor unavailable");
  await page.getByTestId("submit-refund-request").click();
  await expect(page.getByTestId("payment-refunds")).toContainText("Requested");
  await page.keyboard.press("Escape");

  await page.goto("/admin/refunds");
  await page.getByTestId("refund-row").first().click();
  await page.getByTestId("approve-refund").click();
  await expect(page.getByTestId("process-refund")).toBeVisible();
  await expect(page.getByTestId("mark-refunded")).toBeDisabled();
  await page.getByLabel("Refund UTR / bank reference").fill(`RF${utr}`);
  await page.getByTestId("refund-sent").click();
  await page.getByTestId("mark-refunded").click();
  await expect(page.getByRole("dialog").getByTestId("refund-status")).toHaveText("Refunded");
  await expect(page.getByRole("dialog")).toContainText(`RF${utr}`);
});
