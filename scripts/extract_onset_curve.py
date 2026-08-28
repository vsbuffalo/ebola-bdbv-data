#!/usr/bin/env python
"""Read the symptom-onset epidemic curve out of the sitrep PDFs' pixels.

Which source: the INSP situation-report PDFs pinned in
`data/raw/sitrep_pdfs/` (primary). The chart is an embedded raster with no
data table anywhere, so its pixels are the only record of the DHIS2 onset
curve the reports publish. The one manual input is
`registers/onset_axis_anchors.tsv`, a printed tick label per distinct image,
triple-checked against the detected geometry.

What it produces, all under `data/build/onset/`:
  vintages.csv    one row per report: identity, calibration, read totals,
                  printed-total reconciliation, deduplication, and a gate
                  verdict with its reasons. Refusals are rows, not absences.
  snapshots.csv   the levels: one row per (distinct image, onset date) with
                  alive and dead counts, flags, and the render's resolution.
  triangle.csv    derived, never primary: increments between consecutive
                  accepted deduplicated vintages on the intersection of
                  their axis extents, both endpoints named on every row.
  images/         the exact decoded pixels every number was read from.
  proof/          the reader's conclusions drawn onto those pixels, for the
                  human check no CSV can give.

Fitted: no. This is extraction; nothing here enters a model.

Validated by: the figure's own printed total (24 titled renders reconcile to
a worst deficit of -0.6%), cross-vintage monotonicity and alignment gates
over all of history on every run, and the design's regression fixtures in
tests/test_onset.py. Design: notes/2026-08-28-onset-digitiser-design.md;
measured failure modes it answers:
notes/2026-08-28-onset-digitiser-requirements.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import polars as pl
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.onset.pdfimg import extract_chart_candidates, tool_version   # noqa: E402
from lib.onset.identify import identify                               # noqa: E402
from lib.onset.calibrate import calibrate, CalibrationError           # noqa: E402
from lib.onset.readers import read_bars, refine_scale                 # noqa: E402
from lib.onset.assemble import (Vintage, load_anchors, slot_dates,    # noqa: E402
                                value_dedup, triangle)
from lib.onset.gates import judge                                     # noqa: E402
from lib.onset.proof import draw_proof                                # noqa: E402
from lib.report_date import FILENAME, report_key                      # noqa: E402

# The onset figure first appears in sitrep 059 (12 July). Earlier reports
# carry no onset chart at all and are not candidates, not refusals.
FIRST_ONSET_SITREP = 59


def locate_and_identify(pdf_dir: Path, images_dir: Path,
                        lo: int, hi: int) -> tuple[list[dict], dict]:
    """One inventory row per report, and the earliest carrier per image."""
    rows: list[dict] = []
    first_carrier: dict[str, dict] = {}     # sha -> {file, sitrep, date}
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
                rows.append({"sitrep": number, "report_date": data_date,
                             "page": None, "width": None, "height": None,
                             "encoding": None, "compressed_bytes": None,
                             "decoded_sha256": None, "image_file": None,
                             "kind": "refused", "evidence": reason})
                continue
            c, ident = onset[0]
            if c.decoded_sha256 not in first_carrier:
                name = f"{data_date}-{number:03d}-{c.decoded_sha256[:12]}.png"
                shutil.copyfile(c.png_path, images_dir / name)
                first_carrier[c.decoded_sha256] = {
                    "file": name, "sitrep": number, "date": data_date}
            rows.append({"sitrep": number, "report_date": data_date,
                         "page": c.page, "width": c.width,
                         "height": c.height, "encoding": c.encoding,
                         "compressed_bytes": c.compressed_bytes,
                         "decoded_sha256": c.decoded_sha256,
                         "image_file": first_carrier[c.decoded_sha256]["file"],
                         "kind": ident.kind, "evidence": ident.evidence})
    return rows, first_carrier


def read_vintages(rows: list[dict], first_carrier: dict,
                  images_dir: Path) -> tuple[dict[str, Vintage],
                                             dict[str, str]]:
    """Calibrate, read and date each distinct image; failures become
    refusal reasons keyed by hash."""
    anchors = load_anchors()
    vintages: dict[str, Vintage] = {}
    failures: dict[str, str] = {}
    carriers: dict[str, list[int]] = {}
    for row in rows:
        sha = row["decoded_sha256"]
        if sha:
            carriers.setdefault(sha, []).append(row["sitrep"])
    for sha, info in first_carrier.items():
        img = Image.open(images_dir / info["file"]).convert("RGB")
        im = np.asarray(img).astype(float)
        try:
            cal = refine_scale(im, calibrate(im))
            anchor = anchors.get(sha[:12])
            if anchor is None:
                raise CalibrationError(
                    f"no anchor row for {sha[:12]} in "
                    "registers/onset_axis_anchors.tsv; add the printed "
                    "tick labels from the proof crop")
            dates = slot_dates(cal, anchor)
        except CalibrationError as e:
            failures[sha] = str(e)
            continue
        bars = read_bars(im, cal)
        vintages[sha] = Vintage(
            sha256=sha, image_file=info["file"],
            sitreps=tuple(sorted(carriers[sha])),
            report_date=dt.date.fromisoformat(info["date"]),
            printed_n=cal.printed_n, calibration=cal,
            bars=tuple(bars), dates=tuple(dates))
    return vintages, failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf-dir", type=Path,
                    default=Path("data/raw/sitrep_pdfs"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/build/onset"))
    ap.add_argument("--min-sitrep", type=int, default=FIRST_ONSET_SITREP)
    ap.add_argument("--max-sitrep", type=int, default=999)
    args = ap.parse_args()

    images_dir = args.out_dir / "images"
    proof_dir = args.out_dir / "proof"
    for d in (images_dir, proof_dir):
        d.mkdir(parents=True, exist_ok=True)

    rows, firsts = locate_and_identify(args.pdf_dir, images_dir,
                                       args.min_sitrep, args.max_sitrep)
    vintages, failures = read_vintages(rows, firsts, images_dir)

    # Re-encodes and re-renders of one data snapshot collapse; the gates
    # then judge the surviving heads in report-date order.
    groups = value_dedup(list(vintages.values()))
    head_of: dict[str, str] = {}
    for head, members in groups:
        head_of[head.sha256] = head.sha256
        for mv in members:
            head_of[mv.sha256] = head.sha256
    heads = [head for head, _ in groups]
    verdicts = judge(heads)

    # --- vintages.csv: one row per report, everything joined on.
    out_rows = []
    for row in rows:
        sha = row["decoded_sha256"]
        r = dict(row)
        if sha is None:
            r.update({"status": "refused", "reasons": row["evidence"],
                      "dedup_head": None, "printed_n": None,
                      "read_total": None, "read_alive": None,
                      "read_dead": None, "stable_total": None,
                      "px_per_case": None, "day_px": None, "y_step": None,
                      "agreement": None})
        elif sha in failures:
            r.update({"status": "refused", "reasons": failures[sha],
                      "dedup_head": None, "printed_n": None,
                      "read_total": None, "read_alive": None,
                      "read_dead": None, "stable_total": None,
                      "px_per_case": None, "day_px": None, "y_step": None,
                      "agreement": None})
        else:
            head_sha = head_of[sha]
            head = next(v for v in heads if v.sha256 == head_sha)
            v = vintages[sha]
            verdict = verdicts[head_sha]
            from lib.onset.gates import stable_total
            r.update({
                "status": verdict.status,
                "reasons": "; ".join(verdict.reasons),
                "dedup_head": head_sha[:12],
                "printed_n": v.printed_n,
                "read_total": v.total,
                "read_alive": sum(b.alive for b in v.bars),
                "read_dead": sum(b.dead for b in v.bars),
                "stable_total": stable_total(v),
                "px_per_case": round(v.calibration.px_per_case, 4),
                "day_px": round(v.calibration.day_px, 3),
                "y_step": v.calibration.y_step,
                "agreement": round(
                    sum(b.reader_agreement for b in v.bars) / len(v.bars), 3),
            })
        out_rows.append(r)
    pl.DataFrame(out_rows).sort("sitrep").write_csv(
        args.out_dir / "vintages.csv")

    # --- snapshots.csv: levels for every read vintage, judged or not; the
    # status travels on each row so nothing consumes a refused level blind.
    snap = []
    for head, members in groups:
        verdict = verdicts[head.sha256]
        for b, d in zip(head.bars, head.dates):
            snap.append({
                "report_date": head.report_date.isoformat(),
                "sitrep": head.sitreps[0],
                "sha12": head.sha256[:12],
                "onset_date": d.isoformat(),
                "alive": b.alive, "dead": b.dead,
                "total": b.alive + b.dead,
                "provisional": b.provisional,
                "reader_agreement": b.reader_agreement,
                "margin": round(b.margin, 2),
                "resolution_cases": round(b.resolution_cases, 4),
                "status": verdict.status,
            })
    pl.DataFrame(snap).write_csv(args.out_dir / "snapshots.csv")

    # --- triangle.csv: increments between consecutive accepted heads only.
    accepted = [h for h in heads
                if verdicts[h.sha256].status != "refused"]
    pl.DataFrame(triangle(accepted)).write_csv(
        args.out_dir / "triangle.csv")

    # --- proof overlays, one per distinct image.
    for head, members in groups:
        verdict = verdicts[head.sha256]
        for v in [head] + members:
            img = Image.open(images_dir / v.image_file)
            draw_proof(img, v, verdict.status, verdict.reasons).save(
                proof_dir / v.image_file)

    n_ok = sum(1 for h in heads if verdicts[h.sha256].status == "accepted")
    n_cav = sum(1 for h in heads
                if verdicts[h.sha256].status == "accepted_with_caveat")
    n_ref = len(heads) - n_ok - n_cav
    print(f"  {args.out_dir}: {len(out_rows)} reports, "
          f"{len(vintages)} read images -> {len(heads)} vintages after "
          f"dedup ({n_ok} accepted, {n_cav} with caveat, {n_ref} refused); "
          f"{len(failures)} calibration refusals   [{tool_version()}]")


if __name__ == "__main__":
    main()
