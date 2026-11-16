/**
 * Copy-paste code for putting the booking page on another website (a Shopify store or any HTML page).
 * Everything here is public: the code contains only the booking page address, never a key or secret.
 */
import { bookingUrl, type BookingParams } from "@/lib/booking-params";

/** A Liquid string literal. Values come from our own slugs, but quote-escape anyway. */
function liquidString(value: string): string {
  return `'${value.replace(/\\/g, "").replace(/'/g, "")}'`;
}

function htmlAttr(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** `{% render %}` call for the appointment-booking-button snippet, with the clinic's own values filled in. */
export function liquidButtonCode(origin: string, slug: string, hints: BookingParams = {}, label = "Book appointment", campaign: Record<string, string> = {}): string {
  const args: [string, string][] = [["booking_url", origin], ["clinic", slug]];
  if (hints.service) args.push(["service", hints.service]);
  if (hints.branch) args.push(["branch", hints.branch]);
  if (hints.doctor) args.push(["doctor", hints.doctor]);
  if (campaign.utm_source) args.push(["source", campaign.utm_source]);
  if (campaign.utm_campaign) args.push(["campaign", campaign.utm_campaign]);
  args.push(["label", label]);
  return `{% render 'appointment-booking-button',\n${args.map(([k, v]) => `  ${k}: ${liquidString(v)}`).join(",\n")}\n%}`;
}

/**
 * A responsive iframe plus a small listener that grows the frame to fit the booking page. The listener only accepts
 * messages from the booking site's own origin, and only the one message type the page sends.
 */
export function iframeEmbedCode(origin: string, slug: string, hints: BookingParams = {}, title = "Book an appointment", campaign: Record<string, string> = {}): string {
  const src = bookingUrl(origin, slug, hints, true, campaign);
  const bookingOrigin = new URL(origin).origin;
  const id = `appointment-booking-${slug}`;
  return [
    `<iframe id="${htmlAttr(id)}" src="${htmlAttr(src)}" title="${htmlAttr(title)}"`,
    `  style="display:block;width:100%;height:900px;border:0;border-radius:16px"`,
    `  loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>`,
    `<script>`,
    `  window.addEventListener("message", function (event) {`,
    `    if (event.origin !== ${JSON.stringify(bookingOrigin)} || !event.data || event.data.type !== "appointment-booking:resize") return;`,
    `    var h = parseInt(event.data.height, 10);`,
    `    if (h > 300 && h < 8000) document.getElementById(${JSON.stringify(id)}).style.height = h + "px";`,
    `  });`,
    `</script>`,
  ].join("\n");
}

/** Plain HTML link button for any website. */
export function htmlButtonCode(origin: string, slug: string, hints: BookingParams = {}, label = "Book appointment", campaign: Record<string, string> = {}): string {
  return `<a href="${htmlAttr(bookingUrl(origin, slug, hints, false, campaign))}" style="display:inline-block;padding:12px 24px;border-radius:999px;background:#0f5132;color:#fff;font-weight:600;text-decoration:none">${htmlAttr(label)}</a>`;
}

const ORIGIN = /^https:\/\/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+(?::\d{1,5})?$/;

/**
 * Turn what an admin typed ("mystore.com", "https://mystore.com/pages/book") into the origin the browser compares
 * against. Returns null for anything that is not an https website. The server validates again when saving.
 */
export function normalizeOrigin(input: string): string | null {
  let raw = input.trim().toLowerCase();
  if (!raw) return null;
  if (!/^[a-z]+:\/\//.test(raw)) raw = `https://${raw}`;
  try {
    const url = new URL(raw);
    const origin = `${url.protocol}//${url.host}`;
    return ORIGIN.test(origin) ? origin : null;
  } catch {
    return null;
  }
}

/** A WhatsApp share link: opens WhatsApp with a ready message containing the booking link (to send to patients). */
export function whatsappShareLink(message: string, link: string): string {
  return `https://wa.me/?text=${encodeURIComponent(`${message.trim()} ${link}`.trim())}`;
}

/** A small React component (no package to install) for React / Next.js websites: a link button, or the iframe. */
export function reactComponentCode(origin: string, slug: string, hints: BookingParams = {}, campaign: Record<string, string> = {}): string {
  const link = bookingUrl(origin, slug, hints, false, campaign);
  const embed = bookingUrl(origin, slug, hints, true, campaign);
  const bookingOrigin = new URL(origin).origin;
  return [
    `import { useEffect, useRef } from "react";`,
    ``,
    `// A plain link: works everywhere, opens the booking page.`,
    `export function BookAppointmentButton({ label = "Book appointment" }) {`,
    `  return (`,
    `    <a href=${JSON.stringify(link)} style={{ display: "inline-block", padding: "12px 24px", borderRadius: 999, background: "#0f5132", color: "#fff", fontWeight: 600, textDecoration: "none" }}>`,
    `      {label}`,
    `    </a>`,
    `  );`,
    `}`,
    ``,
    `// The booking page inside your site (add your website under Allowed websites first).`,
    `export function BookingWidget() {`,
    `  const frame = useRef(null);`,
    `  useEffect(() => {`,
    `    const onMessage = (event) => {`,
    `      if (event.origin !== ${JSON.stringify(bookingOrigin)} || event.data?.type !== "appointment-booking:resize") return;`,
    `      const h = parseInt(event.data.height, 10);`,
    `      if (frame.current && h > 300 && h < 8000) frame.current.style.height = h + "px";`,
    `    };`,
    `    window.addEventListener("message", onMessage);`,
    `    return () => window.removeEventListener("message", onMessage);`,
    `  }, []);`,
    `  return <iframe ref={frame} src=${JSON.stringify(embed)} title="Book an appointment" loading="lazy"`,
    `    style={{ display: "block", width: "100%", height: 900, border: 0, borderRadius: 16 }} />;`,
    `}`,
  ].join("\n");
}
