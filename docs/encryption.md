# Encryption

What is protected, with what, and how to handle the keys. Short version: **passwords cannot be recovered by anyone**,
**the most sensitive fields are encrypted inside the database**, **backups are encrypted**, and **everything on the
network is HTTPS**. The keys live only in the server's `.env` and in your password manager.

## In transit

* Browsers → Nginx: HTTPS only, TLS 1.2/1.3 with forward-secret AEAD ciphers. HTTP redirects to HTTPS, and HSTS tells
  browsers never to use plain HTTP again (`deployment/nginx/snippets/tls.conf`). Cookies are `Secure`, `HttpOnly`
  where possible, and `SameSite`.
* Nginx → API → PostgreSQL/Redis: inside Docker networks on the same server, never on the internet. PostgreSQL
  passwords use SCRAM-SHA-256.
* App → message providers, webhooks, calendars: HTTPS with certificate checks (a Semgrep rule fails CI if anyone
  turns verification off).

## At rest, inside the database (application-level encryption)

AES-256-GCM with `DATA_ENCRYPTION_KEY`: every value gets its own random 96-bit nonce, and the key id is bound to the
ciphertext (`enc:v2:<key id>:...`). A modified value or an unknown key raises an error. It never returns garbage, and
it never silently stores plain text: servers refuse to start without a valid key.

Encrypted fields:
* clinical notes;
* calendar and video integration credentials;
* each clinic's own SMS/email/WhatsApp provider secrets;
* webhook signing secrets;
* two-step sign-in secrets;
* stored idempotent responses (they can contain a booking's access token).

Hashed, never reversible:

| What | How |
|---|---|
| Passwords | Argon2id (time cost 3, 64 MiB memory) |
| One-time codes | HMAC with `OTP_PEPPER`, bound to the challenge and the destination (a hash copied to another row is useless) |
| Refresh tokens, API keys, two-step backup codes | keyed hashes |

## Backups

Encrypted with `BACKUP_ENCRYPTION_KEY` (AES-256-GCM in authenticated 1 MiB chunks; a truncated or reordered file is
rejected). Production refuses to start without it. See [backup-restore.md](backup-restore.md).

## Disks

* **Windows PC:** turn on BitLocker for the drive that holds `backend\data\` and `backend\uploads\`.
* **Server:** use the provider's encrypted volumes, or LUKS. SQLCipher (an encrypted SQLite file) was evaluated and not
  adopted: it needs a separately built driver on every PC and does not apply to PostgreSQL. The application-level
  encryption above protects the most sensitive fields even in a copied database file.

## Keys

| Key | Used for | If lost | If leaked |
|---|---|---|---|
| `DATA_ENCRYPTION_KEY` | encrypted fields | those fields are unreadable forever | rotate it (below) |
| `BACKUP_ENCRYPTION_KEY` | backups | backups are unreadable forever | rotate, then take a new backup; old backups stay readable with the old key |
| `SECRET_KEY` | signing sign-in tokens | everyone signs in again | change it: every session ends |
| `OTP_PEPPER` | one-time code hashes | codes in flight stop working | change it |
| `METRICS_TOKEN` | Prometheus access | set a new one | set a new one |

`deploy.sh` generates every key at random for each server. **Copy `DATA_ENCRYPTION_KEY` and `BACKUP_ENCRYPTION_KEY`
into a password manager**, off the server. Never send keys by email or chat, and never commit them (Gitleaks checks
every commit). Keys are never logged.

### Rotating `DATA_ENCRYPTION_KEY` (no downtime)

1. Back up: `deployment/scripts/backup.sh`.
2. Generate a new key: `python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`.
3. In `.env`, put the new key in `DATA_ENCRYPTION_KEY` and the old one in `DATA_ENCRYPTION_PREVIOUS_KEYS`.
   Restart: `docker compose up -d api worker`. Everything keeps working: old values are read with the old key, and new
   values use the new one.
4. Re-encrypt everything with the new key:
   * `docker compose run --rm api python -m app.ops.rotate_keys --dry-run` (counts only);
   * then the same without `--dry-run`. It works in batches and can be stopped and run again.
5. When it reports nothing left, remove the old key from `DATA_ENCRYPTION_PREVIOUS_KEYS` and restart.
