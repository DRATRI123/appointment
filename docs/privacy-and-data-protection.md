# Privacy and data protection

How the platform protects patient information: what is encrypted, who can see what, what can leave the system, and
what no software can prevent. Clinic administrators change the rules in **Admin → Settings → Privacy & data
protection**. The server enforces every rule. The website only shows the result, because anything sent to a browser
can be read by whoever controls that browser.

> **Honest limits.** No system is risk-free. A website **cannot stop screenshots**, screen recording, a photo of the
> screen, or a person copying what they are allowed to see. The protections below make leaks less likely, smaller
> and traceable. They do not make them impossible.

## 1. What is encrypted

| Data | Protection | Where |
|---|---|---|
| Everything on the network | HTTPS (TLS 1.2/1.3), HSTS, secure cookies | Nginx, [encryption.md](encryption.md) |
| Clinical notes | AES-256-GCM, per-value nonce, key id in the value | `customer_notes.body` |
| Family member notes | AES-256-GCM | `customer_dependents.notes` |
| Sensitive booking-form answers (fields marked sensitive) | AES-256-GCM per answer | `booking_form_responses.answers` |
| Payer UPI ID and payer name on payment submissions | AES-256-GCM | `payment_submissions` |
| Uploaded files: patient documents, payment screenshots, other private files | AES-256-GCM per file (`APENC1` format), own sub-key | private storage |
| Provider, calendar, webhook and two-step sign-in secrets | AES-256-GCM | several tables |
| Backups | AES-256-GCM in authenticated chunks, separate `BACKUP_ENCRYPTION_KEY` | [backup-restore.md](backup-restore.md) |
| Passwords | Argon2id, cannot be reversed | `users.password_hash` |
| One-time codes (OTP) | keyed hash with `OTP_PEPPER`; the code itself is never stored | `otp_codes` |
| Refresh tokens, API keys, backup codes | keyed hashes | several tables |
| Audit history | each row signed (HMAC), and on PostgreSQL it cannot be changed or deleted | `audit_logs.signature` |

**Key separation.** Files, audit signatures and download links each use their own key derived from
`DATA_ENCRYPTION_KEY` with HKDF-SHA256. A leaked download-link key cannot decrypt files. Backups use a different key
altogether. Rotation re-encrypts fields, form answers **and files**:
`python -m app.ops.rotate_keys --dry-run` first, then without `--dry-run` ([encryption.md](encryption.md)).

**Existing data.** The first start after the upgrade encrypts existing rows and files once (`app/ops/setup.py`,
marker `privacy.encrypted_at_rest_v1`). Old unencrypted files stay readable until then, and nothing is deleted.
Back up first: deploy.sh does this before every migration. On Windows, run `START-APP.bat`.

**Not encrypted, on purpose.**

| Data | Why not | How it is protected instead |
|---|---|---|
| Patient name and mobile number | needed for search, duplicate checks and booking matching | masked for staff (below); access audited |
| UPI transaction reference (UTR) | needed to match bank statements | visible only with payment permissions |
| Appointment times and services | needed for the calendar and double-booking protection | tenant and branch isolation |

## 2. Who can see what

The server checks permissions, the clinic (organization) and the branch on every request. A guessed ID from another
clinic gives "not found". Full table: [permissions-matrix.md](permissions-matrix.md).

| Data | Owner | Admin | Branch manager | Doctor | Professional | Receptionist | Accountant | Staff | Patient |
|---|---|---|---|---|---|---|---|---|---|
| Patient list and profile | ✓ | ✓ | ✓ (own branch) | own patients* | own patients* | ✓ | – | – | own only |
| Full mobile and email | Show† | Show† | Show† | Show† | Show† | Show† | – | – | own only |
| Clinical notes, documents, sensitive form answers | ✓ | ✓ | – | ✓ | – | – | – | – | own answers |
| Payments and UPI submissions | ✓ | ✓ | ✓ | – | – | ✓ | ✓ | – | own only |
| Approving payments | ✓ | ✓ | ✓ | – | – | – | ✓ | – | – |
| Patient export (CSV) and summary PDF | ✓ | ✓ | – | – | – | – | – | – | – |
| Report exports | ✓ | ✓ | ✓ | – | – | – | ✓ | – | – |
| Audit history | ✓ | ✓ | – | – | – | – | ✓ | – | – |

\* With **Doctors see only their own patients** on (the default), doctors and professionals without full appointment
access see only patients they have an appointment with.
† **Show** = masked by default (`+9198111XXXXX`, `ash***@example.com`). Pressing Show is checked on the server, may
ask "confirm it is you", and is written to the audit log.

API responses never contain password hashes, code hashes, token hashes, encryption keys or provider secrets. A test
walks every API response schema to prove it (`test_no_api_response_can_contain_secrets_or_hashes`). Edits ignore
a masked value sent back unchanged, so saving a form never overwrites a real number with `XXXXX`.

## 3. Screens that show sensitive data

| Screen | What it shows | Protection |
|---|---|---|
| Admin → Customers (list) | names, masked contacts | watermark, masking, bulk-access alert |
| Customer record | profile, family, appointments; notes and documents for clinical roles | watermark, masking + Show, audit of every opening |
| Appointments, calendar, payments, refunds | patient names, masked mobile | watermark, branch scope |
| Booking-form answers on an appointment | answers; sensitive ones only for clinical roles | encrypted, "Hidden: clinical access needed" otherwise |
| Documents | file contents | 60-second personal link, confirmation, audit, export limit |
| Staff, roles, privacy settings | staff accounts | confirmation before changes |
| Patient area (`/customer`) | the patient's own data | not masked, no watermark: it is their own information |

## 4. What can leave the system (exports)

| Export | Who | Checks |
|---|---|---|
| Patients CSV | `customers:export` | confirm it is you, row limit, daily limit, audit |
| Patient summary PDF | `customers:export` | confirm it is you, daily limit, **watermark on every page**, confidentiality footer, audit; full contacts only with `customers:reveal` |
| Documents | `customers:clinical_read` | confirm it is you, a link that works **for 60 seconds**, only for that person in that sign-in session, access checked again when opened, audit |
| Reports (CSV/XLSX) | `reports:export` | confirm it is you when the report has personal data, row and daily limits, audit |
| Reconciliation CSV | reconciliation permissions | daily limit, audit |
| Platform organizations export | super admin | confirm it is you, limit, audit |

Defaults: 20 exports per person per day, 10,000 rows per export (Admin → Settings → Privacy). There are no public or
permanent links to private files.

**Unusual access.** One person opening more than 60 patient records in an hour raises an alert (`BulkPatientRecordAccess`
in `deployment/monitoring/alerts.yml`). Above 300, opening more is refused until the hour passes. Export spikes,
repeated failed confirmations and infected uploads also raise alerts.

## 5. Screenshot and copy deterrence (what is implemented)

| Measure | Details |
|---|---|
| Dynamic watermark | faint, diagonal, repeating: `U-XXXXXXXX · clinic · date time · S-XXXXXX` (account and session references, **no name, email or number**). Strength 0.03–0.3. Updates every minute. Hidden from screen readers and never takes clicks. |
| Watermarked PDF | every page of the patient summary carries the watermark and a confidentiality footer |
| Confidentiality notice | at the foot of every staff screen |
| Printing | clinic chooses: allow, warn (default) or print only a notice. Sidebar and header never print. **Every print attempt is recorded** (`privacy.print_attempt`, page path only). |
| Screen lock | after 15 minutes without use (per-role times, for example 10 for receptionists), or as soon as the tab is hidden. While locked, **the page content is removed** and the server refuses every request until the password, authenticator code or a sent code is given. |
| Confirm it is you | before Show, exports, documents, staff/role/key/UPI changes, privacy and security settings. Valid for 10 minutes by default. |
| Sessions | inactive devices are signed out after 12 hours (`SESSION_IDLE_MINUTES`). Admins see each staff member's devices and can **sign out everywhere**; super admins can do it for any account. |
| No caching | private API answers carry `Cache-Control: no-store`. Nothing sensitive is kept in browser storage or in URLs. |

The super admin pages have no clinic selected, so a clinic's lock and watermark settings do not apply there. They are
protected by required two-step sign-in, "confirm it is you" before sensitive changes, and the idle sign-out.

## 6. What is technically impossible

* **Stopping screenshots or screen recording in a browser.** Operating systems (Windows Snipping Tool, macOS, Android,
  iOS) capture the screen outside the page's control. No JavaScript can detect or block this reliably.
* **Stopping a phone camera** pointed at the screen.
* **Hiding data from someone who may see it.** A person allowed to see a record can copy it by hand, and browser developer
  tools can read anything the page received. This is why masking and permissions are enforced on the server, so the
  page never receives what the person may not see.
* **Stopping "Save as PDF"** from the browser print dialog. "Print only a notice" covers normal printing; the attempt is
  still recorded.
* **Watermarks can be cropped or edited** out of an image. They discourage leaks and help find their source; they are
  not proof against a determined person.

**Native apps (future).** An Android app could set `FLAG_SECURE`, which blocks screenshots and hides the app in the
recent-apps view on most devices. iOS does not allow blocking screenshots; an app can only detect that one was taken,
or hide content while the screen is being recorded. Neither helps against a camera. There is no native app today.

## 7. Files, database and audit

* Private files are encrypted and never served from the public media folder. Uploads are checked by type, size and
  content. Optional virus scanning: `UPLOAD_SCANNER=clamav` with the `antivirus` compose profile; when the scanner is
  unreachable, uploads are refused rather than accepted unscanned.
* The SQLite file (Windows/local) lives in `backend/data/`, never in a public folder. Turn on BitLocker on that drive.
* Audit history records sign-ins, record openings, Show, document views and downloads, exports, prints, screen locks,
  confirmations, appointment, payment, permission and settings changes, session revocations and super admin actions.
  It never records passwords, OTPs, keys, tokens or full contact details (contact changes are stored masked).
* Integrity: `python -m app.ops.verify_audit` checks every signature (exit code 1 if a row was altered). On
  PostgreSQL, a trigger refuses UPDATE and DELETE on `audit_logs`.
* Backups are encrypted; `python -m app.ops.backup verify <file>` checks one can be opened and read ([backup-restore.md](backup-restore.md)).

## 8. Tests that prove this

| Area | Tests |
|---|---|
| Encryption of files, form answers, notes, payer fields; rotation; migration of existing data | `backend/tests/test_privacy_encryption.py` |
| Masking, Show, confirmation, lock, idle sign-out, sign out everywhere, export limits, PDF watermark, signed links, bulk detection, audit signatures and append-only, no-store, no secrets in responses, privacy settings validation, virus scan, print audit | `backend/tests/test_privacy_access.py` |
| Confirm-and-retry, shared dialog, lock handling, masked-value detection | `frontend/tests/unit/privacy.test.ts` |
| In the browser: masked list, Show, call links, watermark, PDF download, lock screen with wrong and right password, privacy settings page | `frontend/e2e/privacy.spec.ts` |

Security tests use generated test data only, never real patient data or production credentials.
