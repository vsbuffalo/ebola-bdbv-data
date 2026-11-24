"""The day's national laboratory total, read from the front page.

SOURCE       The INSP situation reports' first page, the "faits saillants"
             (highlights) block. PRIMARY.
PRODUCES     One row per report: how many new samples the laboratories that
             reported analysed that day nationally, how many were positive,
             and the positivity the page prints beside them.
FITTED       Intended for the national model class as the testing-effort
             anchor, in place of a sum over whichever provinces the
             laboratory section happened to write out legibly.
VALIDATED BY the sentence itself: the positive count is accepted only when it
             is the unique integer in the sentence that, divided by the sample
             count, reproduces the printed percentage. Independently, by the
             laboratory section: of the 42 reports from 130 to 177 that both
             readers cover, the province paragraphs read by
             `extract_lab_prose.py` sum to this sentence's samples and
             positives exactly on 13, and to less on most of the rest
             (median 98 %), where a paragraph was refused or never written
             out. And the positives equal the day's printed new confirmed
             cases on 50 of the 53 single-day intervals where both are read.

WHY THIS READER EXISTS. From report 176 (6 November 2026) the laboratory
section's province paragraphs changed shape and kept changing: one day
"Ituri : 308 échantillons reçus et testés au total ... positivité globale de
12,2 %", the next a three-way split into new samples, repeat samples and
samples from deaths, each with its own rate, and on some days no positive
count at all ("Nord-Kivu : Sur 165 échantillons reçus, 164 ont été
analysés"). The per-province reader refused most of them, and the national
testing series built from its sum fell from about 450 samples a day to under
40 while every gate passed. The front page kept printing one sentence of
fixed shape throughout:

    "Un total de 435 nouveaux échantillons a été analysé dans les
     laboratoires ayant transmis leurs données ; 56 de ces échantillons se
     sont révélés positifs au virus Bundibugyo, soit 12,9 % de positivité."

Its opening varies ("Au total, 453 nouveaux échantillons ont été analysés",
"Des 446 nouveaux échantillons analysés, 56 ...", "Pour la journée du 22
septembre 2026, 328 nouveaux échantillons ..."), so the reader anchors on
"N nouveaux échantillons" and on the printed percentage, never on the
opening words.

WHAT THE NUMBER MEANS, AND WHERE IT CHANGES. Through report 177 the sample
count is the sum of the province paragraphs. From report 178 it is
about a third higher (roughly 620 a day against 450) while the positives,
which still equal the day's new confirmed cases, do not rise; the province
paragraphs of the same reports start counting repeat samples of known
patients in their totals ("relevés et nouveaux échantillons confondus").
The denominator most likely widened at 178 to include repeat samples, and
positivity computed from it is not comparable across that date. Each row
carries `vintage` so a consumer can tell the two apart.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pdftext import pdftotext  # noqa: E402
from lib.report_date import FILENAME, report_key  # noqa: E402
from lib.archive import held_pdfs, report_skipped  # noqa: E402

#: The first report whose sample count no longer equals the sum of the
#: province paragraphs; see the module docstring.
WIDENED_FROM = 178

#: A count, allowing a thin-space or space thousands separator ("1 045").
_NUM = r"\d{1,3}(?:[   ]\d{3})+|\d+"
SAMPLES = re.compile(rf"(?<![\d,.])({_NUM})\s+nouveaux\s+[ée]chantillons", re.I)
PCT = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d{1,2})?)\s*%")
INT = re.compile(rf"(?<![\d,.])({_NUM})(?![\d]|[.,]\d|\s*%)")
#: The highlights block ends where the dashboard tiles begin.
TILES = re.compile(r"CUMUL\s+DES", re.I)


def _int(s: str) -> int:
    return int(re.sub(r"\D", "", s))


def licensed_positives(n: int, candidates: list[int], pct: float) -> int | None:
    """The unique candidate k <= n with 100 k / n within rounding (or the
    source's habit of truncating) of the printed percentage: 0.15 for a
    one-decimal percentage, 0.55 for an integer one. None when no candidate
    or more than one fits."""
    tol = 0.55 if float(pct).is_integer() else 0.15
    fits = {k for k in candidates if k <= n and abs(100.0 * k / n - pct) <= tol}
    return fits.pop() if len(fits) == 1 else None


def read_sentence(flat: str) -> tuple[dict | None, str | None]:
    """The day's (samples, positives, printed percentage) from the highlights
    text, or (None, why) when the block prints no such sentence or prints
    one that does not check."""
    m = SAMPLES.search(flat)
    if m is None:
        return None, None
    n = _int(m.group(1))
    window = flat[m.end():m.end() + 260]
    p = PCT.search(window)
    if p is None:
        return None, "no_printed_rate"
    pct = float(p.group(1).replace(",", "."))
    body = window[:p.start()]
    ks = [_int(x) for x in INT.findall(body)]
    if n == 0:
        return None, "zero_samples"
    k = licensed_positives(n, ks, pct)
    if k is None:
        return None, "no_unique_licensed_count"
    sentence = flat[m.start():m.end() + p.end()].strip()
    return {"samples": n, "positives": k, "printed_pct": pct,
            "sentence": sentence[:300]}, None


def extract(pdf: Path) -> tuple[dict | None, str | None]:
    text = pdftotext(pdf, "-layout", "-l", "2")
    flat = re.sub(r"\s+", " ", text)
    t = TILES.search(flat)
    return read_sentence(flat[:t.start()] if t else flat)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdfs", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows, status = [], []
    pdfs, extra = held_pdfs(args.pdfs)
    report_skipped(extra)
    for pdf in pdfs:
        if not FILENAME.search(pdf.stem):
            continue
        num, date = report_key(pdf)
        got, why = extract(pdf)
        if got is not None:
            vintage = "widened" if num >= WIDENED_FROM else "province_sum"
            rows.append({"sitrep": num, "date": date, **got,
                         "vintage": vintage})
        status.append({"sitrep": num, "date": date,
                       "parsed": got is not None, "refused": why or ""})

    schema = {"sitrep": pl.Int64, "date": pl.Utf8, "samples": pl.Int64,
              "positives": pl.Int64, "printed_pct": pl.Float64,
              "sentence": pl.Utf8, "vintage": pl.Utf8}
    out = pl.DataFrame(rows, schema=schema).sort("date")
    out.write_csv(args.out)
    st = pl.DataFrame(status, schema={"sitrep": pl.Int64, "date": pl.Utf8,
                                      "parsed": pl.Boolean,
                                      "refused": pl.Utf8}).sort("date")
    st.write_csv(args.out.with_name(args.out.stem + "_status.csv"))
    n_ref = st.filter(pl.col("refused") != "").height
    span = (f"; span {out['date'].min()} .. {out['date'].max()}"
            if out.height else "")
    print(f"{st.height} reports scanned; {out.height} print a front-page "
          f"laboratory total that checks against its own percentage; "
          f"{n_ref} print one that does not (see the status file){span}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
