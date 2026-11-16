# n8n automation

n8n receives events from the app and can ask the app to do a few approved things. n8n is never the database or the
booking engine: it cannot book, confirm, cancel, reschedule or verify payments.

## 1. Events from the app to n8n

1. In n8n add a **Webhook** node (method POST), activate the workflow and copy its **Production URL**.
2. Admin → Integrations → **n8n automation**: paste the URL, choose events (comma-separated or `*`), Save.
   Two secrets are shown **once**: copy them.
3. **Test connection** sends a signed `ping` and waits for n8n's answer.

Events: `appointment.created`, `appointment.confirmed`, `appointment.rescheduled`, `appointment.cancelled`,
`appointment.expired`, `appointment.checked_in`, `appointment.completed`, `appointment.no_show`, `customer.created`,
`customer.updated`, `customer.deleted`, `payment.submitted`, `payment.verified`, `payment.rejected`, `refund.processed`,
`schedule.updated`, `reminder.due`, `notification.failed`.

Each request has `X-Webhook-Id` (use it to ignore duplicates), `X-Webhook-Event`, `X-Webhook-Timestamp` and
`X-Webhook-Signature: t=<unix>,v1=<hex>`, where hex = HMAC-SHA256(secret, "<t>.<raw body>"). Retries: 1 min, 5 min,
30 min, 2 h, 6 h, 12 h, 24 h; history and safe redelivery in Admin → Developers → Webhooks.

Check the signature in an n8n **Code** node (raw body option on the Webhook node):

```js
const crypto = require('crypto');
const secret = $env.APPOINTMENT_WEBHOOK_SECRET;            // the outgoing secret
const header = $input.first().json.headers['x-webhook-signature'];
const raw = $input.first().binary?.data ? Buffer.from($input.first().binary.data.data, 'base64') : Buffer.from(JSON.stringify($input.first().json.body));
const [t, v1] = header.split(',').map(p => p.split('=')[1]);
const expected = crypto.createHmac('sha256', secret).update(`${t}.${raw}`).digest('hex');
if (expected !== v1 || Math.abs(Date.now() / 1000 - Number(t)) > 300) throw new Error('Bad signature');
return $input.all();
```

## 2. Actions from n8n to the app

POST to the **Request URL** shown on the n8n page (`/api/v1/automation/n8n/<id>`), body
`{"action": "...", "data": {...}}`, with headers:

* `X-Request-Id`: unique per request (8–80 letters/digits/`-_.:`). A repeated id is refused (409).
* `X-Webhook-Signature: t=<unix>,v1=<hex>` made with the **incoming** secret, same formula. Older than 5 minutes = 401.

| Action | data | Result |
|---|---|---|
| `get_appointment` | `appointment_id` or `reference` | the appointment (same shape as webhook events) |
| `create_follow_up` | `title`, optional `details`, `due_at`, `customer_id`, `appointment_id`/`reference` | a follow-up task (listed on the n8n page) |
| `send_notification` | `reference`, `event` = `appointment.confirmed`, `appointment.reminder`, `appointment.meeting_link` or `appointment.pending_payment` | the clinic's approved template is sent |
| `trigger_reminder` | `reference` | the reminder is sent now |
| `update_customer` | `customer_id`, `tags` and/or `communication_preferences` | only those fields change |

Only actions listed under "Actions n8n may perform" work (default: `get_appointment, create_follow_up`). Every action is
audit-logged ("n8n automation").

## Secrets

Stored encrypted, shown once. **Rotate secrets** creates new ones (shown once); the old ones stop at once.

## Troubleshooting

* Test fails with HTTP 404: the workflow is not active, or the Test URL was used instead of the Production URL.
* 401 from the app: wrong secret, clock difference over 5 minutes, or the body was changed after signing.
* 403 `action_not_allowed`: add the action in the n8n settings.
