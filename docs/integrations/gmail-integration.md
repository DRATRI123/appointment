# Gmail

Send the clinic's emails (confirmations, reminders, cancellations, payment messages, sign-in codes) from the clinic's own
Gmail or Google Workspace address, through the official Gmail API (`users.messages.send`, scope `gmail.send`).

## Setup

1. The clinic's own Google Cloud app must be set up (Admin → Integrations → Google Cloud app, see
   [google-integration.md](google-integration.md)) with the Gmail API enabled and the `gmail.send` scope on its consent screen.
2. Admin → Integrations → **Gmail** → **Connect Google account** → sign in with the address that should send.
3. Enter your address under "Send a test email to" and press **Test connection**: a real email is sent.
4. "Send all clinic emails through Gmail" is on by default. Off = Gmail is used only for test emails.

## How it behaves

* Messages are sent by the worker (never inside a booking). If Gmail refuses (daily limit, expired access), the
  platform's default email provider sends the message instead (fallback), so patients still get it.
* Sender = the connected Google address. Reply-To = the clinic's reply address (Admin → Notifications settings).
* Delivery history: Admin → Notifications → each message shows which provider sent it.

## Limits

Google limits sending (about 2,000 messages a day for Workspace, about 500 for personal gmail.com) and may block bulk
sending. For large volumes use Amazon SES or Brevo ([email-providers.md](email-providers.md)).

Credentials: an encrypted refresh token; nothing is typed into the app. **Disconnect** revokes it at Google.
