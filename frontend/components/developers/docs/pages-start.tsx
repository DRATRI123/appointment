"use client";

import Link from "next/link";
import { CalendarCheck, Code2, Globe, Webhook } from "lucide-react";
import { C, Callout, CodeBlock, DocLink, H2, H3, Lead, P, Request, Response, Steps, Table, UL, docHref, useDocsEnv } from "./ui";

const SCOPES: [string, string, string][] = [
  ["appointments:read", "Read appointments, the calendar, availability and the waitlist", "/appointments, /availability, /waitlist"],
  ["appointments:write", "Create, reschedule and cancel appointments; place and release holds", "/appointments, /appointments/holds"],
  ["appointments:checkin", "Check in, start, complete and mark no-show", "/appointments/{id}/status"],
  ["customers:read", "Read customers and their family members", "/customers"],
  ["customers:write", "Create and update customers", "/customers"],
  ["services:read", "Read services, categories and packages", "/services, /service-categories, /service-packages"],
  ["branches:read", "Read branches (locations)", "/branches"],
  ["professionals:read", "Read doctors and their weekly schedules", "/professionals, /schedules"],
  ["payments:read", "Read payment status. Never record or verify payments", "/payments"],
  ["booking_forms:read", "Read booking forms and answers", "/booking-forms"],
  ["reports:read", "Read the dashboard and report previews", "/analytics, /reports"],
];

export function OverviewPage() {
  const cards = [
    { icon: Code2, title: "REST API", body: "Read and change appointments, customers and your catalogue from your own server.", page: "quickstart" },
    { icon: Webhook, title: "Webhooks", body: "Get a signed HTTPS call the moment a booking is made, changed, paid or cancelled.", page: "webhooks" },
    { icon: CalendarCheck, title: "Public booking API", body: "Build your own booking app or kiosk on the same endpoints as the booking page. No key needed.", page: "public-booking" },
    { icon: Globe, title: "Links, embed & Shopify", body: "Put booking on any website with a link, a button or an iframe. No code on your side.", page: "embed" },
  ];
  return (
    <>
      <Lead>Everything you need to connect your website, app, CRM, accounting or automation tools to your clinic&apos;s appointment system. Start with the quickstart; it takes about five minutes.</Lead>
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {cards.map((c) => (
          <Link key={c.page} href={docHref(c.page)} className="group rounded-xl border bg-card p-4 transition-colors hover:border-primary">
            <c.icon className="size-5 text-primary" aria-hidden />
            <p className="mt-3 font-semibold group-hover:text-primary">{c.title}</p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">{c.body}</p>
          </Link>
        ))}
      </div>

      <H2 id="which">Which option do I need?</H2>
      <Table head={["I want to…", "Use", "Guide"]} mono={[]} rows={[
        ["Add a “Book appointment” button to my website or Shopify store", "Booking link or iframe", <DocLink key="1" page="embed">Links, embed & Shopify</DocLink>],
        ["Show new bookings in my CRM, Google Sheet or WhatsApp tool", "Webhooks (+ API to read more)", <DocLink key="2" page="recipes" anchor="crm">Recipe: sync to a CRM</DocLink>],
        ["Book appointments from my own system (call centre, partner app)", "REST API with an API key", <DocLink key="3" page="appointments">Appointments</DocLink>],
        ["Build my own patient app or kiosk", "Public booking API", <DocLink key="4" page="public-booking">Public booking API</DocLink>],
        ["Pull daily numbers into accounting or BI", "Reports API", <DocLink key="5" page="reports">Reports & analytics</DocLink>],
      ]} />

      <H2 id="basics">The basics</H2>
      <UL>
        <li>Base URL: <C>{useDocsEnv().base}</C>. All requests use HTTPS and JSON.</li>
        <li>Authenticate with an API key: <C>Authorization: Bearer ak_live_…</C>. Create keys under <Link className="underline" href="/admin/developers">Developers → API keys</Link>.</li>
        <li>Money is in <strong>paise</strong> (integers): <C>80000</C> = ₹800.00. Times are ISO 8601 in UTC; show them in the clinic&apos;s <C>timezone</C>.</li>
        <li>IDs are opaque strings (UUIDs). Store them as text.</li>
        <li>The full machine-readable reference is at <a className="underline" href="/docs" target="_blank" rel="noreferrer">/docs</a> (Swagger UI) and <C>/api/v1/openapi.json</C>.</li>
      </UL>

      <H2 id="safety">What the API will never do</H2>
      <P>These rules are enforced on the server for every caller, so a bug or a leaked key cannot break them:</P>
      <UL>
        <li><strong>No double booking.</strong> Two requests for the same slot: exactly one wins, the other gets <C>409 slot_unavailable</C>.</li>
        <li><strong>Prices come from the server.</strong> Any amount you send is ignored; the price is calculated from your catalogue.</li>
        <li><strong>An API key can never mark money as received.</strong> Recording, verifying and refunding payments is only possible for signed-in staff who checked the bank.</li>
        <li><strong>One clinic per key.</strong> A key cannot read or change another organization&apos;s data.</li>
        <li><strong>No clinical data.</strong> Notes, documents and form uploads are not available to API keys or in webhooks.</li>
      </UL>
    </>
  );
}

export function QuickstartPage() {
  return (
    <>
      <Lead>Make your first real booking through the API in five steps. Run the examples in a terminal; switch the language tabs for Python, Node.js or PHP.</Lead>
      <Steps items={[
        { title: "Create an API key", body: <>Go to <Link className="underline" href="/admin/developers">Developers → API keys → New key</Link>. Name it after the system that will use it (e.g. “Call centre CRM”), tick <C>branches:read</C>, <C>services:read</C>, <C>professionals:read</C>, <C>appointments:read</C> and <C>appointments:write</C>, then copy the key. It is shown <strong>only once</strong>.</> },
        { title: "Keep it in an environment variable", body: <>Never paste the key into website code, a mobile app or a Git repository. On your server: <C>export API_KEY=&quot;ak_live_…&quot;</C></> },
        { title: "List branches, services and doctors", body: "You need their ids for availability and booking." },
        { title: "Find a free time", body: "Ask for the free times of one day." },
        { title: "Book it", body: "Send the slot and the customer. You get the appointment back with its reference and price." },
      ]} />

      <H2 id="step-3">Step 3 · Read your catalogue</H2>
      <Request title="List branches" method="GET" path="/branches" />
      <Response status={200} body={[{ id: "b86b360f-c60c-4bdd-8bb3-7012be151195", name: "Navrangpura", slug: "navrangpura", code: "NAV", phone: "+91 98250 12345", is_active: true, is_default: true, "…": "…" }]} />
      <Request title="List services" method="GET" path="/services" />
      <Response status={200} body={[{ id: "63a0410f-0674-4101-ab1c-a9fe0ceac452", name: "Ayurvedic Consultation", slug: "consultation", duration_minutes: 30, price_paise: 80000, payment_mode: "full_advance", professional_ids: ["bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae"], "…": "…" }]} />
      <Request title="Doctors who offer that service" method="GET" path="/professionals" query={{ service_id: "63a0410f-0674-4101-ab1c-a9fe0ceac452" }} />

      <H2 id="step-4">Step 4 · Find a free time</H2>
      <Request title="Free times on one day" method="GET" path="/availability" query={{ service_id: "63a0410f-0674-4101-ab1c-a9fe0ceac452", branch_id: "b86b360f-c60c-4bdd-8bb3-7012be151195", professional_id: "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae", date: "2026-11-20" }} />
      <Response status={200} body={{ date: "2026-11-20", timezone: "Asia/Kolkata", duration_minutes: 30, professionals: [{ professional_id: "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae", display_name: "Dr. Kavya Shah", slots: [{ start_at: "2026-11-20T04:00:00Z", end_at: "2026-11-20T04:30:00Z", remaining: 1 }, { start_at: "2026-11-20T04:30:00Z", end_at: "2026-11-20T05:00:00Z", remaining: 1 }] }] }} note="04:00Z is 9:30 am in Asia/Kolkata" />

      <H2 id="step-5">Step 5 · Book</H2>
      <Request title="Create an appointment" method="POST" path="/appointments" body={{ professional_id: "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae", branch_id: "b86b360f-c60c-4bdd-8bb3-7012be151195", service_id: "63a0410f-0674-4101-ab1c-a9fe0ceac452", start_at: "2026-11-20T05:30:00Z", customer: { full_name: "Asha Patel", mobile: "9812345678" }, source: "api" }} />
      <Response status={201} body={{ id: "e1df655e-961b-4323-a8ac-c990cbb658e3", reference: "APT-AKSHAR-01M7F8J748S8VJ5620QZ3YNMKW", status: "pending_payment", source: "api", service_name: "Ayurvedic Consultation", professional_name: "Dr. Kavya Shah", branch_name: "Navrangpura", customer: { id: "59b37f80-…", full_name: "Asha Patel", mobile: "+919812345678" }, start_at: "2026-11-20T05:30:00Z", end_at: "2026-11-20T06:00:00Z", timezone: "Asia/Kolkata", total_amount_paise: 80000, advance_due_paise: 80000, paid_amount_paise: 0, payment_due_at: "2026-11-15T09:58:10Z", "…": "…" }} />
      <P>Send the same request again and you get <C>409</C> with <C>{"\"code\": \"slot_unavailable\""}</C>: the slot is taken. That is the double-booking protection at work.</P>
      <Callout title="Next steps">
        Subscribe to <DocLink page="webhooks">webhooks</DocLink> so your system hears about bookings made on the website or at reception, read <DocLink page="errors">errors</DocLink> to handle failures properly, and go through the <DocLink page="go-live">go-live checklist</DocLink> before using it with real patients.
      </Callout>
    </>
  );
}

export function AuthenticationPage() {
  return (
    <>
      <Lead>API keys let a server act for your clinic. A key belongs to one organization, carries a set of scopes, and can be limited by IP address, expiry date and request rate.</Lead>

      <H2 id="sending">Sending the key</H2>
      <P>Use either header. Both are equivalent:</P>
      <CodeBlock label="Key headers" code={`Authorization: Bearer ak_live_0fc99b87_…\nX-API-Key: ak_live_0fc99b87_…`} />
      <UL>
        <li>The key already knows its organization. You do not need <C>X-Organization-Id</C>; if you send a different one you get <C>403 wrong_organization</C>.</li>
        <li>Keys look like <C>ak_live_&lt;8-character id&gt;_&lt;secret&gt;</C>. The id part (the <em>prefix</em>) is shown in the admin so you can tell keys apart; the secret is never shown again.</li>
        <li>Only a salted hash of the key is stored. If you lose a key, revoke it and create a new one.</li>
      </UL>

      <H2 id="scopes">Scopes</H2>
      <P>Give each key only the scopes it needs. A call outside the key&apos;s scopes returns <C>403 permission_denied</C> with the missing scope in <C>detail</C>.</P>
      <Table head={["Scope", "Allows", "Endpoints"]} mono={[0]} rows={SCOPES.map(([s, a, e]) => [s, a, <span key={s} className="font-mono text-xs text-muted-foreground">{e}</span>])} />
      <Callout kind="security" title="A key is never more powerful than the person who created it">
        What a key can do = its scopes <strong>∩</strong> the creator&apos;s current role permissions. If the creator&apos;s role loses a permission, their keys lose it too. If the creator is removed from the clinic, the key stops working (<C>401 api_key_owner_removed</C>). Create integration keys from a long-lived owner or administrator account.
      </Callout>

      <H2 id="not-available">What keys cannot reach</H2>
      <P>Keys only work on these API areas: appointments, availability, waitlist, branches, professionals, schedules, services, service categories and packages, customers, payments (read), booking forms, reports and analytics. Everything else answers <C>403 api_key_not_allowed</C>, including:</P>
      <UL>
        <li>recording, verifying or rejecting payments, refunds and bank reconciliation;</li>
        <li>UPI accounts, staff, roles, organization settings, website, integrations;</li>
        <li>creating or managing API keys and webhooks;</li>
        <li>clinical notes and documents (customers&apos; private medical files).</li>
      </UL>

      <H2 id="limits">IP allow-list, expiry and rate limit</H2>
      <Table head={["Setting", "How it works"]} mono={[]} rows={[
        ["Allowed IPs", <>Optional list of IP addresses or CIDR ranges, e.g. <C>203.0.113.10</C> or <C>203.0.113.0/24</C>. Calls from anywhere else get <C>403 ip_not_allowed</C>. Recommended for every production key.</>],
        ["Expiry", <>Optional date. After it the key returns <C>401 invalid_api_key</C>. Use it for contractors and short projects.</>],
        ["Rate limit", <>Requests per minute per key, default <strong>120</strong>, adjustable from 1 to 1,200. Over the limit you get <C>429 rate_limited</C> with a <C>Retry-After</C> header (seconds).</>],
        ["Usage", "Each key shows daily requests, client errors, server errors and rate-limited calls in the admin, so you can spot a broken integration."],
      ]} />

      <H2 id="rotate">Rotating a key without downtime</H2>
      <Steps items={[
        { title: "Create a second key", body: "Same scopes and IP list as the old one." },
        { title: "Deploy it", body: "Update the environment variable on your server and restart." },
        { title: "Watch usage", body: "The new key's usage should rise and the old key's “last used” stop changing." },
        { title: "Revoke the old key", body: "Revoking takes effect immediately." },
      ]} />

      <H2 id="never-browser">Never put a key in a browser or app</H2>
      <Callout kind="warning" title="Keys are server-side secrets">
        Anything shipped to a browser, a mobile app, a Shopify theme or a WordPress page can be read by anyone. For a booking experience in the browser use the <DocLink page="public-booking">public booking API</DocLink> (no key) or the <DocLink page="embed">booking link / iframe</DocLink>. If a key leaks, revoke it at once under Developers → API keys; every create and revoke is written to the audit log.
      </Callout>
    </>
  );
}

export function ConventionsPage() {
  return (
    <>
      <Lead>Rules that apply to every endpoint.</Lead>
      <H2 id="format">Requests and responses</H2>
      <UL>
        <li>Send JSON with <C>Content-Type: application/json</C>. Responses are JSON.</li>
        <li>Unknown fields in a request are ignored; missing or invalid ones return <C>422 validation_failed</C> with an <C>errors</C> list.</li>
        <li>Every response has an <C>X-Request-ID</C> header (also in error bodies as <C>request_id</C>). Log it; support can find your exact request with it.</li>
      </UL>

      <H2 id="ids">IDs and references</H2>
      <P>Every object has an <C>id</C> (UUID string). Appointments, payments and refunds also have a human <C>reference</C> such as <C>APT-AKSHAR-01M7F8J7…</C> that staff and patients see. Use the id in API calls; show the reference to people.</P>

      <H2 id="time">Dates and times</H2>
      <UL>
        <li>Timestamps are ISO 8601. Responses use UTC (<C>2026-11-20T05:30:00Z</C>).</li>
        <li>You may send any offset: <C>2026-11-20T11:00:00+05:30</C> and <C>2026-11-20T05:30:00Z</C> are the same moment.</li>
        <li>Plain dates (<C>date=2026-11-20</C>, <C>from_date</C>) are in the clinic&apos;s time zone, returned as <C>timezone</C> (for example <C>Asia/Kolkata</C>).</li>
        <li>Always book a <C>start_at</C> that came from <DocLink page="availability">availability</DocLink>; other times are rejected.</li>
      </UL>

      <H2 id="money">Money</H2>
      <P>All amounts are integers in <strong>paise</strong> with a <C>currency</C> (INR). <C>80000</C> = ₹800.00. Divide by 100 only when displaying. The server always calculates prices, discounts, tax and the advance due; amounts you send in requests are ignored.</P>

      <H2 id="pagination">Lists and pagination</H2>
      <P>Large lists (customers, payments, webhook deliveries) are paged:</P>
      <CodeBlock label="Paged list" code={`GET /customers?page=2&page_size=50\n\n{\n  "data": [ … ],\n  "meta": { "page": 2, "page_size": 50, "total": 318 }\n}`} />
      <P>Keep requesting the next page while <C>page × page_size &lt; total</C>. Other lists (branches, services, professionals) return a plain array. Appointments are filtered by a time window instead: <C>from_at</C> and <C>to_at</C>.</P>

      <H2 id="versioning">Versioning</H2>
      <P>The API path is versioned (<C>/api/v1</C>). New fields may be added to responses at any time, so ignore fields you don&apos;t know. Webhooks carry an <C>api_version</C> (currently <C>2026-11</C>); a change that could break receivers will get a new version.</P>

      <H2 id="retries">Retrying safely</H2>
      <UL>
        <li>GET requests can always be retried.</li>
        <li>For POST <C>/appointments</C>: if a call times out, don&apos;t blindly repeat it. First list appointments for that customer and time (<C>GET /appointments?from_at=…&amp;to_at=…&amp;search=&lt;mobile&gt;</C>); if it&apos;s there, the first call worked. A repeat for the same slot cannot create a second booking anyway; it returns <C>409 slot_unavailable</C>.</li>
        <li>On <C>429</C> wait for <C>Retry-After</C> seconds. On <C>5xx</C> retry with exponential backoff (1 s, 2 s, 4 s… up to a minute).</li>
      </UL>
    </>
  );
}

const ERRORS: [string, string, string, string][] = [
  ["400", "bad_request", "The request can't be processed as sent.", "Check the body against the reference."],
  ["401", "invalid_api_key", "Key unknown, expired or revoked.", "Check the environment variable; create a new key if needed."],
  ["401", "api_key_owner_removed", "The person who created the key left the clinic.", "Create a new key from a current administrator."],
  ["403", "api_key_not_allowed", "Keys can't call this endpoint (payments verification, settings…).", "Do this in the admin instead."],
  ["403", "permission_denied", "The key lacks a scope (named in detail).", "Create a key with that scope."],
  ["403", "ip_not_allowed", "Call came from an IP outside the key's allow-list.", "Add your server's outbound IP to the key."],
  ["403", "wrong_organization", "X-Organization-Id names another clinic.", "Remove the header; keys know their clinic."],
  ["404", "not_found", "No such object in this clinic.", "Check the id; it may belong to another clinic or be deleted."],
  ["409", "slot_unavailable", "Someone else booked or is holding that time.", "Fetch availability again and pick another slot."],
  ["409", "invalid_transition", "Status change not allowed (e.g. complete a cancelled visit).", "Read the appointment's status first."],
  ["409", "hold_expired", "The hold ran out before booking.", "Place a new hold."],
  ["409", "plan_limit", "The clinic's plan limit was reached.", "Upgrade the plan or remove unused items."],
  ["422", "validation_failed", "A field is missing or invalid; see errors[].", "Fix the fields listed."],
  ["422", "form_invalid", "Booking-form answers failed validation.", "Read errors[] per field."],
  ["422", "coupon_invalid", "The coupon can't be used.", "Book without it or ask the clinic."],
  ["429", "rate_limited", "Too many requests for this key.", "Wait Retry-After seconds; spread requests out."],
  ["500", "internal_error", "Something failed on our side.", "Retry with backoff; send the request_id to support."],
];

export function ErrorsPage() {
  return (
    <>
      <Lead>Errors use normal HTTP status codes and a stable machine-readable <C>code</C>. Branch on <C>code</C>, show <C>detail</C> to people.</Lead>
      <H2 id="shape">Error body</H2>
      <Response status={409} body={{ detail: "That time is not available.", code: "slot_unavailable", request_id: "067482d4e32f4d03a9cc3dcd82e41d56" }} />
      <Response status={422} body={{ detail: "Validation failed", code: "validation_failed", errors: [{ type: "missing", loc: ["body", "customer", "full_name"], msg: "Field required" }], request_id: "a1c437334cc9495090509ce45bea9fe2" }} />
      <H2 id="codes">Common codes</H2>
      <div className="mt-4 overflow-x-auto rounded-xl border" tabIndex={0} role="region" aria-label="Error codes">
        <table className="w-full min-w-[44rem] text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th scope="col" className="px-3 py-2">HTTP</th><th scope="col" className="px-3 py-2">code</th><th scope="col" className="px-3 py-2">Meaning</th><th scope="col" className="px-3 py-2">What to do</th></tr></thead>
          <tbody className="divide-y">{ERRORS.map(([h, c, m, d]) => <tr key={c} className="align-top"><td className="px-3 py-2 font-mono text-xs">{h}</td><td className="px-3 py-2 font-mono text-xs">{c}</td><td className="px-3 py-2">{m}</td><td className="px-3 py-2 text-muted-foreground">{d}</td></tr>)}</tbody>
        </table>
      </div>
      <H3>Handling them in code</H3>
      <CodeBlock label="Error handling in Python" code={`import time, requests

def call(method, url, **kw):
    for attempt in range(5):
        r = requests.request(method, url, timeout=15, **kw)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5")))
            continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if r.ok:
            return r.json()
        err = r.json()
        if err.get("code") == "slot_unavailable":
            raise SlotTaken(err["detail"])          # ask the user for another time
        raise ApiError(r.status_code, err.get("code"), err.get("detail"), err.get("request_id"))
    raise ApiError(503, "gave_up", "API unavailable after retries", None)`} />
    </>
  );
}
