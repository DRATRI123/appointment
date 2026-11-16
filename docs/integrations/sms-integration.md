# SMS providers

Used for mobile sign-in codes, booking confirmations, reminders, cancellations and reschedules (text per message:
Admin → Notifications → Templates).

| Provider | Use | Settings |
|---|---|---|
| MSG91 (India, DLT) | all SMS | auth key, sender ID, DLT flow/template id on each template |
| Twilio | all SMS | account SID, auth token, from number or Messaging Service SID |
| Amazon SNS | all SMS | region, access keys, sender ID, DLT entity ID, DLT template ID per template |
| 2Factor.in | **sign-in codes only** | API key, OTP template name |

Where: Super admin → Integrations → SMS (platform default) or `.env` (`SMS_PROVIDER`, `MSG91_*`, `TWILIO_*`,
`AWS_*`, `SNS_SENDER_ID`, `DLT_ENTITY_ID`, `TWOFACTOR_API_KEY`, `SMS_FALLBACK_PROVIDER`). A clinic can use its own
MSG91 or Twilio account for sign-in codes: Admin → Settings → OTP & verification.

## India: DLT

Transactional SMS in India must use a DLT-registered sender ID (header) and a template approved on the DLT portal, with
the variables in the same order. Put the template ID on each SMS template (Admin → Notifications → Templates →
"Provider template id"). Amazon SNS sends the entity and template IDs as the `AWS.MM.SMS.EntityId` and
`AWS.MM.SMS.TemplateId` attributes. An SMS whose text does not match the approved template is dropped by the operator.

## 2Factor

Only the sign-in-code API (`/API/V1/{key}/SMS/{number}/{code}/{template}`) is used, because 2Factor's transactional-SMS
API parameters could not be confirmed from official documentation. Other SMS through 2Factor are refused with a clear
error; set a **fallback provider** (e.g. MSG91) for them.

## Delivery and fallback

Retries and fallback work as for email ([email-providers.md](email-providers.md)). Delivery reports from MSG91, Twilio
and SNS are not received yet: "sent" means the provider accepted the message.

## Testing

Super admin → Integrations → SMS → "Send a test SMS to" → Test connection (a real SMS; DLT rules apply to the text).

## The clinic's own account sends all its messages

When a clinic sets up its own SMS account (Admin → Settings → OTP & verification) and switches it on,
it sends **all** of that clinic's SMS messages: sign-in codes, confirmations, reminders, cancellations, reschedules and
payment messages. If the clinic's account fails, the platform's default provider (super admin) sends the message instead.
