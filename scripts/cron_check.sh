#!/bin/zsh
# Scheduled `make check`, for launchd -- see `make cron-install`.
#
# CHECK ONLY, NEVER REFRESH. The check is read-only and safe to run
# unattended; a refresh is not: BEHIND can mean a revision or a late-listed
# backfill whose build stops on a finding that needs a human page-read
# (sitrep 063 did exactly that on its first fetch). So this job watches and
# notifies, and a person runs `make refresh`.
#
# Repo root derived from this file's location; nothing absolute is baked in.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

# launchd's login shell loads .zprofile, not .zshrc, and uv lives on the
# interactive PATH -- the first scheduled run died with `uv: No such file`.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

TS="$(date '+%Y-%m-%d %H:%M:%S')"
# The checker is invoked DIRECTLY, not through make: make exits 2 on any
# recipe failure, which is indistinguishable from the checker's own exit 2
# (CHANGED) -- the first run's PATH failure was logged as the source moving.
OUT="$(uv run python scripts/check_upstream.py 2>&1)"
CODE=$?
case $CODE in
  0) LABEL="CURRENT" ;;
  1) LABEL="BEHIND" ;;
  2) LABEL="CHANGED" ;;
  3) LABEL="UNREACHABLE" ;;
  4) LABEL="STALE" ;;
  *) LABEL="ERROR" ;;
esac

{
  echo "[$TS] exit=$CODE ($LABEL)"
  echo "$OUT" | sed 's/^/    /'
} >> logs/check_upstream.log

# A visible nudge when there is something to do. UNREACHABLE (3) is usually
# transient network and not worth a ping; everything else is.
if [ "$CODE" -ne 0 ] && [ "$CODE" -ne 3 ]; then
  osascript -e "display notification \"make check: $LABEL (exit $CODE) -- see logs/check_upstream.log\" with title \"ebola-bdbv-data\"" 2>/dev/null || true
fi
exit 0
