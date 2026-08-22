"""The front-page dashboard banner: patients in isolation, and cumulative recoveries.

SOURCE       The INSP situation reports' page-1 banner. PRIMARY -- read from
             the tiles the page draws, not from anyone's transcription.
PRODUCES     One row per report: `patients_isolated` (everyone in isolation
             or a treatment centre AT THAT MOMENT -- confirmed AND suspected),
             `patients_isolated_confirmed` (of those, the confirmed ones), and
             `cumul_recovered` (recoveries to date, national).

             THE TWO ISOLATION SERIES ARE NOT INTERCHANGEABLE, and only the
             second observes a compartment of confirmed cases. Sitrep 070
             prints the banner tile as 766 and its own occupancy table breaks
             that figure into 278 confirmed and 488 suspects -- the narrative
             says so in words. The suspect share is large and moves with
             testing and triage rather than with transmission (36% confirmed
             on sitrep 070, 43% in Ituri on 093), so fitting the tile to an
             isolated-case compartment would score a mostly-suspect census
             against a confirmed-case state.
FITTED       Intended for the model class that observes the isolated
             compartment and the recovered compartment directly.
VALIDATED BY the epiforecasts scan, which read the same banner independently
             (`data/raw/scan/insp_sitrep_scanned.csv`, columns
             `patients_isolated` and `cumul_recovered`) -- reported by
             `compare_extractions.py`, never consumed here.

WHY EXTRACT WHAT THE SCAN ALREADY HAS. Because a third party's reading is a
check and never a trunk: adopting it would leave us unable to audit our own
series against the page, and would end these streams eight reports early
(the scan stops at 085; the archive runs to 093). Reading the banner
ourselves makes the scan an independent validation whose disagreements are
findings.

BOTH QUANTITIES ARE STOCKS, NOT FLOWS. `patients_isolated` is a prevalence --
how many people are in care right now -- and `cumul_recovered` is a running
total. Neither accumulates over an interval, so neither is differenced and
neither carries the `days_covered` span the incidence streams do; each row is
a reading at an instant.

HOW A TILE IS READ. The banner is a dashboard laid out in COLUMNS: a tile's
label sits above its value, at the same horizontal position, with other
tiles' labels and values to the left and right on the same lines. So the
value is found by column alignment -- take the label's starting column, then
the first number that begins within a few columns of it on a following line.

READING ACROSS INSTEAD OF DOWN IS THE FAILURE THIS AVOIDS. A first version
searched the whitespace-collapsed page text for the first number after the
label and produced `725390` for sitrep 062: the isolation tile's 725 and the
recovery tile's 390, adjacent on one line, glued into a single plausible
five-digit number. Two of twenty-two values agreed with the scan. Reading by
column instead, they agree everywhere the scan has a value.

The modern vintage draws each tile as one cell holding label and value
together ("PATIENTS EN ISOLEMENT / CTE 730"), which the same rule reads as a
same-line match. A tile whose label appears with no number beneath it
refuses; nothing reaches further down the page for something plausible.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pdftable import read as read_tables
from lib.report_date import FILENAME, report_key
from extract_zone_table import to_int

#: The two tiles, by every spelling the series prints. `GUÉRIS` must not match
#: the daily-recoveries phrasings ("nouveaux guéris", "guéris du jour"), which
#: are a FLOW and belong to a different quantity.
TILES = {
    # The tile is found by its distinctive WORD, because the labels wrap:
    # "Patients en / isolement - / hospitalisation" spans three lines, and
    # "Nombre cumulé / des guéris" two, so no whole-phrase pattern matches
    # every vintage.
    "patients_isolated": re.compile(r"isolement", re.I),
    "cumul_recovered": re.compile(
        r"cumul\s+des\s+gu[ée]ris|gu[ée]ris\s*[—–-]\s*cumul"
        r"|^(?:des\s+)?gu[ée]ris$|^cumul[ée]?\s+des\s+gu[ée]ris", re.I),
}
#: The care-occupancy table, a second and older route to the same census:
#: one row per province ending in a national total. It carries the
#: confirmed/suspect split the banner tile does not.
OCCUPANCY = {
    "patients_isolated": re.compile(
        r"patients?\s+en\s+isolement\s*\(?\s*fin\s*J", re.I),
    "patients_isolated_confirmed": re.compile(r"dont\s+confirm[ée]s", re.I),
}
#: Every number on a line of the occupancy table.
ROW_NUMS = re.compile(r"(?<![\d,.%])(\d{1,3}(?:[\u00a0\u202f ]\d{3})*)(?![\d%])")


def _national(nums: list[int]) -> int | None:
    """The national figure from one occupancy row: the printed total where the
    table has a total column, otherwise the provinces summed.

    THE ROW'S OWN ARITHMETIC DECIDES WHICH IT IS, because the table gained a
    sixth province and lost its total column without announcing either. Taking
    the last number unconditionally read sitrep 080's Bas-Uele column, 20, as
    the national census of 707."""
    if not nums:
        return None
    if len(nums) >= 2 and nums[-1] == sum(nums[:-1]):
        return nums[-1]
    return sum(nums)
#: A LABEL IS A SHORT FIELD. Both keywords also occur in the front page's
#: prose ("...ont été déclarés guéris après avoir obtenu des tests..."), and
#: the discriminator that holds across every vintage is length: a dashboard
#: tile's label is a few words in its own column, prose is a paragraph in
#: one field. Measured across the archive, tile labels run to 31 characters.
LABEL_MAX = 34

#: A field that is nothing but a count. The internal space is a thousands
#: separator, and it is only allowed before exactly three digits -- which is
#: what stops two adjacent tiles' values from reading as one number.
NUM = re.compile(r"^\*?\s*(\d{1,3}(?:[\u00a0\u202f ]\d{3})*)\s*\*?$")
#: How far a value's column may drift from its label's before it belongs to
#: somebody else's tile, and how many lines below the label to look.
COL_TOL, LOOK_AHEAD = 8, 6


def _fields(line: str) -> list[tuple[int, str]]:
    """(starting column, text) for each run of text separated by 2+ spaces --
    the layout's own column structure, which collapsing whitespace destroys."""
    return [(m.start(), m.group(0).strip())
            for m in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", line)]


def extract(pdf: Path) -> tuple[dict, list[str]]:
    """The banner's two values, and the tiles that refused."""
    # The banner tiles are page 1; the occupancy table sits deeper in the
    # report (page 6 to 9 depending on vintage), so the two routes read
    # different extents of the same document.
    def _text(*extent: str) -> str:
        return subprocess.run(["pdftotext", "-q", "-layout", *extent,
                               str(pdf), "-"],
                              capture_output=True, text=True).stdout
    lines = _text("-f", "1", "-l", "1").splitlines()
    all_lines = _text().splitlines()
    out: dict[str, int] = {}
    why: list[str] = []

    # ROUTE 2 FIRST, because it is the one that separates confirmed from
    # suspected. The table prints a row per province ending in the national
    # total, and where it prints all three rows the page checks itself:
    # confirmed + suspects must equal the total.
    occ: dict[str, int] = {}
    for name, pat in OCCUPANCY.items():
        for line in all_lines:
            if not pat.search(line):
                continue
            nums = [n for n in (to_int(x) for x in ROW_NUMS.findall(line))
                    if n is not None]
            got = _national(nums)
            if got is not None:
                occ[name] = got
                break
    susp = None
    for line in all_lines:
        if re.search(r"dont\s+suspects?", line, re.I):
            nums = [n for n in (to_int(x) for x in ROW_NUMS.findall(line))
                    if n is not None]
            susp = _national(nums)
            break
    if (susp is not None and "patients_isolated" in occ
            and "patients_isolated_confirmed" in occ
            and occ["patients_isolated_confirmed"] + susp != occ["patients_isolated"]):
        why.append(f"occupancy table does not close: "
                   f"{occ['patients_isolated_confirmed']} confirmed + {susp} "
                   f"suspect != {occ['patients_isolated']} total")
        occ = {}
    out.update(occ)

    for name, pat in TILES.items():
        if name in out:
            continue
        hit = None
        for li, line in enumerate(lines):
            for col, txt in _fields(line):
                if len(txt) <= LABEL_MAX and pat.search(txt):
                    hit = (li, col, txt)
                    break
            if hit:
                break
        if hit is None:
            why.append(f"{name}: tile absent")
            continue
        li, col, txt = hit

        # Same field first: the modern vintage prints "PATIENTS EN ISOLEMENT
        # / CTE 730" as one cell, so the value trails its own label.
        m = pat.search(txt)
        same = re.match(r"[^\d]{0,12}?(\d{1,3}(?:[\u00a0\u202f ]\d{3})*)\s*\*?$",
                        txt[m.end():])
        if same:
            out[name] = to_int(same.group(1))
            continue

        # Otherwise look down the tile's own column.
        val = None
        for ln in lines[li + 1: li + 1 + LOOK_AHEAD]:
            for c, txt in _fields(ln):
                got = NUM.match(txt)
                if abs(c - col) <= COL_TOL and got:
                    val = to_int(got.group(1))
                    break
            if val is not None:
                break
        if val is None:
            why.append(f"{name}: label with no aligned number beneath it")
        else:
            out[name] = val
    return out, why


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdfs", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows, status = [], []
    for pdf in sorted(args.pdfs.glob("*.pdf")):
        if not FILENAME.search(pdf.stem):
            continue
        num, date = report_key(pdf)
        got, why = extract(pdf)
        rows.append({"sitrep": num, "date": date,
                     "patients_isolated": got.get("patients_isolated"),
                     "patients_isolated_confirmed":
                         got.get("patients_isolated_confirmed"),
                     "cumul_recovered": got.get("cumul_recovered")})
        status.append({"sitrep": num, "date": date, "n_read": len(got),
                       "refused": "; ".join(why)})
        if not args.quiet and why:
            print(f"  {pdf.stem}  read {len(got)}/2  ({'; '.join(why)})")

    schema = {"sitrep": pl.Int64, "date": pl.Utf8,
              "patients_isolated": pl.Int64,
              "patients_isolated_confirmed": pl.Int64,
              "cumul_recovered": pl.Int64}
    d = pl.DataFrame(rows, schema=schema).sort("sitrep")
    d.write_csv(args.out)
    pl.DataFrame(status).write_csv(
        args.out.with_name(args.out.stem + "_status.csv"))

    print(f"\n{d.height} reports scanned; "
          f"patients_isolated on {d['patients_isolated'].is_not_null().sum()}, "
          f"of which confirmed split on "
          f"{d['patients_isolated_confirmed'].is_not_null().sum()}, "
          f"cumul_recovered on {d['cumul_recovered'].is_not_null().sum()} "
          "(a figure the page does not print is null, never inferred)")


if __name__ == "__main__":
    main()
