"""Is the archive current, and does the source still look the way we think?

    python scripts/check_upstream.py            # ask, and say what to do
    python scripts/check_upstream.py --quiet    # exit code only, for cron

WHY THIS EXISTS. On 2026-08-15 this project's archive sat eleven days behind
INSP with every check green. Ten reports had been published and none had been
fetched, because the index fetch queried `search=sitrep` and INSP had renamed
the series to `SITREP_MVEBDB_NNN`. Nothing errored. Nothing failed. The
extraction identities all held -- because every check in this pipeline asks
whether the reports we HOLD are internally consistent, and not one asked whether
we hold the reports that EXIST.

That is the gap this closes. It is the only check here that looks OUTWARD.

THE THREE ANSWERS, and they are deliberately different from each other:

  CURRENT    the archive holds every report the source lists, and the source is
             still publishing. Nothing to do.
  BEHIND     the source has reports we do not. Ordinary; run the fetch. This is
             the expected state on any day INSP publishes before we pull.
  CHANGED    something about the source moved -- our own predicate now finds
             FEWER reports than we already hold, or a URL we recorded has begun
             returning 404, or files are appearing that we cannot classify.
             This is the state that hid for eleven days, and it is the reason
             the exit code for it is distinct from BEHIND.

A SILENT SOURCE IS ALSO A FINDING. If the newest upload is older than
`--stale-days`, that is reported too: it means either the outbreak's reporting
has stopped or the site has changed in a way that hides it, and those want
different responses.

EXIT CODES, so a cron job or a Makefile can branch on this:
    0  current
    1  behind -- new reports available
    2  changed -- the source moved; a human should look
    3  unreachable -- the API did not answer
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_sitrep_index import (API, EPIDEMIC_START, QUERY, _BARE, _NUM,
                                parse_row)
from lib.provenance import REPO_ROOT, UA

OK, BEHIND, CHANGED, UNREACHABLE = 0, 1, 2, 3


def _fetch(start: str) -> list[dict]:
    """Every media entry since `start`, following pagination via the header."""
    query = QUERY.format(start=start)
    out, page, total_pages = [], 1, 1
    while page <= total_pages:
        req = urllib.request.Request(f"{API}?{query}&page={page}",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            if page == 1:
                total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            out.extend(json.loads(resp.read()))
        page += 1
    return out


def _committed(index: Path) -> tuple[set[int], dict[str, str]]:
    """Report numbers in the committed index, and each pick's filename -> URL."""
    nums, urls = set(), {}
    with index.open() as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["sitrep"]:
                nums.add(int(r["sitrep"]))
            if r["pick"] == "yes":
                urls[r["filename"]] = r["url"]
    return nums, urls


def _head(url: str) -> int:
    """Status for one URL. A dead link in the committed index is a CHANGE."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path,
                    default=REPO_ROOT / "data/raw/insp_sitrep_index.tsv")
    ap.add_argument("--pdfs", type=Path, default=REPO_ROOT / "data/raw/sitrep_pdfs")
    ap.add_argument("--stale-days", type=int, default=4,
                    help="report the SOURCE as quiet if its newest upload is "
                         "older than this. INSP publishes daily, so several "
                         "days of silence is itself worth knowing about.")
    ap.add_argument("--spot-check", type=int, default=5,
                    help="how many committed URLs to HEAD. A link that has "
                         "begun 404ing means the source moved files under us, "
                         "which is how reports 083-085 went missing.")
    ap.add_argument("--quiet", action="store_true", help="exit code only")
    args = ap.parse_args()

    def say(*a):
        if not args.quiet:
            print(*a)

    have_nums, have_urls = _committed(args.index)
    on_disk = {p.name for p in args.pdfs.glob("*.pdf")} if args.pdfs.exists() else set()

    try:
        entries = _fetch(EPIDEMIC_START)
    except Exception as e:
        say(f"UNREACHABLE  the INSP media API did not answer: "
            f"{type(e).__name__}: {e}")
        say("  This is not evidence about the outbreak. Retry; if it persists, "
            "the endpoint itself has changed.")
        raise SystemExit(UNREACHABLE)

    rows = [r for r in (parse_row(e) for e in entries) if r]
    # THE OVERRIDES ARE PART OF THE PREDICATE. Nine reports carry no number in
    # their filename and are resolved from their front page; without applying
    # the same table the fetch applies, they read here as "no longer listed",
    # which is a false alarm on precisely the check that must not cry wolf.
    ov = REPO_ROOT / "registers/sitrep_number_overrides.tsv"
    if ov.exists():
        table = {}
        for line in ov.read_text().splitlines():
            if line.startswith("#") or not line.strip() or line.startswith("filename\t"):
                continue
            fn, num, date = line.split("\t")
            table[fn] = (num, date)
        for r in rows:
            if r["filename"] in table:
                r["sitrep"], r["data_date"] = table[r["filename"]]
    listed = {int(r["sitrep"]) for r in rows if r["sitrep"]}
    newest = max((e.get("date", "")[:10] for e in entries), default="")

    # A SITUATION REPORT WE CANNOT NUMBER -- not merely a PDF we do not want.
    # The site hosts necrology notices, infodemic bulletins and the previous
    # outbreak's reports, and flagging those would make this check noise. What
    # matters is a file our own predicate ACCEPTED as a report of this epidemic
    # and could not name: `91.pdf` was exactly that.
    unclassified = [r for r in rows if not r["sitrep"]]

    findings, verdict = [], OK

    # --- THE REGRESSION GUARD, and the one that would have caught this. ---
    # If our own enumeration finds fewer reports than we already hold, the
    # source has moved in a way our predicate no longer follows. Being BEHIND is
    # ordinary; finding LESS THAN WE HAVE is not.
    missing_from_listing = sorted(have_nums - listed)
    if missing_from_listing:
        verdict = CHANGED
        findings.append(
            f"the listing no longer includes {len(missing_from_listing)} "
            f"report(s) we already hold: {missing_from_listing[:12]}"
            f"{' ...' if len(missing_from_listing) > 12 else ''}\n"
            f"      Our query or the site's naming has changed. THIS IS THE "
            f"FAILURE MODE THAT HID FOR ELEVEN DAYS -- do not assume the "
            f"reports were withdrawn.")

    dead = []
    for name, url in list(have_urls.items())[-args.spot_check:]:
        code = _head(url)
        if code not in (200, 301, 302, 0):
            dead.append((name, code))
    if dead:
        verdict = CHANGED
        findings.append(
            "committed URLs that no longer resolve: "
            + ", ".join(f"{n} -> HTTP {c}" for n, c in dead)
            + "\n      The source re-uploads reports under new names; the old "
              "URL dies and the media entry stays. Re-run the index fetch.")

    if unclassified:
        verdict = max(verdict, CHANGED)
        names = [r["filename"] for r in unclassified]
        findings.append(
            f"{len(names)} PDF(s) in the window that we cannot classify: "
            f"{names[:8]}{' ...' if len(names) > 8 else ''}\n"
            f"      A report published under a name carrying no series token "
            f"is invisible to every rule here. Read its front page and record "
            f"it in registers/sitrep_number_overrides.tsv.")

    new = sorted(listed - have_nums)
    if new:
        verdict = max(verdict, BEHIND) if verdict != CHANGED else CHANGED
        by_num = {int(r["sitrep"]): r for r in rows if r["sitrep"]}
        findings.append(
            f"{len(new)} report(s) published that this archive does not hold: "
            + ", ".join(str(n) for n in new)
            + "\n      "
            + "; ".join(f"{n} ({by_num[n]['data_date'] or 'date unread'})"
                        for n in new[:6]))

    if newest:
        import datetime as dt
        age = (dt.date.today() - dt.date.fromisoformat(newest)).days
        if age > args.stale_days:
            findings.append(
                f"the SOURCE itself has published nothing for {age} days "
                f"(newest upload {newest}).\n"
                f"      Either reporting has paused or the site changed in a "
                f"way that hides it. Those want different responses.")

    label = {OK: "CURRENT", BEHIND: "BEHIND", CHANGED: "CHANGED"}[verdict]
    say(f"{label}  --  {len(listed)} reports listed by INSP, "
        f"{len(have_nums)} in our index, {len(on_disk)} PDFs on disk")
    say(f"          newest upload {newest or 'unknown'}; "
        f"our latest report {max(have_nums) if have_nums else 'none'}")
    for f in findings:
        say(f"\n  * {f}")
    if verdict == BEHIND:
        say("\n  To update:  make refresh      "
            "(fetch the index, the PDFs, then rebuild)")
    elif verdict == CHANGED:
        say("\n  A human should look before fetching. `make refresh` may "
            "silently do the wrong thing while the source is in this state.")
    elif not findings:
        say("\n  Nothing to do.")
    raise SystemExit(verdict)


if __name__ == "__main__":
    main()
