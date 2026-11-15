#!/usr/bin/env bash
# Back up now: database + uploaded files, encrypted with BACKUP_ENCRYPTION_KEY, then verified by reading it back.
# The daily backup runs by itself (the backup container, BACKUP_AT); use this before risky changes.
#   deployment/scripts/backup.sh            create one now
#   deployment/scripts/backup.sh list       show the backups on this server
#   deployment/scripts/backup.sh copy DIR   copy the newest backup out of Docker to DIR (then move it off the server)

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$REPO_DIR"; require_tools; require_env
export TAG="${TAG:-$(current_tag)}"; TAG="${TAG:-latest}"
case "${1:-create}" in
    create)
        say "Creating a verified backup"
        dc run --rm --no-deps -T backup python -m app.ops.backup create ;;
    list)
        dc run --rm --no-deps -T backup python -m app.ops.backup list ;;
    copy)
        dest="${2:?give a folder, e.g. backup.sh copy /root/backups}"
        mkdir -p "$dest"
        newest="$(dc run --rm --no-deps -T backup sh -c 'ls -1t /data/backups/backup-* 2>/dev/null | head -n1' | tr -d '\r')"
        [ -n "$newest" ] || die "no backups yet"
        id="$(dc ps -q backup)"; [ -n "$id" ] || die "the backup service is not running"
        docker cp "$id:$newest" "$dest/"
        ok "copied $(basename "$newest") to $dest (it is encrypted; keep BACKUP_ENCRYPTION_KEY separately)" ;;
    *) die "unknown command: $1 (create | list | copy DIR)" ;;
esac
