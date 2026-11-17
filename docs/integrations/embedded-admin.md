# Admin panel inside your clinic app (embedded panel)

Your clinic's own app (for example your clinic software, where you write the case paper) can show this
appointment app's admin panel inside one of its pages. You see the calendar and appointments without leaving your app.
Both apps keep working on their own: they share no database and no data passes through your clinic app.

The super admin is not involved: the clinic admin sets it up.

## How it works

```
Your clinic app (https://myclinic.com)
┌──────────────────────────────────────────────┐
│ Patients   │  ┌─────────────────────────────┐ │
│ Case paper │  │ Appointment admin panel     │ │
│ Billing    │  │ (sign in first, then panel) │ │
│            │  └─────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

1. The clinic admin switches it on and adds the clinic app's address.
2. The clinic app shows `https://<appointment app>/panel/<clinic>` in an iframe.
3. The frame asks for a sign-in: email and password, plus the authenticator code if the person uses one.
4. The admin panel opens inside the frame.

## Set it up (clinic admin)

1. **Admin → Panel in your app** (also linked from Organization settings).
2. Turn on **Allow the panel inside my clinic app**.
3. Add the clinic app's address exactly as the browser shows it, without a path, for example
   `https://app.myclinic.com` (up to 5). While testing on your own computer, `http://localhost:5000` also works.
4. Press **Save**. The page asks you to confirm it is you, because this setting changes who can see what.
5. Copy the **code for your clinic app** and put it on a page of your app:

   ```html
   <iframe src="https://appointments.myclinic.com/panel/my-clinic" title="Appointments" style="width:100%;height:100vh;border:0"></iframe>
   ```

Nothing else is needed in your clinic app: no API key and no change to its database.

## Who can sign in

* Owners and organization administrators: they have the permission **"Open the admin panel inside the clinic's own
  app"** (`panel:use`).
* Other roles only if you give them that permission in **Roles & permissions** (custom role).
* People from other clinics cannot sign in, even with a correct password.
* If the clinic requires two-step sign-in for administrators, an administrator without it is asked to turn it on in the
  appointment app first.

## Safety

| Rule | How |
|---|---|
| Only your listed app can show the panel | The browser refuses every other website (`Content-Security-Policy: frame-ancestors`, set per clinic, only while the panel is on). Every other page of the app still refuses frames |
| The sign-in stays inside the panel | Its tokens are kept in that frame's session storage, **never in cookies**. Your clinic app cannot read them, and the panel never signs you in or out of the appointment app opened normally in the same browser |
| One clinic only | The server ties the sign-in to this clinic: it cannot open another clinic (even one the same person belongs to), create organizations or use super admin powers |
| Turn off at once | Switching the panel off, removing the address list or removing the permission closes open panels at their next click (checked by the server on every request) |
| Closing the tab signs the panel out | The tokens live only as long as that tab |
| Screen lock, watermark, "confirm it is you", masking | Work inside the panel as everywhere |
| Audit log | Every panel sign-in (`auth.panel_login`, with the clinic app's address) and every refused one (`auth.panel_login_refused`) |
| Separate session | Listed as "Clinic app panel" under Profile & security → devices; can be signed out from there |

## Where to host it (important for some browsers)

| Clinic app | Appointment app | Result |
|---|---|---|
| `https://myclinic.com` | `https://appointments.myclinic.com` | ✅ Best: everything works, including reloading the frame |
| `https://myclinic.com` | `https://myclinic.com/appointments` (same address through Nginx) | ✅ Works |
| `http://localhost:5000` | `http://localhost:3000` (testing) | ✅ Works |
| `https://myclinic.com` | `https://bookings-company.com` (different domain) | ✅ Sign-in and use work. If the browser blocks cookies in frames, reloading the frame (right-click → Reload frame) may show a blank frame: open the clinic app's page again |

Signing in does not depend on cookies, so it works in every modern browser.

## Performance

The frame loads straight from the appointment app's server, so your clinic app does no extra work. Moving between admin
screens inside the frame does not reload the page. The server check for panel sign-ins is one small settings read per
request.

## Troubleshooting

| What you see | Why / fix |
|---|---|
| Blank frame, browser console says `frame-ancestors` | The panel is off, or the address is not exactly the clinic app's address (scheme, sub-domain and port must match). Changes reach browsers within a minute |
| "Opens inside your clinic app" | The panel link was opened on its own. Use the normal sign-in at `/login` instead |
| "Admin panel is not switched on" | Admin → Panel in your app → switch it on and add the address |
| "This account cannot open the admin panel here" | The role has no `panel:use` permission, or the person belongs to another clinic |
| "This clinic requires two-step sign-in for administrators" | Turn on two-step sign-in in the appointment app (Profile & security), then sign in in the panel |
| Asked to sign in again | The tab was closed, you signed out, the session was idle too long, or the panel was switched off |

## Pieces

| Piece | File |
|---|---|
| Rules (who, which clinic, on/off) | `backend/app/services/panel_service.py` |
| Sign-in, second step, refresh, sign-out | `backend/app/api/v1/panel.py` (`/api/v1/panel/...`) |
| One-clinic limit on every request | `backend/app/api/deps.py` (`resolve_tenant`), `user_sessions.panel_organization_id` |
| Frame permission per clinic | `frontend/proxy.ts` (`panelOrigins`, `panelReturnPath`) |
| Panel sign-in page | `frontend/app/panel/[slug]/` |
| Tokens in the frame | `frontend/lib/panel-session.ts` |
| Settings screen | `frontend/app/admin/settings/panel/page.tsx` |
| Tests | `backend/tests/test_panel.py`, `frontend/e2e/embedded-panel.spec.ts`, `frontend/tests/unit/csp.test.ts` |
