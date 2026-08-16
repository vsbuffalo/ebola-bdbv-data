"""Refresh the committed index of INSP situation-report PDFs.

INSP (Institut National de Sante Publique, DRC) publishes the situation reports
for the 17th Ebola epidemic as PDFs attached to its WordPress site. The
`wp/v2/media` REST endpoint lists them without authentication.

Writes a committed, human-readable TSV -- one row per PDF, never deduplicated
destructively, because the source is messy in ways that matter:

  * The endpoint is PAGINATED. `per_page` caps at 100 and there are ~199
    matching items, so a single request silently returns half the series.
  * The `search=sitrep` query also matches measles/rubella ("Rougeole") reports
    and the 2016 Ebola outbreak ("MVE16"), which are filtered out here.
  * The report number appears as N18, N°040, NA°047 (a mojibake degree sign),
    N_61, N°_64 and No59 across vintages.
  * Most reports are published TWICE, as a draft and a final/corrected version.
    Both rows are kept and marked; `pick` flags the one to prefer.
  * A few filenames carry no parseable number at all. These are emitted with an
    empty `sitrep` and flagged, NOT guessed -- the report's own front page
    states its number, so they are resolved by reading the PDF.
  * The SERIES GETS RENAMED. Reports 005-083 are `SitRep_MVE_RDC_N_NNN_...`;
    from 084 they are `SITREP_MVEBDB_NNN_DDMMYY`. Report 091 is uploaded as
    the bare `91.pdf`, carrying no series name at all -- so it is absent from
    this index and has to be resolved by hand.

THE OUTPUT IS MACHINE-GENERATED AND CARRIES NO COMMENT HEADER. Everything worth
saying about it is here, in the generator, because a comment written into the
TSV is destroyed by the next refresh -- and `fetch_sitrep_pdfs.py` reads the
file with `csv.DictReader`, which takes line one as the header and fails on a
comment.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

from lib.provenance import REPO_ROOT, UA, record

API = "https://insp.cd/wp-json/wp/v2/media"

# ENUMERATE BY DATE, NOT BY SEARCH TERM, and filter locally.
#
# This used to be `search=sitrep`, and that query SILENTLY STOPPED FINDING THE
# SERIES. On 2026-08-15 it returned nothing above report 060 while INSP had
# published through 092: from report 083 the uploads are named
# `SITREP_MVEBDB_086_080826.pdf` rather than `SitRep_MVE_RDC_N_082_...`, and
# WordPress's search index no longer matched them. Nothing errored. The index
# simply stopped growing, and the archive sat eleven days behind the source
# while every downstream check stayed green -- because every check we have
# asks whether the reports we HOLD are consistent, and none asks whether we
# hold the reports that EXIST.
#
# `after=` is a first-class filter on the endpoint and does not depend on how
# the site titles anything. The predicate that decides what is a situation
# report then lives HERE, in `parse_row`, where it is readable and testable,
# rather than in an opaque relevance index on someone else's server.
QUERY = ("after={start}T00:00:00&per_page=100&orderby=date&order=asc"
         "&_fields=id,date,source_url")

# Number token, in the two shapes the series has used:
#   N / No / N° / NA° / N_ / N°_ then 1-3 digits   -- through report 083
#   MVEBDB_086, MVEBDB 086                         -- from report 084
# NB: `\b` is useless here -- underscore is a word character, so `\bN` never
# matches in `RDC_N_082`. Anchor on "not preceded by a letter" instead, and
# close with a digit lookahead rather than `\b` for the same reason.
_NUM = re.compile(
    r"(?<![A-Za-z])N[°ºoA]*[_\s°]*(\d{1,3})(?!\d)"
    r"|MVE?BDB[_\s-]*(\d{2,3})(?!\d)", re.I)
_DATE = re.compile(r"(?<!\d)(\d{2})[-_](\d{2})[-_](20\d{2})(?!\d)")   # 04_08_2026
_DATE8 = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")          # 20260512
_DATE_COMPACT = re.compile(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)")   # 26052026
# DDMMYY, introduced with the MVEBDB naming: `..._086_080826.pdf` is 8 Aug 2026.
# Anchored to a 20xx-implying year to keep it from eating an ordinary 6-digit
# run. The DATA DATE IS READ FROM THE PAGE regardless -- see
# `lib/report_date.py` -- so this only has to be good enough to name a file.
_DATE6 = re.compile(r"(?<!\d)(\d{2})(\d{2})(2[0-9])(?!\d)")           # 080826

# Version markers. Matched as SUBSTRINGS, not whole words: the marker is
# routinely suffixed with a digit ("Vf2", "FDv2", "-FD-1-1"), and a word-
# boundary match silently misses those. SitRep 12's corrected re-issue is
# exactly such a case, and it differs from the original on a real figure.
_DRAFT = re.compile(r"draft|daft", re.I)
_FINAL = re.compile(r"final|vf\d*|fv\d*|_ok|revised|corrige|corrigé", re.I)

# Non-MVE-2026 reports that the `sitrep` search also returns.
_BARE = re.compile(r"\d{1,3}\.pdf", re.I)
_EXCLUDE = re.compile(r"rougeole|rubeole|rubéole|MVE16|MVE-Ituri|MVE_Ituri", re.I)

# The endpoint also returns situation reports for the PREVIOUS DRC Ebola
# outbreak (the 16th epidemic, from September 2025), whose report numbers run
# 1-31 and so COLLIDE with the 2026 series. They are excluded by publication
# date. The 2026 (17th) epidemic's first report was published 2026-05-12.
EPIDEMIC_START = "2026-05-01"


def _pages(start: str):
    """Yield every media entry uploaded since `start`, following pagination.

    PAGINATION IS FOLLOWED VIA THE HEADER, never by stopping when a page comes
    back short. WordPress returns 99 items for `per_page=100` here, so the
    natural-looking `if len(batch) < per_page: break` exits after one page and
    silently drops two thirds of the series. The header is the only reliable
    statement of how many pages there are.
    """
    query = QUERY.format(start=start)
    page, total_pages = 1, 1
    while page <= total_pages:
        req = urllib.request.Request(f"{API}?{query}&page={page}",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            if page == 1:
                total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            yield from json.loads(resp.read())
        page += 1


def parse_row(entry: dict) -> dict | None:
    url = entry.get("source_url", "")
    name = url.rsplit("/", 1)[-1]
    if not url.lower().endswith(".pdf"):
        return None
    # A BARE-NUMBERED UPLOAD IS A CANDIDATE, NOT A MATCH. INSP re-uploaded
    # reports 083-085 as `83.pdf` after their named URLs began returning 404,
    # and published 091 only as `91.pdf`. A name carrying nothing but a digit
    # satisfies no predicate, so it is admitted here on the strength of the
    # window alone and left UNRESOLVED -- empty `sitrep`, which the summary
    # prints loudly -- until someone reads the front page and records it in
    # `sitrep_number_overrides.tsv`. Admitting it is what makes it visible;
    # guessing that `83.pdf` is report 83 is what this file exists to avoid.
    if not _BARE.fullmatch(name) and "MVE" not in name.upper():
        return None
    if _EXCLUDE.search(name):
        return None

    m_num = _NUM.search(name)
    num = next((g for g in m_num.groups() if g), None) if m_num else None
    date = ""
    if m := _DATE.search(name):
        date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    elif m := _DATE8.search(name):
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    elif m := _DATE_COMPACT.search(name):
        date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    elif m := _DATE6.search(name):
        date = f"20{m.group(3)}-{m.group(2)}-{m.group(1)}"

    is_draft = bool(_DRAFT.search(name))
    is_final = bool(_FINAL.search(name))
    return {
        "sitrep": str(int(num)) if num else "",
        "data_date": date,
        "published": entry.get("date", "")[:10],
        "status": "draft" if is_draft and not is_final else "final" if is_final else "plain",
        "pick": "",
        "filename": name,
        "url": url,
    }


def choose(rows: list[dict]) -> list[str]:
    """Mark one row per SitRep number as the preferred version, in place.

    Preference: a version marked final beats an unmarked one, which beats a
    draft; ties break on the later publication date. Rows with no parseable
    number are left unmarked and reported for manual resolution. Returns the
    SitRep numbers whose versions could not be ordered.
    """
    rank = {"final": 0, "plain": 1, "draft": 2}
    by_num: dict[str, list[dict]] = {}
    for r in rows:
        if r["sitrep"]:
            by_num.setdefault(r["sitrep"], []).append(r)
    ambiguous: list[str] = []
    for num, group in by_num.items():
        # A SAME-DAY PAIR IS AN AMBIGUITY; A LATER RE-UPLOAD IS A REPLACEMENT.
        # Re-issues of one report are normally uploaded the same day as the
        # original, and those genuinely cannot be ordered by date -- they are
        # ranked on the version marker alone and reported if still tied, because
        # the versions disagree on real figures and guessing is worse than
        # asking.
        #
        # But a re-upload DAYS later is a different event. Reports 083-085 were
        # published on 2026-08-09 at URLs that now return 404, and re-published
        # on 2026-08-13 as `83.pdf`. Treating that as an unresolvable tie picks
        # alphabetically, which picks the dead link. When the marker ties and
        # the publication dates DIFFER, the later upload wins.
        group.sort(key=lambda r: (rank[r["status"]], r["published"], r["filename"]))
        tied = [r for r in group if rank[r["status"]] == rank[group[0]["status"]]]
        if len(tied) > 1 and len({r["published"] for r in tied}) > 1:
            group = sorted(tied, key=lambda r: r["published"], reverse=True)
        group[0]["pick"] = "yes"
        if len(group) > 1 and rank[group[0]["status"]] == rank[group[1]["status"]] \
                and group[0]["published"] == group[1]["published"]:
            ambiguous.append(num)
    return ambiguous


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out

    # Committed overrides for PDFs whose filename carries no report number.
    # Read from the PDF front pages; see the file's header for why the
    # filename digits must not be parsed instead.
    overrides: dict[str, tuple[str, str]] = {}
    ov_path = REPO_ROOT / "registers" / "sitrep_number_overrides.tsv"
    # A MISSING REGISTER IS A HARD FAILURE, NOT AN EMPTY ONE. These overrides
    # carry the report number and DATA DATE for uploads whose filename states
    # neither correctly -- the filename gives the publication date on some, no
    # date at all on others, and on sitrep 038 a timestamp that parses as 2022.
    # When the file was moved and this path was not updated, the index rebuilt
    # itself from filename-derived dates without a word, and the next fetch
    # downloaded eleven reports we already held under a second, wrong name.
    if not ov_path.exists():
        raise SystemExit(
            f"the overrides register is missing: {ov_path}\n"
            "Without it the index takes its data dates from upload filenames, "
            "which are wrong on eleven reports. Refusing to write an index.")
    if ov_path.exists():
        for line in ov_path.read_text().splitlines():
            if line.startswith("#") or not line.strip() or line.startswith("filename\t"):
                continue
            fn, num, date = line.split("\t")
            overrides[fn] = (num, date)

    entries = list(_pages(EPIDEMIC_START))
    all_mve = [r for r in (parse_row(e) for e in entries) if r]
    for r in all_mve:
        if r["filename"] in overrides:
            r["sitrep"], r["data_date"] = overrides[r["filename"]]
    rows = [r for r in all_mve if r["published"] >= EPIDEMIC_START]
    prior_epidemic = len(all_mve) - len(rows)
    ambiguous = choose(rows)
    rows.sort(key=lambda r: (int(r["sitrep"]) if r["sitrep"] else 999, r["published"]))

    cols = ["sitrep", "data_date", "published", "status", "pick", "filename", "url"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(r[c] for c in cols) + "\n")

    # The API is paginated, so hash the emitted index rather than any single
    # response.
    record(out, f"{API}?{QUERY.format(start=EPIDEMIC_START)}")

    nums = sorted({int(r["sitrep"]) for r in rows if r["sitrep"]})
    picks = [r for r in rows if r["pick"]]
    unresolved = [r for r in rows if not r["sitrep"]]
    print(f"{len(entries)} media items -> {len(rows)} MVE PDFs for this epidemic -> {len(picks)} distinct reports")
    print(f"  excluded, prior (16th) epidemic published before {EPIDEMIC_START}: {prior_epidemic}")
    print(f"  SitRep range {min(nums)}-{max(nums)}")
    # "Absent from the media API" is not the same as "never published": a
    # corrected re-issue is sometimes only reachable through the per-post
    # endpoint. Report the gaps without asserting they do not exist.
    print(f"  absent from the media API: {sorted(set(range(min(nums), max(nums)+1)) - set(nums))}")
    print(f"  duplicate uploads collapsed: {len(rows) - len(picks) - len(unresolved)}")
    if ambiguous:
        print(f"  AMBIGUOUS version choice (same marker, same date) for SitRep "
              f"{sorted(ambiguous, key=int)} -- versions of the same report are known to\n"
              f"    disagree on real figures, so these need adjudicating, not guessing.")
    if unresolved:
        print(f"  UNRESOLVED (no number in filename; read the PDF front page):")
        for r in unresolved:
            print(f"    {r['published']}  {r['filename']}")


if __name__ == "__main__":
    main()
