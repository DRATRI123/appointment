"use client";

import Link from "next/link";
import { C, Callout, Checklist, CodeBlock, CodeTabs, DocLink, Endpoints, H2, H3, Lead, P, Request, Response, Steps, Table, UL, useDocsEnv } from "./ui";

export function PublicBookingPage() {
  const { slug } = useDocsEnv();
  const pub = `/public/organizations/${slug}`;
  return (
    <>
      <Lead>The clinic&apos;s own booking page is built only on these public endpoints. Use them to build your own patient app, kiosk or booking widget. They need <strong>no API key</strong>, are rate limited, and show only what any visitor may see.</Lead>
      <Callout kind="security" title="Safe to call from a browser or mobile app">
        Unlike API keys, these endpoints contain no secrets. The server still enforces everything: real prices, free slots, verification codes, no double booking and payment rules.
      </Callout>

      <H2 id="flow">The booking flow</H2>
      <CodeBlock label="Public booking flow" code={`GET  ${pub}                         clinic, branches, categories, settings
GET  ${pub}/services                catalogue (filter branch_id, category_id)
GET  ${pub}/professionals           doctors (filter branch_id, service_id)
GET  ${pub}/availability/summary    which days have free times
GET  ${pub}/availability            free times for one day
GET  ${pub}/quote                   price calculated by the server
POST ${pub}/holds                   reserve the time for a few minutes
GET  ${pub}/verification            which code channels the clinic offers
POST ${pub}/verification/start      send a one-time code (SMS, WhatsApp or email)
POST ${pub}/verification/{id}/verify  exchange the code for a verification token
POST ${pub}/appointments            book the held time with the token
GET  ${pub}/appointments/{ref}/payment          UPI QR and app links
POST ${pub}/appointments/{ref}/payment/submit   patient's UTR (never confirms payment)
GET  ${pub}/appointments/{ref}?access_token=…  booking status`} />

      <H2 id="hold">1 · Hold the time</H2>
      <P>Create one random <C>session_key</C> (8–64 characters) per visitor and send it with every call; it proves the hold is theirs.</P>
      <Request auth="none" title="Hold" method="POST" path={`${pub}/holds`} body={{ service_id: "63a0410f-…", branch_id: "b86b360f-…", professional_id: "bfe0259d-…", start_at: "2026-11-16T13:00:00Z", session_key: "web-6fa0cc0e5a644f0d" }} />
      <Response status={201} body={{ id: "d6ce41ac-9cba-4df1-88d7-0acd21a17a31", start_at: "2026-11-16T13:00:00Z", end_at: "2026-11-16T13:30:00Z", expires_at: "2026-11-16T12:31:17Z", session_key: "web-6fa0cc0e5a644f0d", status: "active" }} />

      <H2 id="verify">2 · Verify the patient&apos;s mobile or email</H2>
      <P>When the clinic requires it (the default), booking needs a verification token. The code is sent by the clinic&apos;s own SMS, WhatsApp Business or email provider and is never returned by the API.</P>
      <Request auth="none" title="Send a code" method="POST" path={`${pub}/verification/start`} body={{ channel: "sms", destination: "9876535433", hold_id: "d6ce41ac-…", session_key: "web-6fa0cc0e5a644f0d" }} />
      <Response status={200} body={{ challenge_id: "b86bd47e-24ee-4f22-bc20-501cc84b6d9d", channel: "sms", destination: "+91•••••433", code_length: 6, expires_in_seconds: 299, resend_after_seconds: 59, resends_left: 3 }} />
      <Request auth="none" title="Check the code" method="POST" path={`${pub}/verification/b86bd47e-…/verify`} body={{ code: "123456", session_key: "web-6fa0cc0e5a644f0d" }} />
      <Response status={200} body={{ verification_token: "eyJhbGciOiJIUzI1NiIs…", channel: "sms", destination: "+919876535433", expires_in_seconds: 1800 }} />
      <P>The token only works for this clinic, this hold, this session and exactly this mobile or email, for 30 minutes.</P>

      <H2 id="book">3 · Book</H2>
      <Request auth="none" title="Book" method="POST" path={`${pub}/appointments`} body={{ hold_id: "d6ce41ac-…", session_key: "web-6fa0cc0e5a644f0d", customer: { full_name: "Priya Shah", mobile: "+919876535433" }, verification_token: "eyJhbGciOiJIUzI1NiIs…", attribution: { utm_source: "instagram", utm_campaign: "diwali" } }} />
      <P>The response includes the booking <C>reference</C> and a one-time <C>access_token</C>. Keep both: they open the patient&apos;s status and payment page (<C>/{slug}/appointments/&lt;reference&gt;?t=&lt;access_token&gt;</C>). Never put them in analytics or share them.</P>

      <H2 id="errors">Errors you should handle</H2>
      <Table head={["code", "What to show"]} rows={[
        ["slot_unavailable (409)", "“Sorry, that time was just taken.” Reload times."],
        ["hold_expired (409)", "“Your reserved time ran out.” Let them pick again."],
        ["contact_not_verified (422)", "Ask for the code."],
        ["otp_incorrect (401)", <><C>detail</C> says how many attempts are left.</>],
        ["otp_cooldown / otp_*_limit (429)", "Wait before sending another code."],
        ["otp_delivery_failed (503)", "Offer another channel (WhatsApp or email)."],
      ]} />
      <P>Full request and response examples for every public endpoint are in <C>documentation/public-booking-api.md</C> in the code repository.</P>
    </>
  );
}

export function EmbedPage() {
  const { base, slug } = useDocsEnv();
  const site = base.replace(/\/api\/v1$/, "");
  return (
    <>
      <Lead>Add booking to any website, Shopify store, Instagram bio, Google Business profile or WhatsApp message, without writing code and without any secret. The admin screen <Link className="underline" href="/admin/booking-page">Booking page &amp; Shopify</Link> builds all of these for you.</Lead>

      <H2 id="links">Booking links</H2>
      <CodeBlock label="Booking URLs" code={`${site}/${slug}                       clinic website
${site}/${slug}/book                  booking
${site}/${slug}/book?service=consultation
${site}/${slug}/book?branch=navrangpura&doctor=dr-kavya-shah
${site}/${slug}/book?service=consultation&date=2026-11-20
${site}/${slug}/book?utm_source=instagram&utm_campaign=diwali
${site}/embed/${slug}                 the same flow without header and footer, for iframes`} />
      <Table head={["Parameter", "Accepts", "Effect"]} rows={[
        ["service", "service slug or id", "Opens with that service chosen"],
        ["branch (or location)", "branch slug or id", "Opens with that location chosen"],
        ["doctor (or professional)", "doctor slug or id", "Opens on that doctor's page"],
        ["date", "YYYY-MM-DD", "Opens the calendar on that day"],
        ["utm_source, utm_medium, utm_campaign, utm_content, utm_term, ref", "lower-case labels", "Counted in Website analytics and stored on the booking"],
      ]} />
      <Callout kind="security" title="Parameters are only hints">
        An unknown value is ignored and the visitor chooses. Parameters can never change a price, a permission or who the patient is. <C>price=</C>, <C>amount=</C> or <C>discount=</C> are simply ignored.
      </Callout>

      <H2 id="iframe">Iframe embed</H2>
      <Steps items={[
        { title: "Allow your website", body: <>In <Link className="underline" href="/admin/booking-page">Booking page &amp; Shopify → Allowed websites</Link>, add every exact address your site is visited on (e.g. <C>https://www.myclinic.in</C> and <C>https://myclinic.in</C>). Only <C>https://</C>, no wildcards, up to 20.</> },
        { title: "Paste the code", body: "Paste this where the booking should appear." },
      ]} />
      <CodeBlock label="Iframe code" code={`<iframe id="appointment-booking" src="${site}/embed/${slug}" title="Book an appointment"
  style="display:block;width:100%;height:900px;border:0;border-radius:16px"
  loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>
<script>
  window.addEventListener("message", function (event) {
    if (event.origin !== "${site}" || !event.data || event.data.type !== "appointment-booking:resize") return;
    var h = parseInt(event.data.height, 10);
    if (h > 300 && h < 8000) document.getElementById("appointment-booking").style.height = h + "px";
  });
</script>`} />
      <P>The page sends <C>{"{ type: \"appointment-booking:resize\", height }"}</C> when its height changes, so the frame grows with the content. Sites not on the allowed list cannot frame the page at all (protection against click-jacking and look-alike sites).</P>

      <H2 id="shopify">Shopify</H2>
      <P>No Shopify app or API key is needed. Use a Book button snippet, a theme section (button or embedded) or a plain link in your navigation. The snippet and section files and step-by-step instructions are on the <Link className="underline" href="/admin/booking-page">Booking page &amp; Shopify</Link> screen and in <C>documentation/shopify-integration.md</C>.</P>
      <CodeBlock label="Shopify snippet" code={`{% render 'appointment-booking-button',
  booking_url: '${site}',
  clinic: '${slug}',
  service: product.metafields.custom.booking_service,
  source: 'shopify',
  label: 'Book a consultation'
%}`} />

      <H2 id="whatsapp">WhatsApp, QR codes and social</H2>
      <UL>
        <li>Share the <C>/book</C> link with <C>utm_source=whatsapp</C> in your WhatsApp Business catalogue or replies, so you can see in Website analytics how many bookings it brought.</li>
        <li>Print a QR code of the link at reception: patients scan it to book their follow-up.</li>
        <li>Use <C>utm_source=instagram</C>, <C>google</C>, <C>facebook</C> in bio and profile links.</li>
      </UL>
    </>
  );
}

export function RecipesPage() {
  return (
    <>
      <Lead>Complete patterns for the most common integrations.</Lead>

      <H2 id="crm">Sync bookings to a CRM or spreadsheet</H2>
      <Steps items={[
        { title: "Subscribe", body: <>Webhook endpoint for <C>appointment.*</C> and <C>payment.verified</C>.</> },
        { title: "Upsert by id", body: <>For every event, create or update the CRM record keyed by <C>data.id</C> (store <C>data.reference</C> for people). Skip event ids you have already processed.</> },
        { title: "Contact", body: <>Match or create the contact by <C>data.customer.mobile</C> (international format) or <C>data.customer.id</C>.</> },
        { title: "Safety net", body: <>Every night, list yesterday&apos;s appointments with <C>GET /appointments?from_at&amp;to_at</C> and fix differences.</> },
      ]} />
      <CodeTabs label="CRM sync worker" samples={[{ lang: "python", title: "Python", code: `def handle(event):
    a = event["data"]
    if event["type"].startswith("appointment."):
        crm.upsert_deal(
            external_id=a["id"],
            title=f'{a["service"]["name"]} – {a["customer"]["name"]}',
            stage=a["status"],                     # pending_payment, confirmed, completed…
            start=a["start_at"],
            doctor=a["professional"]["name"],
            amount=a["amounts"]["total_paise"] / 100,
            contact={"phone": a["customer"]["mobile"], "email": a["customer"]["email"]},
        )
    elif event["type"] == "payment.verified":
        crm.mark_paid(external_id=a["appointment"]["id"], amount=a["verified_amount_paise"] / 100, utr=a["utr"])` }]} />

      <H2 id="no-code">Zapier, Make, n8n and other no-code tools</H2>
      <P>Create a “catch webhook” trigger in the tool, add the URL it gives you as a webhook endpoint, and press <strong>Send test</strong> so the tool learns the fields. Many no-code tools cannot check signatures, so:</P>
      <UL>
        <li>keep the catch-hook URL private (it is the only protection),</li>
        <li>treat the event as a notification, and for anything important (a payment) confirm it with an API call, e.g. <C>GET /payments/&#123;id&#125;</C> with a read-only key,</li>
        <li>in n8n you can verify the signature with a Crypto node (HMAC-SHA256 of <C>t + &quot;.&quot; + raw body</C>).</li>
      </UL>

      <H2 id="call-centre">Book from a call centre or partner system</H2>
      <Steps items={[
        { title: "Show free times", body: <><C>GET /availability</C> for the service and branch; leave out the doctor for “anyone available”.</> },
        { title: "Hold while talking", body: <><C>POST /appointments/holds</C> as soon as the caller picks a time.</> },
        { title: "Book", body: <><C>POST /appointments</C> with <C>hold_id</C>, the customer and <C>source: &quot;api&quot;</C>. On <C>409</C>, offer the next free time.</> },
        { title: "Tell the patient", body: "The clinic's own notifications (SMS / WhatsApp / email, as configured) go out automatically, including the payment link if an advance is due." },
      ]} />

      <H2 id="accounting">Daily numbers to accounting or BI</H2>
      <P>Once a day, with a key that has <C>reports:read</C> and <C>payments:read</C>, fetch <C>/reports/daily_summary</C> and <C>/reports/payments</C> for yesterday, and write the rows to your sheet or warehouse. Amounts are in paise. Only <C>verified</C> payments count as money received.</P>

      <H2 id="reminders">Your own reminders or follow-ups</H2>
      <P>Listen for <C>appointment.completed</C> and schedule a follow-up message or feedback request in your own tool; listen for <C>appointment.no_show</C> to trigger a “we missed you, book again” message with a booking link. Respect the patient&apos;s consent and communication preferences.</P>
    </>
  );
}

export function GoLivePage() {
  return (
    <>
      <Lead>Check these before connecting a real system, and use the troubleshooting table when something goes wrong.</Lead>
      <H2 id="checklist">Go-live checklist</H2>
      <Checklist items={[
        <>One key per system, named after it, with only the scopes it needs.</>,
        <>Keys and webhook secrets live in server environment variables or a secret manager, never in code, a browser, a mobile app or a theme.</>,
        <>Allowed IPs set on production keys; expiry set on keys for contractors.</>,
        <>Webhook receiver checks the signature on the raw body, rejects old timestamps and skips repeated <C>X-Webhook-Id</C>s.</>,
        <>Receiver answers within 10 seconds and processes in the background.</>,
        <>Code handles <C>409 slot_unavailable</C>, <C>429</C> with <C>Retry-After</C>, and <C>5xx</C> with backoff.</>,
        <>Amounts are shown from paise; times are shown in the clinic&apos;s time zone.</>,
        <>Only <C>payment.verified</C> / status <C>verified</C> is treated as paid.</>,
        <>A nightly reconciliation job compares your data with <C>GET /appointments</C>.</>,
        <>Someone owns the integration: they watch key usage and webhook failures in Developers.</>,
      ]} />

      <H2 id="troubleshooting">Troubleshooting</H2>
      <Table head={["Problem", "Fix"]} mono={[]} rows={[
        [<C key="1">401 invalid_api_key</C>, "Key copied wrongly, expired or revoked. Check for spaces or line breaks in the environment variable."],
        [<C key="2">403 permission_denied</C>, <>The <C>detail</C> names the missing scope. Create a key with it (you can&apos;t add scopes to an existing key).</>],
        [<C key="3">403 api_key_not_allowed</C>, "That action is staff-only (payments, settings…). Do it in the admin."],
        [<C key="4">403 ip_not_allowed</C>, "Your server's outbound IP changed. Add it to the key."],
        [<C key="5">409 slot_unavailable</C>, "Normal: someone else took the time. Fetch availability again."],
        [<C key="6">429 rate_limited</C>, "Spread requests out, cache catalogue data, or raise the key's limit."],
        ["Webhook signature never matches", "You verified parsed/re-serialised JSON, or used the wrong secret (after rotation). Use the raw body."],
        ["Webhooks stopped", "The endpoint was auto-paused after repeated failures. Fix the receiver, press Resume, then Resend the missed deliveries from the log."],
        ["Webhook shows HTTP 3xx", "Redirects are not followed. Use the final https:// URL."],
        ["Iframe is blank / refused", "Add the exact site address (with or without www.) to Allowed websites and reload after a minute."],
        ["Times look wrong by hours", <>You displayed UTC. Convert using the <C>timezone</C> field.</>],
      ]} />
      <H3>Getting help</H3>
      <P>Send the <C>request_id</C> from the error (or <C>X-Request-ID</C> header), the time and the endpoint to your platform administrator. Never send the API key itself.</P>
    </>
  );
}

export function AdminApiPage() {
  return (
    <>
      <Lead>Endpoints for managing keys and webhooks. They are used by the Developers screen and need a signed-in staff member with the <C>api_keys:manage</C> permission. An API key can never call them, so a leaked key cannot create more keys.</Lead>
      <Endpoints rows={[
        ["GET", "/developers/scopes", "api_keys:manage", "Scope catalogue and whether you hold each permission."],
        ["GET / POST", "/developers/api-keys", "api_keys:manage", <>Create with <C>{"{name, scopes, expires_at?, allowed_ips?, rate_limit_per_minute?}"}</C>; the key is returned once. Up to 25 active keys.</>],
        ["GET", "/developers/api-keys/{id}/usage?days=30", "api_keys:manage", "Daily requests, client errors, server errors, rate-limited."],
        ["DELETE", "/developers/api-keys/{id}", "api_keys:manage", "Revoke immediately."],
        ["GET / POST", "/developers/webhooks", "api_keys:manage", <>Create with <C>{"{name, url, events}"}</C> (<C>[&quot;*&quot;]</C> for all); the secret is returned once.</>],
        ["PATCH / DELETE", "/developers/webhooks/{id}", "api_keys:manage", "Change URL or events, pause / resume, delete."],
        ["POST", "/developers/webhooks/{id}/rotate-secret", "api_keys:manage", "New secret, returned once."],
        ["POST", "/developers/webhooks/{id}/test", "api_keys:manage", "Send a signed ping now."],
        ["GET", "/developers/webhooks/{id}/deliveries", "api_keys:manage", <>Delivery log, filter <C>status</C>.</>],
        ["GET / POST", "/developers/deliveries/{id} · /redeliver", "api_keys:manage", "Payload and response; send again."],
        ["GET", "/developers/events", "api_keys:manage", "Event catalogue with example payloads."],
      ]} />
      <P>Every key and webhook change is recorded in the <Link className="underline" href="/admin/audit-logs">audit log</Link> with who did it and when.</P>
      <Callout>See <DocLink page="authentication">Authentication</DocLink> for how scopes combine with the creator&apos;s role.</Callout>
    </>
  );
}
