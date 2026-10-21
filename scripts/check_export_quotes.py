"""Every quoted value in the export tables is on the page it cites. OFFLINE.

Two checks, against the snapshots `make fetch-exports` took:

1. Each snapshot hashes to what `snapshots.manifest.tsv` records, so a quote is
   being checked against the bytes the table was written from and not against
   whatever a later fetch returned.
2. Each quote whose `quote_check` is `snapshot` appears in its source's text
   (`lib.snapshot_text`: tags stripped, typographic quotes and whitespace
   normalised, case folded -- nothing that would let a misquote through).

A quote marked `transcribed` is read off a scanned image with no text layer and
cannot be checked mechanically. That is allowed only for a source declared
`scanned`; a `transcribed` quote from an HTML page or a text PDF is a check
someone skipped, and fails here.

Not part of `make streams`: a consumer rebuilding from a tag holds the tables
but not the snapshots, which are uncommitted like the sitrep PDFs. It runs in
the release gate, where the snapshots are present.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.snapshot_text import document_text, normalise  # noqa: E402


def read_tsv(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader((ln for ln in fh if not ln.startswith("#")),
                                   delimiter="\t"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exports", type=Path, required=True)
    args = ap.parse_args()
    snap_dir = args.exports / "snapshots"

    sources = {s["source_id"]: s for s in read_tsv(args.exports / "sources.tsv")}
    manifest = {m["source_id"]: m for m in read_tsv(args.exports / "snapshots.manifest.tsv")}

    failures: list[str] = []
    texts: dict[str, str] = {}

    def text_of(sid: str) -> str | None:
        if sid in texts:
            return texts[sid]
        m = manifest.get(sid)
        files = list(snap_dir.glob(f"{sid}.*"))
        if not m or not m["sha256"] or not files:
            return None
        got = hashlib.sha256(files[0].read_bytes()).hexdigest()
        if got != m["sha256"]:
            failures.append(f"{sid}: snapshot hashes {got[:12]}, manifest "
                            f"records {m['sha256'][:12]} -- re-run "
                            "`make fetch-exports` and re-read the quotes")
            texts[sid] = ""
            return ""
        texts[sid] = document_text(files[0])
        return texts[sid]

    rows = ([("counts", r, r["source_id"]) for r in read_tsv(args.exports / "counts.tsv")]
            + [("cases", r, r["quote_source"]) for r in read_tsv(args.exports / "cases.tsv")])
    n_checked = n_transcribed = 0
    for table, r, sid in rows:
        label = f"{table}.tsv {r.get('case_id') or r['country'] + ' ' + r['as_of']}"
        quote = r["quote"] if table == "counts" else r["classification_verbatim"]
        if r["quote_check"] == "transcribed":
            if sources[sid]["text_layer"] != "scanned":
                failures.append(f"{label}: marked transcribed, but {sid} has a "
                                f"{sources[sid]['text_layer']} text layer and "
                                "can be checked")
            n_transcribed += 1
            continue
        text = text_of(sid)
        if text is None:
            failures.append(f"{label}: no snapshot of {sid} to check against "
                            "(run `make fetch-exports`)")
        elif normalise(quote) not in text:
            failures.append(f"{label}: «{quote[:70]}» is not in {sid}")
        n_checked += 1

    print(f"  {n_checked} quotes checked against their snapshots; "
          f"{n_transcribed} transcribed from scanned images and not checkable")
    if failures:
        print("EXPORT QUOTES DO NOT CHECK:\n  " + "\n  ".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    main()
