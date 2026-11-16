# CRM: HubSpot and Zoho CRM

Each patient becomes a CRM contact; changes update the same contact; erasure on request deletes it. Optionally,
appointments are logged as notes on the contact ("Consultation with Dr. Mehta on 16 Nov 2026, 10:30. Status: confirmed").
Clinical notes, documents, booking-form answers and payment details are **never** sent.

## Field mapping (you choose)

| This app | HubSpot | Zoho CRM | Sent |
|---|---|---|---|
| Name (split into first / last) | firstname, lastname | First_Name, Last_Name | always |
| Mobile | phone | Mobile | if "Send mobile numbers" |
| Email | email | Email | if "Send emails" |
| City (address) | city | Mailing_City | if "Send city" |
| Appointment summary | note (associated, type 202) | Note on the contact | if "Log appointments" |

## Duplicates

1. The stored contact id (from an earlier sync) is used first.
2. Otherwise a search by email, then by phone; a match is updated.
3. Only then a new contact is created.

## HubSpot

HubSpot → Settings → Integrations → **Private apps** → create one with scopes `crm.objects.contacts.read`,
`crm.objects.contacts.write` (and notes write if you log appointments). Admin → Integrations → **HubSpot**: paste the
access token → Save → **Test connection** → **Send all existing records** for the first sync.

## Zoho CRM

1. https://api-console.zoho.in (or .com/.eu…) → **Server-based application**. Homepage = your site; Authorized redirect
   URI = the one shown on the Zoho CRM page (`…/api/v1/integrations/hub/zoho/callback`).
2. Admin → Integrations → **Zoho CRM**: data centre, client ID, client secret → Save → **Connect Zoho account**.
   The data centre is corrected automatically if Zoho says the account lives elsewhere.
3. API: Zoho CRM v7 (`/crm/v7/Contacts`, `/Contacts/search`, `/Contacts/{id}/Notes`). Scopes:
   `ZohoCRM.modules.contacts.ALL`, `ZohoCRM.modules.notes.ALL`, `ZohoCRM.users.READ`.

## Sync, retries, logs

Changes are queued and sent by the worker; temporary errors retry with growing waits up to the retry limit, then stop
("Retry" on the integration page). A revoked token marks the integration "Needs attention" and pauses its queue until you
reconnect. Every attempt is in the History table (30 days).
