"""Append an entry to the shared data channel WITHOUT waking our own watcher.

    python scripts/post_data_channel.py --file ../ebola-bdbv-camdl/data-agent-channel.md < entry.md
    ... | python scripts/post_data_channel.py            # defaults to that path

WHY THIS EXISTS. The channel is one file that both sides append to, and
`watch_data_channel.py` reports any growth it did not already know about. It
cannot tell our own writes from theirs, so posting an entry fires our own
watcher and reads our own words back to us. Nothing is lost -- `--state`
records what was reported, so the next genuine write is still caught -- but a
watcher that cries every time we speak is one nobody leaves running.

So: append, then advance the watcher's state to the new line count in the same
breath. The next fire is theirs by construction.

THE STATE FILE IS ADVANCED, NEVER REWOUND. If the other side appended while we
were composing, their lines sit below ours and are already inside the count we
are about to write -- which would swallow them. So the count is only moved
forward past OUR OWN addition: we record the length as it was before we wrote,
plus the lines we added. Anything they contributed in between stays unreported
and the watcher still fires on it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CHANNEL = REPO.parent / "ebola-bdbv-camdl" / "data-agent-channel.md"
DEFAULT_STATE = REPO / "logs" / ".data_channel_seen"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=DEFAULT_CHANNEL)
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    args = ap.parse_args()

    entry = sys.stdin.read()
    if not entry.strip():
        print("refusing to append an empty entry", file=sys.stderr)
        return 1
    if not args.file.exists():
        print(f"channel not found: {args.file}", file=sys.stderr)
        return 3

    before = len(args.file.read_text().splitlines())
    if not entry.startswith("\n"):
        entry = "\n" + entry
    if not entry.endswith("\n"):
        entry += "\n"
    with args.file.open("a") as fh:
        fh.write(entry)

    added = len(entry.splitlines())
    after = len(args.file.read_text().splitlines())

    # Only ever advance, and only past our own lines -- see the docstring.
    prev = 0
    if args.state.exists():
        try:
            prev = int(args.state.read_text().strip() or 0)
        except ValueError:
            prev = 0
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(str(max(prev, before + added)))

    theirs = after - (before + added)
    print(f"appended {added} lines to {args.file.name} (now {after})")
    print(f"watcher state -> {max(prev, before + added)}; our own write will not fire it")
    if theirs > 0:
        print(f"NOTE: {theirs} line(s) below ours are not ours and remain unreported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
