# Public booking API

The public booking page (`/{clinic}` and `/embed/{clinic}`) is built only on these endpoints. You can use them to
build your own booking experience (mobile app, kiosk, a different website). They need **no API key**: they are
public, rate limited, and expose only what a visitor may see. Server-to-server integrations that read or change
clinic data use the authenticated Developer API (`api.md`, "Developer API").

* Base URL: `https://<booking-site>/api/v1/public/organizations/{slug}` (the web app proxies `/api/v1` to FastAPI;
  call the API host directly if you run it on its own domain).
* JSON in and out, except the payment submission (multipart form).
* Money is integer **paise** (`80000` = ₹800.00). Times are UTC ISO-8601; display them in the `timezone` returned.
* Errors: `{"detail": "...", "code": "machine_readable_code", "request_id": "..."}`; validation errors add `errors`.
* Every example below is a real exchange with the demo clinic `akshar-clinic` (ids shortened where noted).

## Flow

```
GET  /                         clinic, branches, categories, public settings
GET  /services, /professionals catalogue (filter by branch_id, service_id)
GET  /availability/summary     which days have free times
GET  /availability             free times for one day
GET  /quote                    server-calculated price
POST /holds                    reserve the slot for a few minutes (session_key owns it)
GET  /verification             which methods (SMS, WhatsApp, email) the clinic offers
POST /verification/start       send a one-time code to the customer's mobile or email
POST /verification/{id}/verify exchange the code for a verification token
POST /appointments             book the held slot (send the token)
GET  /appointments/{ref}/payment          UPI QR, UPI id, app links
POST /appointments/{ref}/payment/submit   customer's UTR (+ optional screenshot); never confirms payment
GET  /appointments/{ref}       status page (reference + access token)
```

## Patients see their bookings without keeping the link

A patient who booked without signing in can see every booking, its status and payment later, on any device:
**My bookings** on the clinic's website → **Sign in with code** → a one-time code to the mobile number or email they
booked with. Their account then shows every booking made with that number or email, at every clinic
(`GET /customer/appointments`, `/customer/payments`, `/customer/refunds`), and each booking page opens without the
private link (`GET /public/organizations/{slug}/appointments/{reference}` with the session instead of `access_token`).

* Only contacts the account has proved count: a one-time code to that number or email, Google with a verified email,
  or the email verification link. A number typed at registration but never verified shows nothing.
* At sign-in the clinic's patient record is linked to the account (audit log `customer.linked_to_account`); booking
  again while signed in reuses that record, so the clinic's patient list gets no duplicate.
* If a clinic already has another record for the same person, it is not merged automatically (staff decide), but its
  bookings are still visible to the patient.
* Code: `backend/app/services/customer_link.py`; tests: `backend/tests/test_my_bookings.py`,
  `frontend/e2e/my-bookings.spec.ts`.

## Security rules the server enforces

| Rule | How |
|---|---|
| Prices are never taken from the client | `/appointments` ignores any amount fields; price is recalculated from the catalogue, branch pricing, doctor fee, coupon and tax at booking time. |
| No double booking | Holds and appointments are checked under row locks and a unique constraint; parallel requests for one slot yield exactly one success (`test_races.py`, SQLite and PostgreSQL). |
| Contact verification | When the clinic requires it (default), `/appointments` needs a token from `/verification/{id}/verify`. The token is bound to the clinic, the held slot, the browser session and the exact mobile number (SMS/WhatsApp) or email that was verified, and expires after 30 minutes. A signed-in customer whose own mobile is already verified skips this. |
| OTP abuse | Per clinic policy (Settings → OTP & verification): codes per destination, per IP and per session per hour, resend cool-down and cap, wrong-attempt lock, expiry; plus a platform-wide 10 codes per destination per hour and route limits (start 5/min and 30/h per IP, verify 10/min). Counters live in the database. Codes are never returned or logged. |
| Hold ownership | Every call that uses a hold must send the same `session_key` that created it (`403 hold_mismatch`). |
| Private data | Public endpoints return no patient data except the customer's own booking, which needs the reference **and** the random `access_token` returned at booking. Doctor contact details are stripped. |
| Payments | A QR is only a payment request. Submitting a UTR or screenshot sets the payment to `submitted`; only authorised staff can mark it verified. |
| Unknown or malformed input | Pydantic validation (`422`), unknown ids `404`, unknown clinics `404`. |

## Endpoints

### Clinic

```http
GET /api/v1/public/organizations/akshar-clinic
```

`200`

```json
{
  "organization": {
    "id": "27b1c2c1-8ab8-42c8-a8cb-f8788fb0a773",
    "slug": "akshar-clinic",
    "name": "Akshar Ayurveda Clinic",
    "phone": "+91 98250 12345",
    "description": "Classical Ayurveda and Panchakarma care in Ahmedabad since 2009.",
    "timezone": "Asia/Kolkata",
    "currency": "INR"
  },
  "branches": "[\u2026]",
  "categories": "[\u2026]",
  "settings": "{ branding, booking, cancellation, legal, general }"
}
```

### Services

`GET /services?branch_id=&category_id=` — active, online-bookable services.

```http
GET /api/v1/public/organizations/akshar-clinic/services
```

`200`

```json
[
  {
    "id": "63a0410f-0674-4101-ab1c-a9fe0ceac452",
    "slug": "consultation",
    "name": "Ayurvedic Consultation",
    "short_description": "Nadi pariksha, prakriti assessment and a personalised diet and herbal plan.",
    "duration_minutes": 30,
    "price_paise": 80000,
    "discounted_price_paise": null,
    "payment_mode": "full_advance",
    "consultation_mode": "in_person",
    "category_name": "Consultation"
  },
  {
    "id": "bbc4b180-dfc5-47b5-a73a-81c869eeaabb",
    "slug": "follow-up",
    "name": "Follow-up Visit",
    "short_description": "Review progress and adjust your treatment.",
    "duration_minutes": 15,
    "price_paise": 40000,
    "discounted_price_paise": null,
    "payment_mode": "pay_at_clinic",
    "consultation_mode": "in_person",
    "category_name": "Consultation"
  },
  "\u2026"
]
```

### Doctors

`GET /professionals?service_id=&branch_id=` — doctors who offer the service at the branch.

```http
GET /api/v1/public/organizations/akshar-clinic/professionals?service_id=63a0410f-0674-4101-ab1c-a9fe0ceac452&branch_id=b86b360f-c60c-4bdd-8bb3-7012be151195
```

`200`

```json
[
  {
    "id": "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae",
    "slug": "dr-kavya-shah",
    "display_name": "Dr. Kavya Shah",
    "title": null,
    "specialization": "Shalakya (ENT & Eye)",
    "qualification": "BAMS, MS (Ayurveda)",
    "experience_years": 7,
    "languages": [
      "English",
      "Gujarati"
    ],
    "consultation_modes": null,
    "profile_photo_url": null
  },
  {
    "id": "9a16af5b-0822-4723-8e84-c5299a29b37b",
    "slug": "dr-meera-joshi",
    "display_name": "Dr. Meera Joshi",
    "title": null,
    "specialization": "Kayachikitsa (General Medicine)",
    "qualification": "BAMS, MD (Ayurveda)",
    "experience_years": 14,
    "languages": [
      "English",
      "Gujarati",
      "\u2026"
    ],
    "consultation_modes": null,
    "profile_photo_url": null
  },
  "\u2026"
]
```

### Free days

`GET /availability/summary?service_id&branch_id&from_date&to_date[&professional_id]` (omit `professional_id` for "any doctor").

```http
GET /api/v1/public/organizations/akshar-clinic/availability/summary?service_id=63a0410f-0674-4101-ab1c-a9fe0ceac452&branch_id=b86b360f-c60c-4bdd-8bb3-7012be151195&professional_id=bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae&from_date=2026-11-16&to_date=2026-11-22
```

`200`

```json
[
  {
    "date": "2026-11-16",
    "available": true,
    "slot_count": 11
  },
  {
    "date": "2026-11-17",
    "available": true,
    "slot_count": 14
  },
  "\u2026"
]
```

### Free times for a day

`GET /availability?service_id&branch_id&date[&professional_id]`

```http
GET /api/v1/public/organizations/akshar-clinic/availability?service_id=63a0410f-0674-4101-ab1c-a9fe0ceac452&branch_id=b86b360f-c60c-4bdd-8bb3-7012be151195&professional_id=bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae&date=2026-11-16
```

`200`

```json
{
  "date": "2026-11-16",
  "timezone": "Asia/Kolkata",
  "service_id": "63a0410f-0674-4101-ab1c-a9fe0ceac452",
  "branch_id": "b86b360f-c60c-4bdd-8bb3-7012be151195",
  "duration_minutes": 30,
  "professionals": [
    {
      "professional_id": "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae",
      "display_name": "Dr. Kavya Shah",
      "slots": [
        {
          "start_at": "2026-11-16T05:00:00Z",
          "end_at": "2026-11-16T05:30:00Z",
          "remaining": 1,
          "professional_id": "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae"
        },
        {
          "start_at": "2026-11-16T05:30:00Z",
          "end_at": "2026-11-16T06:00:00Z",
          "remaining": 1,
          "professional_id": "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae"
        },
        "\u2026"
      ]
    }
  ]
}
```

### Price quote

`GET /quote?service_id&branch_id[&professional_id][&coupon_code]` — for display. The booking recalculates it.

```http
GET /api/v1/public/organizations/akshar-clinic/quote?service_id=63a0410f-0674-4101-ab1c-a9fe0ceac452&branch_id=b86b360f-c60c-4bdd-8bb3-7012be151195&professional_id=bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae
```

`200`

```json
{
  "currency": "INR",
  "subtotal_paise": 80000,
  "discount_paise": 0,
  "tax_paise": 0,
  "total_amount_paise": 80000,
  "advance_due_paise": 80000,
  "payment_mode": "full_advance",
  "breakdown": {
    "price_source": "service",
    "tax_percent": 0,
    "service_id": "63a0410f-0674-4101-ab1c-a9fe0ceac452",
    "branch_id": "b86b360f-c60c-4bdd-8bb3-7012be151195",
    "professional_id": "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae",
    "coupon_code": null,
    "coupon_discount_paise": 0
  }
}
```

### Reserve the slot

`POST /holds`. Generate a random `session_key` (8–64 characters) per visitor and keep it for the whole flow.
`409 slot_unavailable` when someone else got the slot first; pick another time.

```http
POST /api/v1/public/organizations/akshar-clinic/holds
{
  "service_id": "63a0410f-0674-4101-ab1c-a9fe0ceac452",
  "branch_id": "b86b360f-c60c-4bdd-8bb3-7012be151195",
  "professional_id": "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae",
  "start_at": "2026-11-16T13:00:00Z",
  "session_key": "demo-6fa0cc0e5a644f0d"
}
```

`201`

```json
{
  "id": "d6ce41ac-9cba-4df1-88d7-0acd21a17a31",
  "professional_id": "bfe0259d-e77b-45ea-bb7f-67c5eb8e1aae",
  "branch_id": "b86b360f-c60c-4bdd-8bb3-7012be151195",
  "service_id": "63a0410f-0674-4101-ab1c-a9fe0ceac452",
  "start_at": "2026-11-16T13:00:00Z",
  "end_at": "2026-11-16T13:30:00Z",
  "expires_at": "2026-11-14T12:21:17.791845Z",
  "session_key": "demo-6fa0cc0e5a644f0d",
  "status": "active"
}
```

`DELETE /holds/{id}?session_key=` releases it early (e.g. when the visitor goes back).

### Verification methods

`GET /verification`

```json
{
  "required": true,
  "channels": [
    "sms",
    "whatsapp",
    "email"
  ],
  "default_channel": "sms",
  "code_length": 6,
  "resend_cooldown_seconds": 60
}
```

### Send a code

`POST /verification/start`. The response never contains the code.

```http
POST /api/v1/public/organizations/akshar-clinic/verification/start
{
  "channel": "sms",
  "destination": "9876535433",
  "hold_id": "fe86e651-7ce4-4827-806d-2611cd4b1ccd",
  "session_key": "demo-16f0b470c4c6"
}
```

`200`

```json
{
  "challenge_id": "b86bd47e-24ee-4f22-bc20-501cc84b6d9d",
  "channel": "sms",
  "destination": "+91•••••433",
  "code_length": 6,
  "expires_in_seconds": 299,
  "resend_after_seconds": 59,
  "resends_left": 3
}
```

Errors: `429 otp_destination_limit` / `otp_ip_limit` / `otp_session_limit`, `422 otp_channel_unavailable`,
`503 otp_delivery_failed` (provider refused; try again or another method), `409 hold_expired`, `403 hold_mismatch`,
`422 hold_not_found`.

`POST /verification/{challenge_id}/resend` with `{"session_key": …}` sends a new code for the same request:

`429`

```json
{
  "detail": "Please wait 59 seconds before asking for another code.",
  "code": "otp_cooldown"
}
```

### Check the code

`POST /verification/{challenge_id}/verify` with `{"code": "…", "session_key": …}`. A wrong code:

`401`

```json
{
  "detail": "That code is not right. 4 attempts left.",
  "code": "otp_incorrect"
}
```

The right code:

`200`

```json
{
  "verification_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9…",
  "channel": "sms",
  "destination": "+919876535433",
  "expires_in_seconds": 1800
}
```

Other errors: `429 otp_locked`, `401 otp_expired`, `401 otp_superseded` (a newer code was sent), `409 otp_used`,
`404 otp_not_found` (unknown id, or another browser session's request).

### Book

`POST /appointments`. Without a token (when verification is required):

```http
POST /api/v1/public/organizations/akshar-clinic/appointments
{
  "hold_id": "d6ce41ac-9cba-4df1-88d7-0acd21a17a31",
  "session_key": "demo-6fa0cc0e5a644f0d",
  "customer": {
    "full_name": "Priya Shah",
    "mobile": "+919876546388"
  }
}
```

`422`

```json
{
  "detail": "Please verify your contact details with the code we send you.",
  "code": "contact_not_verified"
}
```

With the token. The request below also sends `"total_amount_paise": 1`; the server ignores it and charges the
catalogue price (₹800):

```http
POST /api/v1/public/organizations/akshar-clinic/appointments
{
  "hold_id": "d6ce41ac-9cba-4df1-88d7-0acd21a17a31",
  "session_key": "demo-6fa0cc0e5a644f0d",
  "customer": {
    "full_name": "Priya Shah",
    "mobile": "+919876546388",
    "email": "priya@example.com"
  },
  "verification_token": "eyJhbGciOiJIUzI1NiIsInR…",
  "attribution": {"utm_source": "instagram", "utm_campaign": "monsoon-care", "entry": "website"},
  "total_amount_paise": 1
}
```

`201`

```json
{
  "id": "cfa566a0-b3ee-4075-a6f4-1c2b4b999dad",
  "reference": "APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1",
  "status": "pending_payment",
  "organization_slug": "akshar-clinic",
  "branch_name": "Navrangpura",
  "professional_name": "Dr. Kavya Shah",
  "service_name": "Ayurvedic Consultation",
  "customer": {
    "id": "f20055a0-b95e-48a4-bb21-c005034d50b8",
    "full_name": "Priya Shah",
    "mobile": "+919876573289",
    "email": "priya@example.com",
    "is_guest": true
  },
  "start_at": "2026-11-16T13:00:00Z",
  "end_at": "2026-11-16T13:30:00Z",
  "timezone": "Asia/Kolkata",
  "currency": "INR",
  "subtotal_paise": 80000,
  "discount_paise": 0,
  "tax_paise": 0,
  "total_amount_paise": 80000,
  "advance_due_paise": 80000,
  "paid_amount_paise": 0,
  "payment_due_at": "2026-11-14T12:41:17.822460Z",
  "can_cancel": true,
  "can_reschedule": true,
  "access_token": "EXAMPLE-booking-access-token-from-the-response"
}
```

Keep `reference` and `access_token`: they are the only way (besides signing in) to see or manage the booking.
The booking page sends the visitor to `/{clinic}/appointments/{reference}?t={access_token}`. The booking steps themselves live at `/{clinic}/book`; `/{clinic}` is the clinic website.

With a token for a different number than the one being booked:

`422`

```json
{
  "detail": "The verified contact does not match the details in this booking. Please verify again.",
  "code": "contact_not_verified"
}
```

`attribution` is optional: only `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `ref` and `entry`
with short lower-case values are kept, for reporting.

Other errors: `409 slot_unavailable`, `409 hold_expired`, `422 contact_verification_expired`,
`422 form_invalid` (booking-form answers), `422 login_required` (when the clinic turned guest booking off).

### Payment (own UPI QR)

`GET /appointments/{reference}/payment?access_token=` — `null` when nothing is due.

```http
GET /api/v1/public/organizations/akshar-clinic/appointments/APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1/payment?access_token=EXAMPLE-booking-access-token-from-the-response
```

`200`

```json
{
  "payment": {
    "reference": "PAY-AKSHAR-01M7CZG6E847ZDPPZ1V4C5ZXC9",
    "status": "awaiting_payment",
    "amount_paise": 80000,
    "currency": "INR",
    "expires_at": "2026-11-14T12:41:17.822460Z",
    "submitted_at": null,
    "verified_at": null,
    "appointment_reference": "APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1",
    "appointment_status": "pending_payment",
    "upi_id": "akshar.clinic@okhdfcbank"
  },
  "upi": {
    "account_name": "Clinic UPI",
    "upi_id": "akshar.clinic@okhdfcbank",
    "merchant_name": "Akshar Ayurveda Clinic",
    "instructions": "Pay the exact amount and keep the UTR number.",
    "is_static": false,
    "upi_uri": "upi://pay?pa=akshar.clinic@okhdfcbank&pn=Akshar%20Ayurveda%20Clinic&tr=PAY-AKSHAR-01M7CZG6E847ZDPPZ1V4C5ZXC9&tn=APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1&am=800.00&cu=INR",
    "qr_data_url": "data:image/png;base64,iVBORw0KGgo\u2026",
    "static_qr_url": null,
    "app_links": {
      "any": "upi://pay?pa=akshar.clinic@okhdfcbank&pn=Akshar%20Ayurveda%20Clinic&tr=PAY-AKSHAR-01M7CZG6E847ZDPPZ1V4C5ZXC9&tn=APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1&am=800.00&cu=INR",
      "gpay": "tez://upi/pay?pa=akshar.clinic@okhdfcbank&pn=Akshar%20Ayurveda%20Clinic&tr=PAY-AKSHAR-01M7CZG6E847ZDPPZ1V4C5ZXC9&tn=APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1&am=800.00&cu=INR",
      "phonepe": "phonepe://pay?pa=akshar.clinic@okhdfcbank&pn=Akshar%20Ayurveda%20Clinic&tr=PAY-AKSHAR-01M7CZG6E847ZDPPZ1V4C5ZXC9&tn=APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1&am=800.00&cu=INR",
      "paytm": "paytmmp://pay?pa=akshar.clinic@okhdfcbank&pn=Akshar%20Ayurveda%20Clinic&tr=PAY-AKSHAR-01M7CZG6E847ZDPPZ1V4C5ZXC9&tn=APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1&am=800.00&cu=INR",
      "bhim": "bhim://pay?pa=akshar.clinic@okhdfcbank&pn=Akshar%20Ayurveda%20Clinic&tr=PAY-AKSHAR-01M7CZG6E847ZDPPZ1V4C5ZXC9&tn=APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1&am=800.00&cu=INR"
    }
  },
  "can_submit": true,
  "latest_submission": null,
  "message": null
}
```

`POST /appointments/{reference}/payment/submit?access_token=` (multipart: `utr` required, optional
`screenshot`, `payer_upi_id`, `paid_at`, `notes`). The status becomes `submitted` and the appointment
`pending_verification`; staff verify it against the bank statement.

```http
POST /api/v1/public/organizations/akshar-clinic/appointments/APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1/payment/submit?access_token=EXAMPLE-booking-access-token-from-the-response
multipart/form-data: utr=412345678901 (+ optional screenshot file)
```

`200`

```json
{
  "payment": {
    "reference": "PAY-AKSHAR-01M7CZG6E847ZDPPZ1V4C5ZXC9",
    "status": "submitted",
    "amount_paise": 80000,
    "submitted_at": "2026-11-14T12:11:18.005475Z",
    "verified_at": null,
    "latest_utr": "412345678901",
    "appointment_status": "pending_verification"
  },
  "upi": "\u2026",
  "can_submit": false,
  "latest_submission": {
    "id": "f7c48a6b-4698-4468-816b-2ccc21c72e4a",
    "utr": "412345678901",
    "transaction_reference": null,
    "payer_upi_id": null,
    "payer_name": null,
    "paid_at": null,
    "claimed_amount_paise": 80000,
    "has_screenshot": false,
    "notes": null,
    "is_superseded": false,
    "created_at": "2026-11-14T12:11:18Z"
  },
  "message": "Thanks. The clinic is checking the payment with their bank. Your booking is confirmed once they verify it."
}
```

### Booking status

`GET /appointments/{reference}?access_token=` (also `/cancel` and `/reschedule`, same token, subject to the
clinic's cancellation settings).

```http
GET /api/v1/public/organizations/akshar-clinic/appointments/APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1?access_token=EXAMPLE-booking-access-token-from-the-response
```

`200`

```json
{
  "reference": "APT-AKSHAR-01M7CZG6DYF6ST1F1YC7Y1ZVZ1",
  "status": "pending_payment",
  "start_at": "2026-11-16T13:00:00Z",
  "service_name": "Ayurvedic Consultation",
  "professional_name": "Dr. Kavya Shah",
  "total_amount_paise": 80000,
  "paid_amount_paise": 0,
  "can_cancel": true,
  "can_reschedule": true
}
```

### Embed policy

`GET /embed-policy` — read by the web server to build the `frame-ancestors` header for `/embed/{clinic}`
(cached 60 s). Edited in **Admin → Booking page & Shopify** (`PUT /organizations/{id}/settings/embed`,
`{"values": {"allowed_origins": ["https://yourstore.com"]}}`, permission `organization:write`; only exact
`https://` origins, max 20).

```http
GET /api/v1/public/organizations/akshar-clinic/embed-policy
```

`200`

```json
{
  "allowed_origins": [],
  "booking_page_enabled": true
}
```

## Iframe messages

`/embed/{clinic}` posts `{"type": "appointment-booking:resize", "height": <number>}` to `window.parent` when its
height changes. It sends nothing else and accepts no messages. Check `event.origin` before using it.
