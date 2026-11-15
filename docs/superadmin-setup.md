# Super admin setup

The **super admin** (platform administrator) runs the whole platform: every clinic, plans, platform settings, system
health and the database page. A **clinic owner / admin** runs one clinic only. They are different accounts with
different powers: see [permissions-matrix.md](permissions-matrix.md).

## Safety rules (enforced by the code)

* **No sign-up page, no default account, no default password.** The only way to create a super admin is a command on
  the server. Whoever can run it already has full access to the server, so it adds no new door.
* **Never silent:** an existing ordinary account is promoted only with `--promote-existing`. A second super admin needs
  `--add-another`.
* **Passwords:** typed twice at a hidden prompt, at least 12 characters plus the normal password policy, and stored
  only as an Argon2id hash. They are never printed or logged.
* **Two-step sign-in is required.** A super admin without an authenticator app is sent to set it up and can do
  nothing else first. Servers refuse to start with `PLATFORM_ADMIN_REQUIRE_MFA=false`.
* **Optional IP allow-list:** `PLATFORM_ADMIN_ALLOWED_IPS=203.0.113.7,198.51.100.0/24` makes super admin pages answer
  only from those addresses (the office, a VPN). Others get "not allowed from this network", including when they
  are viewing a clinic as its admin.
* **Everything is audit-logged:** creation, recovery, sign-ins and every super admin action.

## Create the first super admin

On the server, after the first `deploy.sh` (it reminds you):

```bash
docker compose run --rm api python -m app.ops.platform_admin --email you@yourclinic.in --name "Your Name"
```

Then open `https://<your domain>/login`, sign in, and scan the QR code with an authenticator app (Google
Authenticator, Microsoft Authenticator, 1Password, ...). **Save the backup codes** it shows once.

On your own PC (development), from `backend\` with the virtual environment active:

```powershell
python -m app.ops.platform_admin --email you@example.com
```

Development does not require two-step sign-in (`PLATFORM_ADMIN_REQUIRE_MFA=false` in `.env.development.example`), so
you can try things quickly. Servers always require it.

## Lost password or authenticator (recovery)

```bash
docker compose run --rm api python -m app.ops.platform_admin --email you@yourclinic.in --recover
```

This sets a new password, removes the old authenticator (you set up a new one at the next sign-in) and signs that
account out on every device. It is audit-logged as `platform.admin_recovered`.

## A second super admin

```bash
docker compose run --rm api python -m app.ops.platform_admin --email colleague@yourclinic.in --name "Colleague" --add-another
```

Keep the number of super admins small. Use clinic roles (owner, admin, receptionist, ...) for daily clinic work.

## Automation

For a scripted set-up only, the password can come from `PLATFORM_ADMIN_PASSWORD` instead of the prompt. Unset it
straight afterwards. Never put it in `.env` or a file in the repository.
