"""Every PDF we hold hashes to what the manifest records, and none is missing.

The PDF archive is not committed -- it is ~141 MB and regenerable -- so what
pins it is `data/raw/sitrep_pdfs.manifest.tsv`: one row per report, with its
byte count and SHA-256. That makes the archive verifiable without being
versioned, but only if something actually verifies it.

This is that something, and it is the check that makes an archive obtained by
any route trustworthy. `fetch_sitrep_pdfs.py` downloads from INSP; a working
copy can equally be populated from a colleague's disk or a backup. Those are
the same archive only if every byte agrees, and the manifest is the arbiter.

THREE FAILURES ARE DISTINGUISHED, because they mean different things:

  missing   the manifest lists a report we do not hold -- an incomplete copy,
            fixed by fetching.
  extra     we hold a file the manifest does not list -- either the manifest is
            stale (a fetch that did not rewrite it) or the file does not belong
            to this archive. Never silently ignored: an unlisted PDF that
            reaches a parser is data with no provenance.
  corrupt   the file is present and its hash disagrees. This is the serious one.
            It means either a damaged copy or a report INSP revised in place
            under the same name -- and the second is a source event worth
            knowing about, not a transfer error to paper over.

Exit codes mirror `check_upstream.py`: 0 clean, 1 incomplete (fetch), 2 the
archive disagrees with its manifest (look first).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

READ_CHUNK = 1 << 20


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(READ_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdfs", required=True, type=Path)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    with args.manifest.open() as fh:
        expected = {r["file"]: r for r in csv.DictReader(fh, delimiter="\t")}

    held = {p.name for p in args.pdfs.glob("*.pdf")} if args.pdfs.is_dir() else set()

    missing = sorted(set(expected) - held)
    extra = sorted(held - set(expected))
    corrupt: list[tuple[str, str, str]] = []

    for name in sorted(set(expected) & held):
        path = args.pdfs / name
        row = expected[name]
        if path.stat().st_size != int(row["bytes"]):
            corrupt.append((name, f"{row['bytes']} bytes", f"{path.stat().st_size} bytes"))
            continue
        got = sha256(path)
        if got != row["sha256"]:
            corrupt.append((name, row["sha256"][:16], got[:16]))

    ok = len(expected) - len(missing) - len(corrupt)
    if not args.quiet:
        print(f"manifest lists {len(expected)} reports; {ok} verified")
    for name in missing:
        print(f"  MISSING  {name}", file=sys.stderr)
    for name in extra:
        print(f"  EXTRA    {name} (held, not in manifest)", file=sys.stderr)
    for name, want, got in corrupt:
        print(f"  CORRUPT  {name}: manifest {want}, file {got}", file=sys.stderr)

    if corrupt or extra:
        sys.exit(2)
    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
