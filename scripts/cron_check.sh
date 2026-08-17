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

TS="$(date '+%Y-%m-%d %H:%M:%S')"
OUT="$(make check 2>&1)"
CODE=$?
LABEL="CURRENT"
case $CODE in
  1) LABEL="BEHIND" ;;
  2) LABEL="CHANGED" ;;
  3) LABEL="UNREACHABLE" ;;
  4) LABEL="STALE" ;;
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
