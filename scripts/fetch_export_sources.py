"""Snapshot every document the export tables cite. NETWORKED.

Reads `data/raw/exports/sources.tsv` and downloads each `url` to
`data/raw/exports/snapshots/<source_id>.<ext>`, then writes
`data/raw/exports/snapshots.manifest.tsv`: one row per source with the sha256,
size, content type and fetch time of the bytes the quotes were checked against.

Why snapshots at all. The values in `cases.tsv` and `counts.tsv` are
transcribed by hand from web pages that change -- WHO's alert table is
overwritten in place, and one Nigerian ministry page sits on a site that is
publishing spam. A quote is only auditable against the bytes it was read from,
so those bytes are pinned by hash. Like the sitrep PDFs, the snapshots are not
committed; the manifest is, and a re-fetch whose hash differs is a page that
changed under us, which is worth knowing before trusting a quote from it.

A source that cannot be fetched is recorded with an empty hash and the error,
not dropped: a quote from it then fails `make check-exports` loudly rather
than passing for want of anything to check.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.provenance import UA, _encode  # noqa: E402

EXT = {"html": "html", "pdf": "pdf", "scanned": "pdf"}


def read_sources(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader((ln for ln in fh if not ln.startswith("#")),
                                   delimiter="\t"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sources", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for s in read_sources(args.sources):
        dest = args.out_dir / f"{s['source_id']}.{EXT[s['text_layer']]}"
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            req = urllib.request.Request(_encode(s["url"]),
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = resp.read()
                ctype = resp.headers.get("Content-Type", "")
            # A DOCUMENT OF THE WRONG KIND IS A FAILED FETCH. iris.who.int
            # serves a 755-byte JavaScript app shell, with HTTP 200, at the
            # bitstream link WHO publishes; it was accepted as a PDF until
            # this check. The direct content endpoint returns the file.
            if s["text_layer"] in ("pdf", "scanned") and not payload.startswith(b"%PDF"):
                raise OSError(f"expected a PDF, got {ctype or 'unknown type'} "
                              f"({len(payload)} B)")
            dest.write_bytes(payload)
            rows.append([s["source_id"], s["url"], hashlib.sha256(payload).hexdigest(),
                         len(payload), ctype, now, ""])
            print(f"  ok      {s['source_id']:20s} {len(payload):>9d} B")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            rows.append([s["source_id"], s["url"], "", 0, "", now, str(e)[:200]])
            print(f"  FAILED  {s['source_id']:20s} {e}")
    with args.manifest.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["source_id", "url", "sha256", "bytes", "content_type",
                    "fetched_utc", "error"])
        w.writerows(rows)
    failed = sum(1 for r in rows if not r[2])
    print(f"{len(rows) - failed} of {len(rows)} sources snapshotted"
          + (f"; {failed} failed (recorded, not dropped)" if failed else ""))


if __name__ == "__main__":
    main()
