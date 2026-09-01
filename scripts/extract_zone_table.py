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
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pdftable import read
from lib.report_date import FILENAME, report_key
from lib.archive import held_pdfs, report_skipped  # noqa: E402
from lib.pdftable import FONT_BBOX  # noqa: E402
from lib.tablespec import (ALL_SPECS, PROVINCIAL_SUMMARY, Role, SPECS,
                           TableSpec, norm, rows_are_provinces, select)

#: Register paths resolve against the REPOSITORY, not the working directory.
#: A relative path here made `load_rejected_routes` return {} when the script
#: ran from anywhere but the repo root -- no error, and sitrep 033's rejected
#: route was silently re-admitted. A register that cannot be found must stop
#: the build, and one that can must be found from any directory.
ROOT = Path(__file__).resolve().parents[1]

#: The three characters the reports use as a thousands separator: ASCII
#: space, no-break space (U+00A0) and narrow no-break space (U+202F).
#: WRITTEN AS ESCAPES ON PURPOSE. Spelled as literal characters these are
#: indistinguishable from three ordinary spaces in every editor and diff,
#: and they were silently flattened to `"   "` at some point -- which made
#: `to_int` reject every count of a thousand or more that the source prints
#: with a no-break separator, and those are most of them.
SPACES = "\u0020\u00a0\u202f"
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
    r"|^(?:zs\s+)?non\s+identifiee?s?|^inconnue?$|^nd$|^sans\s+fiche"
    # `Echantillons sans fiche` -- samples without a case-investigation form:
    # counted in the totals, but not a place. Sitrep 007 prints it among the
    # zone rows with 4 cases, and reading it as a health zone both invents a
    # zone and hands those cases to whichever province the carry reaches first.
    r"|^echantillons?\b")

VALUE_ROLES = (Role.CUM_CASES, Role.CUM_DEATHS, Role.NEW_CASES,
               Role.DEATHS_COMMUNITY, Role.DEATHS_CTE, Role.DEATHS_TOTAL,
               Role.SUSPECTED, Role.NEW_SUSPECTED, Role.SUSPECTED_DEATHS,
               Role.CONTACTS)


def to_int(s: str) -> int | None:
    """A printed count, or None when the cell carries no value.

    The thousands separator is a space, and the reports use three different
    ones -- ASCII, no-break and narrow no-break. A footnote marker can attach to
    a number as readily as to a name, and it is typography rather than value.

    THE MARKER CAN PRECEDE THE VALUE, not only follow it. Sitrep 088's
    `A ventiler` row -- the confirmed deaths that occurred in a province's
    treatment centres and are awaiting classification by health zone -- prints
    its death count as a footnote marker with the figure wrapped onto the next
    line, so the cell reads `* 59`. Stripping markers only from the end left
    `* 59`, which matches no number, and the 59 deaths were dropped: Ituri's
    cases reconciled exactly while its deaths came up 59 short. Because that
    column is cumulative the shortfall would have grown with it.

    Markers are therefore stripped from both ends. Internal spacing is left
    alone, because there the space is a thousands separator and not padding.
    """
    t = s.strip().strip(MARKERS + " ")
    if not t or t.upper() in NOT_REPORTED:
        return None
    if not NUM.match(t):
        return None
    return int(re.sub(f"[{SPACES}]", "", t))


#: A printed percentage, with its decimal part captured separately so the
#: PRECISION the source chose is recoverable. The reports print a comma for the
#: decimal point, sometimes a space before the sign, and sometimes no sign at
#: all.
PCT = re.compile(rf"^(\d+)(?:[,\.](\d+))?[{SPACES}]*%?$")


def to_pct(s: str) -> tuple[float, str] | None:
    """A printed percentage and its printed decimal digits, kept separately.

    THE DIGITS COME BACK WITH THE VALUE because the precision the source
    resolved is what licenses the comparison, and the value alone does not
    carry it: `9,1 %` and `9,10 %` are the same number printed to different
    places. `letality_precision` decides which of those places is real.
    """
    t = s.strip().strip(MARKERS + " ")
    if not t or t.upper() in NOT_REPORTED:
        return None
    m = PCT.match(t)
    if not m:
        return None
    whole, frac = m.group(1), m.group(2) or ""
    return float(f"{whole}.{frac or '0'}"), frac


def letality_precision(rows: Iterable[dict]) -> int:
    """How many decimal places this report's letality column actually resolves.

    NOT THE NUMBER OF DIGITS IT PRINTS, and the difference is the whole reason
    this function exists. Sitrep 074 prints `9,10 %`, `41,40 %`, `35,30 %` --
    two decimal digits on every one of its 54 rows, and a zero in the second
    place on every one of them. The column is rounded to ONE decimal and then
    formatted to two. Read literally, its admissible window is ±0.005
    percentage points, 29 of its 54 rows "fail", and a clean report is
    condemned as a displaced column.

    What the format ROUNDS to is a property of the column rather than of a
    cell, and the column reveals it: if any value resolves the hundredths place
    the format rounds there, and if none of them does -- 54 rows all ending in
    zero -- it does not. So this is the longest run of decimal digits any of
    the column's values leaves once trailing zeros are dropped.

    It is an upper bound on what a cell can be held to, never a floor: see
    `letality_check`, where a cell that prints fewer digits than this is held
    to its own.
    """
    best = 0
    for r in rows:
        got = to_pct(r.get("letality_printed", "") or "")
        if got is not None:
            best = max(best, len(got[1].rstrip("0")))
    return best


#: How far a printed percentage may sit from the value its own row implies and
#: still be the same number, IN UNITS OF THE LAST PLACE THE COLUMN RESOLVES
#: rather than in percentage points. Both numbers below are measurements of
#: what these pages do, taken over the 3,182 checkable rows in the corpus.
#:
#: ROUNDING (half a place, either way). Rounding to a decimal place moves a
#: number by at most half a place in EITHER direction; truncating moves it by
#: up to a whole place and only ever DOWNWARD. The observed residuals settle
#: which the source does: 3,110 of the 3,182 rows land within half a place,
#: 1,480 of them exactly on zero, and the outermost bins are as full above as
#: below -- 158 rows in [+0.4, +0.5] against 160 in [-0.5, -0.4]. A truncating
#: source leaves the upper bin empty. So the source rounds, and the window is
#: symmetric because of that measurement rather than by assumption.
#:
#: ONE WHOLE PLACE. Five rows sit between half a place and a whole one, and the
#: corpus then holds nothing at all until two places. That empty band is why
#: this second number is a boundary rather than an invented threshold. Four of
#: the five are a national or provincial `Total`, and two of those are the only
#: truncations in the corpus (sitrep 048 prints 30,9 % for 452/1460 = 30.96 %;
#: sitrep 081 prints 45,1 % for 45.20 %) -- so truncation exists, on 2 rows in
#: 3,182, and widening the window to a whole place downward to admit them would
#: double the slack on every row to excuse two, and would still not admit the
#: two that miss high. They are recorded under their own name instead.
#:
#: Past a whole place the residuals are not printing at all: 4 rows within two
#: to five places and 62 beyond five, the largest of them a whole 100
#: percentage points.
LETALITY_ROUNDING = 0.5
LETALITY_PLACE = 1.0

#: Floating-point slack, not tolerance. `100 * 2 / 7` is not exactly 28.571...
#: in binary, and a residual sitting exactly on a window edge -- which happens
#: whenever the implied value falls on a half, and it happens often -- must not
#: fall out of it because of the last bit. Six orders below the window.
EPS = 1e-6


def letality_check(r: dict, column_decimals: int) -> dict | None:
    """One row's printed case fatality against the two counts on its own line.

    The source derives this column from the two columns we actually publish, so
    it is a free per-row check on them -- and the only check in the report that
    survives when a whole column is displaced, because it is a claim about ONE
    ROW rather than about a sum over many. A national or provincial identity
    still closes when every value is one line out of place; a row-level identity
    cannot.

    A CELL IS HELD TO THE COARSER OF WHAT IT PRINTS AND WHAT ITS COLUMN
    RESOLVES. Neither alone is right. Its own digit count alone condemns sitrep
    074, whose column pads one decimal out to two on every row. Its column's
    resolution alone condemns sitreps 064 and 065, which do not format their
    column uniformly: 064 resolves the hundredths somewhere in the table and
    still prints Sud-Kivu as `33,3 %`, and holding that cell to a place it
    never printed makes 33.3 a failure against 33.3333. A cell cannot resolve
    finer than it prints, and the column cannot round finer than its own values
    show, so the admissible precision is the smaller of the two.

    Returns None when the row states nothing to check: no printed percentage, a
    missing count, or a zero denominator (a zone with no cases has no case
    fatality, and the source prints `0,0 %` or a dash for it either way).
    """
    got = to_pct(r.get("letality_printed", "") or "")
    if got is None:
        return None
    printed, frac = got
    decimals = min(len(frac), column_decimals)
    cases, deaths = r.get("cum_cases"), r.get("cum_deaths")
    if cases is None or deaths is None or cases <= 0:
        return None
    implied = 100.0 * deaths / cases
    ulp = 10.0 ** -decimals
    residual = (printed - implied) / ulp
    # A CELL MAY BE WRITTEN COARSER THAN ITS OWN COLUMN. Sitrep 064 resolves
    # the hundredths across the table (`36,83 %`, `32,51 %`) and still prints
    # Sud-Kivu's 1/3 as `33,30 %` -- one third rounded to a single decimal and
    # then padded. Held to the column's place that is a failure by 3 units;
    # read as what it is, it is the implied value written correctly at a place
    # the source was entitled to use. So a printed figure that is the implied
    # one rounded at ANY coarser place is as consistent as one rounded at its
    # own, and the residual is reported beside it either way.
    coarser = any(abs(printed - round(implied, k)) <= EPS
                  for k in range(decimals))
    if coarser or abs(residual) <= LETALITY_ROUNDING + EPS:
        verdict = "ok"
    elif abs(residual) <= LETALITY_PLACE + EPS:
        verdict = "source_rounding"
    else:
        verdict = "inconsistent"
    return {"zone_reported": r["zone_reported"], "level": r["level"],
            "cum_cases": cases, "cum_deaths": deaths,
            "letality_printed": printed, "decimals": decimals,
            "letality_implied": round(implied, 4),
            "residual_ulp": round(residual, 4),
            "verdict": verdict, "carried_from": None}


def letality_carried_forward(checks: list[dict]) -> list[dict]:
    """Re-label the rows whose printed letality is the PREVIOUS report's.

    A recurring source behaviour, not a reading defect: the report is assembled
    by editing the previous day's table, and on a row where the counts were
    updated but the derived percentage was not, the stale figure is left
    standing. Sitrep 073's Beni prints 69,8 %, which is exactly its own figure
    in the previous report (30 deaths over 43 cases) against that report's
    34/44 = 77,3 %.

    This cannot be decided inside one report, so it is a second pass over the
    whole panel: for a row that failed, does the printed percentage close
    against the same row's counts in the last report that carried it? The
    comparison uses the same window, for the same reason.

    Only the IMMEDIATELY PRECEDING appearance is tried. Reaching further back
    would eventually explain almost any percentage by coincidence, and the
    claim being made -- "yesterday's figure was left in place" -- is about one
    report, not about the report's whole history.
    """
    prev: dict[tuple[str, str], tuple[int, int]] = {}
    out = []
    for c in sorted(checks, key=lambda c: (c["sitrep"], c["level"])):
        key = (c["level"], norm(c["zone_reported"]).strip(MARKERS + " "))
        was = prev.get(key)
        if c["verdict"] == "inconsistent" and was is not None and was[0] > 0:
            implied = 100.0 * was[1] / was[0]
            ulp = 10.0 ** -c["decimals"]
            residual = (c["letality_printed"] - implied) / ulp
            if abs(residual) <= LETALITY_ROUNDING + EPS:
                c = {**c, "verdict": "carried_forward",
                     "carried_from": f"{was[1]}/{was[0]}"}
        prev[key] = (c["cum_cases"], c["cum_deaths"])
        out.append(c)
    return sorted(out, key=lambda c: (c["sitrep"], c["level"], c["zone_reported"]))


def letality_verdict(counts: dict[str, int]) -> str:
    """A whole report's verdict, from its per-row ones.

    THE BOUNDARY IS A MAJORITY, and that is a structural claim rather than a
    threshold anyone tuned. A handful of rows disagreeing is the SOURCE: a
    figure left over from yesterday, a typo, a percentage derived before a
    revision. Those are per-row defects in a column we never publish, and they
    are worth recording and nothing more. A column that disagrees with more
    than half of its own rows is a different statement -- it is not this
    table's column, and whatever put it out of place put the columns beside it
    out of place too. The same shape of test separates a value column from a
    label column (`classify`) and the provincial summary from the zone table
    (`rows_are_provinces`).

    Measured, the two cases do not come close to touching: the worst report in
    the corpus fails 47 of 56 rows and the next worst 3 of 40.
    """
    n = sum(counts.values())
    if n == 0:
        return "not_printed"
    bad = counts.get("inconsistent", 0)
    if bad == 0:
        return "ok"
    return "column_displaced" if bad * 2 > n else "rows_disagree"


#: A row's ordinal, bullet or footnote marker, which is numbering rather than
#: name. Some reports number their zone rows -- `1- Bunia`, `2- Rwampara` --
#: and others prefix them with a dash or a footnote star: sitrep 090 prints its
#: Haut-Uélé summary row as `* Haut Uélé`, and requiring a row name to begin
#: with a letter discarded it whole -- 119 cases visible only as a -119
#: residual. (The same letter requirement once discarded EVERY numbered zone
#: row: sitrep 020 kept five rows out of twenty-eight and Ituri came up 265
#: cases short.) The prefix carries no information and is dropped, not
#: captured.
ORDINAL = re.compile(r"^\s*(?:\d{1,2}\s*[-.\)]\s*|[-•·–*†‡]\s*)+")


def strip_ordinal(name: str) -> str:
    return ORDINAL.sub("", name).strip()


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


#: The register's `columns` value meaning "the whole route", as against a
#: named subset of its value columns.
WHOLE_ROUTE = "*"


@dataclass(frozen=True)
class Rejection:
    """What a register entry rejects on one document.

    A route can be wrong about a table in two different ways, and the register
    has to be able to say which. Sitrep 033's route reads the WRONG TABLE --
    nothing it produces is usable and a fallback route carries the report.
    Sitrep 080's route reads the right table, and the labels and cumulative
    columns are correct; a block of columns within it is displaced. Rejecting
    the whole report there would throw away a correct cumulative series to be
    rid of a wrong daily one.

    So an entry names either `*` -- the route, entire -- or the value columns
    that are wrong. Anything not named is read as usual, which keeps the entry
    an exact claim about the page rather than a blanket refusal.
    """

    route: str
    columns: frozenset[str]

    @property
    def whole_route(self) -> bool:
        return not self.columns


#: Column names a register entry may reject: the value roles this route reads.
#: `letality` is among them although it is never emitted -- see `main`, where
#: naming it licenses the letality check's verdict on that document.
REJECTABLE = frozenset(r.value for r in VALUE_ROLES) | {Role.LETALITY.value}


def load_rejected_routes(path: Path, pdfs: Path) -> dict[int, Rejection]:
    """Reports whose zone route is rejected by hand -- see the register itself.

    Hash-verified like every register: a revised document must return for a
    fresh judgement, not inherit one made about its predecessor.
    """
    import hashlib
    if not path.exists():
        sys.exit(f"register not found: {path} -- a register that cannot be "
                 "read cannot be applied, and applying nothing silently is "
                 "how a rejected route comes back")
    out: dict[int, Rejection] = {}
    d = pl.read_csv(path, separator="\t", comment_prefix="#",
                    infer_schema_length=None)
    if "columns" not in d.columns:
        sys.exit(f"{path} has no `columns` field. An entry must say whether it "
                 "rejects the whole route (`*`) or named value columns; "
                 "without it the scope of every judgement is a guess.")
    for e in d.iter_rows(named=True):
        hits = sorted(pdfs.glob(f"sitrep_{int(e['sitrep']):03d}_*.pdf"))
        if not hits:
            sys.exit(f"rejected-route register names sitrep {e['sitrep']}, "
                     "which is not in the archive")
        if len(hits) > 1:
            sys.exit(f"sitrep {e['sitrep']} matches {len(hits)} archive files "
                     f"({', '.join(h.name for h in hits)}); the register "
                     "cannot know which document its judgement is about")
        got = hashlib.sha256(hits[0].read_bytes()).hexdigest()[:16]
        if got != e["sha256_16"]:
            sys.exit(f"REJECTED-ROUTE ENTRY IS STALE for sitrep {e['sitrep']}: "
                     f"register says {e['sha256_16']}, file is {got}. Re-read "
                     "the new version; do not refresh the hash.")
        spec = (e["columns"] or "").strip()
        if not spec:
            sys.exit(f"rejected-route entry for sitrep {e['sitrep']} leaves "
                     "`columns` blank; write `*` for the whole route or name "
                     "the columns it reads wrongly.")
        cols = frozenset() if spec == WHOLE_ROUTE else frozenset(
            c.strip() for c in spec.split("|") if c.strip())
        # A MISSPELLED COLUMN REJECTS NOTHING, SILENTLY, which is the one
        # failure mode a register must not have: the entry would read as a
        # judgement applied while the wrong values went on being published.
        unknown = sorted(cols - REJECTABLE)
        if unknown:
            sys.exit(f"rejected-route entry for sitrep {e['sitrep']} names "
                     f"column(s) this route does not read: {', '.join(unknown)}."
                     f" Known: {', '.join(sorted(REJECTABLE))}")
        out[int(e["sitrep"])] = Rejection(route=e["route"], columns=cols)
    return out


def row_name(page, cells) -> tuple[str, str]:
    """The row's own name and its printed parent, rejoining a name that Word
    split across two label columns.

    Two filled label cells are usually a parent beside a child -- the early
    layout's merged province cell against a zone name -- and the rightmost cell
    is then the row's name. But `Sous total`, `TOTAL NATIONAL` and `Haut Uélé`
    are each ONE name that the grid sometimes splits in two, and the rightmost
    fragment alone misnames the row: sitrep 013's provincial subtotals were
    levelled `national` from the fragment `total`, sitrep 087's national total
    became a health zone named `NATIONAL`, and the provincial summary filed
    Haut-Uélé's 135 cases under a zone called `Uélé` in a province called
    `Haut`. The joined text decides: if it names a level -- a subtotal, a
    total, a province, an unassigned pool -- it is one split name with no
    parent; otherwise the cells keep their parent/child reading.
    """
    parts = page.label_cells(cells)
    if len(parts) >= 2:
        joined = strip_ordinal(" ".join(parts))
        if level_of(joined) != "zone":
            return joined, ""
    name = strip_ordinal(page.label(cells))
    parent = page.parent(cells)
    # A ROW IS NOT ITS OWN PARENT. `parent()` reads the leftmost label column
    # whether or not the name came from that same column, and where a table
    # outdents some rows into it -- sitrep 095 prints its province row and two
    # of its zones at the left margin, the rest indented -- those rows were
    # emitted with `province_printed` equal to their own name. The carry then
    # took `Adja` and `Aru` for merged province labels, found no such
    # province, and left all 55 of that report's zone rows unattributed.
    return name, ("" if parent == name else parent)


def extract(pdf: Path, specs=SPECS) -> tuple[list[dict], str]:
    tables = read(pdf)
    if not tables:
        return [], "no_tables"
    for spec in specs:
        got = select(tables, spec)
        if not got:
            continue
        # A ZONE SPEC MUST NOT WIN A DOCUMENT WHOSE ONLY TABLE IS THE SUMMARY.
        # The provincial summary's heading satisfies the zone table's
        # vocabulary (both name a province, a case count, a death count), and
        # on 62 reports only the row-count ranking keeps it out of the zone
        # series. On a report that prints NO per-zone table that defence
        # vanishes: sitreps 017 and 033 print their zone data as narrative
        # prose, the summary was the only candidate left, and it was emitted
        # as `zone_cumulative` -- rows of provinces posing as zones. What the
        # heading cannot decide, the rows can: a table whose own row names are
        # mostly provinces is the summary whatever spec claimed it.
        if (spec.name != PROVINCIAL_SUMMARY.name
                and rows_are_provinces(got.pages[0].table)):
            continue
        break
    else:
        return [], "no_matching_table"

    rows: list[dict] = []
    for page in got.pages:
        t = page.table
        recs: list[dict] = []
        for i in range(t.header_rows(), t.nrows):
            cells = t.row(i)
            name, parent = row_name(page, cells)
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
            # THE LETALITY CELL IS CARRIED AS PRINTED, not parsed into `vals`.
            # It is a check on the two columns beside it and never data, so it
            # travels beside the row far enough to be checked and no further --
            # the trunk schema below does not carry it, and no consumer can
            # mistake the source's derived percentage for an observation.
            recs.append({"name": name, "parent": parent, "vals": vals,
                         "letality_printed": page.get(cells, Role.LETALITY),
                         "empty": all(v is None for v in vals.values())})

        # A NAME CAN WRAP ONTO ITS OWN GRID ROWS. The row snap is tight enough
        # that a wrapped label becomes name-fragment / numbers / name-fragment,
        # or the label lands entirely on the row below its numbers (sitrep
        # 090's `Haut Uélé` summary row). The numbers row then has no label,
        # and dropping it silently lost `Echantillons sans fiche` -- 6 cases on
        # sitreps 009 and 013, each visible only as a -6 residual. A value row
        # with no name therefore adopts its adjacent value-less label
        # fragments, joined in print order. Donors are short (a footnote line
        # is a sentence, a wrapped name is not) and each donates once.
        def named(r: dict) -> bool:
            # A bare footnote marker in the label cell is typography, not a
            # name: sitrep 090's Haut-Uélé summary row prints `*` beside its
            # numbers with the name on the row below.
            return bool(r["name"]) and bool(re.match(r"^[A-Za-zÀ-ÿ]", r["name"]))

        for k, r in enumerate(recs):
            if named(r) or r["empty"]:
                continue
            frags = [(kk, recs[kk]["name"]) for kk in (k - 1, k + 1)
                     if 0 <= kk < len(recs) and recs[kk]["empty"]
                     and named(recs[kk]) and len(recs[kk]["name"]) <= 40
                     and not recs[kk].get("donated")]
            if frags:
                r["name"] = " ".join(n for _, n in sorted(frags))
                for kk, _ in frags:
                    recs[kk]["donated"] = True

        for r in recs:
            name = r["name"]
            if r["empty"] or not name or not re.match(r"^[A-Za-zÀ-ÿ]", name):
                continue
            rows.append({
                "zone_reported": name,
                "province_printed": r["parent"],
                "level": level_of(name),
                "table": got.spec.name,
                "page": t.page,
                "letality_printed": r["letality_printed"],
                **r["vals"],
            })
    return demote_repeats(rows), "ok" if rows else "no_rows"


def demote_repeats(rows: list[dict]) -> list[dict]:
    """A province name printed twice is a province and then one of its own zones.

    `Tshopo` is both a province and a health zone WITHIN that province, and both
    rows are printed in the same table -- on sitrep 092, `Tshopo 11 6` opening
    the block and `Tshopo 1 0` among the zones inside it. Classifying by name
    alone makes both province rows, and the aggregation then compares the zone
    sum of 10 against a printed total of 1.

    The two are told apart by POSITION, which is the only thing that
    distinguishes them: the province row opens its block and the zone row sits
    inside it, so the first occurrence is the province and any repeat below it
    is a health zone. `Kinshasa` and `Maniema` have the same property and would
    behave the same way if the outbreak reached them.

    A repeat is demoted rather than dropped, because it is a real place with a
    real count that belongs in the province's parts.

    A REPEAT WITH THE SAME COUNTS IS A DIFFERENT THING ENTIRELY, and telling the
    two apart is the whole of this function. When the table runs onto a second
    page, Word repeats the province row at the top of the continuation -- sitrep
    048 prints `ITURI 1333 380` at the head of page 4 and again at the head of
    page 5. That repeat is typography, not a place, and demoting it to a zone
    added the province's own total to its parts and doubled them.

    So: a repeated name carrying the SAME counts is a repeated header and is
    dropped, and one carrying DIFFERENT counts is the province's namesake health
    zone and is demoted. Nothing with a distinct value is ever discarded.
    """
    seen: dict[str, tuple] = {}
    out: list[dict] = []
    for r in rows:
        if r["level"] != "province":
            out.append(r)
            continue
        # A BARE `Sous total` IS NOT A NAME. The early layout labels every
        # province's closing row the same way, so all of them share one key
        # here -- and treating the second as a repeat of the first either
        # dropped it or demoted a province total to a health zone. Which
        # province each subtotal closes is the carry's question, not this
        # function's; subtotals are never namesakes and pass through.
        if SUBTOTAL.match(norm(r["zone_reported"])):
            out.append(r)
            continue
        key = norm(r["zone_reported"]).strip(MARKERS + " ")
        counts = (r.get("cum_cases"), r.get("cum_deaths"))
        if key in seen:
            if seen[key] == counts:
                continue                      # a repeated header row
            r["level"] = "zone"               # the province's own health zone
        else:
            seen[key] = counts
        out.append(r)
    return out


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
        by_name = {s.name: s for s in ALL_SPECS}
        missing = [n for n in args.spec if n not in by_name]
        if missing:
            sys.exit(f"unknown spec(s): {', '.join(missing)}; "
                     f"known: {', '.join(by_name)}")
        specs = tuple(by_name[n] for n in args.spec)

    rejected = load_rejected_routes(ROOT / "registers/rejected_routes.tsv",
                                    args.pdfs)

    # A PDF THE PATTERN CANNOT NAME IS A REPORT THE EXTRACTION CANNOT SEE.
    # An upload with no parseable date is archived as `sitrep_NNN_undated.pdf`,
    # which passes the manifest and `make verify` -- and then silently skipped
    # here, so a held report contributed nothing with no message anywhere.
    # Five reports (10, 11, 21, 38, 59) have already needed date overrides for
    # exactly this shape. The skip is now a hard failure: fix the index's date
    # override, do not lose the report.
    pdfs, extra = held_pdfs(args.pdfs)
    report_skipped(extra)
    strays = sorted(p.name for p in pdfs if not FILENAME.search(p.stem))
    if strays:
        sys.exit("archive holds PDFs the extraction cannot recognise "
                 "(no `sitrep_NNN_YYYY-MM-DD` name):\n  "
                 + "\n  ".join(strays)
                 + "\nAdd a date override in registers/sitrep_number_overrides"
                   ".tsv and re-run the fetch; these reports would otherwise "
                   "be silently absent from every series.")

    out, status, letality = [], [], []
    for pdf in pdfs:
        if not FILENAME.search(pdf.stem):
            continue
        # THE DATA DATE COMES FROM THE PAGE, not the filename: some uploads are
        # named with the publication date, which dates those reports a day early.
        num, date = report_key(pdf)
        rows, st = extract(pdf, specs)
        rej = rejected.get(num)
        if rows and rej is not None and rej.route == rows[0]["table"]:
            if rej.whole_route:
                rows, st = [], "route_rejected_by_register"
            else:
                # THE ROWS STAY; THE REJECTED COLUMNS BECOME NULL. Null is
                # already this panel's word for "this table does not report
                # that quantity", so a rejected column is indistinguishable
                # downstream from a column the vintage never printed -- and
                # every consumer already handles that. Dropping the rows
                # instead would take the report's correct cumulative series
                # down with its wrong daily one.
                #
                # `letality_printed` is deliberately NOT nulled: it is not
                # emitted anywhere, and the check below must still run and
                # still report, or the register would be silencing the
                # evidence for its own entry.
                for r in rows:
                    for c in rej.columns:
                        if c in r:
                            r[c] = None
                st = "columns_rejected_by_register"

        # THE LETALITY COLUMN IS A CHECK, NEVER DATA -- the source derives it
        # from the two columns we publish, so every row that prints one states
        # its own consistency for free.
        decimals = letality_precision(rows)
        checks = [c for c in (letality_check(r, decimals) for r in rows) if c]
        for c in checks:
            c["sitrep"], c["date"] = num, date
        letality.extend(checks)
        # The cell leaves the row here. The trunk carries no percentage a
        # consumer could mistake for an observation.
        for r in rows:
            r.pop("letality_printed", None)

        # THE IDENTITY RUNS ON THE COLUMN THE TABLE ACTUALLY PRINTS. The daily
        # table (sitrep 087) has no cumulative column, but its parts must still
        # sum to its printed totals -- in the day's new cases.
        col = ("new_cases" if rows and all(r.get("cum_cases") is None
                                           for r in rows) else "cum_cases")
        chk = reconcile(rows, column=col) if rows else {}
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

    # THE CARRIED-FORWARD PASS NEEDS THE WHOLE PANEL, so it runs once here
    # rather than per report: whether a printed percentage is yesterday's is a
    # question no single document can answer.
    letality = letality_carried_forward(letality)
    by_report: dict[int, dict[str, int]] = {}
    for c in letality:
        counts = by_report.setdefault(c["sitrep"], {})
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    gated: list[str] = []
    for s in status:
        got = by_report.get(s["sitrep"], {})
        n_ok = got.get("ok", 0)
        n_round = got.get("source_rounding", 0)
        n_carried = got.get("carried_forward", 0)
        n_bad = got.get("inconsistent", 0)
        verdict = letality_verdict(got)
        # AN ENTRY IS SCOPED TO ITS ROUTE, and this script runs once per route.
        # Sitrep 080's entry is about the zone table; its provincial summary is
        # a different table on the same page and answers for itself. Without
        # the route test the summary run reads the entry, finds nothing wrong,
        # and stops the build for a stranded licence that was never its own.
        rej = rejected.get(s["sitrep"])
        if rej is not None and rej.route != s["table"]:
            rej = None
        registered = rej is not None and Role.LETALITY.value in rej.columns
        # A REGISTERED DISPLACEMENT IS RECORDED, NOT SILENCED. The entry is a
        # human's reading of the page, hash-pinned to the document; the check
        # still runs, the counts still appear here, and only the BUILD GATE is
        # released. A licence that stops being needed is an error for the same
        # reason a stranded reconciliation exception is: it describes a state
        # that no longer exists.
        if registered:
            if verdict != "column_displaced":
                sys.exit(
                    f"REJECTED-ROUTE ENTRY IS STRANDED for sitrep {s['sitrep']}"
                    f": it rejects the `letality` column, but the letality "
                    f"check on that document now comes back `{verdict}` "
                    f"({n_ok} ok, {n_round} source rounding, {n_carried} "
                    f"carried forward, {n_bad} inconsistent). Re-read the page "
                    f"and delete or rewrite the entry; do not leave a licence "
                    f"nothing needs.")
            verdict = "displacement_registered"
        elif verdict == "column_displaced":
            gated.append(
                f"  sitrep {s['sitrep']:>3} ({s['date']}): {n_bad} of "
                f"{sum(got.values())} rows that print a case fatality disagree "
                f"with their own cases and deaths")
        s.update({"letality_checked": sum(got.values()), "letality_ok": n_ok,
                  "letality_source_rounding": n_round,
                  "letality_carried_forward": n_carried,
                  "letality_inconsistent": n_bad, "letality": verdict})

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
    # THE PER-ROW DETAIL IS WRITTEN WHATEVER THE VERDICT, and written BEFORE
    # the gate fires: the file is the evidence someone needs in order to read
    # the page and decide, and a gate that destroys its own evidence sends the
    # reader back to the PDF with nothing.
    pl.DataFrame(letality, schema={
        "sitrep": pl.Int64, "date": pl.Utf8, "zone_reported": pl.Utf8,
        "level": pl.Utf8, "cum_cases": pl.Int64, "cum_deaths": pl.Int64,
        "letality_printed": pl.Float64, "decimals": pl.Int64,
        "letality_implied": pl.Float64, "residual_ulp": pl.Float64,
        "verdict": pl.Utf8, "carried_from": pl.Utf8,
    }).write_csv(args.out.with_name(args.out.stem + "_letality.csv"))

    s = pl.DataFrame(status)
    print(f"\n{s.height} reports; {s.filter(pl.col('identity') == 'ok').height} "
          f"satisfy the page's own arithmetic")
    # Reported once rather than a line per font per page. See
    # lib.pdftable._FontBBoxCounter for why it is safe to suppress and why it
    # is still counted.
    if FONT_BBOX.n:
        print(f"  {FONT_BBOX.n} embedded font(s) carry no usable FontBBox; "
              "pdfminer's per-font warning is suppressed. Nothing here reads a "
              "glyph box, and every table is checked against the page's own "
              "arithmetic.")
    print(s.group_by("status").len().sort("len", descending=True))
    tally: dict[str, int] = {}
    for c in letality:
        tally[c["verdict"]] = tally.get(c["verdict"], 0) + 1
    print(f"\nletality check, over {len(letality)} printed case fatalities in "
          f"{len({c['sitrep'] for c in letality})} reports:")
    print(f"  {tally.get('ok', 0):>5}  close against their own row")
    print(f"  {tally.get('source_rounding', 0):>5}  within one printed place "
          f"-- the source's own rounding")
    print(f"  {tally.get('carried_forward', 0):>5}  are the previous report's "
          f"figure, left standing")
    print(f"  {tally.get('inconsistent', 0):>5}  disagree")
    with pl.Config(tbl_rows=40):
        print(s.filter(pl.col("letality").is_in(["ok", "not_printed"]).not_())
              .select("sitrep", "date", "letality_checked", "letality_ok",
                      "letality_source_rounding", "letality_carried_forward",
                      "letality_inconsistent", "letality"))

    # THE GATE. An isolated disagreement is the SOURCE's -- a stale figure, a
    # typo -- and is recorded above rather than stopping a build over a number
    # we do not publish. A column that disagrees with most of its own rows is
    # something else: it is not this table's column, and every value read
    # beside it is suspect. That is a defect in the reading, it has to be read
    # off the page by a person, and the judgement belongs in
    # registers/rejected_routes.tsv -- so the build stops until one is there.
    if gated:
        print("\nA PRINTED CASE-FATALITY COLUMN DOES NOT DESCRIBE ITS OWN "
              "ROWS:\n" + "\n".join(gated)
              + "\n\nThe source derives that column from the cases and deaths "
                "printed beside it, so a majority disagreement means the "
                "column is displaced -- and whatever displaced it displaced "
                "the columns read next to it too. Read the page, decide which "
                "columns the route reads wrongly, and record the judgement in "
                "registers/rejected_routes.tsv. Per-row evidence: "
              + str(args.out.with_name(args.out.stem + "_letality.csv")),
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
