# Troubleshooting

Find the symptom, try the fix. Error messages from the app always say what to change, and staff-facing errors carry a
request id that you can search for in the logs.

## On your Windows PC (START-APP.bat)

| Symptom | Fix |
|---|---|
| "Python was not found" / "npm was not found" | Install Python 3.11+ (tick *Add to PATH*) and Node.js 22, then double-click again |
| The API window closes with `Unsafe development configuration` | `backend\.env` asks for real SMS/email or a remote database. Use `console`, or set `DEV_ALLOW_REAL_MESSAGES=true` / `DEV_ALLOW_REMOTE_DATABASE=true` on purpose ([environment-configuration.md](environment-configuration.md)) |
| `database is locked` | Close every app window and start again. Only one copy of the app should use `backend\data\app.db` |
| Website opens but shows "cannot reach the API" | The API window must be open. Wait until it shows `Application startup complete`, then reload |
| Port 3000 or 8000 already in use | Another copy is running: close its windows, or restart the PC |
| Sign-in code never arrives | On your PC codes are not sent: they are printed in the **API window** |
| Start over with an empty database | Close the app, rename `backend\data\app.db` (keep it as a backup), double-click START-APP.bat |
| PowerShell refuses `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once |
| Mobile numbers show as `98111XXXXX` | Privacy masking (on by default). Press **Show** on the patient page, or turn it off in Admin → Settings → Privacy & data protection |
| "Screen locked" appears | No use for 15 minutes (or as the clinic set). Enter your password, or sign out. Change the time in the privacy settings |
| "Confirm it is you" keeps appearing | It lasts 10 minutes by default (the privacy settings allow up to 120). Accounts without a password use **Send me a code**: on your PC the code is printed in the API window |
| "This link has expired" for a document | Document links work for 60 seconds. Open the document again from the patient's record |
| "You have reached today's limit of 20 exports" | The daily export limit (20 per person by default). Raise it in the privacy settings if this is normal work |
| Uploads refused with "Files cannot be checked for viruses right now" | `UPLOAD_SCANNER=clamav` is set but ClamAV is not running: start it (`docker compose --profile antivirus up -d clamav`) or set `UPLOAD_SCANNER=none` |

## Docker development

| Symptom | Fix |
|---|---|
| `EACCES: permission denied` in the web container (Linux) | Start with your user id: `DEV_UID=$(id -u) DEV_GID=$(id -g) docker compose -f compose.yaml -f compose.dev.yaml up` |
| Changes do not reload | Polling is on; give it 2-3 seconds. Check the service logs for a syntax error |
| Tests: `database "app_test" does not exist` | `docker compose -f compose.yaml -f compose.test.yaml down -v`, then run again (the database is created at first start) |

## On the server

Start with:

```bash
deployment/scripts/health-check.sh
```

Then look at the logs of whatever it flags, e.g. `docker compose logs --tail 50 api`.

| Symptom | Cause and fix |
|---|---|
| deploy.sh: "The server settings (.env) are not ready" | It lists each problem (an empty secret, an example domain, a `console` provider...). Fix `.env` and run again; nothing was changed |
| deploy.sh: "the application refused these settings" | The app's own checks; the list above the error says exactly what. Common: `EMAIL_PROVIDER=smtp needs SMTP_HOST, SMTP_FROM` |
| "Let's Encrypt refused" | The domain's A record must point at this server (`ping your.domain`) and ports 80/443 must be open (`sudo ufw status`). Then run deploy.sh again. Let's Encrypt limits retries, so check DNS first |
| Site shows "This site is being set up" | Nginx has no certificate yet: run deploy.sh (it requests one) |
| `502 Bad Gateway` | The API or website is restarting or crashed: `docker compose ps`, then `docker compose logs api web` |
| `429 Too Many Requests` for real users | Many people behind one office IP. Raise the limits in `deployment/nginx/nginx.conf` (`limit_req_zone`) and the API's `RATE_LIMIT_DEFAULT`, then redeploy |
| Every visitor has the same IP in the audit log | You are behind Cloudflare or a load balancer: add their ranges with `set_real_ip_from` ([production-deployment.md](production-deployment.md) §7) |
| `migrate` exited with an error | `docker compose logs migrate`. The old release keeps running. Fix the cause, or `rollback.sh` |
| deploy.sh asks you to type `apply` | A pending migration removes or rewrites data. Read it first ([database-migrations.md](database-migrations.md)). A backup was just taken |
| rollback.sh: "The database schema changed since release ..." | Fix forward, or restore the backup taken before that release, then roll back with `--code-only` |
| health-check: "no recent verified backup" | `docker compose logs backup`. Common causes: a full disk, or a wrong `BACKUP_ENCRYPTION_KEY`. Then `deployment/scripts/backup.sh` |
| health-check: "worker heartbeat is old" | `docker compose logs worker`, then `docker compose restart worker`. Reminders and messages wait until it runs |
| health-check: "disk 85% used" | `docker system prune` (old images); move old backups off the server; check `docker compose logs` sizes |
| Certificate expires soon | `docker compose logs certbot`. Renewal runs twice a day; port 80 must stay open for it |
| Super admin: "not allowed from this network" | `PLATFORM_ADMIN_ALLOWED_IPS` does not include your current IP. Edit `.env` over SSH and run `docker compose up -d api` |
| Super admin lost password or phone | `docker compose run --rm api python -m app.ops.platform_admin --email you@x.in --recover` ([superadmin-setup.md](superadmin-setup.md)) |
| A payment is "submitted" but not confirmed | By design: staff verify each UPI payment against the bank statement (Admin → Payments). Nothing is marked paid automatically |
| "This UTR was already used" | The same bank reference was submitted for another booking at this clinic. Check both payments in the verification queue |

## Getting help

Collect, without any patient data:
* the output of `deployment/scripts/health-check.sh`;
* the request id from the error message;
* `docker compose logs --since 30m api | grep <request id>`.

Never share `.env` or its keys.
