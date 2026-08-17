"""Download the INSP situation-report PDFs listed in the committed index.

Only the preferred version of each report is fetched (the `pick` column; see
fetch_sitrep_index.py for how draft-vs-final is chosen). Files are renamed
canonically as `sitrep_<NNN>_<data-date>.pdf` so the directory sorts
chronologically regardless of the source filename, which is inconsistent.

The PDFs are large (~1.5 MB each, ~110 MB total) so they are NOT committed;
`data/raw/insp_sitrep_index.tsv` plus PROVENANCE.tsv is what pins them. Already
downloaded files are skipped, so this is safe to re-run to pick up new reports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

from lib.provenance import REPO_ROOT, fetch


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0, help="fetch at most N (0 = all)")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="THE RULE'S OUTPUT, in place of the directory itself. "
                         "Declaring the 124 MB archive as a `directory()` output "
                         "made the primary source a build artefact -- Snakemake "
                         "removes those on a forced or failed job, so `-F` "
                         "deleted and re-downloaded it. The manifest lists every "
                         "PDF with its size and SHA-256, so it changes when the "
                         "archive changes and not otherwise, and it doubles as "
                         "the bidirectional index check: an index row with no "
                         "file and a file with no index row are both errors.")
    args = ap.parse_args()

    index = args.index if args.index.is_absolute() else REPO_ROOT / args.index
    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)

    with index.open() as fh:
        rows = [r for r in csv.DictReader(fh, delimiter="\t") if r["pick"] == "yes"]
    rows.sort(key=lambda r: int(r["sitrep"]))
    if args.limit:
        rows = rows[: args.limit]

    # WHAT WE ALREADY HOLD, BY CONTENT. A file is recognised by its bytes, not
    # by the name we happened to give it. Recognising it by name instead meant
    # that when the naming rule changed, every held report was downloaded a
    # SECOND time under the new name: one refresh took the archive from 82 files
    # to 94, with eleven documents present twice, byte-identical, under two
    # different dates. The extraction would then have read each of those reports
    # twice and placed the same counts at two points in the series.
    held = {}
    for f in out.glob("*.pdf"):
        held[hashlib.sha256(f.read_bytes()).hexdigest()] = f

    got = skipped = renamed = failed = 0
    revised: list[str] = []
    for r in rows:
        date = r["data_date"] or "undated"
        dest = out / f"sitrep_{int(r['sitrep']):03d}_{date}.pdf"
        if dest.exists():
            # A HELD NAME IS NOT A HELD DOCUMENT. Skipping on the filename
            # alone is blind to revision in both of its forms: a corrected
            # upload re-picked under a NEW url usually shares the data date,
            # so it maps to this same canonical name -- the committed index
            # already has that exact shape for sitrep 012 -- and a report
            # revised IN PLACE keeps its url entirely. The held file is
            # therefore checked against what the pick URL currently serves,
            # by size first (a HEAD request; the server sends Content-Length)
            # and by bytes if the size matches nothing we can rule out. A
            # difference is never silently resolved in either direction: a
            # revision changes what every register judgement was ABOUT, so it
            # stops the fetch and asks for adjudication.
            try:
                import urllib.request
                from lib.provenance import UA, _encode
                # The UA and the percent-encoding matter here exactly as they
                # do on the GET path: INSP 403s default user agents, and many
                # filenames carry a literal degree sign urllib cannot put on
                # the wire. The first run of this check forgot both and
                # reported all 83 held reports unverifiable.
                req = urllib.request.Request(_encode(r["url"]), method="HEAD",
                                             headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    clen = int(resp.headers.get("Content-Length") or -1)
            except Exception as exc:  # noqa: BLE001
                print(f"  SitRep {r['sitrep']}: held, but the pick URL could "
                      f"not be checked ({type(exc).__name__}) -- treating as "
                      "unverified, NOT as current", file=sys.stderr)
                failed += 1
                continue
            if clen == dest.stat().st_size:
                skipped += 1
                continue
            revised.append(
                f"  sitrep {r['sitrep']}: held {dest.name} is "
                f"{dest.stat().st_size} bytes; the pick URL now serves "
                f"{clen} bytes ({r['url']})")
            continue
        try:
            payload = fetch(r["url"], dest)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  FAILED SitRep {r['sitrep']}: {type(exc).__name__}: {exc}")
            failed += 1
            continue
        if not payload.startswith(b"%PDF"):
            print(f"  FAILED SitRep {r['sitrep']}: not a PDF ({payload[:20]!r})")
            dest.unlink(missing_ok=True)
            failed += 1
            continue

        # ALREADY HELD UNDER ANOTHER NAME. The index's `data_date` comes from
        # the UPLOAD FILENAME, and the filename is not reliable: it carries the
        # publication date on some reports, no date at all on others, and on
        # sitrep 038 a timestamp that parses as the year 2022. The archive is
        # named from the page's own `Date de rapportage` instead. When the two
        # disagree the download is a document we already have, so it is
        # discarded and the held copy keeps its page-derived name.
        digest = hashlib.sha256(payload).hexdigest()
        if digest in held and held[digest] != dest:
            dest.unlink(missing_ok=True)
            print(f"  SitRep {r['sitrep']}: already held as "
                  f"{held[digest].name} (the index dates it {date})")
            renamed += 1
            continue
        held[digest] = dest
        got += 1

    total = len(list(out.glob("*.pdf")))
    print(f"downloaded {got}, already present {skipped}, "
          f"already held under another name {renamed}, failed {failed}")
    print(f"  {total} PDFs in {out.relative_to(REPO_ROOT)}")
    if revised:
        sys.exit("THE SOURCE HAS REVISED REPORTS WE HOLD:\n"
                 + "\n".join(revised)
                 + "\nNothing was replaced. Download the revision beside the "
                   "held copy, read both, and adjudicate: every hash-keyed "
                   "register judgement is about ONE version of a document.")
    undated = sorted(f.name for f in out.glob("sitrep_*_undated.pdf"))
    if undated:
        sys.exit("archive holds reports with no data date: "
                 + ", ".join(undated)
                 + "\nAdd a date override in registers/sitrep_number_overrides"
                   ".tsv -- the extraction refuses undated names, so these "
                   "reports contribute nothing until dated.")
    if failed:
        raise SystemExit(1)

    if args.manifest:
        # Keyed on the report NUMBER, not on the index's date: the archive is
        # named from the page and the index from the upload filename, and the
        # two disagree on eleven reports. What must hold is that we have one
        # file per picked report, not that its name matches the index's guess.
        want_nums = {int(r["sitrep"]) for r in rows}
        mf = (args.manifest if args.manifest.is_absolute()
              else REPO_ROOT / args.manifest)
        _write_manifest(out, want_nums, mf)


def _write_manifest(out_dir: Path, want_nums: set[int], manifest: Path) -> None:
    """Every PDF with its hash, and the index checked in BOTH directions.

    One direction alone is half a check: a missing report and a stray file are
    different failures, and testing only for the first leaves the second silent
    -- a stray PDF in this directory is globbed straight into the trunk.

    RECONCILED ON THE REPORT NUMBER, not on the filename. The archive is named
    from each page's own `Date de rapportage` and the index from the upload
    filename, and the two disagree on eleven reports -- the filename carries the
    publication date on some, no date at all on others, and on sitrep 038 a
    timestamp that parses as the year 2022. Comparing names made every one of
    those look like a missing report AND a stray file at once. What must hold is
    that we have exactly one file per picked report.
    """
    import hashlib
    import re as _re
    files = sorted(out_dir.glob("*.pdf"))
    rows, by_num, unnamed = [], {}, []
    for f in files:
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        rows.append({"file": f.name, "bytes": f.stat().st_size, "sha256": h})
        m = _re.match(r"sitrep_(\d+)_", f.name)
        if m:
            by_num.setdefault(int(m.group(1)), []).append(f.name)
        else:
            # A file the pattern cannot NAME would escape both directions of
            # this reconciliation -- in the manifest (so `verify` blesses it)
            # yet in no number bucket (so it is never stray) -- and the
            # extraction would then read or skip it unchecked.
            unnamed.append(f.name)
    missing = sorted(want_nums - by_num.keys())
    stray = sorted(n for n in by_num if n not in want_nums)
    doubled = {n: v for n, v in by_num.items() if len(v) > 1}
    if missing or stray or doubled or unnamed:
        sys.exit(f"archive does not match the index.\n"
                 f"  in the index, no file: {missing}\n"
                 f"  file, not in the index: {stray}\n"
                 f"  report held more than once: {doubled}\n"
                 f"  file the naming pattern cannot place: {unnamed}")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "bytes", "sha256"],
                           delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    print(f"  manifest: {len(rows)} PDFs, index reconciles in both directions")


if __name__ == "__main__":
    main()
