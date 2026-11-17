# Integration troubleshooting

Start at Admin → Integrations: a card says **Needs attention** with the last error. Open it: **History** shows every
test, sign-in and sync with the exact answer from the provider; **Synchronisation** lists records that could not be
sent, with Retry.

| Symptom | Cause and fix |
|---|---|
| Status stays "Not tested yet" | Press **Test connection**; Connected is shown only after a real test |
| "Not connected" for Google/Zoho | Press **Connect …** and finish the sign-in |
| Needs attention, "revoked or has expired" | The account owner removed access or changed the password: **Reconnect** |
| Google: "Add your clinic's Google Cloud app first" | Admin → Integrations → Google Cloud app (each clinic has its own; the super admin key is only for Sign in with Google) |
| Google: `redirect_uri_mismatch` | Add the redirect URI shown on the Google Cloud app page to the clinic's OAuth client |
| Google: "unverified app" warning | Your Google app is not verified yet; add test users or request verification |
| Zoho: `invalid_client` | Wrong client ID/secret or wrong data centre; the redirect URI must match exactly |
| HubSpot 401 | The private app token was rotated or lacks the contacts scopes |
| Records "stopped" | The provider refused them permanently (e.g. invalid email). Fix the record, then Retry |
| n8n test: HTTP 404 | Workflow not active, or Test URL used instead of Production URL |
| n8n action: 401 / 409 | Signature or clock wrong / the X-Request-Id was used before |
| WhatsApp reports not arriving | Callback URL, verify token, app secret, and the "messages" subscription in Meta |
| Emails not sent with Gmail | Daily Gmail limit reached: the platform provider sends them meanwhile |
| S3 test: "bucket does not exist" / "region is wrong" | Check bucket name and region (R2 region: `auto`) |
| S3 test: "access denied" | The key needs get, put, delete and list on the bucket |
| Storage move "failed" | Read the error, fix (often permissions or disk), press the button again: it continues |
| "Real message providers cannot be chosen in the test environment" | Expected: tests and development computers never send real messages (`DEV_ALLOW_REAL_MESSAGES=true` on purpose only) |
| "On a server, 'console' would only write messages to the log" | Choose a real provider or `disabled` |
| Panel value ignored | A panel value always wins; check the field label (saved here / from .env) |
| Sentry not reporting | Restart the API and worker after saving |
| Admin panel inside the clinic app is blank or asks to sign in again | See [embedded-admin.md](embedded-admin.md#troubleshooting) |
