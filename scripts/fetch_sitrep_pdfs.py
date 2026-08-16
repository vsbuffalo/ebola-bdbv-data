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

    got = skipped = failed = 0
    for r in rows:
        date = r["data_date"] or "undated"
        dest = out / f"sitrep_{int(r['sitrep']):03d}_{date}.pdf"
        if dest.exists():
            skipped += 1
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
        got += 1

    total = len(list(out.glob("*.pdf")))
    print(f"downloaded {got}, already present {skipped}, failed {failed}")
    print(f"  {total} PDFs in {out.relative_to(REPO_ROOT)}")
    if failed:
        raise SystemExit(1)

    if args.manifest:
        want = {f"sitrep_{int(r['sitrep']):03d}_{r['data_date'] or 'undated'}.pdf"
                for r in rows}
        mf = (args.manifest if args.manifest.is_absolute()
              else REPO_ROOT / args.manifest)
        _write_manifest(out, want, mf)


def _write_manifest(out_dir: Path, index, manifest: Path) -> None:
    """Every PDF with its hash, and the index checked in BOTH directions.

    One direction alone is half a check: a missing file and a stray file are
    different failures, and testing only for the first leaves the second silent
    -- and a stray PDF in this directory is globbed straight into the trunk by
    both parsers.
    """
    import hashlib
    files = sorted(out_dir.glob("*.pdf"))
    rows = []
    for f in files:
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        rows.append({"file": f.name, "bytes": f.stat().st_size, "sha256": h})
    have = {r["file"] for r in rows}
    want = {r for r in index}
    missing, stray = sorted(want - have), sorted(have - want)
    if missing or stray:
        sys.exit(f"archive does not match the index.\n"
                 f"  in the index, no file: {missing}\n"
                 f"  file, not in the index: {stray}")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "bytes", "sha256"],
                           delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    print(f"  manifest: {len(rows)} PDFs, index reconciles in both directions")


if __name__ == "__main__":
    main()
