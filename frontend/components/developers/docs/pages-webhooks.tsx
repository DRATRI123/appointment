"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/components/auth/auth-provider";
import { developersService } from "@/services/developers";
import { C, Callout, CodeBlock, CodeTabs, DocLink, H2, H3, Lead, P, Response, Steps, Table, UL } from "./ui";

const APPOINTMENT_DATA = {
  id: "8c1f2a0e-…", reference: "APT-AKSHAR-01JD8Q…", status: "confirmed", start_at: "2026-11-16T05:00:00+00:00", end_at: "2026-11-16T05:30:00+00:00",
  timezone: "Asia/Kolkata", consultation_mode: "in_person", source: "online", meeting_link: null,
  service: { id: "63a0410f-…", name: "Ayurvedic Consultation" }, professional: { id: "bfe0259d-…", name: "Dr. Kavya Shah" }, branch: { id: "b86b360f-…", name: "Navrangpura" },
  customer: { id: "59b37f80-…", name: "Asha Patel", mobile: "+919812345678", email: "asha@example.com" },
  amounts: { currency: "INR", total_paise: 80000, advance_due_paise: 80000, paid_paise: 80000 },
};

export const EVENTS: [string, string, string][] = [
  ["appointment.created", "A booking was made (online, by staff or through the API).", "appointment"],
  ["appointment.confirmed", "Confirmed: payment verified, nothing due, or confirmed by staff.", "appointment"],
  ["appointment.rescheduled", "Date, time or doctor changed. Adds previous_start_at.", "appointment"],
  ["appointment.cancelled", "Cancelled by the patient or the clinic.", "appointment"],
  ["appointment.expired", "An unpaid booking was released after the payment window.", "appointment"],
  ["appointment.checked_in", "The patient arrived.", "appointment"],
  ["appointment.completed", "The visit was completed.", "appointment"],
  ["appointment.no_show", "The patient did not come.", "appointment"],
  ["payment.submitted", "A patient submitted a UTR. Not verified: do not treat as paid.", "payment"],
  ["payment.verified", "Staff verified the money in the bank. This is the “paid” signal.", "payment"],
  ["payment.rejected", "Staff could not verify the payment.", "payment"],
  ["refund.processed", "Staff recorded a refund they sent.", "refund"],
  ["ping", "Test event from the “Send test” button.", "ping"],
];

const PY_VERIFY = `# pip install flask
import hashlib, hmac, os, time
from flask import Flask, abort, request

SECRET = os.environ["WEBHOOK_SECRET"]          # whsec_… shown once when you created the endpoint
app = Flask(__name__)
seen = set()                                    # use your database in production

def valid(header: str, body: bytes, tolerance: int = 300) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance:       # too old: possible replay
        return False
    expected = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))

@app.post("/webhooks/appointments")
def receive():
    body = request.get_data()                   # the RAW bytes, before any JSON parsing
    if not valid(request.headers.get("X-Webhook-Signature", ""), body):
        abort(400)
    event_id = request.headers["X-Webhook-Id"]
    if event_id in seen:                        # retries reuse the same id
        return "", 200
    seen.add(event_id)
    event = request.get_json()
    queue_for_processing(event)                 # do slow work later; answer within 10 seconds
    return "", 200`;

const NODE_VERIFY = `// npm install express
import crypto from "node:crypto";
import express from "express";

const SECRET = process.env.WEBHOOK_SECRET;     // whsec_… shown once when you created the endpoint
const app = express();

function valid(header = "", rawBody, toleranceSec = 300) {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split("=")));
  const ts = Number(parts.t);
  if (!ts || Math.abs(Date.now() / 1000 - ts) > toleranceSec) return false;
  const expected = crypto.createHmac("sha256", SECRET).update(\`\${ts}.\`).update(rawBody).digest();
  const given = Buffer.from(parts.v1 ?? "", "hex");
  return given.length === expected.length && crypto.timingSafeEqual(expected, given);
}

// express.raw keeps the exact bytes that were signed
app.post("/webhooks/appointments", express.raw({ type: "application/json" }), async (req, res) => {
  if (!valid(req.get("X-Webhook-Signature"), req.body)) return res.sendStatus(400);
  const eventId = req.get("X-Webhook-Id");
  if (await alreadyProcessed(eventId)) return res.sendStatus(200);
  const event = JSON.parse(req.body.toString("utf8"));
  await queueForProcessing(event);              // answer within 10 seconds
  res.sendStatus(200);
});

app.listen(3000);`;

const PHP_VERIFY = `<?php
// webhook.php
$secret = getenv('WEBHOOK_SECRET');            // whsec_… shown once when you created the endpoint
$body   = file_get_contents('php://input');    // raw bytes
$header = $_SERVER['HTTP_X_WEBHOOK_SIGNATURE'] ?? '';

$parts = [];
foreach (explode(',', $header) as $p) {
    [$k, $v] = array_pad(explode('=', $p, 2), 2, '');
    $parts[$k] = $v;
}
$ts = (int)($parts['t'] ?? 0);
$expected = hash_hmac('sha256', $ts . '.' . $body, $secret);

if (abs(time() - $ts) > 300 || !hash_equals($expected, $parts['v1'] ?? '')) {
    http_response_code(400);
    exit;
}

$eventId = $_SERVER['HTTP_X_WEBHOOK_ID'];
// if (already_processed($eventId)) { http_response_code(200); exit; }
$event = json_decode($body, true);
// save $event for processing, then answer quickly
http_response_code(200);`;

export function WebhooksPage() {
  return (
    <>
      <Lead>Webhooks push events to your server the moment something happens: a booking, a cancellation, a verified payment. No polling needed. Each request is signed so you can prove it came from us.</Lead>

      <H2 id="setup">Set up an endpoint</H2>
      <Steps items={[
        { title: "Build a receiver", body: <>An HTTPS URL on your server that accepts <C>POST</C> with JSON and answers <C>2xx</C> quickly. Copy one of the <a className="underline" href="#verify">verification examples</a>.</> },
        { title: "Add it in the admin", body: <>Open <Link className="underline" href="/admin/developers">Developers → Webhooks → Add endpoint</Link>. Give it a name, paste the URL, choose events (or all events).</> },
        { title: "Store the signing secret", body: <>The <C>whsec_…</C> secret is shown <strong>once</strong>. Put it in your receiver&apos;s environment as <C>WEBHOOK_SECRET</C>.</> },
        { title: "Send a test", body: <>Press <strong>Send test</strong>. A signed <C>ping</C> event is sent at once; the delivery log shows your server&apos;s response.</> },
      ]} />
      <Table head={["Rule", "Detail"]} mono={[]} rows={[
        ["HTTPS only", "Plain http:// is refused in production."],
        ["Public address", "URLs that resolve to private, loopback or cloud-metadata addresses are refused, and checked again at every send."],
        ["No credentials in the URL", <>Don&apos;t use <C>https://user:pass@…</C>. Authenticate with the signature instead.</>],
        ["Limits", "Up to 20 endpoints per clinic. Redirects are not followed."],
      ]} />

      <H2 id="request">What we send</H2>
      <CodeBlock label="Webhook headers" code={`POST /webhooks/appointments HTTP/1.1
Content-Type: application/json
User-Agent: AppointmentPlatform-Webhooks/1.0
X-Webhook-Id: evt_01JD8S3V4K5M6N7P8Q9R0S1T2U
X-Webhook-Event: appointment.created
X-Webhook-Timestamp: 1763273521
X-Webhook-Signature: t=1763273521,v1=5f2c9a…e81b`} />
      <Response status={200} note="request body" body={{ id: "evt_01JD8S3V4K5M6N7P8Q9R0S1T2U", type: "appointment.created", api_version: "2026-11", created_at: "2026-11-14T06:12:01+00:00", organization: { id: "27b1c2c1-8ab8-42c8-a8cb-f8788fb0a773", slug: "akshar-clinic" }, data: APPOINTMENT_DATA }} />
      <UL>
        <li><C>data</C> is a snapshot at the moment of the event. For the latest state call <C>GET /appointments/&#123;id&#125;</C>.</li>
        <li>Payloads contain public ids and contact details only, never medical notes, form answers, documents or payment screenshots.</li>
        <li>An event is only created when the change is saved. You never get an event for something that was rolled back.</li>
      </UL>

      <H2 id="verify">Verify the signature</H2>
      <P>The signature is <C>HMAC-SHA256(secret, &quot;&lt;t&gt;.&lt;raw body&gt;&quot;)</C> in hex, sent as <C>t=&lt;unix seconds&gt;,v1=&lt;hex&gt;</C>. Check it on the <strong>raw</strong> body before parsing JSON (re-serialised JSON will not match), use a constant-time comparison, and reject timestamps more than five minutes old.</P>
      <CodeTabs label="Webhook receiver" samples={[
        { lang: "python", title: "Python (Flask)", code: PY_VERIFY },
        { lang: "node", title: "Node.js (Express)", code: NODE_VERIFY },
        { lang: "php", title: "PHP", code: PHP_VERIFY },
      ]} />

      <H2 id="respond">Responding, retries and duplicates</H2>
      <Table head={["Topic", "Behaviour"]} mono={[]} rows={[
        ["Success", <>Any <C>2xx</C> within <strong>10 seconds</strong>. Do slow work (CRM calls, emails) after answering, in a queue.</>],
        ["Failure", "Timeouts, network errors, 3xx, 4xx and 5xx all count as failures."],
        ["Retries", <>Up to <strong>8 attempts</strong>: after 1 min, 5 min, 30 min, 2 h, 6 h, 12 h and 24 h. Then the delivery is marked dead (you can still resend it by hand).</>],
        ["Duplicates", <>The same event can arrive more than once. Retries keep the same <C>X-Webhook-Id</C>; store processed ids and skip repeats.</>],
        ["Order", <>Events can arrive out of order (a retry may land after a newer event). Compare <C>created_at</C>, or fetch the object for its current status.</>],
        ["Speed", "Events are usually sent within about a minute."],
        ["Auto-pause", "After 50 failed attempts in a row an endpoint is switched off and the clinic sees it in the admin. Fix the receiver, then Resume (this resets the counter). Events that happen while it is off are not stored for it."],
        ["Delivery log", "Every attempt with status code and the first part of your response, kept for 30 days. Open one to see the exact payload or press Resend."],
      ]} />

      <H2 id="secrets">Rotating the signing secret</H2>
      <P>Use <strong>Rotate secret</strong> on the endpoint if the secret may have leaked. The new secret is shown once and is used for all deliveries from that moment, so update <C>WEBHOOK_SECRET</C> on your receiver straight away. Deliveries that fail in between are retried automatically.</P>

      <H2 id="local">Testing on your computer</H2>
      <P>Webhook URLs must be public HTTPS addresses. To receive events on your own computer, run a tunnel (for example <C>cloudflared tunnel --url http://localhost:3000</C> or <C>ngrok http 3000</C>), add the HTTPS address it gives you as an endpoint, and press <strong>Send test</strong>. Remove the endpoint when you are done.</P>
      <Callout title="Make sure you don't miss anything">
        Webhooks are reliable but not a database. Run a nightly job that lists yesterday&apos;s appointments through the <DocLink page="appointments" anchor="list">API</DocLink> and fixes any differences in your system.
      </Callout>
    </>
  );
}

export function EventsPage() {
  const { hasPermission } = useAuth();
  const live = useQuery({ queryKey: ["webhook-events"], queryFn: developersService.events, enabled: hasPermission("api_keys:manage") });
  const sample = (name: string) => live.data?.find((e) => e.name === name)?.sample;
  return (
    <>
      <Lead>Every event has the same envelope (<C>id</C>, <C>type</C>, <C>api_version</C>, <C>created_at</C>, <C>organization</C>, <C>data</C>). Subscribe to the ones you need, or to all with <C>*</C>.</Lead>
      <H2 id="list">All events</H2>
      <Table head={["Event", "When", "data"]} rows={EVENTS.map(([n, d, k]) => [n, d, <span key={n} className="font-mono text-xs text-muted-foreground">{k}</span>])} />

      <H2 id="appointment">Appointment events</H2>
      <P>All <C>appointment.*</C> events carry the same <C>data</C>. <C>appointment.rescheduled</C> adds <C>previous_start_at</C>.</P>
      <Response status={200} note="data for appointment.*" body={sample("appointment.created") ? (sample("appointment.created") as { data: unknown }).data : APPOINTMENT_DATA} />
      <H3>Field notes</H3>
      <UL>
        <li><C>status</C>: <C>pending_payment</C>, <C>pending_verification</C>, <C>confirmed</C>, <C>checked_in</C>, <C>in_progress</C>, <C>completed</C>, <C>cancelled</C>, <C>no_show</C>, <C>expired</C>.</li>
        <li><C>source</C>: <C>online</C> (booking page), <C>reception</C>, <C>walk_in</C>, <C>professional</C>, <C>api</C>.</li>
        <li><C>meeting_link</C>: video link for online consultations, when the clinic connected a video provider.</li>
        <li><C>amounts.paid_paise</C> counts verified payments only.</li>
      </UL>

      <H2 id="payment">Payment events</H2>
      <Response status={200} note="data for payment.*" body={(sample("payment.verified") as { data: unknown } | undefined)?.data ?? { id: "2977a123-…", reference: "PAY-AKSHAR-01M7F8J7…", status: "verified", method: "upi_qr", kind: "advance", amount_paise: 80000, verified_amount_paise: 80000, utr: "412345678901", currency: "INR", verified_at: "2026-11-14T06:12:00+00:00", rejection_reason: null, appointment: { id: "8c1f2a0e-…", reference: "APT-AKSHAR-01JD8Q…" } }} />
      <Callout kind="warning" title="payment.submitted is not a payment">
        It only means the patient typed a UTR or uploaded a screenshot. Wait for <C>payment.verified</C>, which is sent only after staff matched the money in the bank.
      </Callout>

      <H2 id="refund">Refund events</H2>
      <Response status={200} note="data for refund.processed" body={{ id: "…", reference: "RFD-AKSHAR-01JD9…", status: "processed", amount_paise: 50000, method: "upi", refund_reference: "512345678901", processed_at: "2026-11-15T10:00:00+00:00", payment: { id: "…", reference: "PAY-AKSHAR-01JD8R…" } }} />
      <H2 id="ping">ping</H2>
      <Response status={200} note="data for ping" body={{ message: "Test event" }} />
    </>
  );
}
