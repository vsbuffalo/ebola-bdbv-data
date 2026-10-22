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

uv run python scripts/daily_update.py "$@"
CODE=$?
# A crash in the runner itself files nothing on GitHub, so it gets the one
# local nudge; gate failures are GitHub's to announce.
if [ "$CODE" -ne 0 ]; then
  osascript -e "display notification \"daily update crashed (exit $CODE) -- see logs/\" with title \"ebola-bdbv-data\"" 2>/dev/null || true
fi
exit $CODE
