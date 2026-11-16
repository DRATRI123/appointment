# Email providers

Emails: sign-in codes, account verification, confirmations, reminders, cancellations, reschedules, password reset,
payment messages, and staff/admin notices. Text of each message: Admin → Notifications → Templates (test, preview,
reset). Credentials are never in the website code.

## Choose a provider

| Provider | Where to set it | Needs |
|---|---|---|
| SMTP (any mail server, Gmail SMTP, Zoho Mail…) | Super admin → Integrations → Email, or `.env` | host, port, security, user, password, sender |
| Brevo (transactional API) | same | API key (Brevo → SMTP & API → API keys, not the SMTP key), verified sender |
| Amazon SES (API v2) | same | region, access key, secret key, verified sender identity |
| Gmail (clinic's own) | Admin → Integrations → Gmail | Google sign-in ([gmail-integration.md](gmail-integration.md)) |
| Clinic's own SMTP for sign-in codes | Admin → Settings → OTP & verification | the clinic's SMTP details |

`.env` names: `EMAIL_PROVIDER` (`console`, `smtp`, `brevo`, `ses`, `disabled`), `EMAIL_FROM`, `SMTP_*`,
`BREVO_API_KEY`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `EMAIL_FALLBACK_PROVIDER`.

## Fallback

Set a **fallback provider**: when the main one fails, the same message is tried once with the fallback. The delivery
log records which one sent it.

## Testing

Super admin → Integrations → Email → "Send a test email to" → Test connection. A real email is sent.
On a development computer real providers are blocked unless `DEV_ALLOW_REAL_MESSAGES=true`; in tests they are always
console. On a server "console" is refused.

## Delivery status and retries

Each message has a status (pending, sent, failed, cancelled) and a log of attempts. Temporary failures retry after 1, 2,
4 and 8 minutes (`NOTIFICATION_MAX_ATTEMPTS`). A message that finally fails raises the n8n/webhook event
`notification.failed`.

## Amazon SES notes

Start in the SES sandbox (only verified recipients) and request production access. The sender must be a verified
identity in the same region. The access key needs `ses:SendEmail`.

## The clinic's own account sends all its messages

When a clinic sets up its own email account (Admin → Settings → OTP & verification, or Gmail in Integrations) and switches it on,
it sends **all** of that clinic's email messages: sign-in codes, confirmations, reminders, cancellations, reschedules and
payment messages. If the clinic's account fails, the platform's default provider (super admin) sends the message instead.
