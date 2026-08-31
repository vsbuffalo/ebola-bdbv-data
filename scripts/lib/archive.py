"""Which reports a build reads: the manifest, not whatever is on disk.

The PDF archive is not committed — it is too large — so what pins a release to
its inputs is `data/raw/sitrep_pdfs.manifest.tsv`, which *is* committed, one row
per report with its size and SHA-256. Every extractor used to read
`pdf_dir.glob("*.pdf")` instead, which means a build read whatever happened to
be in the directory at the time.

Why that mattered. It made a release reproducible only at the moment it was
cut. Check out `data/2026-08-22`, whose manifest lists 91 reports, with today's
100 on disk, and the build would read all 100 — so the figures and streams it
produced would not be that release's. `verify_archive.py` exits 2 on a held
file the manifest does not list, so the attempt failed rather than silently
producing the wrong answer, but it failed: there was no way to rebuild a past
release at all, and no way to see how a figure changed between two of them
except by having kept the images.

Reading the manifest instead closes that. A checkout of any tag reads exactly
the reports that tag pinned, whatever else is on disk, so
`make figures-release TAG=...` can reconstruct any release's figures on demand
and none of them need to be committed.

The manifest path is derived from the archive directory rather than passed
around: `data/raw/sitrep_pdfs` -> `data/raw/sitrep_pdfs.manifest.tsv`, which is
the convention `verify_archive.py` and the Makefile already use. One fewer flag
on seven scripts, and no way for a caller to point the two at different things.

Three failures, all loud:

  no manifest        A build with no pinned input set is not a build we can
                     reproduce. There is deliberately no fall-back to globbing:
                     that fall-back is the behaviour this module exists to end,
                     and a silent one would be indistinguishable from it.
  a listed report    The manifest names a report the archive does not hold.
  missing            The build would be short of inputs and every downstream
                     count wrong, with nothing to say so.
  unreadable row     The manifest is the pin; a row that cannot be parsed means
                     we do not know what the pin says.

A held PDF the manifest does not list is *skipped*, and that is the whole
point — but never in silence. It is returned in `extra` so the caller can say
how many reports it passed over, which is information only when building an
older tag and is exactly when a reader needs it.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path


def manifest_for(pdf_dir: Path) -> Path:
    """The manifest that pins this archive directory."""
    return pdf_dir.with_name(pdf_dir.name + ".manifest.tsv")


def held_pdfs(pdf_dir: Path) -> tuple[list[Path], list[str]]:
    """`(the reports this build reads, the held files it passed over)`.

    The first list is every PDF the manifest names, in manifest order, as paths
    under `pdf_dir`. The second is the names of PDFs present on disk that the
    manifest does not name — skipped, and reported by the caller rather than
    ignored.
    """
    manifest = manifest_for(pdf_dir)
    if not manifest.exists():
        sys.exit(
            f"no manifest at {manifest}, so there is nothing pinning which "
            "reports this build reads. The archive directory is not the pin: "
            "it holds whatever was last fetched, and a build over it cannot be "
            "reproduced from a tag. Run `make manifest`.")
    listed: list[str] = []
    with manifest.open(newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh, delimiter="\t"), start=2):
            name = (row.get("file") or "").strip()
            if not name:
                sys.exit(f"{manifest}:{i}: row has no `file`; the manifest is "
                         "what pins this build's inputs and it cannot be read.")
            listed.append(name)

    absent = [n for n in listed if not (pdf_dir / n).exists()]
    if absent:
        sys.exit(
            f"{manifest} lists {len(absent)} report(s) the archive does not "
            f"hold:\n  " + "\n  ".join(absent)
            + "\nEvery count downstream would be short by whatever these "
              "carry, with nothing in the output to say so. Run `make fetch`.")

    on_disk = {p.name for p in pdf_dir.glob("*.pdf")}
    extra = sorted(on_disk - set(listed))
    return [pdf_dir / n for n in listed], extra


def report_skipped(extra: list[str], where: str = "") -> None:
    """Say how many held reports the manifest did not name, if any.

    Zero on a current build, non-zero exactly when an older tag is being
    rebuilt over a newer archive — which is the case a reader must not have to
    infer from a row count.
    """
    if not extra:
        return
    head = ", ".join(extra[:3]) + (" ..." if len(extra) > 3 else "")
    print(f"  {where}note: {len(extra)} PDF(s) on disk are not in this "
          f"manifest and were not read ({head})", file=sys.stderr)
