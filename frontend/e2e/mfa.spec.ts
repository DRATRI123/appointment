import crypto from "node:crypto";
import { expect, test } from "@playwright/test";

/** RFC 6238 code for a base32 secret, `offset` 30-second steps from now. */
function totp(secret: string, offset = 0): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/\s|=/g, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000) + offset));
  const mac = crypto.createHmac("sha1", key).update(counter).digest();
  const o = mac[mac.length - 1] & 0x0f;
  return String((mac.readUInt32BE(o) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

test("an administrator turns on two-step sign-in and then needs the authenticator code to sign in", async ({ page }) => {
  const email = `mfa-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Secure Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL(/\/onboarding/);

  await page.goto("/customer/profile");
  const card = page.getByTestId("two-step-card");
  await expect(card).toContainText("Off");
  await page.getByTestId("mfa-start").click();
  await expect(page.getByRole("img", { name: "QR code for your authenticator app" })).toBeVisible();
  const secret = (await page.getByTestId("mfa-secret").textContent())!.replace(/\s/g, "");
  await page.getByLabel("Code from the app").fill(totp(secret));
  await page.getByTestId("mfa-enable").click();
  await expect(page.getByTestId("recovery-codes").locator("li")).toHaveCount(10);
  await page.getByRole("button", { name: "I have saved them" }).click();
  await expect(card).toContainText("On");

  // Sign out and back in: the password alone is no longer enough.
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByRole("tab", { name: "Email & password" }).click();
  await page.locator("#email").fill(email);
  await page.locator("#password").fill("Str0ngPass123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("mfa-form")).toBeVisible();
  await page.getByLabel("Authenticator code").fill("000000");
  await page.getByRole("button", { name: "Verify & sign in" }).click();
  await expect(page.getByTestId("mfa-form")).toContainText("That code is not right");
  await page.getByLabel("Authenticator code").fill(totp(secret, 1)); // the next code: the set-up code cannot be reused
  await page.getByRole("button", { name: "Verify & sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
});
