import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Markdown, parseBlocks, safeHref } from "@/components/website/markdown";
import { bookHref, buttonHref, campaignParams, navHref, whatsappLink, type LinkContext } from "@/lib/site-links";
import type { SiteButton } from "@/types/website";

const ctx: LinkContext = { base: "/akshar-clinic", settings: { phone: "+91 98250 12345", whatsapp: "98250 12345", address: "CG Road, Ahmedabad", clinic_name: "Akshar" } };
const button = (over: Partial<SiteButton>): SiteButton => ({
  id: "b", label: "Go", kind: "book", url: "", page: "", phone: "", service: "", branch: "", message: "", style: "solid", color: "primary",
  custom_color: "", icon: "none", new_tab: false, visible: true, positions: [], ...over,
});

describe("website buttons", () => {
  it("builds each kind of link", () => {
    expect(buttonHref(button({ kind: "book", service: "consultation" }), ctx)?.href).toBe("/akshar-clinic/book?service=consultation");
    expect(buttonHref(button({ kind: "call" }), ctx)?.href).toBe("tel:+919825012345");
    expect(buttonHref(button({ kind: "whatsapp", message: "Hi there" }), ctx)?.href).toBe("https://wa.me/919825012345?text=Hi%20there");
    expect(buttonHref(button({ kind: "page", page: "our-story" }), ctx)?.href).toBe("/akshar-clinic/our-story");
    expect(buttonHref(button({ kind: "pdf", url: "/media/org/x/a.pdf" }), ctx)).toMatchObject({ href: "/media/org/x/a.pdf", newTab: true });
    expect(buttonHref(button({ kind: "maps" }), ctx)?.href).toContain("google.com/maps/search/?api=1&query=Akshar%20CG%20Road");
    expect(buttonHref(button({ kind: "contact" }), { ...ctx, sectionIds: { contact: "reach-us" } })?.href).toBe("/akshar-clinic#reach-us");
  });

  it("never produces script, data or plain-http links, and hides buttons that cannot work", () => {
    for (const url of ["javascript:alert(1)", "data:text/html,x", "http://example.com", "//evil.com", "https://ex ample.com", "/media/../secret"]) {
      expect(buttonHref(button({ kind: "url", url }), ctx)).toBeNull();
    }
    expect(buttonHref(button({ kind: "call" }), { ...ctx, settings: { ...ctx.settings, phone: "" } })).toBeNull();
    expect(buttonHref(button({ kind: "page", page: "../admin" }), ctx)).toBeNull();
    expect(bookHref("/c", { service: "<script>", branch: "main" })).toBe("/c/book?branch=main");
    expect(navHref({ label: "x", kind: "url", target: "javascript:alert(1)", new_tab: false }, "/c")).toBeNull();
    expect(navHref({ label: "x", kind: "section", target: "faq", new_tab: false }, "/c")?.href).toBe("/c#faq");
  });

  it("keeps only clean campaign parameters", () => {
    const params = new URLSearchParams("utm_source=Instagram&utm_campaign=diwali-2026&ref=<x>&price=1");
    expect(campaignParams(params)).toEqual({ utm_source: "instagram", utm_campaign: "diwali-2026" });
    expect(bookHref("/c", { service: "consultation" }, { utm_source: "shopify" })).toBe("/c/book?service=consultation&utm_source=shopify");
    expect(whatsappLink("+1 415 555 0100")).toBe("https://wa.me/14155550100");
  });
});

describe("markdown", () => {
  it("parses headings, paragraphs and lists", () => {
    expect(parseBlocks("## Title\nLine one\nline two\n\n- a\n- b\n1. c")).toEqual([
      { kind: "h2", text: "Title" }, { kind: "p", text: "Line one\nline two" }, { kind: "ul", items: ["a", "b"] }, { kind: "ol", items: ["c"] },
    ]);
  });

  it("renders text as text: no HTML, scripts or unsafe links", () => {
    const html = renderToStaticMarkup(<Markdown source={'<img src=x onerror=alert(1)> **bold** [ok](https://example.com) [bad](javascript:alert(1)) [tel](tel:+919825012345)'} />);
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain('href="https://example.com"');
    expect(html).not.toContain("javascript:");
    expect(html).toContain('href="tel:+919825012345"');
    expect(safeHref("/akshar-clinic/book")).toBe("/akshar-clinic/book");
    expect(safeHref("//evil.com")).toBeNull();
  });
});
