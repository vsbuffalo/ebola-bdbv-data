#!/bin/zsh
# Scheduled daily update, for launchd -- see `make daily-install`.
#
# Unlike cron_check.sh this one does refresh, commit, tag and push: every
# release gate stands between a fetch and a tag, and a failure files a
# `gate-failure` issue and hands the branch to a fixing agent instead of
# releasing. See scripts/daily_update.py.
#
# Repo root derived from this file's location; nothing absolute is baked in.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

# launchd's login shell loads .zprofile, not .zshrc: uv, gh, quarto and
# claude live on the interactive PATH.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# The job's GitHub credential: a fine-grained token scoped to this repository
# alone, kept in the login keychain, never the interactive `gh` login (which
# reaches every organisation the account belongs to). gh and git push both
# honour GH_TOKEN. Override the keychain service name with DAILY_TOKEN_SERVICE.
SERVICE="${DAILY_TOKEN_SERVICE:-ebola-bdbv-daily}"
if ! GH_TOKEN="$(security find-generic-password -s "$SERVICE" -w 2>/dev/null)"; then
  osascript -e "display notification \"daily update: no keychain token named $SERVICE\" with title \"ebola-bdbv-data\"" 2>/dev/null || true
  echo "no keychain item with service $SERVICE; not running" >&2
  exit 1
fi
export GH_TOKEN

uv run python scripts/daily_update.py "$@"
CODE=$?
# A crash in the runner itself files nothing on GitHub, so it gets the one
# local nudge; gate failures are GitHub's to announce.
if [ "$CODE" -ne 0 ]; then
  osascript -e "display notification \"daily update crashed (exit $CODE) -- see logs/\" with title \"ebola-bdbv-data\"" 2>/dev/null || true
fi
exit $CODE
