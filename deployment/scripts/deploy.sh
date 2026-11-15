#!/usr/bin/env bash
# Deploy (or redeploy) this checkout on a server. Safe to run again at any time.
#
# First time:   deployment/scripts/deploy.sh --domain book.yourclinic.in --email you@yourclinic.in [--env staging]
#               -> creates .env with fresh random secrets and STOPS, so you can add your SMTP / SMS details.
# Then:         deployment/scripts/deploy.sh
#
# Steps: check settings -> build images (tagged with the git commit) -> start PostgreSQL/Redis -> verified backup
# (whenever migrations are pending) -> stop if a migration would remove data, unless you confirm -> migrate -> start
# -> HTTPS certificate on first run -> health check -> record the release (rollback.sh can go back to it).
#
# Options:
#   --domain D --email E   first run only: where patients will reach the site, and the Let's Encrypt contact address
#   --env production|staging   first run only (default production)
#   --self-signed          rehearsal without a public domain (e.g. DOMAIN=localhost): a 30-day self-signed certificate
#   --allow-destructive    apply migrations that remove data without the typed confirmation (after reading them!)
#   --no-build             reuse images already built for this commit

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

DOMAIN_ARG="" EMAIL_ARG="" ENV_ARG="production" SELF_SIGNED=0 ALLOW_DESTRUCTIVE=0 BUILD=1
while [ $# -gt 0 ]; do
    case "$1" in
        --domain) DOMAIN_ARG="${2:?--domain needs a value}"; shift 2 ;;
        --email) EMAIL_ARG="${2:?--email needs a value}"; shift 2 ;;
        --env) ENV_ARG="${2:?--env needs production or staging}"; shift 2 ;;
        --self-signed) SELF_SIGNED=1; shift ;;
        --allow-destructive) ALLOW_DESTRUCTIVE=1; shift ;;
        --no-build) BUILD=0; shift ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
done

cd "$REPO_DIR"
require_tools

# --- 1. Settings ---------------------------------------------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    [ -n "$DOMAIN_ARG" ] || die "No .env yet: run with --domain your.domain --email you@domain (and --env staging for a staging server)."
    [ -n "$EMAIL_ARG" ] || [ "$SELF_SIGNED" = 1 ] || die "--email is needed for the Let's Encrypt certificate."
    command -v python3 >/dev/null || die "python3 is needed once to create .env (Ubuntu has it)."
    say "Creating .env for $ENV_ARG with fresh random secrets"
    args=(--domain "$DOMAIN_ARG" --env "$ENV_ARG" --output "$ENV_FILE")
    [ -z "$EMAIL_ARG" ] || args+=(--letsencrypt-email "$EMAIL_ARG")
    python3 scripts/generate_env.py "${args[@]}"
    chmod 600 "$ENV_FILE"
    cat <<EOF

${BOLD}Next:${RESET}
  1. Copy DATA_ENCRYPTION_KEY and BACKUP_ENCRYPTION_KEY from .env into your password manager (off this server).
     Without them, clinical notes and backups cannot be read. Never share them.
  2. Fill in the message settings in .env (SMTP_* for email; MSG91_* or TWILIO_* for SMS), or set a channel to
     'disabled'. nano .env
  3. Run deployment/scripts/deploy.sh again.
EOF
    exit 0
fi
say "Checking settings"
validate_env
DOMAIN="$(env_value DOMAIN)"
APP_ENV="$(env_value APP_ENV)"
LE_EMAIL="$(env_value LETSENCRYPT_EMAIL)"
[ -n "$LE_EMAIL" ] || [ "$SELF_SIGNED" = 1 ] || [ -f "$STATE_DIR/current" ] \
    || die "LETSENCRYPT_EMAIL is empty in .env (Let's Encrypt needs it for the first certificate). Nothing was changed."

# --- 2. Images -------------------------------------------------------------------------------------------------------
TAG="$(git rev-parse --short=12 HEAD 2>/dev/null || date -u +%Y%m%d%H%M)"
if [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    warn "this checkout has local changes; the release is tagged $TAG-local"
    TAG="$TAG-local"
fi
export TAG
if [ "$BUILD" = 1 ]; then
    say "Building images $TAG (base images are re-pulled for security updates)"
    dc build --pull
fi
say "Checking the application accepts these settings for $APP_ENV"
dc run --rm --no-deps -T --entrypoint python api -c "
import sys
try:
    from app.core.config import get_settings
    print('  settings OK:', get_settings().app_env)
except Exception as exc:
    print(str(exc).split(' [type=')[0].split('Value error, ')[-1], file=sys.stderr)
    sys.exit(1)" || die "the application refused these settings (list above). Fix .env, then run deploy.sh again. Nothing was changed."

# --- 3. Database, backup, migrations -----------------------------------------------------------------------------------
say "Starting PostgreSQL and Redis"
dc up -d postgres redis
wait_healthy postgres 180
wait_healthy redis 60

say "Checking pending database migrations"
set +e
dc run --rm --no-deps -T --entrypoint python api -m app.ops.migration_check
check=$?
set -e
case "$check" in
    0|3) ;;
    *) die "could not check the migrations (see above). Nothing was changed." ;;
esac
pending="$(dc run --rm --no-deps -T --entrypoint python api -m app.ops.migration_check --json | tail -n1)"
if printf '%s' "$pending" | grep -q '"pending": \[\]'; then
    ok "no migrations pending"
elif printf '%s' "$pending" | grep -q '"current": null'; then
    ok "new database: the schema will be created"
else
    say "Backing up before migrating (verified; kept under the backups volume)"
    dc run --rm --no-deps -T backup python -m app.ops.backup create
fi
if [ "$check" = 3 ] && [ "$ALLOW_DESTRUCTIVE" != 1 ]; then
    confirm "A migration above removes or rewrites data (a backup was just taken). Type 'apply' to continue:" apply
fi

# --- 4. Start ---------------------------------------------------------------------------------------------------------
say "Starting the new release (migrations run first; the API starts only if they succeed)"
dc up -d --remove-orphans

# --- 5. HTTPS certificate -------------------------------------------------------------------------------------------------
has_cert() { dc run --rm --no-deps -T --entrypoint sh certbot -c "test -s /etc/letsencrypt/live/$DOMAIN/fullchain.pem" >/dev/null 2>&1; }
if ! has_cert; then
    wait_healthy nginx 240 || die "Nginx did not start; see: docker compose logs nginx"
    if [ "$SELF_SIGNED" = 1 ]; then
        say "Creating a self-signed certificate for $DOMAIN (rehearsal only: browsers will warn)"
        dc run --rm --no-deps -T --entrypoint sh certbot -c "mkdir -p /etc/letsencrypt/live/$DOMAIN && cd /etc/letsencrypt/live/$DOMAIN \
            && openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 30 -subj /CN=$DOMAIN \
               -addext subjectAltName=DNS:$DOMAIN -keyout privkey.pem -out fullchain.pem 2>/dev/null"
    else
        say "Requesting the Let's Encrypt certificate for $DOMAIN (DNS must already point at this server)"
        dc run --rm --no-deps -T --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
            --config-dir /etc/letsencrypt --work-dir /var/lib/letsencrypt --logs-dir /tmp \
            -d "$DOMAIN" --email "$LE_EMAIL" --agree-tos --no-eff-email --non-interactive \
            || die "Let's Encrypt refused. Check the DNS A record for $DOMAIN and that ports 80/443 are open, then run deploy.sh again."
    fi
    dc restart nginx
fi

# --- 6. Health ---------------------------------------------------------------------------------------------------------------
say "Checking health"
for service in api worker web nginx; do
    wait_healthy "$service" 240 || die "$service is not healthy. Logs: docker compose logs $service. To go back: deployment/scripts/rollback.sh"
done
if ! "$REPO_DIR/deployment/scripts/health-check.sh" --quiet --only-backup >/dev/null 2>&1; then
    say "Taking a baseline backup (none in the last 26 hours)"
    dc run --rm --no-deps -T backup python -m app.ops.backup create \
        || warn "THE BACKUP FAILED: the site is live, but fix this today (docker compose logs backup; deployment/scripts/backup.sh)"
fi
"$REPO_DIR/deployment/scripts/health-check.sh" --quiet --backup-warn-only \
    || die "health check failed. Logs: docker compose logs. To go back: deployment/scripts/rollback.sh"

record_release "$TAG" "$(db_revision)"
docker image ls --format '{{.Repository}}:{{.Tag}}' | grep -E '^appointment-(api|web):' \
    | grep -vE ":($TAG|$(cat "$STATE_DIR/previous" 2>/dev/null || echo none)|latest)$" | tail -n +7 | xargs -r docker image rm >/dev/null 2>&1 || true

say "${GREEN}Release $TAG is live at https://$DOMAIN${RESET}"
if ! dc exec -T api python -c "
from sqlalchemy import select
from app.core.database import session_scope
from app.models import User
with session_scope() as db:
    raise SystemExit(0 if db.scalar(select(User.id).where(User.is_platform_admin.is_(True)).limit(1)) else 1)" >/dev/null 2>&1; then
    cat <<EOF

${BOLD}No super admin yet.${RESET} Create yours (you type the password; it is never stored in a file):
  docker compose run --rm api python -m app.ops.platform_admin --email you@yourclinic.in --name "Your Name"
Then sign in at https://$DOMAIN/login and set up two-step sign-in (required for super admins).
EOF
fi
