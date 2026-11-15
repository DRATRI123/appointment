#!/usr/bin/env bash
# Go back to an earlier release (its images are kept on the server).
#   deployment/scripts/rollback.sh                 the release before the current one
#   deployment/scripts/rollback.sh --tag TAG       a specific release (see: rollback.sh --list)
#   deployment/scripts/rollback.sh --list          releases deployed on this server
#
# Code only: the database stays as it is. If the newer release changed the database schema, the older code may not
# work with it; then this script stops and explains the choice: keep the current release and fix forward (usually
# best), or restore the backup taken just before that release with restore.sh (loses changes made since then).

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$REPO_DIR"; require_tools; require_env
TARGET="" FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --tag) TARGET="${2:?--tag needs a value}"; shift 2 ;;
        --list) printf 'deployed (UTC)\ttag\tcommit\tschema\n'; cat "$STATE_DIR/history.tsv" 2>/dev/null || echo "(no releases recorded)"; exit 0 ;;
        --code-only) FORCE=1; shift ;;
        *) die "unknown option: $1" ;;
    esac
done
TARGET="${TARGET:-$(cat "$STATE_DIR/previous" 2>/dev/null || true)}"
[ -n "$TARGET" ] || die "no earlier release recorded on this server (rollback.sh --list)."
for image in appointment-api appointment-web appointment-nginx; do
    docker image inspect "$image:$TARGET" >/dev/null 2>&1 || die "image $image:$TARGET is no longer on this server; deploy that commit instead: git checkout <commit> && deploy.sh"
done

now_schema="$(db_revision)"
target_schema="$(release_revision "$TARGET")"
if [ -n "$target_schema" ] && [ "$target_schema" != "unknown" ] && [ "$now_schema" != "$target_schema" ] && [ "$FORCE" != 1 ]; then
    cat >&2 <<MSG
${RED}The database schema changed since release $TARGET${RESET} (now $now_schema, that release used $target_schema).
Older code may fail against the newer schema. Options:
  1. Fix forward: keep the current release and deploy a fix (no data loss).
  2. Restore the backup taken just before the newer release (loses everything since then):
       deployment/scripts/backup.sh list   then   deployment/scripts/restore.sh <that backup>
     and then run: deployment/scripts/rollback.sh --tag $TARGET --code-only
  3. Only if you know the schema change is compatible: rollback.sh --tag $TARGET --code-only
MSG
    exit 1
fi

say "Rolling back to release $TARGET (database untouched; migrations are not run)"
export TAG="$TARGET"
dc up -d --no-deps --no-build api worker web backup nginx
for service in api worker web nginx; do wait_healthy "$service" 240 || die "$service is not healthy on $TARGET: docker compose logs $service"; done
"$REPO_DIR/deployment/scripts/health-check.sh" --quiet || warn "some checks failed; see deployment/scripts/health-check.sh"
record_release "$TARGET" "$now_schema"
say "${GREEN}Now running release $TARGET.${RESET}"
