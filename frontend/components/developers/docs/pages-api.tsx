"use client";

import { C, Callout, CodeBlock, DocLink, Endpoints, H2, H3, Lead, P, Request, Response, Table, UL } from "./ui";

const SVC = "63a0410f-0674-4101-ab1c-a9fe0ceac452";
const BR = "b86b360f-c60c-4bdd-8bb3-7012be151195";
const PRO = "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae";
const APPT = "e1df655e-961b-4323-a8ac-c990cbb658e3";

export function CataloguePage() {
  return (
    <>
      <Lead>Branches (locations), services, categories, packages and doctors. You need their ids to check availability and book. These endpoints are read-only for API keys; edit the catalogue in the admin.</Lead>
      <H2 id="endpoints">Endpoints</H2>
      <Endpoints rows={[
        ["GET", "/branches", "branches:read", "All branches with address, phone, business hours and time zone."],
        ["GET", "/branches/{id}", "branches:read", "One branch."],
        ["GET", "/service-categories", "services:read", "Categories with service_count."],
        ["GET", "/services", "services:read", <>Filters: <C>category_id</C>, <C>branch_id</C> (applies branch price overrides), <C>kind</C>, <C>search</C>.</>],
        ["GET", "/services/{id}", "services:read", "One service with per-branch pricing and the doctors who offer it."],
        ["GET", "/service-packages", "services:read", "Bundles of services."],
        ["GET", "/professionals", "professionals:read", <>Doctors. Filters: <C>branch_id</C>, <C>service_id</C>, <C>search</C>.</>],
        ["GET", "/professionals/{id}", "professionals:read", "One doctor with branches, fees and services."],
        ["GET", "/schedules", "professionals:read", <>Weekly working hours. Filters: <C>professional_id</C>, <C>branch_id</C>.</>],
        ["GET", "/schedules/exceptions · /holidays · /leaves", "professionals:read", "Date overrides, holidays and approved leave."],
      ]} />
      <H2 id="services">Services</H2>
      <Request title="Services offered at one branch" method="GET" path="/services" query={{ branch_id: BR }} />
      <Response status={200} body={[{ id: SVC, name: "Ayurvedic Consultation", slug: "consultation", kind: "standard", category_id: "68f00b49-…", category_name: "Consultation", duration_minutes: 30, buffer_minutes: 0, consultation_mode: "in_person", currency: "INR", price_paise: 80000, discounted_price_paise: null, payment_mode: "full_advance", tax_percent: 0, is_active: true, is_bookable_online: true, pricing: [], professional_ids: [PRO] }]} />
      <Table head={["payment_mode", "Meaning"]} rows={[
        ["full_advance", "The full price is due online before the visit."],
        ["partial_advance", "A fixed amount or percent is due online; the rest at the clinic."],
        ["pay_at_clinic", "Nothing due online. Bookings are confirmed straight away."],
        ["free", "No charge."],
      ]} />
      <H2 id="professionals">Doctors</H2>
      <Request title="Doctors offering a service" method="GET" path="/professionals" query={{ service_id: SVC }} />
      <Response status={200} body={[{ id: PRO, display_name: "Dr. Kavya Shah", slug: "dr-kavya-shah", qualification: "BAMS, MS (Ayurveda)", specialization: "Shalakya (ENT & Eye)", experience_years: 7, languages: ["English", "Gujarati"], default_duration_minutes: 30, slot_capacity: 1, is_active: true, is_bookable_online: true, branches: ["…"], services: ["…"] }]} />
      <Callout>Use <C>slug</C> values (e.g. <C>dr-kavya-shah</C>) in booking links: <DocLink page="embed" anchor="links">links & URL parameters</DocLink>.</Callout>
    </>
  );
}

export function AvailabilityPage() {
  return (
    <>
      <Lead>Free times are calculated live from the doctor&apos;s weekly hours, date exceptions, holidays, leave, existing appointments and active holds. Never compute slots yourself; always ask this endpoint.</Lead>
      <Endpoints rows={[
        ["GET", "/availability/summary", "appointments:read", <>Which days have free times. <C>service_id</C>, <C>branch_id</C>, <C>from_date</C>, <C>to_date</C> (max 31 days), optional <C>professional_id</C>.</>],
        ["GET", "/availability", "appointments:read", <>Free times for one <C>date</C>, grouped by doctor. Same filters.</>],
      ]} />
      <H2 id="summary">Which days are free</H2>
      <Request title="Days with free times" method="GET" path="/availability/summary" query={{ service_id: SVC, branch_id: BR, from_date: "2026-11-20", to_date: "2026-11-21" }} />
      <Response status={200} body={[{ date: "2026-11-20", available: true, slot_count: 14 }, { date: "2026-11-21", available: true, slot_count: 7 }]} />
      <H2 id="day">Free times for a day</H2>
      <Request title="Free times" method="GET" path="/availability" query={{ service_id: SVC, branch_id: BR, date: "2026-11-20" }} />
      <Response status={200} body={{ date: "2026-11-20", timezone: "Asia/Kolkata", service_id: SVC, branch_id: BR, duration_minutes: 30, professionals: [{ professional_id: PRO, display_name: "Dr. Kavya Shah", slots: [{ start_at: "2026-11-20T04:00:00Z", end_at: "2026-11-20T04:30:00Z", remaining: 1, professional_id: PRO }] }] }} />
      <UL>
        <li>Leave out <C>professional_id</C> to get every doctor who offers the service at that branch: useful for “first available doctor”.</li>
        <li><C>remaining</C> is more than 1 when a doctor sees several people at the same time (group sessions, capacity).</li>
        <li>Minimum notice and how far ahead people can book come from the service or the clinic&apos;s booking settings. Staff and API bookings may ignore the minimum notice when using a hold.</li>
        <li>Availability is a snapshot. Between reading it and booking, someone else can take the slot; then booking returns <C>409 slot_unavailable</C>.</li>
      </UL>
    </>
  );
}

export function AppointmentsPage() {
  return (
    <>
      <Lead>Create, read, reschedule, cancel and move appointments through their life cycle. Every change is checked against availability and written to the audit log.</Lead>
      <H2 id="endpoints">Endpoints</H2>
      <Endpoints rows={[
        ["GET", "/appointments", "appointments:read", <>Filters: <C>from_at</C>, <C>to_at</C>, <C>status</C>, <C>professional_id</C>, <C>branch_id</C>, <C>customer_id</C>, <C>search</C> (reference, name or mobile).</>],
        ["GET", "/appointments/calendar", "appointments:read", <>Compact events between <C>from_at</C> and <C>to_at</C>, for calendar views.</>],
        ["GET", "/appointments/{id}", "appointments:read", "One appointment with status history and the price breakdown."],
        ["POST", "/appointments", "appointments:write", "Book a slot (directly, or from a hold)."],
        ["POST", "/appointments/holds", "appointments:write", "Hold a slot for a few minutes while you collect details."],
        ["DELETE", "/appointments/holds/{id}", "appointments:write", "Release a hold early."],
        ["POST", "/appointments/recurring", "appointments:write", <>A series: <C>occurrences</C> (2–26) every <C>interval_days</C>. Blocked dates come back in <C>skipped</C>.</>],
        ["POST", "/appointments/{id}/reschedule", "appointments:write", <>New <C>start_at</C> (and optionally <C>professional_id</C>), or a <C>hold_id</C>.</>],
        ["POST", "/appointments/{id}/status", "appointments:write / appointments:checkin", "confirm, cancel, expire, check_in, start, complete, no_show."],
        ["GET / POST / DELETE", "/waitlist[/{id}]", "appointments:read / write", "People waiting for a time to open up."],
      ]} />

      <H2 id="create">Book an appointment</H2>
      <P>Send the doctor, branch, service and a <C>start_at</C> that came from <DocLink page="availability">availability</DocLink>, plus the customer. If a customer with the same mobile already exists in the clinic, the booking is linked to them; otherwise a customer is created.</P>
      <Request title="Book" method="POST" path="/appointments" body={{ professional_id: PRO, branch_id: BR, service_id: SVC, start_at: "2026-11-20T05:30:00Z", customer: { full_name: "Asha Patel", mobile: "9812345678", email: "asha@example.com" }, customer_notes: "Prefers Gujarati", source: "api" }} />
      <Response status={201} body={{ id: APPT, reference: "APT-AKSHAR-01M7F8J748S8VJ5620QZ3YNMKW", status: "pending_payment", source: "api", branch_id: BR, branch_name: "Navrangpura", professional_id: PRO, professional_name: "Dr. Kavya Shah", service_id: SVC, service_name: "Ayurvedic Consultation", customer: { id: "59b37f80-…", full_name: "Asha Patel", mobile: "+919812345678", email: "asha@example.com", is_guest: false }, start_at: "2026-11-20T05:30:00Z", end_at: "2026-11-20T06:00:00Z", timezone: "Asia/Kolkata", consultation_mode: "in_person", currency: "INR", subtotal_paise: 80000, discount_paise: 0, tax_paise: 0, total_amount_paise: 80000, advance_due_paise: 80000, paid_amount_paise: 0, payment_due_at: "2026-11-15T09:58:10Z", can_cancel: true, can_reschedule: true, history: [{ from_status: null, to_status: "pending_payment" }] }} />
      <Table head={["Field", "Notes"]} rows={[
        ["customer", <><C>full_name</C> (required), <C>mobile</C>, <C>email</C>, or <C>customer_id</C> of an existing customer. <C>whatsapp_opt_in</C>: the customer agreed to WhatsApp updates.</>],
        ["dependent_id", "Book for a family member of the customer."],
        ["source", <><C>api</C> (recommended for integrations), <C>reception</C>, <C>walk_in</C>, <C>professional</C>. Shown in reports.</>],
        ["consultation_mode", <><C>in_person</C> or <C>online</C> when the service allows both.</>],
        ["customer_notes / internal_notes", "Up to 2,000 characters. Internal notes are never shown to the customer."],
        ["coupon_code", <>Re-validated on the server; <C>422 coupon_invalid</C> if it can&apos;t be used.</>],
        ["form_answers", <>Answers to the service&apos;s booking form, keyed by field key; <C>422 form_invalid</C> with per-field errors.</>],
        ["confirm_without_payment", <>Confirms the visit now even though money is due. It does <strong>not</strong> record a payment: the amount stays due and is collected at the clinic.</>],
        ["hold_id", "Book a slot you held earlier instead of sending doctor/branch/service/start_at."],
      ]} />
      <Callout kind="security" title="Price and payment are the server's job">
        Amount fields you send are ignored. The price is worked out from the service, branch pricing, doctor fee, coupon and tax. If an advance is due, the appointment starts as <C>pending_payment</C>; the patient pays the clinic&apos;s own UPI and staff verify it in the admin. An API key cannot mark it paid.
      </Callout>

      <H2 id="holds">Holding a slot first</H2>
      <P>When a person is on the phone, hold the time while you take their details. A hold blocks the slot for everyone else for a few minutes (the clinic&apos;s hold time, default 10).</P>
      <Request title="Hold" method="POST" path="/appointments/holds" body={{ professional_id: PRO, branch_id: BR, service_id: SVC, start_at: "2026-11-20T06:00:00Z" }} />
      <Response status={201} body={{ id: "d6ce41ac-9cba-4df1-88d7-0acd21a17a31", professional_id: PRO, branch_id: BR, service_id: SVC, start_at: "2026-11-20T06:00:00Z", end_at: "2026-11-20T06:30:00Z", expires_at: "2026-11-15T09:40:00Z", session_key: "JjitDdjbeR2JQ500bC4x8w", status: "active" }} />
      <Request title="Book the held slot" method="POST" path="/appointments" body={{ hold_id: "d6ce41ac-9cba-4df1-88d7-0acd21a17a31", customer: { full_name: "Asha Patel", mobile: "9812345678" }, source: "api" }} />
      <P>A hold that ran out returns <C>409 hold_expired</C>; place a new one. Release holds you no longer need with <C>DELETE /appointments/holds/&#123;id&#125;</C> so the time opens up again.</P>

      <H2 id="status">Status and life cycle</H2>
      <CodeBlock label="Appointment life cycle" code={`pending_payment ─(patient submits UTR)─► pending_verification ─(staff verify)─► confirmed
      │                                                                              │
      ├─(payment window passes)─► expired                    check_in ─► checked_in ─ start ─► in_progress
      │                                                                              │              │
      └─(confirm: staff decision, payment still due)─► confirmed          complete ─► completed ◄────┘

cancel  : any open status ─► cancelled          no_show : confirmed / checked_in ─► no_show`} />
      <Request title="Cancel" method="POST" path={`/appointments/${APPT}/status`} body={{ action: "cancel", reason: "Patient called to cancel" }} />
      <Table head={["action", "Scope", "Allowed from"]} rows={[
        ["confirm", "appointments:write", "pending_payment, pending_verification (a staff decision; no payment is recorded and the amount stays due)"],
        ["cancel", "appointments:write", "pending_payment, pending_verification, confirmed, checked_in"],
        ["expire", "appointments:write", "pending_payment"],
        ["check_in", "appointments:checkin", "confirmed, pending_payment"],
        ["start", "appointments:checkin", "confirmed, checked_in"],
        ["complete", "appointments:checkin", "confirmed, checked_in, in_progress"],
        ["no_show", "appointments:checkin", "confirmed, pending_payment, checked_in"],
      ]} />
      <P>A change that isn&apos;t allowed returns <C>409 invalid_transition</C>. <C>completed</C>, <C>cancelled</C>, <C>no_show</C> and <C>expired</C> are final.</P>

      <H2 id="reschedule">Reschedule</H2>
      <Request title="Move to another time" method="POST" path={`/appointments/${APPT}/reschedule`} body={{ start_at: "2026-11-21T06:30:00Z", reason: "Patient asked" }} />
      <P>The new time is checked like a new booking. Add <C>professional_id</C> to move to another doctor. Webhook <C>appointment.rescheduled</C> includes <C>previous_start_at</C>.</P>

      <H2 id="list">Listing</H2>
      <Request title="Today's confirmed visits at one branch" method="GET" path="/appointments" query={{ from_at: "2026-11-20T00:00:00+05:30", to_at: "2026-11-21T00:00:00+05:30", status: "confirmed", branch_id: BR }} />
      <P>Keep windows to a few weeks. To keep another system in sync, prefer <DocLink page="webhooks">webhooks</DocLink> plus a nightly list of the last day as a safety net.</P>

      <H2 id="waitlist">Waitlist</H2>
      <Request title="Add to waitlist" method="POST" path="/waitlist" body={{ customer: { full_name: "Ravi Mehta", mobile: "9876500011" }, service_id: SVC, branch_id: BR, preferred_date: "2026-11-22T00:00:00+05:30", notes: "Mornings only" }} />
    </>
  );
}

export function CustomersPage() {
  return (
    <>
      <Lead>The clinic&apos;s patient list: contact details, tags, family members and visit statistics. Medical notes and documents are deliberately not available through API keys.</Lead>
      <Endpoints rows={[
        ["GET", "/customers", "customers:read", <>Paged. <C>search</C> (name, mobile, email, code), <C>tag</C>, <C>segment</C> (<C>new_30d</C>, <C>upcoming</C>, <C>returning</C>, <C>inactive_90d</C>), <C>is_guest</C>, <C>page</C>, <C>page_size</C>.</>],
        ["GET", "/customers/{id}", "customers:read", "One customer with stats (visits, no-shows, cancellations)."],
        ["POST", "/customers", "customers:write", "Create. Mobile must be unique within the clinic."],
        ["PATCH", "/customers/{id}", "customers:write", "Update only the fields you send."],
        ["GET / POST / PATCH / DELETE", "/customers/{id}/dependents[/{dep_id}]", "customers:read / write", "Family members, usable as dependent_id when booking."],
      ]} />
      <H2 id="search">Find a customer by mobile</H2>
      <Request title="Search" method="GET" path="/customers" query={{ search: "9742245886", page_size: "5" }} />
      <Response status={200} body={{ data: [{ id: "26ff7363-66e2-4f9e-87ea-b27fb61ec05a", full_name: "Meera Desai", mobile: "+919742245886", email: null, tags: [], is_guest: true, source: "online", registered_at: "2026-11-15T08:58:10Z", last_visit_at: null, dependents_count: 0 }], meta: { page: 1, page_size: 5, total: 1 } }} />
      <H2 id="create">Create or update</H2>
      <Request title="Create" method="POST" path="/customers" body={{ full_name: "Asha Patel", mobile: "9812345678", email: "asha@example.com", date_of_birth: "1988-04-12", gender: "female", tags: ["corporate-tie-up"], consent: { marketing: false } }} />
      <P>Mobiles are normalised to international format (<C>+91…</C>). A mobile already used by another customer returns <C>409 mobile_taken</C>; search first and <C>PATCH</C> the existing record instead. <C>gender</C> is one of <C>male</C>, <C>female</C>, <C>other</C>, <C>undisclosed</C>.</P>
      <Callout kind="security" title="Personal data">
        Only request <C>customers:read</C> if your system really needs patient details, store them securely, and delete them when no longer needed. The clinic is responsible for patient consent; respect <C>consent</C> and <C>communication_preferences</C> before sending marketing.
      </Callout>
    </>
  );
}

export function PaymentsPage() {
  return (
    <>
      <Lead>Patients pay the clinic&apos;s own UPI ID (no payment gateway). Staff check the bank and verify each payment in the admin. The API lets you <strong>read</strong> payment status; it can never record, verify or refund money.</Lead>
      <Endpoints rows={[
        ["GET", "/payments", "payments:read", <>Paged. Filters: <C>status</C>, <C>method</C>, <C>search</C> (reference, UTR, name, mobile), <C>appointment_id</C>, <C>customer_id</C>, <C>from_at</C>, <C>to_at</C>.</>],
        ["GET", "/payments/{id}", "payments:read", "One payment with submissions and the verification log."],
      ]} />
      <H2 id="statuses">Payment statuses</H2>
      <Table head={["status", "Meaning"]} rows={[
        ["awaiting_payment", "A UPI request (QR) was created. A QR is only a request, not proof of payment."],
        ["submitted", "The patient entered a UTR / uploaded a screenshot. Not verified yet."],
        ["under_review", "Staff are checking the bank statement."],
        ["verified", <>Staff confirmed the money reached the bank. Only this means paid. <C>verified_amount_paise</C> is what was received.</>],
        ["rejected", <>Staff could not find the money; <C>rejection_reason</C> says why. The patient may submit again.</>],
        ["expired / cancelled", "The payment window passed, or the appointment was cancelled or paid in cash instead."],
      ]} />
      <Callout kind="warning" title="Treat only “verified” as paid">
        Never release a service, send a receipt or mark an order paid on <C>submitted</C>. Listen for the <C>payment.verified</C> webhook, or read the payment and check <C>status === &quot;verified&quot;</C>.
      </Callout>
      <Request title="Payments waiting for staff" method="GET" path="/payments" query={{ status: "submitted", page_size: "20" }} />
      <P>Trying <C>POST /payments</C> or any <C>/admin/payments/…</C> verification endpoint with a key returns <C>403</C>.</P>
    </>
  );
}

export function ReportsPage() {
  return (
    <>
      <Lead>Pull the same numbers the admin dashboard and reports show, for accounting, BI tools or a daily summary.</Lead>
      <Endpoints rows={[
        ["GET", "/analytics/dashboard", "reports:read", <>KPIs with the previous period, daily series, breakdowns by service, doctor, branch, source and payment method, busy-hours heat map. Filters: <C>from</C>, <C>to</C> (dates, up to one year), <C>branch_id</C>, <C>professional_id</C>, <C>service_id</C>.</>],
        ["GET", "/reports", "reports:read", "The reports this key may run, with their columns."],
        ["GET", "/reports/{key}", "reports:read (+ report's own)", <>Rows, totals and row count. Same filters plus <C>page</C>, <C>page_size</C> (max 500).</>],
      ]} />
      <Table head={["Report key", "What it contains"]} rows={[
        ["appointments", "Every appointment in the range with customer, service, doctor and amounts."],
        ["payments", "Payments with status, method, UTR and verification time."],
        ["refunds", "Refunds recorded by staff."],
        ["daily_summary", "Per day: booked, cancelled, no-shows, verified receipts, refunds, net."],
        ["professionals · services", "Bookings, completion, no-show rate, value and utilisation."],
        ["customers", "New and returning customers."],
        ["cancellations", "Cancellations with reasons and timing."],
        ["tax_summary", "Billing summary by month (a working summary for your accountant, not a tax filing)."],
        ["coupons", "Coupon use and discount given."],
      ]} />
      <P>Some reports also need <C>payments:read</C> or <C>customers:read</C>; <C>GET /reports</C> lists exactly what your key can run. File exports (CSV/Excel) are only available to signed-in staff.</P>
      <Request title="Daily summary for a week" method="GET" path="/reports/daily_summary" query={{ from: "2026-11-10", to: "2026-11-16" }} />
      <Response status={200} body={{ key: "daily_summary", title: "Daily summary", columns: [{ key: "date", label: "Date", type: "date" }, { key: "booked", label: "Booked", type: "int" }, { key: "receipts", label: "Verified receipts", type: "money" }, { key: "net", label: "Net received", type: "money" }], rows: [{ date: "2026-11-10", booked: 6, cancelled: 1, no_show: 0, receipts: 320000, refunds: 0, net: 320000 }], totals: { booked: 6, receipts: 320000, net: 320000 }, total_rows: 7, page: 1, page_size: 100, truncated: false, from_date: "2026-11-10", to_date: "2026-11-16" }} note="money columns are in paise" />
      <H3>Definitions</H3>
      <UL>
        <li><strong>Money received</strong> = payments verified in the period (by verification time) minus refunds sent.</li>
        <li><strong>Booked value</strong> = total of appointments that were not cancelled.</li>
        <li><strong>No-show rate</strong> = no-shows ÷ (completed + no-shows).</li>
        <li><strong>Utilisation</strong> = booked minutes ÷ scheduled minutes (ranges up to 92 days).</li>
      </UL>
    </>
  );
}

export function BookingFormsPage() {
  return (
    <>
      <Lead>Clinics can ask extra questions when people book (intake, consent, symptoms). Read the forms and the answers given for an appointment.</Lead>
      <Endpoints rows={[
        ["GET", "/booking-forms", "booking_forms:read", "Forms (latest published version of each)."],
        ["GET", "/booking-forms/{id}", "booking_forms:read", "Fields, validation and conditions."],
        ["GET", "/booking-forms/responses/by-appointment/{appointment_id}", "appointments:read", "The answers given when that appointment was booked."],
      ]} />
      <P>Field types: text, textarea, number, email, mobile, dropdown, radio, checkbox, date, file, multi_select. When you book through the API, send answers in <C>form_answers</C> keyed by the field <C>key</C>; the server validates them the same way the booking page does. Uploaded files are private and are not returned through the API.</P>
      <CodeBlock label="form_answers example" code={`"form_answers": {\n  "chief_complaint": "Dry eyes for two weeks",\n  "allergies": ["none"],\n  "consent_treatment": true\n}`} />
    </>
  );
}
