import crypto from "node:crypto";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { expect, test } from "@playwright/test";

test("API key created in the portal works until revoked; webhook test ping arrives signed", async ({ page }) => {
  // A local receiver for webhook deliveries (private targets are allowed in development).
  const received: { headers: http.IncomingHttpHeaders; body: string }[] = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => { received.push({ headers: req.headers, body }); res.writeHead(200, { "Content-Type": "application/json" }); res.end('{"ok":true}'); });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", () => r()));
  const port = (server.address() as AddressInfo).port;

  await page.goto("/register");
  await page.getByLabel("Full name").fill("Dev Owner");
  await page.getByLabel("Email").fill(`devs-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Dev Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);

  await page.goto("/admin/developers");
  await page.getByTestId("new-api-key").click();
  await page.getByLabel("Name").fill("Website");
  await page.getByLabel("branches:read").check();
  await page.getByTestId("create-api-key").click();
  const key = await page.getByTestId("secret-value").inputValue();
  expect(key).toMatch(/^ak_live_[0-9a-f]{8}_/);
  await page.getByRole("button", { name: "I have stored it safely" }).click();
  await expect(page.getByTestId("api-keys-table")).toContainText(key.slice(0, 16));

  const api = await page.context().browser()!.newContext();
  const ok = await api.request.get("/api/v1/branches", { headers: { Authorization: `Bearer ${key}` } });
  expect(ok.status()).toBe(200);
  expect((await api.request.get("/api/v1/users/me", { headers: { Authorization: `Bearer ${key}` } })).status()).toBe(403);

  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByTestId("api-keys-table")).toContainText("Revoked");
  expect((await api.request.get("/api/v1/branches", { headers: { Authorization: `Bearer ${key}` } })).status()).toBe(401);
  await api.close();

  await page.getByRole("tab", { name: "Webhooks" }).click();
  await page.getByTestId("new-webhook").click();
  await page.getByLabel("Name").fill("Local receiver");
  await page.getByLabel("URL").fill(`http://127.0.0.1:${port}/hook`);
  await page.getByTestId("create-webhook").click();
  const secret = await page.getByTestId("secret-value").inputValue();
  expect(secret).toMatch(/^whsec_/);
  await page.getByRole("button", { name: "I have stored it safely" }).click();
  await page.getByTestId("test-webhook").click();
  await expect(page.getByText(/Test delivered \(HTTP 200\)/)).toBeVisible();

  expect(received).toHaveLength(1);
  const { headers, body } = received[0];
  const parts = Object.fromEntries(String(headers["x-webhook-signature"]).split(",").map((p) => p.split("=")));
  const expected = crypto.createHmac("sha256", secret).update(`${parts.t}.`).update(body).digest("hex");
  expect(parts.v1).toBe(expected);
  expect(JSON.parse(body).type).toBe("ping");

  await page.getByRole("button", { name: "Deliveries" }).click();
  await expect(page.getByTestId("deliveries-table")).toContainText("delivered");
  await page.getByTestId("deliveries-table").getByRole("row").nth(1).click();
  await expect(page.getByTestId("delivery-detail")).toContainText('"type": "ping"');
  server.close();
});

test("developer docs: every guide renders, search and language choice work, pages pass accessibility checks", async ({ page }) => {
  test.setTimeout(120_000);
  const { audit, watch } = await import("./audit");
  const problems = await watch(page);
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Docs Reader");
  await page.getByLabel("Email").fill(`docs-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`Docs Clinic ${Date.now()}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.waitForURL(/\/admin$/);

  // Reachable from the menu and from the Developers screen.
  await page.getByRole("link", { name: "Developer docs" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Introduction" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Developer docs" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("link", { name: "Developers", exact: true })).not.toHaveAttribute("aria-current", "page");

  const nav = page.getByRole("navigation", { name: "Developer docs" });
  const titles = await nav.getByRole("link").allTextContents();
  expect(titles.length).toBeGreaterThanOrEqual(19);
  for (const title of titles) {
    await nav.getByRole("link", { name: title, exact: true }).click();
    await expect(page.locator("article h1")).toHaveText(title);
  }

  // Search narrows the menu.
  await page.getByTestId("docs-search").fill("hmac");
  await expect(nav.getByRole("link")).toHaveText(["Webhooks"]);
  await page.getByTestId("docs-search").fill("");

  // Examples use this site's address and the chosen language everywhere on the page.
  await page.goto("/admin/developers/docs/quickstart");
  const blocks = page.getByTestId("code-tabs");
  await expect(blocks.first().locator("pre")).toContainText(`${new URL(page.url()).origin}/api/v1/branches`);
  await blocks.first().getByRole("tab", { name: "Python" }).click();
  await expect(blocks.last().getByRole("tab", { name: "Python" })).toHaveAttribute("aria-selected", "true");
  await expect(blocks.last().locator("pre")).toContainText("requests.post(");
  await page.reload();
  await expect(blocks.first().getByRole("tab", { name: "Python" })).toHaveAttribute("aria-selected", "true");

  await page.goto("/admin/developers");
  await page.getByRole("tab", { name: "Docs" }).click();
  await page.getByTestId("docs-index").getByRole("link", { name: /Event reference/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Event reference" })).toBeVisible();
  await expect(page.getByText("payment.verified").first()).toBeVisible();

  for (const path of ["/admin/developers/docs/quickstart", "/admin/developers/docs/webhooks", "/admin/developers/docs/appointments"]) await audit(page, path, problems);
});
