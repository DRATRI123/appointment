# Shopify and website integration

Put appointment booking on a Shopify store, or any website, **without installing or building a Shopify app**.
There is no embedded app, no OAuth, no custom app and no Shopify API key. Your store only links to, or frames,
the public booking page. The booking platform keeps doing everything that matters: availability, prices, mobile
verification, double-booking protection and UPI payment verification.

| Option | What visitors see | Shopify setup | Needs "Allowed websites"? |
|---|---|---|---|
| **1. Book button (snippet)** | A button that opens the booking page | Add one snippet, paste one line | No |
| **2. Theme section** | A section with heading, text and a button *or* the embedded page | Add snippet + section, then use the theme editor | Only for embedded mode |
| **3. Iframe embed** | The full booking flow inside your store page | Paste HTML into a *Custom Liquid* section | **Yes** |
| **4. Plain link** | Any link: menus, emails, Instagram bio, WhatsApp | Shopify *Navigation* or anywhere | No |

The admin screen **Admin → Booking page & Shopify** generates every piece of code below with your own address
and clinic filled in, and lets you pick a service, location or doctor to preselect.

---

## Public URL structure

```
https://<booking-site>/<clinic>                                        clinic website
https://<booking-site>/<clinic>/book                                   booking steps
https://<booking-site>/<clinic>/book?service=<service>                 service preselected
https://<booking-site>/<clinic>/book?branch=<branch>&doctor=<doctor>   location and doctor preselected
https://<booking-site>/<clinic>/book?service=consultation&date=2026-11-20
https://<booking-site>/<clinic>/book?utm_source=shopify&utm_campaign=diwali   with campaign labels
https://<booking-site>/<clinic>/<branch>                               a location's page
https://<booking-site>/<clinic>?service=<service>                      older links: forwarded to /<clinic>/book
https://<booking-site>/embed/<clinic>?…                           same flow without header/footer, for iframes
https://<booking-site>/<clinic>/appointments/<reference>?t=<token>  the customer's own booking (link sent to them)
```

Example for the demo clinic: `https://booking.mydomain.com/akshar-clinic/book?service=consultation`.

| Parameter | Alias | Accepts | Effect |
|---|---|---|---|
| `service` | | service slug or id | Skips the service step |
| `branch` | `location` | branch slug or id | Skips the location step |
| `doctor` | `professional` | doctor slug or id | Skips the doctor step |
| `date` | | `YYYY-MM-DD` | Opens the calendar on that day |

Rules the page follows:

* Parameters are **hints only**. A value is used when it matches something the clinic really offers; otherwise it
  is ignored and the visitor chooses. Values must be lower-case slugs (`a-z`, `0-9`, `-`, ≤ 80 characters).
* They **never** change price, availability or permissions. Any `price=`, `amount=` or `discount=` parameter is
  ignored, and the server recalculates the price for every booking (see the API guide).
* The visitor can always go back and change a preselected choice.
* Old links of the form `/o/<clinic>`, `/o/<clinic>/book`, `/o/<clinic>/services/<id>` and
  `/o/<clinic>/professionals/<id>` permanently redirect (308) to the new addresses and keep their query string.
* No patient data is ever placed in a public URL. The appointment page needs the reference **and** a random
  access token, and is marked `noindex`.

Find slugs under **Admin → Services / Branches / Professionals**, or use the dropdowns on the
*Booking page & Shopify* screen.

---

## Option 1: Book button (recommended)

1. Shopify admin → **Online Store → Themes → ⋯ → Edit code**.
2. Under **Snippets** → **Add a new snippet** → name it `appointment-booking-button`.
3. Paste the contents of [`integrations/shopify/snippets/appointment-booking-button.liquid`](../../integrations/shopify/snippets/appointment-booking-button.liquid)
   (also downloadable from the admin screen) and **Save**.
4. Paste this where the button should appear, e.g. in a product template, `main-page.liquid`, the header, or a
   *Custom Liquid* section in the theme editor:

```liquid
{% render 'appointment-booking-button',
  booking_url: 'https://booking.mydomain.com',
  clinic: 'akshar-clinic'
%}
```

All parameters:

```liquid
{% render 'appointment-booking-button',
  booking_url: 'https://booking.mydomain.com',  {%- comment -%} required, must be https {%- endcomment -%}
  clinic: 'akshar-clinic',                      {%- comment -%} required {%- endcomment -%}
  service: 'consultation',                      {%- comment -%} optional preselection {%- endcomment -%}
  branch: 'navrangpura',
  doctor: 'dr-meera-joshi',
  date: '2026-11-20',
  source: 'shopify',                            {%- comment -%} campaign labels (Website analytics) {%- endcomment -%}
  campaign: 'diwali-offer',
  label: 'Book a consultation',                 {%- comment -%} default "Book appointment" {%- endcomment -%}
  style: 'outline',                             {%- comment -%} solid (default) or outline {%- endcomment -%}
  new_tab: true                                 {%- comment -%} open booking in a new tab {%- endcomment -%}
%}
```

Colours: set the CSS variables `--ab-color` (button colour) and `--ab-ink` (text colour) on any parent element,
e.g. `<div style="--ab-color:#7c2d12;--ab-ink:#fff">{% render … %}</div>`. The theme section does this for you.

**Per-product booking.** To book the service that matches a product, store the service slug in a product
metafield (e.g. `custom.booking_service`) and pass it in:

```liquid
{% render 'appointment-booking-button',
  booking_url: 'https://booking.mydomain.com',
  clinic: 'akshar-clinic',
  service: product.metafields.custom.booking_service
%}
```

The snippet is safe with merchant-entered values: every value is cleaned on its own with `handleize` (so a
value cannot add extra parameters), the link must start with `https://`, everything is HTML-escaped, and if the
address or clinic is missing it renders nothing for visitors (and a warning in the theme editor).

## Option 2: Theme section (Online Store 2.0 themes)

1. Add the snippet from option 1.
2. Under **Sections** → **Add a new section** → name it `appointment-booking`, paste
   [`integrations/shopify/sections/appointment-booking.liquid`](../../integrations/shopify/sections/appointment-booking.liquid), **Save**.
3. **Customize** the theme → **Add section → Appointment booking**.
4. Fill in **Booking site address** (`https://booking.mydomain.com`) and **Clinic web address name** (`akshar-clinic`),
   optionally a service/location/doctor, heading, text and colours.
5. **Show as**: *Book appointment button*, or *Embedded booking page* (add your store to **Allowed websites**
   first, see below).

## Option 3: Iframe embed

1. **Admin → Booking page & Shopify → Allowed websites**: add every address the store is visited on, e.g.
   `https://yourstore.myshopify.com` and `https://yourstore.com`, then **Save**. Browsers pick up the change within
   about a minute.
2. In Shopify add a **Custom Liquid** section (or a page in HTML view) and paste the code from the admin screen:

```html
<iframe id="appointment-booking-akshar-clinic" src="https://booking.mydomain.com/embed/akshar-clinic" title="Book an appointment"
  style="display:block;width:100%;height:900px;border:0;border-radius:16px"
  loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>
<script>
  window.addEventListener("message", function (event) {
    if (event.origin !== "https://booking.mydomain.com" || !event.data || event.data.type !== "appointment-booking:resize") return;
    var h = parseInt(event.data.height, 10);
    if (h > 300 && h < 8000) document.getElementById("appointment-booking-akshar-clinic").style.height = h + "px";
  });
</script>
```

The embedded page posts `{ "type": "appointment-booking:resize", "height": <px> }` to the parent whenever its
height changes; the listener above accepts it only from the booking site's own origin. The script is optional: without
it the frame keeps its fixed height and scrolls.

**Why "Allowed websites" exists.** Every page of the booking site sends a `Content-Security-Policy:
frame-ancestors` header. Normal pages send `frame-ancestors 'none'` plus `X-Frame-Options: DENY`, so nobody can frame
them. `/embed/<clinic>` sends `frame-ancestors 'self' <your allowed websites>`, so only the stores you listed can frame
it. If the list is empty, or the policy cannot be loaded, embedding is refused (fail closed). This protects your
patients from click-jacking and look-alike sites.

Only `https://` addresses are accepted (exact host and optional port; no wildcards, paths or `http://`), up to 20.

## Option 4: Plain link

Use the link from the admin screen anywhere: Shopify **Online Store → Navigation**, a rich-text block, an email
campaign, WhatsApp, Google Business Profile, Instagram bio, or a QR code printed in the clinic.

---

## What stays on the booking platform

| Concern | Where it is enforced |
|---|---|
| Free slots, holds, double-booking prevention | FastAPI, row locks + unique constraints (tests: `test_races.py`) |
| Price, discount, tax, advance amount | FastAPI calculates from the catalogue; client values ignored |
| Mobile number verification (one-time code) | FastAPI, token bound to clinic + held slot + number, 30 min |
| Rate limits & OTP abuse | Per clinic policy (per destination, IP and session), platform cap per destination, cool-down, attempt lockout; codes by SMS, WhatsApp or email |
| Payment | Your own UPI QR. A QR, UTR or screenshot never confirms a payment; only authorised staff can verify |
| Customer data | Never in the Shopify theme, never in public URLs |

Shopify never receives booking or patient data, and the booking platform never receives Shopify data.

## CORS and secrets

* **Do not add your Shopify domain to `CORS_ORIGINS`.** The store never calls the API directly: the button is a
  link, and the iframe runs the booking site on its own origin. CORS should list only your booking site's own
  frontend origin(s).
* There is nothing secret in the snippet, section or iframe code. Never paste an API key, staff login or webhook
  secret into a Shopify theme. Server-to-server integrations use the Developer API keys described in `api.md`.

## Testing a theme change

* Use **Customize → Preview** or an unpublished theme copy first.
* Open the booking page from the store on a phone: the button, preselected service and the full flow (code → review
  → UPI payment screen) should work.
* For the iframe, the browser console must not show `Refused to frame … frame-ancestors`. If it does, the exact
  address in the address bar (including `www.`) is missing from **Allowed websites**.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Button not shown on the storefront | `booking_url` must start with `https://` and `clinic` must be set. The theme editor shows a red notice when a value is missing. |
| Embedded page blank / "refused to connect" | Add the store's exact origin under **Allowed websites**, save, wait a minute, reload. |
| Wrong service preselected | Use the slug from the admin dropdown; unknown values are ignored silently. |
| Frame has an inner scrollbar | Add the resize `<script>` and check its origin matches the booking site exactly. |
| "Online booking is paused" | Switch it back on under **Organization settings → General → Booking page enabled**. |

Automated checks: `backend/tests/test_shopify_liquid.py` renders the snippet and section with python-liquid
(link building, preselection, rejected settings, injection attempts, schema), `frontend/tests/unit/embed-code.test.ts`
covers generated code, and `frontend/e2e/public-booking.spec.ts` checks the frame headers in a real browser.
