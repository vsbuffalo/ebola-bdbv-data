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
    4  stale -- current AND the source has published no situation report for
       longer than --stale-days. Distinct so a --quiet cron run can see it:
       a finding that never reached the exit code was invisible in exactly
       the mode the docstring promised it for.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_sitrep_index import (API, EPIDEMIC_START, QUERY, _BARE, _NUM,
                                parse_row)
from lib.provenance import REPO_ROOT, UA
from lib.report_date import load_external_sitreps

OK, BEHIND, CHANGED, UNREACHABLE, STALE = 0, 1, 2, 3, 4


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
                urls[r["filename"]] = (r["url"],
                                       int(r["sitrep"]) if r["sitrep"] else None)
    return nums, urls


def _external_sitreps() -> set[int]:
    """Report numbers held from a secondary archive because INSP does not serve
    them. Absent from the media listing BY DECLARATION, not by a change in the
    source, so this guard must not read them as one.

    Reads through the canonical loader rather than parsing the register again:
    a second parser is a second thing to drift, and this file already imports
    the one `report_date` uses to file those reports in the first place.
    """
    return {int(r.sitrep) for r in load_external_sitreps().values()}


def _url_for(urls: dict, n: int) -> str | None:
    """The picked URL for report `n`, or None if the index has no pick for it."""
    for url, num in urls.values():
        if num == n:
            return url
    return None


def _alive(url: str) -> bool:
    """True only on a 200. A network failure is NOT alive -- the same rule the
    spot-check applies, and for the same reason: an exception treated as a pass
    is how a dead link gets waved through."""
    return _head(url)[0] == 200


def _ascii_url(url: str) -> str:
    """A URL `urllib` can actually send, with non-ASCII path bytes
    percent-encoded.

    INSP NAMES 52 OF ITS 116 UPLOADS WITH `N°`, and `urllib` does not encode
    non-ASCII path characters the way a browser or curl does -- it raises
    `UnicodeEncodeError` while building the request, before any socket opens.
    `_head` catches that with everything else and reports (0, -1), so the
    check called a live URL UNVERIFIED and the gate refused to pass. Which of
    those 52 it hit depended only on which URLs the rotating spot-check
    sampled that day, so the failure looked intermittent and network-shaped
    rather than total and local.

    Only the PATH is encoded, and only bytes that are not already escaped:
    `safe` keeps `%` so a URL recorded in already-encoded form is not
    double-encoded into a 404.
    """
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        parts._replace(path=urllib.parse.quote(parts.path, safe="/%:@&=+$,~")))


def _head(url: str) -> tuple[int, int]:
    """(status, content_length) for one URL; (0, -1) when the request itself
    failed. A dead link in the committed index is a CHANGE, and a link whose
    byte count no longer matches the manifest is a REVISION IN PLACE -- the
    server sends Content-Length, ETag and Last-Modified on every HEAD, and
    throwing them away made an in-place revision invisible end to end. A
    network failure is UNVERIFIED, never 'alive': treating an exception as a
    pass let a timeout wave a dead link through."""
    req = urllib.request.Request(_ascii_url(url), method="HEAD",
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, int(r.headers.get("Content-Length") or -1)
    except urllib.error.HTTPError as e:
        return e.code, -1
    except Exception:
        return 0, -1


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
    if not ov.exists():
        # The index fetch refuses to run without this register, and this
        # check must not be softer than the fetch it gatekeeps.
        say(f"CHANGED  the overrides register is missing: {ov}")
        raise SystemExit(CHANGED)
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
    # THE STALENESS CLOCK RUNS ON SITUATION REPORTS, not on uploads of any
    # kind -- a necrology notice or a measles bulletin must not reset it.
    # "The sitrep series stopped" and "the site is still posting other
    # things" is exactly the discrimination this check exists to make.
    newest = max((r["published"] for r in rows), default="")

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
    # TWO ROUTES NOW PUT REPORTS IN THE ARCHIVE THAT THE LISTING NEVER HELD,
    # and this guard predates both. Left as written it fires on every build:
    #
    #   * `probe_gaps` recovers reports SERVED at a bare-numbered URL but absent
    #     from the media API -- sitrep 097 is the case that motivated it, and it
    #     was never in the listing, so "no longer includes" is the wrong reading.
    #   * `registers/external_sitreps.tsv` declares reports INSP does not serve
    #     at all -- 001, 002 and 004, obtained from a secondary archive.
    #
    # The guard must still catch the eleven-day failure, so neither route is
    # waved through on trust. The externally-sourced reports are subtracted
    # because the register DECLARES they are not INSP's to list. Everything else
    # unlisted is PROBED: still served means the listing never carried it and
    # nothing has moved; not served means the file has gone or been renamed,
    # which is the alarm this guard exists for.
    external = _external_sitreps()
    unlisted = sorted(have_nums - listed - external)
    still_served, gone = [], []
    for n in unlisted:
        url = _url_for(have_urls, n)
        (still_served if url and _alive(url) else gone).append(n)

    if gone:
        verdict = CHANGED
        findings.append(
            f"the listing no longer includes {len(gone)} report(s) we already "
            f"hold, AND their files are no longer served: {gone[:12]}"
            f"{' ...' if len(gone) > 12 else ''}\n"
            f"      Our query or the site's naming has changed. THIS IS THE "
            f"FAILURE MODE THAT HID FOR ELEVEN DAYS -- do not assume the "
            f"reports were withdrawn.")
    if still_served:
        findings.append(
            f"{len(still_served)} report(s) we hold are absent from the "
            f"listing but STILL SERVED: {still_served}\n"
            f"      Recovered by `probe_gaps`; the media API never carried "
            f"them. Not a change in the source.")
    if external:
        findings.append(
            f"{len(external)} report(s) are held from a secondary archive "
            f"because INSP does not serve them: {sorted(external)}\n"
            f"      Declared in registers/external_sitreps.tsv.")

    # THE SPOT-CHECK SAMPLES THE WHOLE RANGE, not only the newest picks --
    # `items[-n:]` HEADed reports 89-93 forever and never once revisited the
    # early archive. The newest three are always checked (they move most);
    # the rest of the budget walks the older picks at an even stride.
    items = list(have_urls.items())
    sample = items[-3:]
    older = items[:-3]
    budget = max(0, args.spot_check - len(sample))
    if older and budget:
        step = max(1, len(older) // budget)
        sample = older[::step][:budget] + sample

    mf_bytes: dict[int, int] = {}
    mf = REPO_ROOT / "data/raw/sitrep_pdfs.manifest.tsv"
    if mf.exists():
        for line in mf.read_text().splitlines()[1:]:
            f, b, _sha = line.split("\t")
            m = re.match(r"sitrep_(\d+)_", f)
            if m:
                mf_bytes[int(m.group(1))] = int(b)

    dead, unverified, resized = [], [], []
    for name, (url, num) in sample:
        code, clen = _head(url)
        if code == 0:
            unverified.append(name)
        elif code not in (200, 301, 302):
            dead.append((name, code))
        elif num in mf_bytes and clen not in (-1, mf_bytes[num]):
            resized.append((name, mf_bytes[num], clen))
    if dead:
        verdict = CHANGED
        findings.append(
            "committed URLs that no longer resolve: "
            + ", ".join(f"{n} -> HTTP {c}" for n, c in dead)
            + "\n      The source re-uploads reports under new names; the old "
              "URL dies and the media entry stays. Re-run the index fetch.")
    if resized:
        verdict = CHANGED
        findings.append(
            "committed URLs whose byte count no longer matches the manifest: "
            + ", ".join(f"{n} ({old} -> {new})" for n, old, new in resized)
            + "\n      A REPORT REVISED IN PLACE at an unchanged URL. Every "
              "hash-keyed register judgement is about the version we hold; "
              "fetch the revision beside it and adjudicate.")
    if unverified:
        findings.append(
            f"{len(unverified)} spot-checked URL(s) could not be reached "
            f"({', '.join(unverified[:4])}): UNVERIFIED, not alive. Retry; a "
            "network failure must not wave a dead link through.")

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
            if verdict == OK:
                verdict = STALE
            findings.append(
                f"the source has published no SITUATION REPORT for {age} days "
                f"(newest sitrep upload {newest}).\n"
                f"      Either reporting has paused or the site changed in a "
                f"way that hides it. Those want different responses.")

    label = {OK: "CURRENT", BEHIND: "BEHIND", CHANGED: "CHANGED",
             STALE: "STALE"}[verdict]
    # THE DISK COUNT EXCEEDS THE INDEX COUNT BY DESIGN, and saying so here
    # stops the summary reading as an inconsistency: reports INSP does not
    # serve are held from a secondary archive and declared in
    # registers/external_sitreps.tsv, so no index row will ever name them.
    n_ext = len(load_external_sitreps())
    say(f"{label}  --  {len(listed)} reports listed by INSP, "
        f"{len(have_nums)} in our index, {len(on_disk)} PDFs on disk "
        f"({n_ext} of them held from a secondary archive INSP does not serve)")
    say(f"          newest upload {newest or 'unknown'}; "
        f"our latest report {max(have_nums) if have_nums else 'none'}")
    for f in findings:
        say(f"\n  * {f}")
    if verdict == BEHIND:
        say("\n  To update:  make refresh      "
            "(fetch the index and PDFs, then rebuild everything offline)")
    elif verdict == CHANGED:
        say("\n  A human should look before fetching. `make refresh` may "
            "silently do the wrong thing while the source is in this state.")
    elif not findings:
        say("\n  Nothing to do.")
    raise SystemExit(verdict)


if __name__ == "__main__":
    main()
