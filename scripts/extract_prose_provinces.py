"""Province-level cumulative cases from the reports that print them only in prose.

Three reports -- sitreps 012, 014 and 016 -- print no per-zone table and no
readable provincial summary. Their case data lives in one narrative sentence:

    "Cumul de cas confirmés 26 mai 2026 : 121 cas dont 110 en Ituri, 10 au
     Nord-Kivu et 1 au Sud-Kivu"

This route reads exactly that sentence shape and nothing else. It is
deliberately narrow, because prose is where an extraction can go quietly wrong
in ways no grid can: the guard here is that THE SENTENCE CHECKS ITSELF. It
states a total and its parts, and a row is emitted only when the parts sum to
the printed total. A sentence that does not close is reported and skipped, not
repaired -- the failure mode is a missing report, never a wrong number.

A report whose sentence states only the national figure (sitrep 014 prints
"210 cas pour les trois provinces affectées" with no breakdown) yields the
national row alone, flagged `breakdown=none`. That is what the page says, and
no more.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.report_date import FILENAME, report_key

#: The cumulative sentence: a total, then optionally `dont` and per-province
#: parts. Written against the three sentences it must read, not against prose
#: in general.
TOTAL = re.compile(
    r"[Cc]umul\s+des?\s+cas\s+confirm\w+[^.;:]{0,60}[:\s]"
    r"[^.;0-9]{0,20}(\d[\d\s  ]{0,6})\s*cas")
PART = re.compile(r"(\d[\d\s  ]{0,6})\s+(?:en|au|a)\s+"
                  r"(Ituri|Nord[-\s]?Kivu|Sud[-\s]?Kivu|Haut[-\s]?U[ée]l[ée]|Tshopo)")

CANON = {"ituri": "Ituri", "nord kivu": "Nord-Kivu", "nord-kivu": "Nord-Kivu",
         "sud kivu": "Sud-Kivu", "sud-kivu": "Sud-Kivu",
         "haut uele": "Haut-Uélé", "haut-uele": "Haut-Uélé", "tshopo": "Tshopo"}


def _canon(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return CANON[re.sub(r"[-\s]+", " ", s.lower()).strip()]


def _int(s: str) -> int:
    return int(re.sub(r"[\s  ]", "", s))


def extract(pdf: Path) -> tuple[list[dict], str]:
    text = subprocess.run(["pdftotext", "-q", "-layout", str(pdf), "-"],
                          capture_output=True, text=True).stdout
    flat = re.sub(r"\s+", " ", text)
    m = TOTAL.search(flat)
    if not m:
        return [], "no_cumulative_sentence"
    total = _int(m.group(1))

    # The parts, taken from the clause that follows the total -- not from the
    # whole document, where other numbers precede province names for other
    # reasons (alert counts, contact counts, vaccination figures).
    clause = flat[m.end():m.end() + 220]
    clause = clause.split(".")[0].split(";")[0]
    parts = [( _canon(name), _int(num)) for num, name in PART.findall(clause)]

    rows = [{"province": "national", "level": "national", "cum_cases": total,
             "breakdown": "closes" if parts else "none"}]
    if not parts:
        return rows, "national_only"

    # THE SENTENCE CHECKS ITSELF, and the check is the licence to use it. A
    # breakdown that does not sum to its own stated total is reported and
    # refused whole -- prose offers no second identity to arbitrate with.
    if sum(v for _, v in parts) != total:
        return [], (f"breakdown_does_not_close: parts "
                    f"{[v for _, v in parts]} vs total {total}")
    rows += [{"province": p, "level": "province", "cum_cases": v,
              "breakdown": "closes"} for p, v in parts]
    return rows, "ok"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdfs", required=True, type=Path)
    ap.add_argument("--only", type=int, nargs="*", default=None,
                    help="restrict to these report numbers; the route is meant "
                         "for the reports no table covers, not as a rival "
                         "extraction for the ones tables cover better")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    out, status = [], []
    for pdf in sorted(args.pdfs.glob("*.pdf")):
        if not FILENAME.search(pdf.stem):
            continue
        num, date = report_key(pdf)
        if args.only is not None and num not in args.only:
            continue
        rows, st = extract(pdf)
        status.append({"sitrep": num, "date": date, "status": st,
                       "rows": len(rows)})
        for r in rows:
            out.append({"sitrep": num, "date": date, **r})
        print(f"  sitrep {num:03d}  {st}")

    pl.DataFrame(out).write_csv(args.out)
    pl.DataFrame(status).write_csv(
        args.out.with_name(args.out.stem + "_status.csv"))


if __name__ == "__main__":
    main()
