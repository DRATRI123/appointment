#!/usr/bin/env bash
# Shared helpers for the deployment scripts. Sourced, never run directly.
# shellcheck disable=SC2034  # variables are used by the scripts that source this file

set -Eeuo pipefail
umask 077

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="$REPO_DIR/.deploy"          # release history (ignored by git)
ENV_FILE="$REPO_DIR/.env"
COMPOSE_FILES=(-f "$REPO_DIR/compose.yaml" -f "$REPO_DIR/compose.production.yaml")

if [ -t 1 ]; then
    BOLD=$'\e[1m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; RESET=$'\e[0m'
else
    BOLD=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

say()  { printf '%s==>%s %s\n' "$BOLD" "$RESET" "$*"; }
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
die()  { printf '%sERROR:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

trap 'die "stopped at line $LINENO (exit code $?). Nothing after this step was changed."' ERR

# Every compose call goes through here: always the production stack, always this folder's .env.
dc() { docker compose --project-directory "$REPO_DIR" --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" "$@"; }

# Value of KEY in .env (first match; inline comments and surrounding quotes removed). Never printed by the scripts.
env_value() {
    local line
    line="$(grep -E "^$1=" "$ENV_FILE" | head -n1 || true)"
    line="${line#*=}"
    line="${line%%[[:space:]]#*}"
    line="${line%"${line##*[![:space:]]}"}"
    line="${line%\"}"; line="${line#\"}"; line="${line%\'}"; line="${line#\'}"
    printf '%s' "$line"
}

require_tools() {
    command -v docker >/dev/null || die "Docker is not installed. Run deployment/scripts/setup-server.sh first."
    docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing (the docker-compose-plugin package)."
    docker info >/dev/null 2>&1 || die "Cannot talk to Docker. Run as a user in the docker group (or with sudo)."
}

require_env() {
    [ -f "$ENV_FILE" ] || die "No .env yet. Run deployment/scripts/deploy.sh --domain your.domain --email you@domain first."
}

# Refuse anything that is still an example, empty, or unsafe for a server. The API repeats its own, stricter checks
# when it starts (docs/environment-configuration.md); this catches mistakes before anything is stopped or built.
validate_env() {
    local problems=() key value perms
    perms="$(stat -c '%a' "$ENV_FILE")"
    if [ "$perms" != "600" ] && [ "$perms" != "400" ]; then
        chmod 600 "$ENV_FILE"; warn ".env was readable by other users; permissions set to 600"
    fi
    value="$(env_value APP_ENV)"
    case "$value" in
        production|staging) ;;
        *) problems+=("APP_ENV must be production or staging on a server (it is '${value:-empty}')") ;;
    esac
    for key in SECRET_KEY DATA_ENCRYPTION_KEY OTP_PEPPER BACKUP_ENCRYPTION_KEY POSTGRES_PASSWORD DOMAIN; do
        [ -n "$(env_value "$key")" ] || problems+=("$key is empty")
    done
    for key in SECRET_KEY DATA_ENCRYPTION_KEY OTP_PEPPER BACKUP_ENCRYPTION_KEY POSTGRES_PASSWORD METRICS_TOKEN; do
        value="$(env_value "$key")"
        if printf '%s' "$value" | grep -qiE 'change.?me|example|replace|placeholder|password|secret|dev-only|test-only|^x+$'; then
            problems+=("$key still holds an example value")
        fi
    done
    value="$(env_value DOMAIN)"
    if printf '%s' "$value" | grep -qiE '(^|\.)example\.(com|org|net|in)$|^your|yourclinic'; then
        problems+=("DOMAIN is still the example ($value)")
    fi
    [ "$(env_value DEBUG)" != "true" ] || problems+=("DEBUG=true is not allowed on a server")
    for key in OTP_PROVIDER EMAIL_PROVIDER SMS_PROVIDER WHATSAPP_PROVIDER; do
        [ "$(env_value "$key")" != "console" ] || problems+=("$key=console only prints messages; use a real provider or 'disabled'")
    done
    [ -z "$(env_value OTP_TEST_CODE)" ] || problems+=("OTP_TEST_CODE must be empty on a server")
    if [ "${#problems[@]}" -gt 0 ]; then
        printf '%sThe server settings (.env) are not ready:%s\n' "$RED" "$RESET" >&2
        printf '  - %s\n' "${problems[@]}" >&2
        exit 1
    fi
    ok "settings in .env look complete (no example values)"
}

# Keep TAG in .env equal to the live release, so plain `docker compose run/up` uses the same images.
set_env_tag() {
    if grep -qE '^TAG=' "$ENV_FILE"; then sed -i "s|^TAG=.*|TAG=$1|" "$ENV_FILE"; else printf 'TAG=%s\n' "$1" >> "$ENV_FILE"; fi
}

current_tag() { if [ -f "$STATE_DIR/current" ]; then cat "$STATE_DIR/current"; fi; }

record_release() {  # tag  alembic_revision
    mkdir -p "$STATE_DIR"
    local previous; previous="$(current_tag)"
    [ -z "$previous" ] || [ "$previous" = "$1" ] || printf '%s\n' "$previous" > "$STATE_DIR/previous"
    printf '%s\n' "$1" > "$STATE_DIR/current"
    set_env_tag "$1"
    printf '%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo unknown)" "${2:-unknown}" \
        >> "$STATE_DIR/history.tsv"
}

# The schema revision recorded for a release tag (from history.tsv), empty if unknown.
release_revision() { awk -F'\t' -v t="$1" '$2 == t { r = $4 } END { print r }' "$STATE_DIR/history.tsv" 2>/dev/null; }

# shellcheck disable=SC2016  # the $POSTGRES_* variables expand inside the postgres container
db_revision() {
    dc exec -T postgres sh -c 'psql -tAq -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version_num from alembic_version" 2>/dev/null' | tr -d '[:space:]' || true
}

wait_healthy() {  # service [timeout seconds]   healthy (or simply running, for a service without a health check)
    local service="$1" timeout="${2:-180}" waited=0 id status
    while :; do
        id="$(dc ps -q "$service" 2>/dev/null || true)"
        status="missing"
        [ -z "$id" ] || status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null || echo missing)"
        [ "$status" = healthy ] && return 0
        if [ "$status" = running ] && [ -z "$(docker inspect -f '{{if .State.Health}}yes{{end}}' "$id")" ]; then return 0; fi
        [ "$waited" -lt "$timeout" ] || { warn "$service is '$status' after ${timeout}s"; return 1; }
        sleep 3; waited=$((waited + 3))
    done
}

confirm() {  # prompt  expected-answer
    local answer
    [ -t 0 ] || die "This step needs a typed confirmation; run it in an interactive terminal."
    read -r -p "$1 " answer
    [ "$answer" = "$2" ] || die "Not confirmed. Nothing was changed."
}
