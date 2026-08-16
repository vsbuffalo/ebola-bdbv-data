"""Per-zone cases and deaths, read from the table geometry the reports draw.

The situation reports print a table of cumulative confirmed cases and deaths per
health zone, nested three levels deep: a national total, a row per province, and
the province's health zones beneath it. From 13 July it gains a daily block
splitting each day's confirmed deaths by how the case was ascertained -- in the
community by post-mortem swab, or inside a treatment centre.

WHY THE OUTER TWO LEVELS ARE KEPT
The province and national rows are not redundant with the zone rows: they are
the check. Each province prints its own total and the table ends with a national
one, so the zone rows plus the rows the source has not yet assigned to a zone
must equal the printed figure at both levels. Discarding the aggregates would
leave no way to tell "this report listed few zones" from "the reader missed
rows", which is the difference between a short table and a silent data loss.

HOW THE TABLE IS FOUND
Not by its title. Table numbers are not stable across reports -- the same table
is Table 2, 4 or 5 depending on the vintage -- so the table is identified by the
roles its own column headings declare (`lib/tablespec.py`), and its columns are
mapped in the same step. A table that is not this one fails to resolve rather
than resolving into the wrong columns.

HOW THE CELLS ARE READ
From the rules the document draws, not from a text rendering of the page
(`lib/pdftable.py`). Every cell's row and column are given by the page rather
than inferred from character offsets, so a health zone whose name is too wide
for its column stays one row, and a blank cell stays blank instead of shifting
its neighbours left.

WHAT IS NOT DONE HERE
Alias resolution, the province carry across rows, and the exception registers
are downstream: they are claims about the outbreak and its sources, not about
the page, and they belong to steps that can be audited on their own.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pdftable import read
from lib.report_date import FILENAME, report_key
from lib.tablespec import Role, SPECS, TableSpec, norm, select

SPACES = "   "
NUM = re.compile(rf"^-?[\d{SPACES}]*\d$")
MARKERS = "*†‡"

#: Marks meaning "not reported", which is not the same as zero and must not
#: become one. A blank daily cell means no event; an em-dash means the report
#: did not say.
NOT_REPORTED = {"—", "–", "-", "ND", "N/D", "NA", "N/A", "*"}

PROVINCES = {norm(p) for p in (
    "Ituri", "Nord-Kivu", "Nord Kivu", "Sud-Kivu", "Sud Kivu", "Haut-Uele",
    "Haut-Uélé", "Haut Uele", "Haut Uélé", "Tshopo", "Kinshasa", "Maniema",
    "Bas-Uele", "Bas-Uélé", "Bas Uele", "Bas Uélé")}

TOTAL = re.compile(r"^total")
#: `Sous total Ituri` -- a province's own total, printed as a labelled subtotal
#: row rather than as a province-named row. It is a PROVINCE-level row and
#: counting it as a zone double-counts that province: the residual came out at
#: exactly twice the printed total on seven reports, which is the signature of
#: summing a level and its own subtotals together.
SUBTOTAL = re.compile(r"^sous[-\s]?total")
#: Rows the source counts but has not assigned to a health zone. A real row of
#: the table, inside the province and national totals, but not a place -- kept
#: under its own level so it never enters a per-zone aggregation and never
#: silently disappears from a provincial one.
UNASSIGNED = re.compile(
    r"^autres?\s+(zs|zones?)|^donnees?\s+non\s+ventilees?|^a\s*ventiler"
    r"|^non\s+identifiee?s?|^inconnue?$|^nd$")

VALUE_ROLES = (Role.CUM_CASES, Role.CUM_DEATHS, Role.NEW_CASES,
               Role.DEATHS_COMMUNITY, Role.DEATHS_CTE, Role.DEATHS_TOTAL,
               Role.SUSPECTED, Role.SUSPECTED_DEATHS, Role.CONTACTS)


def to_int(s: str) -> int | None:
    """A printed count, or None when the cell carries no value.

    The thousands separator is a space, and the reports use three different
    ones -- ASCII, no-break and narrow no-break. A footnote marker can attach to
    a number as readily as to a name, and it is typography rather than value.
    """
    t = s.strip().rstrip(MARKERS).strip()
    if not t or t.upper() in NOT_REPORTED:
        return None
    if not NUM.match(t):
        return None
    return int(re.sub(f"[{SPACES}]", "", t))


def level_of(name: str) -> str:
    key = norm(name).strip(MARKERS + " ")
    if SUBTOTAL.match(key):
        return "province"
    if TOTAL.match(key):
        return "national"
    if UNASSIGNED.match(key):
        return "unassigned"
    if key in PROVINCES:
        return "province"
    return "zone"


def extract(pdf: Path, specs=SPECS) -> tuple[list[dict], str]:
    tables = read(pdf)
    if not tables:
        return [], "no_tables"
    for spec in specs:
        got = select(tables, spec)
        if got:
            break
    else:
        return [], "no_matching_table"

    rows: list[dict] = []
    for page in got.pages:
        t = page.table
        for i in range(t.header_rows(), t.nrows):
            cells = t.row(i)
            name = page.label(cells)
            if not name or not re.match(r"^[A-Za-zÀ-ÿ]", name):
                continue
            # EVERY VALUE COLUMN IS EMITTED, present in this table or not, and
            # the distinction is carried by null. Emitting only the roles this
            # spec resolved makes the row schema depend on which table matched,
            # and a frame built from such rows takes its columns from whichever
            # report sorts first -- the early layout has no cumulative-death
            # column, so `cum_deaths` vanished from the output for all 82
            # reports. A column absent from a table is not data that is missing;
            # it is a quantity that table does not report, and null says so.
            vals = {r.value: (to_int(page.get(cells, r)) if r in page.roles else None)
                    for r in VALUE_ROLES}
            if all(v is None for v in vals.values()):
                continue
            rows.append({
                "zone_reported": name,
                "province_printed": page.parent(cells),
                "level": level_of(name),
                "table": got.spec.name,
                "page": t.page,
                **vals,
            })
    return rows, "ok" if rows else "no_rows"


def reconcile(rows: list[dict], column: str = "cum_cases") -> dict:
    """Does the page's own arithmetic close?

    Two identities, at two levels. Nationally, the province rows plus any
    unassigned rows equal the printed `Total`. Per province, that province's
    zone rows plus its unassigned rows equal the province's own printed row.
    Both are claims the page makes about itself, so a failure is a statement
    about the report or about our reading of it -- never something to repair by
    adjusting a value.
    """
    tot = [r for r in rows if r["level"] == "national"]
    prov = [r for r in rows if r["level"] == "province"]
    if not tot:
        return {"identity": "not_checkable", "residual": None,
                "printed_total": None, "parts_sum": None}
    printed = tot[-1].get(column)
    if printed is None:
        return {"identity": "not_checkable", "residual": None,
                "printed_total": None, "parts_sum": None}

    # THE PARTS ARE THE COARSEST LEVEL PRINTED BENEATH THE TOTAL, and which
    # that is depends on the table, not on the report date. The later layout
    # prints a total row per province, so the provinces are the parts and the
    # zones sit one level below them. The early layout prints the province only
    # as a merged LABEL beside its zones, with no provincial total anywhere, so
    # there the zones themselves are the parts.
    #
    # Choosing by what the table prints rather than by vintage matters because
    # summing zones against a total that provinces already account for would
    # double-count every case, and summing provinces that do not exist would
    # report a residual equal to the whole outbreak. Either would look like a
    # reading failure and neither would be one.
    if not prov:
        parts_rows = [r for r in rows if r["level"] in ("zone", "unassigned")]
        basis = "zones"
        if not parts_rows:
            return {"identity": "not_checkable", "residual": None,
                    "printed_total": None, "parts_sum": None}
        parts = sum((r.get(column) or 0) for r in parts_rows)
        return {"identity": "ok" if parts == printed else "fails",
                "residual": parts - printed, "printed_total": printed,
                "parts_sum": parts, "basis": basis}
    # THE NATIONAL IDENTITY IS OVER PROVINCES ALONE. An unassigned row --
    # `Autres zones non encore identifiées`, `A ventiler` -- is a row WITHIN a
    # province, and its cases are already inside that province's printed total.
    # Adding it here counts those cases twice, which showed up as a residual of
    # exactly +17 on fifteen consecutive reports: the size of Ituri's
    # unallocated row over that stretch, not a reading error anywhere.
    #
    # The province-level identity is the one that consumes the unassigned rows
    # (zones + unassigned == the province's printed row), and it needs each row
    # to know its province -- a carry this step deliberately does not do, since
    # the province is printed once against a merged cell and reconstructing it
    # is a separate, auditable claim.
    parts = sum((r.get(column) or 0) for r in prov)
    return {"identity": "ok" if parts == printed else "fails",
            "residual": parts - printed, "printed_total": printed,
            "parts_sum": parts, "basis": "provinces"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdfs", required=True, type=Path,
                    help="directory of situation report PDFs")
    ap.add_argument("--out", required=True, type=Path,
                    help="trunk CSV; a _status.csv sibling is written beside it")
    ap.add_argument("--spec", action="append", default=None,
                    help="restrict to named table specs, in order of preference")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    specs: tuple[TableSpec, ...] = SPECS
    if args.spec:
        by_name = {s.name: s for s in SPECS}
        missing = [n for n in args.spec if n not in by_name]
        if missing:
            sys.exit(f"unknown spec(s): {', '.join(missing)}; "
                     f"known: {', '.join(by_name)}")
        specs = tuple(by_name[n] for n in args.spec)

    out, status = [], []
    for pdf in sorted(args.pdfs.glob("*.pdf")):
        if not FILENAME.search(pdf.stem):
            continue
        # THE DATA DATE COMES FROM THE PAGE, not the filename: some uploads are
        # named with the publication date, which dates those reports a day early.
        num, date = report_key(pdf)
        rows, st = extract(pdf, specs)
        chk = reconcile(rows) if rows else {}
        status.append({"sitrep": num, "date": date, "status": st,
                       "rows": len(rows),
                       "table": rows[0]["table"] if rows else None,
                       **{k: chk.get(k) for k in
                          ("identity", "residual", "printed_total",
                           "parts_sum", "basis")}})
        for r in rows:
            out.append({"sitrep": num, "date": date, **r})
        if not args.quiet:
            print(f"  {pdf.stem}  {st:<18} {len(rows):3d} rows  "
                  f"{chk.get('identity', '-'):<14} residual={chk.get('residual')}",
                  flush=True)

    # DECLARED, NOT INFERRED. polars infers a column's type from the first rows
    # it sees, and the earliest reports use a layout with no cumulative-death
    # column, so every value there is null and the first integer that arrives
    # later fails to append. Stating the schema also fixes the column ORDER,
    # which otherwise depends on which report sorted first.
    schema = {
        "sitrep": pl.Int64, "date": pl.Utf8, "zone_reported": pl.Utf8,
        "province_printed": pl.Utf8, "level": pl.Utf8, "table": pl.Utf8,
        "page": pl.Int64,
        **{r.value: pl.Int64 for r in VALUE_ROLES},
    }
    pl.DataFrame(out, schema=schema).write_csv(args.out)
    pl.DataFrame(status).write_csv(args.out.with_name(args.out.stem + "_status.csv"))

    s = pl.DataFrame(status)
    print(f"\n{s.height} reports; {s.filter(pl.col('identity') == 'ok').height} "
          f"satisfy the page's own arithmetic")
    print(s.group_by("status").len().sort("len", descending=True))


if __name__ == "__main__":
    main()
