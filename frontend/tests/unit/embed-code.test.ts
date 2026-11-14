import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { htmlButtonCode, iframeEmbedCode, liquidButtonCode, normalizeOrigin } from "@/lib/embed-code";

describe("embed code", () => {
  it("fills the Liquid render call with the clinic's values", () => {
    const code = liquidButtonCode("https://booking.mydomain.com", "akshar-clinic", { service: "consultation", branch: "navrangpura" });
    expect(code).toBe(
      "{% render 'appointment-booking-button',\n  booking_url: 'https://booking.mydomain.com',\n  clinic: 'akshar-clinic',\n" +
      "  service: 'consultation',\n  branch: 'navrangpura',\n  label: 'Book appointment'\n%}",
    );
    expect(liquidButtonCode("https://b.example.com", "x", {}, "Don't 'break' me")).toContain("label: 'Dont break me'");
  });

  it("builds an iframe for the embed page whose resize listener trusts only the booking origin", () => {
    const code = iframeEmbedCode("https://booking.mydomain.com", "akshar-clinic", { doctor: "dr-meera-joshi" });
    expect(code).toContain('src="https://booking.mydomain.com/embed/akshar-clinic?doctor=dr-meera-joshi"');
    expect(code).toContain('event.origin !== "https://booking.mydomain.com"');
    expect(code).toContain('"appointment-booking:resize"');
    expect(code).not.toMatch(/secret|token|api[_-]?key/i);
  });

  it("escapes the label in the HTML button", () => {
    expect(htmlButtonCode("https://b.example.com", "x", {}, '<img onerror="x">')).toContain("&lt;img onerror=&quot;x&quot;&gt;");
  });

  it.each([
    ["mystore.com", "https://mystore.com"],
    ["https://MyStore.myshopify.com/pages/book?x=1", "https://mystore.myshopify.com"],
    ["  https://shop.example.in:8443/  ", "https://shop.example.in:8443"],
    ["http://mystore.com", null],
    ["javascript:alert(1)", null],
    ["https://*.example.com", null],
    ["localhost", null],
    ["", null],
  ])("normalizes %s", (input, expected) => {
    expect(normalizeOrigin(input)).toBe(expected);
  });

  it("serves the same Liquid files that live in integrations/shopify", () => {
    for (const file of ["snippets/appointment-booking-button.liquid", "sections/appointment-booking.liquid"]) {
      const source = readFileSync(resolve(__dirname, "../../../integrations/shopify", file), "utf8");
      const served = readFileSync(resolve(__dirname, "../../public/integrations/shopify", file.split("/")[1]), "utf8");
      expect(served, `${file} is out of date: copy it into frontend/public/integrations/shopify`).toBe(source);
    }
  });
});
