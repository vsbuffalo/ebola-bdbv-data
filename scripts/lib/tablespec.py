"""Which table is this, and what does each of its columns mean.

TWO JOBS, AND THEY NEED DIFFERENT EVIDENCE. This is the central design point,
and getting it wrong is what broke the two previous attempts.

  IDENTIFYING the table -- deciding that this grid is the per-zone cumulative
  table and not the provincial summary beside it -- is a question about
  VOCABULARY. The headings say what the table is, and they say it robustly:
  every vintage of this table names a health zone, a case count, a death count
  and a letality somewhere in its heading block.

  INDEXING its columns -- deciding that cumulative cases are in column 1 -- is a
  question about GEOMETRY, and the headings cannot answer it. Word merges and
  centres heading cells, so a heading's text lands wherever its own cell centres,
  which is not above the data column it labels. On sitrep 080 the heading block
  reads

      col0 `Province / Zone de santé`   col2 `Cas (n)`   col5 `Décès`  col6 `(n)`

  while the data row beneath it is `Ituri | 3 317 | 1 382 | ...` with the cases
  in column 1 and the deaths in column 2. Trusting the heading's column index
  read every zone's death count as its case count.

So the heading is used to identify, and never to index. Columns are indexed from
the DATA: a column that mostly holds numbers is a value column, the value
columns are taken left to right, and each spec declares the order its values are
printed in. Column order within a layout is stable even though the column COUNT
is not -- the daily ascertainment block appears from 13 July and simply extends
the sequence -- so an order declaration survives the vintages that an index
cannot.

This also handles, without special cases, the two things that broke positional
reading before: sitrep 090's Table 2 carries a leading spacer column, and the
early layout carries two label columns (`Provinces` and `Zones de santé`).
Neither holds numbers, so neither is a value column, and the value sequence
starts in the right place either way.

WHAT THIS MODULE KNOWS
The report vocabulary -- French headings, and the order in which each layout
prints its quantities. It knows nothing about PDFs (that is `pdftable`) and
nothing about what the numbers imply epidemiologically (that is the caller).
The specs are DATA and live at the bottom of this file, so supporting a new
vintage means adding a pattern or an order, not a code path.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable, Sequence


class Role(StrEnum):
    """A column's meaning, independent of where it sits or how it is spelled."""

    PROVINCE = "province"                    # label: the province
    ZONE = "zone"                            # label: the health zone
    CUM_CASES = "cum_cases"                  # cumulative confirmed cases
    CUM_DEATHS = "cum_deaths"                # cumulative confirmed deaths
    LETALITY = "letality"                    # printed case fatality; a CHECK, never data
    NEW_CASES = "new_cases"                  # confirmed cases in the last 24 h
    DEATHS_COMMUNITY = "deaths_community"    # community deaths confirmed by post-mortem swab
    DEATHS_CTE = "deaths_treatment_centre"   # deaths inside an Ebola treatment centre
    DEATHS_TOTAL = "deaths_total"            # confirmed deaths in the last 24 h
    SUSPECTED = "suspected"                  # suspected cases, cumulative (a stock)
    NEW_SUSPECTED = "new_suspected"          # suspected cases in 24 h (a flow)
    SUSPECTED_DEATHS = "suspected_deaths"    # suspected deaths
    CONTACTS = "contacts"                    # contacts listed
    RECOVERED = "recovered"                  # recoveries
    HOSPITALISED = "hospitalised"            # currently hospitalised
    PROBABLE = "probable"                    # probable cases
    IGNORED = "ignored"                      # a printed column we deliberately do not keep


def norm(s: str) -> str:
    """Accent- and case-fold text so one pattern matches every spelling.

    The reports print `Décès`, `Deces` and `DECES`. Folding here means the specs
    carry one pattern each instead of an alternation per accent.
    """
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


@dataclass(frozen=True)
class TableSpec:
    """A table, named by the vocabulary of its headings and the order of its columns."""

    name: str

    #: Phrases that must ALL appear somewhere in the heading block. Matched
    #: against the whole block rather than per column, because a heading cell's
    #: column index is not meaningful (see the module docstring) and because a
    #: single heading is routinely split across cells -- `Décès` in one and
    #: `(n)` in the next.
    requires: tuple[re.Pattern[str], ...]

    #: Phrases that must NOT appear. This is what separates tables whose
    #: headings otherwise agree: the per-zone OUTCOMES table prints cases and
    #: deaths beside `Guéris` and `En hospitalisation`, and only those two words
    #: tell it apart from the cumulative table. Without this, sitrep 083 read
    #: Bunia as 35 cases against a printed 967.
    forbids: tuple[re.Pattern[str], ...] = ()

    #: The left-to-right order of the VALUE columns -- the columns that hold
    #: numbers. Shorter tables simply stop early: before 13 July this table
    #: prints only the first three, and the daily block extends the same
    #: sequence rather than reordering it. A trailing column the source prints
    #: but we do not keep is named IGNORED rather than omitted, so the sequence
    #: stays aligned.
    values: tuple[Role, ...] = ()

    #: Names that identify the table by its ROWS rather than its heading. The
    #: provincial summary is often headless -- its heading bleeds into the
    #: dashboard above it -- so no heading vocabulary can find it. What is
    #: distinctive about it instead is that a MAJORITY of its labelled rows are
    #: province names, a closed set: five or six of its seven rows, against five
    #: among fifty in the zone table. Heading identification still applies when
    #: a heading exists; this is the route for tables that have none.
    row_vocabulary: frozenset[str] = frozenset()

    #: A pattern that must appear in the table's DATA cells (at least twice)
    #: for row identification to accept it. Row vocabulary alone is not enough:
    #: the alerts, contact-tracing and indicator tables also carry one row per
    #: province, and on sitrep 084 the alerts table was read as the provincial
    #: summary -- Ituri entered the series with 462 cumulative cases, which is
    #: its ALERT count for that day. What no other per-province table prints is
    #: the zones-touched cell, `53/140 (37,8 %)`: a count over a denominator.
    row_requires: re.Pattern[str] | None = None

    def identifies(self, headings: Sequence[str]) -> bool:
        block = norm(" | ".join(h for h in headings if h))
        if not block:
            return False
        if any(p.search(block) for p in self.forbids):
            return False
        return all(p.search(block) for p in self.requires)


@dataclass(frozen=True)
class Mapped:
    """One page of a table, with that page's own columns identified.

    COLUMNS ARE MAPPED PER PAGE, not once for the whole table. The page that
    carries the heading and the page that carries the data do not always have
    the same column count: on sitrep 090 the heading page has ten columns and
    its continuation has eight, because the title text laid across the heading
    row creates boundaries the data rows do not have. Resolving once on the head
    and indexing the continuation with it read the wrong columns; requiring the
    two to match exactly orphaned the continuation and lost all 61 of its rows.

    Mapping each page separately is safe precisely because the spec declares an
    ORDER rather than indices -- whatever a page's column count, its numeric
    columns still carry cases, then deaths, then letality, then the daily block.
    """

    table: object          # pdftable.Table
    roles: dict[Role, int]
    labels: tuple[int, ...]

    def label(self, row: Sequence[str]) -> str:
        """The row's own name: the RIGHTMOST label column carrying text.

        Two label columns appear together in the early layout, `Provinces` and
        `Zones de santé`, where the province is printed once against a merged
        cell spanning its zones. The rightmost filled label is therefore the
        row's own name and anything to its left is its parent.

        THE RIGHTMOST CELL CAN BE A FRAGMENT. Word sometimes draws one printed
        name across two label columns -- `Sous total` as `Sous | total`,
        `TOTAL NATIONAL` as `TOTAL | NATIONAL`, `Haut Uélé` as `Haut | Uélé` --
        and the rightmost cell alone then misnames the row: sitrep 013's three
        provincial subtotals were all levelled `national` from the fragment
        `total`, and sitrep 087's national total entered the series as a health
        zone named `NATIONAL`. Whether the cells are one split name or a parent
        beside a child is a question about the VOCABULARY of the joined text,
        which this module does not know -- so `label_cells` exposes all the
        fragments and the caller decides.
        """
        for j in reversed(self.labels):
            if j < len(row) and row[j].strip():
                return row[j].strip()
        return ""

    def label_cells(self, row: Sequence[str]) -> tuple[str, ...]:
        """Every filled label cell, left to right, for callers that must decide
        whether they are one split name or a parent beside a child."""
        return tuple(row[j].strip() for j in self.labels
                     if j < len(row) and row[j].strip())

    def parent(self, row: Sequence[str]) -> str:
        """The province printed against this row, when the table prints one separately."""
        if len(self.labels) < 2:
            return ""
        j = self.labels[0]
        return row[j].strip() if j < len(row) else ""

    def get(self, row: Sequence[str], role: Role) -> str:
        j = self.roles.get(role)
        return row[j] if j is not None and j < len(row) else ""


@dataclass(frozen=True)
class Resolved:
    """A table of a document: its spec, and each of its pages already mapped."""

    spec: TableSpec
    pages: tuple[Mapped, ...]


# --------------------------------------------------------------------------
# Column classification, from the data rather than the heading.
# --------------------------------------------------------------------------

#: The three characters the reports use as a thousands separator: ASCII
#: space, no-break space (U+00A0) and narrow no-break space (U+202F).
#: WRITTEN AS ESCAPES ON PURPOSE. Spelled as literal characters these are
#: indistinguishable from three ordinary spaces in every editor and diff,
#: and they were silently flattened to `"   "` at some point -- which made
#: `to_int` reject every count of a thousand or more that the source prints
#: with a no-break separator, and those are most of them.
_SPACES = "\u0020\u00a0\u202f"
_NUMERIC = re.compile(rf"^-?[\d{_SPACES}]*\d\s*[,\.]?\d*\s*%?$")
_SENTINEL = {"nd", "n/d", "na", "n/a", "-", "—", "–", "*", ""}


def _is_value(cell: str) -> bool | None:
    """True if the cell is a number, False if text, None if it carries nothing.

    A sentinel meaning "not reported" is None, not text: a column that is mostly
    em-dashes is still a value column, and classifying it as a label would push
    every later column one place along.
    """
    t = cell.strip().rstrip("*†‡").strip()
    if t.lower() in _SENTINEL:
        return None
    return bool(_NUMERIC.match(t))


def _cell_counts(table, start: int) -> tuple[list[int], list[int]]:
    """Per column: how many data cells are numeric, and how many are text."""
    numeric = [0] * table.ncols
    textual = [0] * table.ncols
    for i in range(start, table.nrows):
        for j, cell in enumerate(table.row(i)):
            got = _is_value(cell)
            if got is True:
                numeric[j] += 1
            elif got is False:
                textual[j] += 1
    return numeric, textual


def classify(table, *, start: int, min_rows: int = 3) -> tuple[list[int], list[int]]:
    """Split a table's columns into labels and values, by what its data rows hold.

    A column is a VALUE column when the cells that carry anything are mostly
    numbers. Label columns are then those to the left of the first value column;
    anything non-numeric to the RIGHT of it is neither, and is dropped -- some
    vintages print a trailing comment column.
    """
    ncols = table.ncols
    numeric, textual = _cell_counts(table, start)

    values = [j for j in range(ncols)
              if numeric[j] >= min_rows and numeric[j] > textual[j]]
    if not values:
        return [], []
    first = values[0]
    labels = [j for j in range(first) if textual[j] > 0]
    return labels, values


# --------------------------------------------------------------------------
# The vocabulary. Data, not code.
# --------------------------------------------------------------------------

P = re.compile

#: The per-zone cumulative table. From 13 July it gains a daily block splitting
#: the day's confirmed deaths by how the case was ascertained. `LETALITY` is
#: read but never used as data -- it is a column the source derives, which makes
#: it a free per-row check on the two columns that ARE used. On sitrep 080 it
#: disagrees with its own row throughout, which is how that report's stale
#: letality column was found.
ZONE_TABLE = TableSpec(
    name="zone_cumulative",
    requires=(
        P(r"provinces?\s*/\s*zones?\s*de\s*sant|zones?\s+de\s+sant"),
        P(r"\bcas\b"),
        P(r"deces"),
    ),
    forbids=(
        P(r"gueri"),
        P(r"hospitalisation"),
        # THE EARLY LAYOUT MUST NOT BE READ BY THIS SPEC. It also heads a zone
        # column, a case count and a death count, so once `Létalité` stopped
        # being required this spec matched it -- and because this spec is tried
        # first, sitrep 005's SUSPECTED cases were written out as CONFIRMED
        # ones. Mongbwalu was recorded with 309 confirmed cases where the page
        # prints 309 suspected and 13 confirmed.
        #
        # Nothing else caught it: the figures were plausible, the columns were
        # internally consistent, and the page's own arithmetic closed, because
        # the whole table had been read one concept to the left. Only a test
        # naming the report found it, which is the argument for having them.
        #
        # The cumulative confirmed table never carries a suspected column; the
        # early table is built around one.
        P(r"suspect"),
        # SITREP 087 PRINTS A DAILY TABLE AND NO CUMULATIVE ONE -- six 24-hour
        # columns, no cumulative column anywhere -- and this spec read it:
        # every requirement matched, and the day's 57 new Ituri cases were
        # written into `cum_cases` (the true cumulative that day was 4,381).
        # `cumul` cannot be required (sitreps 038, 039, 080 print real
        # cumulative tables whose headings never say it) and `du jour` cannot
        # be forbidden (title bleed puts `situation du jour` into 089-091's
        # headings). What only the daily table says is `dont décès parmi les
        # nouveaux confirmés` -- checked against all 83 reports.
        P(r"parmi\s+les\s+nouveaux"),
    ),
    values=(Role.CUM_CASES, Role.CUM_DEATHS, Role.LETALITY, Role.NEW_CASES,
            Role.DEATHS_COMMUNITY, Role.DEATHS_CTE, Role.DEATHS_TOTAL),
)

#: The early layout, to 1 June: suspected cases and deaths, confirmed cases and
#: contacts per zone, with the province in its own merged label column. It has
#: no letality and no cumulative-death column, so it is genuinely a different
#: table rather than a variant of the one above -- and its `suspected` column is
#: a cumulative STOCK where the later national series prints a daily FLOW, which
#: is why the two must never be differenced into one series.
EARLY_ZONE_TABLE = TableSpec(
    name="zone_early",
    requires=(
        P(r"zones?\s+de\s+sant"),
        P(r"suspects?"),
        P(r"confirmes?"),
        P(r"contacts?"),
    ),
    # The early reports print a DAILY table beside this cumulative one, with the
    # same vocabulary under `Nouveaux` -- new confirmed cases, new deaths, new
    # suspected, new contacts -- and a `Guéris du jour` column. It is a real
    # table and a useful one, but it is a flow where this is a stock, and
    # reading one as the other would mix an increment into a cumulative series.
    forbids=(P(r"letalit"), P(r"alertes"), P(r"gueri"), P(r"nouveau")),
    values=(Role.SUSPECTED, Role.SUSPECTED_DEATHS, Role.CUM_CASES, Role.CONTACTS),
)

#: A THIRD LAYOUT, printed around the end of May, which carries the daily and
#: the cumulative side by side: new suspected, suspected deaths, new confirmed,
#: THEN cumulative confirmed cases and cumulative confirmed deaths, recoveries
#: and contacts. Both other specs reject it, and correctly -- the cumulative
#: spec forbids a suspected column and the early spec forbids `Nouveaux` --
#: because reading either of those onto this table would put a daily flow into a
#: cumulative series or the reverse.
#:
#: It is a spec rather than a special case precisely because that is what the
#: architecture is for: a new vintage adds a declared column order, not a code
#: path. The order is what matters here, since `Nouveaux cas confirmés` and
#: `Cumul de cas Confirmés` are adjacent and only their sequence tells them
#: apart.
MIXED_ZONE_TABLE = TableSpec(
    name="zone_mixed",
    requires=(
        P(r"zones?\s+de\s+sant"),
        P(r"nouveaux?\s+cas\s+suspects?"),
        P(r"cumul\s+de\s+cas"),
    ),
    forbids=(P(r"letalit"), P(r"alertes")),
    # THE SUSPECTED COLUMN HERE IS A FLOW, NOT THE STOCK. This layout prints
    # `Nouveaux cas suspects` -- the day's new suspected -- where the early
    # layout prints a cumulative. Mapping both to one role mixed a flow into a
    # stock series: the national suspected panel showed 1,077 falling to 51 in
    # a day, which was sitrep 015's daily figure ending a cumulative series.
    values=(Role.NEW_SUSPECTED, Role.SUSPECTED_DEATHS, Role.NEW_CASES,
            Role.CUM_CASES, Role.CUM_DEATHS, Role.RECOVERED, Role.CONTACTS),
)

#: SITREP 087'S TABLE: the day's flows per zone, with NO cumulative column at
#: all. One report in the corpus prints it (in place of the cumulative table,
#: not beside it), and before this spec existed the cumulative spec claimed it
#: and stored the day's new cases as `cum_cases`. Its signature is the column
#: the daily-block vintage never prints: `Dont décès parmi les nouveaux
#: confirmés`, the deaths among the day's newly confirmed. That column has no
#: role of ours -- it is a subset of `deaths_total` we do not model -- so it is
#: IGNORED, which keeps the sequence aligned.
ZONE_DAILY = TableSpec(
    name="zone_daily",
    requires=(
        P(r"zones?\s+de\s+sant"),
        P(r"nouveaux?\s+cas\s+confirmes?"),
        P(r"parmi\s+les\s+nouveaux"),
    ),
    forbids=(P(r"cumul"), P(r"gueri"), P(r"hospitalisation"), P(r"suspect")),
    values=(Role.NEW_CASES, Role.IGNORED, Role.LETALITY,
            Role.DEATHS_COMMUNITY, Role.DEATHS_CTE, Role.DEATHS_TOTAL),
)

#: THE PROVINCIAL SUMMARY -- one row per province, no zones. Until now this
#: table was only ever something to keep OUT of the zone extraction; it is also
#: a source in its own right, and for the reports that print no per-zone table
#: at all (012, 014, 016, and the 084-086 vintage that dropped it) it is the
#: only tabular case data on the page. Extracted separately, it gives those
#: reports a province-level series and every other report an independent check
#: on the zone-derived sums.
#:
#: `Zones de santé touchées` -- the COUNT of affected zones, printed like
#: `28/36 (77,8 %)` -- is required, because it is the summary's signature.
#: The slash-form label `Province / Zone de santé` is forbidden, because it is
#: the zone table's signature: its rows are provinces AND zones, where this
#: table's are provinces alone. The title text that bleeds into zone-table
#: headings spells `par province et zone de santé` without the slash, so the
#: two do not collide there.
PROVINCIAL_SUMMARY = TableSpec(
    name="provincial_summary",
    requires=(
        P(r"provinces?\b"),
        P(r"\bcas\b"),
        P(r"deces"),
        P(r"zones?\s+de\s+sant\w*\s+touchee|touchee"),
    ),
    forbids=(
        P(r"provinces?\s*/\s*zones?"),
        P(r"gueri"),
        P(r"hospitalisation"),
        P(r"suspect"),
    ),
    # THE ZONES-TOUCHED COLUMN NEVER CLASSIFIES AS A VALUE. It prints
    # `28/36 (77,8 %)`, which `_NUMERIC` rejects, so it never consumes a slot
    # in this sequence -- an `IGNORED` placed for it here swallowed the NEXT
    # column instead, and `Nouveaux cas confirmés (24h)` came out null on all
    # 348 summary rows. The value sequence is what the classifier actually
    # detects: cases, deaths, letality, then the day's new cases.
    values=(Role.CUM_CASES, Role.CUM_DEATHS, Role.LETALITY, Role.NEW_CASES),
    row_vocabulary=frozenset({
        "ituri", "nord-kivu", "nord kivu", "sud-kivu", "sud kivu",
        "haut-uele", "haut uele", "tshopo", "bas-uele", "bas uele",
        "kinshasa", "maniema"}),
    # `21 sur 36 (58,3 %)` is the same zones-touched cell in words -- the 033
    # vintage spells the slash out.
    row_requires=P(r"\d+\s*(?:/|sur)\s*\d+"),
)

#: The zone-level specs, in order of preference. The provincial summary is NOT
#: here: it is a separate route with its own output, because it answers a
#: different question (province totals, not zone detail) and must never compete
#: with the zone table for the same extraction.
SPECS: tuple[TableSpec, ...] = (ZONE_TABLE, MIXED_ZONE_TABLE, EARLY_ZONE_TABLE,
                                ZONE_DAILY)
ALL_SPECS: tuple[TableSpec, ...] = SPECS + (PROVINCIAL_SUMMARY,)


def spans_same(a, b, tol: float = 10.0) -> bool:
    """Two tables have the same left and right edges, so a page break split one table.

    BOTH edges must agree, and that is the strength of the test rather than a
    limitation. Nearly every table in these reports spans most of the text
    width, so a looser criterion -- overlap as a fraction of the wider span --
    chains unrelated tables together and costs far more than it recovers:
    province-reports fell from 216 to 146 under it. Two edges agreeing within a
    few points is a much rarer coincidence than one broad overlap.

    The tolerance is 10 pt, and the history of this number is the point. It was
    set to 8 pt because 10 pt measured WORSE end to end -- 180 reconciling
    province-reports against 198 -- and that measurement was real but its
    conclusion was wrong. Two defects elsewhere were doing the damage: an empty
    row inside a heading was truncating headings, and numbered rows (`1- Bunia`)
    were being discarded entirely. With those fixed, 10 pt gives 238 reconciling
    against 226, recovers sitreps 090 and 093 whose two pages begin 8.5 and 9.0
    pt apart, and adds 67 health-zone rows. 12 pt gives nothing further, so the
    smaller value is kept.

    A tuning parameter measured against a buggy pipeline gives the wrong answer
    confidently, and the number then outlives the bug it was compensating for.
    """
    return abs(a.xs[0] - b.xs[0]) <= tol and abs(a.xs[-1] - b.xs[-1]) <= tol


def same_label_heading(a, b) -> bool:
    """Two headed tables name their label column the same way.

    Adjacency and width are not enough to say that two headed tables are one
    table. The PROVINCIAL SUMMARY heads its label column `Province`; this table
    heads its own `Province / Zone de santé`, because its rows are provinces AND
    their zones. On sitrep 059 the summary sits on page 2 and the zone table
    begins on page 3, so the two are adjacent and equally wide -- they chained,
    the summary's five province rows preceded every zone row, and the province
    carry attached all 43 zones to Tshopo, the last province the summary lists.

    Comparing the label heading separates them without forbidding any
    vocabulary, which matters because the phrase that would exclude the summary
    (`Zones de santé touchées`, a COUNT of affected zones) also appears in this
    table's own heading on four reports, where the title text bleeds across the
    row. Tested: forbidding it gains two reconciling province-reports and loses
    four whole reports.
    """
    ha, hb = a.header(), b.header()
    if not ha or not hb:
        return True                     # a headless continuation carries no claim
    return norm(ha[0]) == norm(hb[0])


def rows_identify(table, spec: TableSpec) -> bool:
    """A majority of the table's labelled rows belong to the spec's vocabulary."""
    if not spec.row_vocabulary:
        return False
    labels, values = classify(table, start=table.header_rows())
    if not values:
        return False
    col = labels[0] if labels else None
    if col is None:
        return False
    names = [norm(table.row(i)[col]) for i in range(table.header_rows(), table.nrows)
             if col < table.ncols and table.row(i)[col].strip()]
    if len(names) < 3:
        return False
    hits = sum(1 for n in names if n in spec.row_vocabulary or n.startswith("total"))
    if hits * 2 <= len(names):
        return False
    if spec.row_requires is not None:
        cells = " | ".join(c for i in range(table.nrows) for c in table.row(i) if c)
        if len(spec.row_requires.findall(cells)) < 2:
            return False
    return True


def rows_are_provinces(table) -> bool:
    """A majority of this table's own row names are provinces or totals -- the
    structural signature of the provincial summary, whatever its heading says.

    The name tested is the RIGHTMOST label column. The early layout's leftmost
    label column is a merged province cell, so testing that column would call
    every early zone table a summary by construction; a row's own name is
    always the rightmost label, and in the summary the two coincide.
    """
    labels, values = classify(table, start=table.header_rows())
    if not values or not labels:
        return False
    col = labels[-1]
    names = [norm(table.row(i)[col]) for i in range(table.header_rows(), table.nrows)
             if col < table.ncols and table.row(i)[col].strip()]
    if len(names) < 3:
        return False
    vocab = PROVINCIAL_SUMMARY.row_vocabulary
    hits = sum(1 for n in names
               if n in vocab or n.startswith("total") or n.startswith("sous"))
    return hits * 2 > len(names)


def _map(table, spec: TableSpec) -> Mapped | None:
    labels, values = classify(table, start=table.header_rows())
    if not values:
        return None
    roles = {role: col for role, col in zip(spec.values, values)
             if role is not Role.IGNORED}
    return Mapped(table=table, roles=roles, labels=tuple(labels))


#: How far a column's centre may sit from its counterpart on a sibling page and
#: still be the same printed column. Pages of one chain share their outer edges
#: to within 10 pt (`spans_same`), and the data columns are 40-70 pt wide, so
#: 15 pt separates "the same column, drawn a little differently" from "the
#: neighbouring column" with a wide margin either way.
_ALIGN_TOL = 15.0


def _remap_by_x(table, spec: TableSpec, ref: Mapped) -> Mapped | None:
    """Map a page's columns by aligning them, in x, to a sibling page of the
    same table -- for pages where order alone misassigns them.

    A chain is ONE table split by page breaks, so its columns line up in x
    across pages even when the drawn grid does not repeat exactly. Mapping each
    page by zip order instead assumes every page RESOLVES the same columns, and
    on sitreps 090-093 the head page does not: it carries only the short Ituri
    block, the intra-CTE deaths column has a single numeric cell there --
    below the classifier's threshold -- and the zip slid `Total décès` into
    `deaths_treatment_centre` and left `deaths_total` null. Only Ituri was
    affected, invisible beside five correct sibling rows, and the emitted
    community-death fraction for the final week read 1.000 against a printed
    0.55.

    So when a page resolves a DIFFERENT number of value columns than the
    chain's best-resolved page, its columns take their roles from that
    reference page by x-position, not by order. A column matching nothing
    within tolerance carries no role, which is honest: better a null than a
    neighbour's meaning.
    """
    # CANDIDATES ARE ANY COLUMN WITH A NUMBER IN IT, not the columns the
    # classifier kept -- the classifier is exactly what failed on this page.
    # Its verdict is majority-based, and two shapes of page defeat it: thin
    # data (sitrep 090's head page holds one numeric intra-CTE cell, below the
    # threshold) and a grid region that sweeps in narrative prose below the
    # table (sitrep 058's last seven rows sit above three paragraphs of text,
    # which outvote them column by column). The x-match against the reference
    # page is what keeps a label column out: labels sit under no value
    # column's centre. Prose that survives into a value column self-filters
    # later -- none of its cells parses as a number.
    numeric, textual = _cell_counts(table, table.header_rows())
    cand = [j for j in range(table.ncols) if numeric[j] >= 1]

    def center(t, j: int) -> float:
        return (t.xs[j] + t.xs[j + 1]) / 2.0

    roles: dict[Role, int] = {}
    used: set[int] = set()
    for role, rj in sorted(ref.roles.items(), key=lambda kv: kv[1]):
        cx = center(ref.table, rj)
        got = min(((abs(center(table, j) - cx), j) for j in cand
                   if j not in used), default=None)
        if got is None or got[0] > _ALIGN_TOL:
            continue
        roles[role] = got[1]
        used.add(got[1])
    if not roles:
        return None
    # LABELS COME FROM THE REFERENCE PAGE TOO. Deriving them from this page's
    # own text ("everything textual left of the first value column") swept in
    # prose fragments as a second label column on sitrep 058's last page --
    # every row's own name then doubled as its printed parent, the carry took
    # those names for province anchors, and forty zones landed in Haut-Uélé.
    # One table, one label set: each reference label column maps to this
    # page's nearest column by x.
    labels = []
    for rj in ref.labels:
        cx = center(ref.table, rj)
        got = min(((abs(center(table, j) - cx), j) for j in range(table.ncols)
                   if j not in used), default=None)
        if got is not None and got[0] <= _ALIGN_TOL:
            labels.append(got[1])
    return Mapped(table=table, roles=roles, labels=tuple(sorted(labels)))


def select(tables: Iterable, spec: TableSpec) -> Resolved | None:
    """The document's instance of `spec`, with its continuation pages attached.

    CANDIDATES ARE RANKED, NOT TAKEN IN ORDER. Heading vocabulary alone does not
    single this table out, and no amount of tightening it did. The provincial
    summary sits above this table on the same page and states the same things
    about itself -- a province, a case count, a death count -- because it IS a
    summary of it. Every phrase that excluded the summary also excluded some
    vintage of the real table, because the title text bleeds across the heading
    row into arbitrary cells.

    The difference that holds is structural: the summary carries one row per
    province, five to eight of them, and this table one row per health zone,
    thirty to sixty. So candidates are grouped into chains by horizontal extent
    and the chain with the most data rows wins.

    Ranking also settles the opposite failure. This table is printed across two
    pages, and taking the LARGEST PAGE as the head made page two the head and
    dropped page one's province rows -- sitrep 060 lost 1,808 of its 2,011 cases
    that way. A chain is scored whole, so both pages count together.
    """
    tabs = sorted(tables, key=lambda t: (t.page, t.ys[0]))
    # A HEAD NEED NOT MAP ITS OWN COLUMNS. Requiring `_map` here excluded any
    # head too thin to classify -- sitrep 067's table opens with a fragment
    # holding a heading and ONE data row, the Ituri province row, and a single
    # row cannot meet the classifier's threshold. Excluded from the chain, the
    # row vanished and all 29 zones beneath it lost their province. Mapping is
    # the chain's problem now: a page that cannot classify its own columns
    # takes them from the chain's best page by x-position.
    heads = [t for t in tabs
             if spec.identifies(t.header()) or rows_identify(t, spec)]
    if not heads:
        return None

    # CHAINING REQUIRES ADJACENCY, not merely a shared width. Nearly every
    # table in these reports spans the full text width, so extent alone linked
    # the provincial summary on page 2 to the zone table on page 4 and then to
    # the laboratory table on page 7 -- one "chain" of three unrelated tables
    # whose province rows were counted twice, giving a residual of exactly the
    # printed total on five reports.
    #
    # A table continued across a page break resumes on the NEXT page. Anything
    # with a page of something else in between is a different table.
    chains: list[list] = []
    for t in heads:
        for chain in chains:
            if (spans_same(t, chain[-1]) and t.page - chain[-1].page <= 1
                    and same_label_heading(t, chain[-1])):
                chain.append(t)
                break
        else:
            chains.append([t])

    # A CONTINUATION CARRIES NO HEADING OF ITS OWN. That is the test, and
    # dropping it was a mistake worth naming: matching on horizontal extent
    # alone attached the alerts and laboratory tables further down the document,
    # because nearly every table on these pages spans the full text width. The
    # sums then included rows from three different tables and the identity
    # failed on 37 reports instead of 6.
    #
    # So a continuation must be headless AND share the extent AND follow the
    # chain without another table of its own intervening -- the chain grows only
    # into what comes directly next.
    for chain in chains:
        anchor = chain[0]
        pos = max((t.page, t.ys[0]) for t in chain)
        for t in tabs:
            if (t.page, t.ys[0]) <= pos or not spans_same(t, anchor):
                continue
            if t.header_rows() != 0 or t.page - pos[0] > 1:
                break
            chain.append(t)
            pos = (t.page, t.ys[0])
        chain.sort(key=lambda t: (t.page, t.ys[0]))

    def weight(chain) -> int:
        return sum(t.nrows - t.header_rows() for t in chain)

    # THE WINNING CHAIN MUST BE READABLE. Now that a head need not map its own
    # columns, a grid that merely TALKS like the table -- title bleed carrying
    # the right vocabulary over rows that classify to nothing -- can form a
    # heavy chain of pure junk, and on sitrep 061 one outweighed the real
    # summary and emptied the extraction. A chain with no mappable page has no
    # reference to remap against and nothing to read; the heaviest chain that
    # can actually be read wins.
    raw, ok = [], []
    for chain in sorted(chains, key=weight, reverse=True):
        raw = [(t, _map(t, spec)) for t in chain]
        ok = [m for _, m in raw if m]
        if ok:
            break
    if not ok:
        return None
    # ONE TABLE, ONE COLUMN SET. A page that resolves fewer (or more) value
    # columns than the chain's best-resolved page has NOT lost those columns
    # on the page -- the classifier lost them in that page's thin or
    # prose-contaminated data -- and a page that resolves none at all is still
    # a page of the same table: sitrep 067's head fragment carries the one
    # Ituri province row (a single data row cannot meet the classifier's
    # threshold), and dropping it orphaned all 29 zones beneath it. Any page
    # that does not resolve exactly the reference set is aligned to the
    # reference page by x instead of by order; pages that match keep the
    # ordered zip unchanged.
    ref = max(ok, key=lambda m: len(m.roles))
    pages = []
    for t, m in raw:
        if m is None or len(m.roles) != len(ref.roles):
            m = _remap_by_x(t, spec, ref) or m
        if m:
            pages.append(m)
    if not pages:
        return None
    return Resolved(spec=spec, pages=tuple(pages))


def select_any(tables: Iterable, specs: Sequence[TableSpec] = SPECS) -> Resolved | None:
    """The first spec that resolves against this document."""
    tabs = list(tables)
    for spec in specs:
        got = select(tabs, spec)
        if got:
            return got
    return None
