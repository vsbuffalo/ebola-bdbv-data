#!/usr/bin/env python
"""Read the symptom-onset epidemic curve out of the sitrep PDFs' pixels.

Which source: the INSP situation-report PDFs pinned in
`data/raw/sitrep_pdfs/` (primary). The chart is an embedded raster with no
data table anywhere, so its pixels are the only record of the DHIS2 onset
curve the reports publish.

What it produces: `data/build/onset/vintages.csv`, one row per report --
either an identified onset figure with its decoded-pixel identity, or an
explicit refusal saying what the report carries instead. Identified charts
are published to `data/build/onset/images/<date>-<sitrep>-<sha12>.png`, one
file per distinct decoded image, named by the earliest report that carried
it. Later stages (calibration, the two readers, the gates) extend this
driver; the inventory is the part every one of them depends on.

Fitted: no. This is extraction; nothing here enters a model.

Validated by: the identification thresholds are measured with an order of
magnitude of margin (scripts/lib/onset/identify.py documents the table), and
reports 084-086 -- whose captions claim an onset figure over notification
charts -- must appear as refusals naming what was actually found. The design
and its failure-mode requirements: notes/2026-08-28-onset-digitiser-design.md.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np                                                    # noqa: E402
from PIL import Image                                                 # noqa: E402

from lib.onset.pdfimg import extract_chart_candidates, tool_version   # noqa: E402
from lib.onset.identify import identify                               # noqa: E402
from lib.onset.calibrate import calibrate, CalibrationError           # noqa: E402
from lib.report_date import FILENAME, report_key                      # noqa: E402

# The onset figure first appears in sitrep 059 (12 July). Earlier reports
# carry no onset chart at all and are not candidates, not refusals.
FIRST_ONSET_SITREP = 59


def inventory(pdf_dir: Path, out_dir: Path,
              lo: int, hi: int) -> pl.DataFrame:
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    seen_sha: dict[str, str] = {}       # decoded_sha256 -> published filename

    with tempfile.TemporaryDirectory(prefix="onset-extract-") as tmp:
        work = Path(tmp)
        for pdf in sorted(pdf_dir.glob("sitrep_*.pdf")):
            m = FILENAME.search(pdf.stem)
            if not m or not lo <= int(m.group(1)) <= hi:
                continue
            number, data_date = report_key(pdf)
            cands = [(c, identify(c.png_path))
                     for c in extract_chart_candidates(pdf, work)]
            onset = [(c, i) for c, i in cands if i.kind == "onset_daily"]
            others = ", ".join(sorted({i.kind for _, i in cands
                                       if i.kind != "onset_daily"})) or "none"

            if len(onset) != 1:
                reason = (f"no onset figure: candidates were [{others}]"
                          if not onset else
                          f"{len(onset)} onset-like figures on one report")
                rows.append({
                    "sitrep": number, "report_date": data_date,
                    "page": None, "width": None, "height": None,
                    "encoding": None, "compressed_bytes": None,
                    "decoded_sha256": None, "image_file": None,
                    "kind": "refused", "evidence": reason,
                })
                continue

            c, ident = onset[0]
            name = seen_sha.get(c.decoded_sha256)
            if name is None:
                name = f"{data_date}-{number:03d}-{c.decoded_sha256[:12]}.png"
                shutil.copyfile(c.png_path, images_dir / name)
                seen_sha[c.decoded_sha256] = name
            rows.append({
                "sitrep": number, "report_date": data_date,
                "page": c.page, "width": c.width, "height": c.height,
                "encoding": c.encoding, "compressed_bytes": c.compressed_bytes,
                "decoded_sha256": c.decoded_sha256, "image_file": name,
                "kind": ident.kind, "evidence": ident.evidence,
            })

    # Calibration runs once per distinct image; reprints inherit their
    # earliest carrier's numbers, which is the deduplication the design
    # requires anyway.
    calib: dict[str, dict] = {}
    for sha, name in seen_sha.items():
        im = np.asarray(Image.open(images_dir / name).convert("RGB")) \
               .astype(float)
        try:
            c = calibrate(im)
            calib[sha] = {
                "day_px": round(c.day_px, 3),
                "px_per_case": round(c.px_per_case, 4),
                "y_step": c.y_step,
                "printed_n": c.printed_n,
                "n_slots": c.n_slots,
                "n_ticks": len(c.tick_xs),
                "band_left": c.band_left,
                "calibration": "ok",
                "calibration_detail": "",
            }
        except CalibrationError as e:
            calib[sha] = {"day_px": None, "px_per_case": None,
                          "y_step": None, "printed_n": None,
                          "n_slots": None, "n_ticks": None,
                          "band_left": None,
                          "calibration": "refused",
                          "calibration_detail": str(e)}
    empty = {k: None for k in next(iter(calib.values()))} if calib else {}
    for row in rows:
        row.update(calib.get(row["decoded_sha256"], empty))

    return pl.DataFrame(rows).sort("sitrep")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf-dir", type=Path,
                    default=Path("data/raw/sitrep_pdfs"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/build/onset"))
    ap.add_argument("--min-sitrep", type=int, default=FIRST_ONSET_SITREP)
    ap.add_argument("--max-sitrep", type=int, default=999)
    args = ap.parse_args()

    df = inventory(args.pdf_dir, args.out_dir, args.min_sitrep,
                   args.max_sitrep)
    out = args.out_dir / "vintages.csv"
    df.write_csv(out)

    n_onset = df.filter(pl.col("kind") == "onset_daily").height
    n_ref = df.filter(pl.col("kind") == "refused").height
    n_img = df["image_file"].drop_nulls().unique().len()
    print(f"  {out}: {df.height} reports -> {n_onset} onset figures "
          f"({n_img} distinct images), {n_ref} refusals   [{tool_version()}]")


if __name__ == "__main__":
    main()
