# WhatsApp Business

Only the official WhatsApp Business Platform is supported: Meta's **WhatsApp Cloud API**, or **Twilio** (an authorized
provider). Unofficial WhatsApp Web automation is not used and will not be added (it breaks WhatsApp's terms and gets
numbers banned).

## Messages

Sign-in codes, appointment confirmations, reminders, cancellations, reschedules, payment instructions, meeting links,
follow-ups. Outside the 24-hour window after a patient writes, WhatsApp only delivers **approved templates**.

## Setup (Meta Cloud API)

1. Meta Business Manager → WhatsApp Manager: add the phone number, create a **System user** with a permanent token
   (`whatsapp_business_messaging`, `whatsapp_business_management`).
2. Super admin → Integrations → WhatsApp: provider `meta`, **WhatsApp Business Account ID**, **Phone number ID**,
   **Access token**, **App secret**, a long random **Webhook verify token**. Save.
3. Meta App → WhatsApp → Configuration → Callback URL: `https://<your site>/api/v1/webhooks/whatsapp`, Verify token: the
   same text. Subscribe to the **messages** field.
4. **Show approved templates** lists your templates; put `name:language` (e.g. `appointment_reminder:en`) on each
   WhatsApp template in Admin → Notifications → Templates, and the sign-in template under "Approved sign-in code template".

Clinics can bring their own WhatsApp number for sign-in codes: Admin → Settings → OTP & verification.

## Delivery reports, read status, opt-out

* The webhook is accepted only with a valid `X-Hub-Signature-256` (HMAC-SHA256 with the app secret).
* `sent`, `delivered`, `read`, `failed` reports are added to the message's delivery log; "read" sets the read time,
  "failed" marks the message failed with WhatsApp's reason.
* Consent: patients opt in when booking (recorded with time and source). A reply of **STOP** (or UNSUBSCRIBE) turns
  WhatsApp off for that number; **START** turns it back on. Both are audit-logged.

## Retries

Temporary errors retry (1, 2, 4, 8 minutes); template or number errors stop at once with the reason.

## Limits

Meta limits business-initiated conversations per day by your number's quality tier, and charges per conversation.
Delivery reports for Twilio WhatsApp are not received yet.
