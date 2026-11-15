#!/usr/bin/env bash
# Replace ALL current data (database + uploaded files) with a backup. Use only to recover from a disaster or
# a bad release. A safety backup of the current data is taken first, so even a restore can be undone.
#
#   deployment/scripts/restore.sh backup-20261115T023000Z.tar.gz.enc      (a file name from: backup.sh list)
#   deployment/scripts/restore.sh /path/to/backup-....tar.gz.enc           (a file copied back onto the server)
#   ... --confirm book.yourclinic.in      confirm without the prompt (the domain must match exactly)
#
# You must type the site's domain to confirm. Patients cannot book while the restore runs (a few minutes).

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$REPO_DIR"; require_tools; require_env
file="" CONFIRMED=""
while [ $# -gt 0 ]; do
    case "$1" in
        --confirm) CONFIRMED="${2:?--confirm needs the domain}"; shift 2 ;;
        -*) die "unknown option: $1" ;;
        *) file="$1"; shift ;;
    esac
done
[ -n "$file" ] || die "which backup? see: deployment/scripts/backup.sh list"
DOMAIN="$(env_value DOMAIN)"
export TAG="${TAG:-$(current_tag)}"; TAG="${TAG:-latest}"

if [ -f "$file" ]; then   # a file from outside Docker: put it into the backups volume first
    id="$(dc ps -q backup)"; [ -n "$id" ] || die "the backup service is not running (deploy first)"
    docker cp "$file" "$id:/data/backups/"
    file="$(basename "$file")"
fi
case "$file" in /*) ;; *) file="/data/backups/$file" ;; esac

say "Checking the backup can be read (checksums, encryption, database)"
dc run --rm --no-deps -T backup python -m app.ops.backup verify "$file"

warn "This replaces every appointment, patient, payment and file on $DOMAIN with the contents of that backup."
if [ -n "$CONFIRMED" ]; then
    [ "$CONFIRMED" = "$DOMAIN" ] || die "--confirm '$CONFIRMED' does not match this site ($DOMAIN). Nothing was changed."
else
    confirm "Type the domain ($DOMAIN) to restore:" "$DOMAIN"
fi

say "Stopping the website, API, worker and scheduled backups"
dc stop nginx web api worker backup
say "Restoring (a safety backup of the current data is taken first)"
dc run --rm --no-deps -T backup python -m app.ops.backup restore "$file" --yes
say "Bringing the schema up to this release and starting again"
dc up -d
for service in api worker web nginx; do wait_healthy "$service" 240 || die "$service is not healthy after the restore: docker compose logs $service"; done
"$REPO_DIR/deployment/scripts/health-check.sh" --quiet || warn "some checks failed; see deployment/scripts/health-check.sh"
say "${GREEN}Restore finished.${RESET} Check a few recent appointments in the admin."
