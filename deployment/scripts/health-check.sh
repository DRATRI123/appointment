#!/usr/bin/env bash
# Is everything working? Prints one line per check; exit code 0 = all good, 1 = something needs attention.
# Safe to run any time, also from cron (e.g. every 5 minutes, mailing you when it fails):
#   */5 * * * * cd /opt/appointment && deployment/scripts/health-check.sh --quiet || echo "check the server" | mail -s "Clinic site" you@x.in
#   --quiet              print only problems
#   --backup-warn-only   a missing backup is reported but does not fail the check (used by deploy.sh)
#   --only-backup        check only that a recent verified backup exists

# shellcheck disable=SC2015  # pass() always succeeds, so "A && pass || fail" is a safe if/else
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
trap - ERR
set +e
QUIET=0 BACKUP_WARN_ONLY=0 ONLY_BACKUP=0
for arg in "$@"; do
    case "$arg" in
        --quiet) QUIET=1 ;;
        --backup-warn-only) BACKUP_WARN_ONLY=1 ;;
        --only-backup) ONLY_BACKUP=1 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done
cd "$REPO_DIR"; require_tools; require_env
DOMAIN="$(env_value DOMAIN)"
failed=0
pass() { [ "$QUIET" = 1 ] || ok "$*"; }
fail() { warn "$*"; failed=1; }

app_status() {
    dc exec -T api python -c "
import json
from app.core.database import session_scope
from app.services.ops_service import system_status
with session_scope() as db:
    s = system_status(db)
failing = [a for a in s.get('attention', []) if a.startswith('Background jobs failing')]
print(json.dumps({'worker': s['worker']['ok'], 'backup': s['backup']['ok'], 'failing_jobs': failing}))
" 2>/dev/null | tail -n1
}
if [ "$ONLY_BACKUP" = 1 ]; then
    case "$(app_status)" in *'"backup": true'*) exit 0 ;; *) exit 1 ;; esac
fi

for service in postgres redis migrate api worker web nginx certbot backup; do
    id="$(dc ps -aq "$service" 2>/dev/null)"
    if [ -z "$id" ]; then fail "$service: not created"; continue; fi
    state="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}} {{.State.ExitCode}}' "$id")"
    case "$service:$state" in
        migrate:"exited  0") pass "migrate: finished successfully" ;;
        migrate:*) fail "migrate: $state (docker compose logs migrate)" ;;
        *:"running healthy "*|certbot:"running  "*|backup:"running  "*) pass "$service: running${state#running}" ;;
        *) fail "$service: $state (docker compose logs $service)" ;;
    esac
done

# Through Nginx exactly as a visitor would, but pinned to this machine (works before DNS points here).
curl_local() { curl -sk --max-time 10 --resolve "$DOMAIN:443:127.0.0.1" -o /dev/null -w '%{http_code}' "https://$DOMAIN$1"; }
code="$(curl_local /api/v1/health/ready)"; [ "$code" = 200 ] && pass "API ready over HTTPS" || fail "API over HTTPS answered $code"
code="$(curl_local /login)"; [ "$code" = 200 ] && pass "website over HTTPS" || fail "website over HTTPS answered $code"
code="$(curl -s --max-time 10 --resolve "$DOMAIN:80:127.0.0.1" -o /dev/null -w '%{http_code}' "http://$DOMAIN/")"
[ "$code" = 301 ] && pass "plain HTTP redirects to HTTPS" || fail "plain HTTP answered $code (expected 301)"
code="$(curl_local /metrics)"; [ "$code" = 404 ] && pass "/metrics is not public" || fail "/metrics answered $code (must be 404)"

if command -v openssl >/dev/null; then
    end="$(echo | openssl s_client -servername "$DOMAIN" -connect 127.0.0.1:443 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
    if [ -n "$end" ]; then
        days=$(( ($(date -d "$end" +%s) - $(date +%s)) / 86400 ))
        [ "$days" -ge 14 ] && pass "certificate valid for $days more days" || fail "certificate expires in $days days (certbot renews from 30 days; see docker compose logs certbot)"
    else
        fail "could not read the HTTPS certificate"
    fi
fi

# Worker, jobs and backups as the app itself sees them (no personal data in this output).
status="$(app_status)"
case "$status" in
    *'"worker": true'*) pass "worker finished a cycle recently" ;;
    *) fail "worker heartbeat is old or missing ($status)" ;;
esac
case "$status" in
    *'"backup": true'*) pass "last backup is recent and verified" ;;
    *) if [ "$BACKUP_WARN_ONLY" = 1 ]; then warn "no recent verified backup (deployment/scripts/backup.sh; docker compose logs backup)"
       else fail "no recent verified backup (run deployment/scripts/backup.sh; check docker compose logs backup)"; fi ;;
esac
case "$status" in *'"failing_jobs": []'*) pass "no background job failing repeatedly" ;; *) fail "jobs failing: $status" ;; esac

use="$(df -P "$(docker info -f '{{.DockerRootDir}}')" | awk 'NR==2 {gsub("%","",$5); print $5}')"
[ "${use:-0}" -lt 85 ] && pass "disk ${use}% used" || fail "disk ${use}% used (clean up: docker system prune; old backups)"

[ "$failed" = 0 ] && { [ "$QUIET" = 1 ] || say "${GREEN}All checks passed${RESET}"; }
exit "$failed"
