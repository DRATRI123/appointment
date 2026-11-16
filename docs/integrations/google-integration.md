# Google: Calendar, Meet, Sign-in, Contacts, Drive (and Gmail)

Two separate Google apps, on purpose:

* **Platform (super admin)**: one OAuth client used **only** for the "Sign in with Google" button.
* **Clinic (admin)**: each clinic creates its **own** Google Cloud app. All of that clinic's Google connections (each
  doctor's Calendar and Meet, Gmail, Contacts, Drive) use it. The platform's key is never used for them.

## 1. Sign in with Google (once, super admin)

Google Cloud Console → Credentials → OAuth client ID → Web application, with Authorized JavaScript origin = your site
(e.g. `https://book.yourclinic.com`). Super admin → Integrations → **Google sign-in**: client ID (the secret is optional;
with it, Test asks Google to check the ID) → Save → Test. Or `GOOGLE_CLIENT_ID` in `.env`.

## 1b. The clinic's Google Cloud app (each clinic, once)

1. Google Cloud Console → new project → **Enable APIs**: Google Calendar API, Gmail API, People API, Google Drive API
   (only the ones the clinic uses).
2. **OAuth consent screen**: External, the clinic's name, support email and domain; add the scopes below.
3. **Credentials → OAuth client ID → Web application**, Authorized redirect URI
   `https://<your site>/api/v1/integrations/google/callback` (shown on the page).
4. Admin → Integrations → **Google Cloud app**: client ID and secret → Save → **Test connection**.

Then connect Calendar (per doctor), Gmail, Contacts or Drive. Tokens remember which app issued them: if the clinic
replaces its Google app, its Google connections must be connected again (the cards say so).

Google review: Gmail send, Contacts and Calendar are "sensitive" scopes. Until Google verifies the clinic's app, only test
users added on its consent screen can connect (max 100), and they see an "unverified app" warning.

## 2. Google Calendar + Meet (each doctor)

Admin → Integrations → **Calendar & video** → the doctor's card → **Connect Google Calendar**.

* Confirmed bookings become events; reschedules update them; cancellations delete them. The event id is stored
  (`appointment_external_events`) so there is never a second event.
* **Choose the calendar**: "Change" next to Calendar lists calendars the doctor can write to (connections made before
  this feature need one reconnect, because the calendar-list permission is new).
* Online consultations get a **Google Meet** link (Calendar conference API), saved on the appointment and sent to the
  patient by email and WhatsApp (message "Online consultation link"); it is updated when the appointment changes.
* The doctor's other events block booking slots (busy time is read every 10 minutes; titles are not stored).
* Expired or revoked access: the card shows "Needs reconnecting"; bookings continue normally.
* The appointment database is the source of truth: Google never confirms or creates an appointment.

Scopes: `openid`, `email`, `calendar.events`, `calendar.calendarlist.readonly`.

## 3. Sign in with Google

Appears on the sign-in page as soon as the platform has a Google sign-in client ID (super admin). The ID token is checked on the server
(Google's keys, audience = your client ID, issuer, verified email). Accounts are linked by verified email; an account
already linked to a **different** Google account is refused (no silent takeover). Two-step sign-in still applies.

## 4. Google Contacts (clinic)

Admin → Integrations → **Google Contacts** → Connect Google account. Each patient becomes one contact (name, and mobile
and email if ticked). Before creating, it searches for the same number or email (no duplicates). Edits update the same
contact; erasure on request deletes it. Notes, documents and payments are never sent. Scope: `contacts`.

## 5. Google Drive (clinic, optional)

Admin → Integrations → **Google Drive** → Connect. A copy of each new patient document goes into a private folder
("Patient documents") in the connected account. Scope `drive.file`: the app can only see files it created. Nothing is
shared: no sharing permission is ever created. Deleting the document here deletes the Drive copy. Access inside this app
still requires clinical permission. Needs `customers:clinical_write`.

Be aware: the Drive copy is readable by whoever has that Google account. Use a clinic account with two-step
verification.

## 6. Gmail

See [gmail-integration.md](gmail-integration.md).

## Troubleshooting

| Message | Fix |
|---|---|
| "Add your clinic's Google Cloud app first" | Admin → Integrations → Google Cloud app (client ID, secret, Test) |
| "This connection was made with a different Google app" | The clinic changed its Google app: connect again |
| `redirect_uri_mismatch` on Google's page | Add the exact redirect URI shown in the panel to the OAuth client |
| "Access to … was not granted" | Connect again and tick the permission box Google shows |
| "Google did not return a refresh token" | Remove the app at myaccount.google.com/permissions, connect again |
| "Connect Google again to choose a calendar" | The connection predates calendar choice: press Reconnect |
