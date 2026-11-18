# Patient help desk

Patients ask the clinic questions about a booking, payment, refund, report or anything else, and the clinic answers in
one place. No email inbox or WhatsApp chat to search through, and every request has a number, an owner and a status.

## For patients (clinic website → My bookings → Help)

1. Sign in with a one-time code (no password).
2. **Ask a question**: choose the topic, optionally the booking, write a title and the question, and attach a photo or
   PDF if useful (for example a payment screenshot). From a booking's page, **Need help with this booking?** opens the
   form with that booking chosen.
3. The clinic's answer appears in the conversation. The patient gets an email (and an in-app notice) saying there is a
   reply; the answer itself is read after signing in, because it can carry health details.
4. Reply to continue, or press **My question is answered** and rate the help from 1 to 5.

Patients see only their own requests (found by their verified mobile number or email) and never the clinic's
internal notes.

## For the clinic (Admin → Help desk)

* **Inbox**: Active, Overdue, Waiting for clinic, Waiting for patient, Solved, Closed, All; filter by who handles it
  (Mine, Unassigned) and topic; search by `#number`, title or patient name. Unread requests are highlighted.
* **Summary**: waiting for clinic, overdue, unassigned, assigned to me, average first-reply time (30 days), patient
  rating.
* **A request**: the conversation, attachments, and the reply box. Switch on **Internal note** for something only
  colleagues should see. **Send and mark solved** answers and closes the loop in one step.
* **Details**: status, priority (low / normal / high / urgent), who handles it, topic; the patient (link to their
  record) and the booking (link to it); asked, reply due, first reply, rating.

Whoever sends the first reply becomes the owner if nobody was assigned. New requests and patient replies notify the
owner, or everyone who answers requests if nobody owns it yet (Notifications → event "Patient request or reply").

### Statuses

| Status | Meaning | Becomes |
|---|---|---|
| Waiting for clinic (`open`) | New, or the patient replied | Waiting for patient when staff reply |
| Waiting for patient (`pending_customer`) | Staff answered | Waiting for clinic when the patient replies; Solved automatically after the close period |
| Solved (`resolved`) | Staff or the patient marked it solved | Reopened if the patient replies; Closed after the close period |
| Closed (`closed`) | Finished | Cannot be reopened: the patient asks a new question |

### Settings (Help desk → Settings, needs "organization settings")

* Patients can ask questions online (on by default).
* First-reply target in hours (default 24): requests not answered by then show as **Overdue**.
* Close solved requests after N days (default 7). The background worker applies it.

## Who can do what

| Permission | Roles by default | Allows |
|---|---|---|
| `helpdesk:read` | Owner, administrator, branch manager, receptionist, accountant | See requests |
| `helpdesk:write` | the same | Reply, add notes, assign, change status |

Staff of one branch see requests about that branch's bookings and general ones (not about one booking). Change roles
in Roles & permissions.

## Privacy and security

* Message text is encrypted in the database (AES-256-GCM). Attachments (PNG, JPEG, WebP or PDF, within the upload
  size limit, virus-scanned when a scanner is set up) are stored privately and encrypted, opened only through the app,
  and each opening is audit-logged.
* Notifications never contain the message text.
* Creating, replying, notes, status / owner changes and patient resolutions are in the audit log.
* Erasing a patient (Customers → Erase) deletes their requests and attachments.
* Limits: 10 new requests per hour per network, at most 10 open requests per patient, 4,000 characters per message.

## API

| Endpoint | Who |
|---|---|
| `GET/POST /customer/organizations/{org}/requests`, `GET /…/{id}`, `POST /…/{id}/messages`, `POST /…/{id}/resolve`, `GET /…/{id}/messages/{mid}/attachment` | Signed-in patient |
| `GET /helpdesk/summary`, `GET /helpdesk/agents`, `GET /helpdesk/tickets`, `GET/PATCH /helpdesk/tickets/{id}`, `POST /helpdesk/tickets/{id}/messages`, `GET /helpdesk/tickets/{id}/messages/{mid}/attachment` | Staff |

Messages are sent as multipart form data (`body`, optional `file`; staff also `internal`, `next_status`).

Code: `backend/app/services/helpdesk_service.py`, `backend/app/api/v1/helpdesk.py`; tests:
`backend/tests/test_helpdesk.py`, `frontend/e2e/helpdesk.spec.ts`.
