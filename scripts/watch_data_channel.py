"""Watch the data-agent channel for a write from the modelling side.

The channel is a file both repositories append to, so a change to it is the
signal that camdl has something for us -- a smoke test, a fix landing, a
question. This polls it and exits as soon as it changes, printing exactly what
was added. Run it in the background; the exit is the notification.

Two details that matter:

  SETTLE  A write is not atomic. Detecting a size change and reading
          immediately can catch a half-written entry, which would be reported
          as a truncated message and read as a different one. So after a
          change is seen, the hash must hold still for --settle seconds before
          anything is reported.

  DIFF    It reports the ADDED lines, not "the file changed". A notification
          that does not carry the content costs a round trip to go and read
          it, and the whole point is to act quickly.

Adapted from ebola-bdbv-camdl/scripts/watch_agent_channel.py -- same settle
and diff behaviour, with the camdl version probe dropped (nothing on this side
depends on it) and the default file pointed at the shared data channel, which
lives in the modelling repository's working tree.

THE BASELINE IS THE LAST REPORTED STATE, NOT THE FILE AS FOUND. Taking the
baseline at launch loses anything appended while no watcher was running: the
entry is already inside the new baseline and can never be reported as added.
That happened -- an entry sat unanswered because each restart re-baselined
over it. `--state` persists the last line count actually reported, so a
watcher started after an append still reports it, and the gap between runs
stops being a blind spot.

ONE-SHOT ON PURPOSE. It exits when the other side writes, because the exit is
the notification: run under a harness that re-invokes on completion and the
agent wakes with the added lines already in hand. `--notify` additionally
raises a macOS banner so a human sees it too, and `--loop` re-arms instead of
exiting for the case where nobody is waiting on the exit.

Exit codes: 0 a change was seen and reported; 2 the timeout expired with no
change; 3 the file went missing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import subprocess
import sys
import time
from pathlib import Path


def digest(p: Path) -> tuple[str, list[str]]:
    b = p.read_bytes()
    return hashlib.sha256(b).hexdigest(), b.decode("utf-8", "replace").splitlines()


def stamp() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path,
                    default=Path("../ebola-bdbv-camdl/data-agent-channel.md"))
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--settle", type=float, default=5.0)
    ap.add_argument("--timeout", type=float, default=6 * 3600)
    ap.add_argument("--context", type=int, default=0,
                    help="also show this many lines of trailing context")
    ap.add_argument("--notify", action="store_true",
                    help="also raise a macOS notification on a change")
    ap.add_argument("--loop", action="store_true",
                    help="re-arm after reporting instead of exiting")
    ap.add_argument("--state", type=Path,
                    default=Path("logs/.data_channel_seen"),
                    help="file holding the last REPORTED line count, so an "
                         "append made while no watcher ran is still reported")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"{stamp()}  {args.file} does not exist", file=sys.stderr)
        return 3

    base_hash, base_lines = digest(args.file)
    if args.state and args.state.exists():
        try:
            seen = int(args.state.read_text().split()[0])
        except (ValueError, IndexError):
            seen = len(base_lines)
        if seen < len(base_lines):
            print(f"{stamp()}  {len(base_lines) - seen} line(s) appended while "
                  f"no watcher was running; reporting them now")
            base_lines = base_lines[:seen]
            base_hash = ""            # force the first comparison to differ
    print(f"{stamp()}  watching {args.file} "
          f"({len(base_lines)} lines, sha {base_hash[:12]}), "
          f"every {args.interval:.0f}s, timeout {args.timeout / 3600:.1f}h")
    sys.stdout.flush()

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        time.sleep(args.interval)
        if not args.file.exists():
            print(f"{stamp()}  {args.file} disappeared", file=sys.stderr)
            return 3
        h, lines = digest(args.file)
        if h == base_hash:
            continue

        # Settle: hold still before reporting, so a half-written append is not
        # reported as a complete message.
        while True:
            time.sleep(args.settle)
            h2, lines2 = digest(args.file)
            if h2 == h:
                break
            h, lines = h2, lines2

        added = [l[1:] for l in difflib.unified_diff(
            base_lines, lines, n=args.context, lineterm="")
            if l.startswith("+") and not l.startswith("+++")]
        removed = sum(1 for l in difflib.unified_diff(
            base_lines, lines, n=0, lineterm="")
            if l.startswith("-") and not l.startswith("---"))

        print(f"\n{stamp()}  CHANGED: {len(base_lines)} -> {len(lines)} lines, "
              f"{len(added)} added, {removed} removed, sha {h[:12]}")
        print("-" * 72)
        print("\n".join(added) if added else "(no added lines; content was removed or edited)")
        print("-" * 72, flush=True)
        if args.state:
            args.state.parent.mkdir(parents=True, exist_ok=True)
            args.state.write_text(f"{len(lines)}\n")
        if args.notify:
            head = next((l for l in added if l.startswith("## ")), "")[:90]
            subprocess.run(["osascript", "-e",
                            f'display notification "{head or args.file.name} updated"'
                            f' with title "data-agent-channel"'],
                           capture_output=True)
        if not args.loop:
            return 0
        base_hash, base_lines = h, lines
        print(f"{stamp()}  re-armed", flush=True)

    print(f"\n{stamp()}  timeout after {args.timeout / 3600:.1f}h, no change "
          f"(sha still {base_hash[:12]})", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
