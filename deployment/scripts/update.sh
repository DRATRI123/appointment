#!/usr/bin/env bash
# Update to the newest version of the code, then deploy it (deploy.sh backs up before any migration).
#   deployment/scripts/update.sh                 newest commit of the current branch
#   deployment/scripts/update.sh --ref v1.4.0    a specific tag, branch or commit
# Local edits on the server stop the update (they would be silently lost otherwise).

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$REPO_DIR"; require_tools; require_env
REF=""
while [ $# -gt 0 ]; do
    case "$1" in
        --ref) REF="${2:?--ref needs a value}"; shift 2 ;;
        *) break ;;
    esac
done
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "this checkout has local changes (git status). Commit or remove them first."

say "Fetching the latest code"
git fetch --tags --prune origin
before="$(git rev-parse --short HEAD)"
if [ -n "$REF" ]; then
    git checkout --quiet "$REF"
    git pull --ff-only --quiet 2>/dev/null || true   # only moves forward when REF is a branch
else
    git pull --ff-only --quiet || die "cannot fast-forward (the branch was rewritten?). Nothing was changed."
fi
after="$(git rev-parse --short HEAD)"
if [ "$before" = "$after" ]; then
    ok "already up to date ($after)"
else
    say "Changes $before -> $after:"
    git log --oneline "$before..$after" | head -n 30
fi
exec "$REPO_DIR/deployment/scripts/deploy.sh" "$@"
