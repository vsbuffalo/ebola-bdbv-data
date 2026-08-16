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
    SUSPECTED = "suspected"                  # suspected cases
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

    def identifies(self, headings: Sequence[str]) -> bool:
        block = norm(" | ".join(h for h in headings if h))
        if not block:
            return False
        if any(p.search(block) for p in self.forbids):
            return False
        return all(p.search(block) for p in self.requires)


@dataclass(frozen=True)
class Resolved:
    """One table of a document, with its columns identified."""

    spec: TableSpec
    roles: dict[Role, int]
    labels: tuple[int, ...]
    tables: tuple  # pdftable.Table, in page order: the head and its continuations

    def label(self, row: Sequence[str]) -> str:
        """The row's own name: the RIGHTMOST label column carrying text.

        Two label columns appear together in the early layout, `Provinces` and
        `Zones de santé`, where the province is printed once against a merged
        cell spanning its zones. The rightmost filled label is therefore the
        row's own name and anything to its left is its parent.
        """
        for j in reversed(self.labels):
            if j < len(row) and row[j].strip():
                return row[j].strip()
        return ""

    def parent(self, row: Sequence[str]) -> str:
        """The province printed against this row, when the table prints one separately."""
        if len(self.labels) < 2:
            return ""
        j = self.labels[0]
        return row[j].strip() if j < len(row) else ""

    def get(self, row: Sequence[str], role: Role) -> str:
        j = self.roles.get(role)
        return row[j] if j is not None and j < len(row) else ""


# --------------------------------------------------------------------------
# Column classification, from the data rather than the heading.
# --------------------------------------------------------------------------

_SPACES = "   "
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


def classify(table, *, start: int, min_rows: int = 3) -> tuple[list[int], list[int]]:
    """Split a table's columns into labels and values, by what its data rows hold.

    A column is a VALUE column when the cells that carry anything are mostly
    numbers. Label columns are then those to the left of the first value column;
    anything non-numeric to the RIGHT of it is neither, and is dropped -- some
    vintages print a trailing comment column.
    """
    ncols = table.ncols
    numeric = [0] * ncols
    textual = [0] * ncols
    for i in range(start, table.nrows):
        for j, cell in enumerate(table.row(i)):
            got = _is_value(cell)
            if got is True:
                numeric[j] += 1
            elif got is False:
                textual[j] += 1

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
        P(r"letalit"),
    ),
    forbids=(P(r"gueri"), P(r"hospitalisation")),
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
    forbids=(P(r"letalit"), P(r"alertes")),
    values=(Role.SUSPECTED, Role.SUSPECTED_DEATHS, Role.CUM_CASES, Role.CONTACTS),
)

SPECS: tuple[TableSpec, ...] = (ZONE_TABLE, EARLY_ZONE_TABLE)


def same_columns(a, b, tol: float = 4.0) -> bool:
    """Two tables share a column geometry, so a page break split one table."""
    return (len(a.xs) == len(b.xs)
            and all(abs(u - v) <= tol for u, v in zip(a.xs, b.xs)))


def select(tables: Iterable, spec: TableSpec) -> Resolved | None:
    """The document's instance of `spec`, with its continuation pages attached.

    The head is the FIRST table that identifies, not the largest. This table is
    printed across two pages in most vintages, with the province rows on the
    first and the health zones on the second, and both repeat the heading.
    Choosing the larger made the second page the head and dropped the first, so
    every province row went missing and the identity had nothing to compare
    against -- sitrep 060 lost 1,808 of its 2,011 cases that way.

    Continuations are found by COLUMN GEOMETRY rather than by looking for a
    repeated heading, because some vintages repeat it and some do not. Columns
    are classified once, over the head and its continuations together, so a
    continuation page that carries no heading at all is still readable.
    """
    tabs = sorted(tables, key=lambda t: (t.page, t.ys[0]))

    # A CANDIDATE MUST BOTH IDENTIFY AND CLASSIFY. Heading vocabulary alone is
    # not sufficient evidence: a page carries small fragments -- a stray caption
    # box, a one-row table -- whose few words can satisfy the required phrases
    # while holding no data at all. Taking the first such fragment as the head
    # then found no value columns and the whole document was reported as having
    # no matching table, on 30 of 82 reports.
    #
    # A table with no column of numbers is not the table we are looking for, so
    # the search continues rather than failing. The first candidate that both
    # names itself correctly AND holds data is the head.
    for head in (t for t in tabs if spec.identifies(t.header())):
        chain = [t for t in tabs
                 if t is head or (same_columns(t, head)
                                  and (t.page, t.ys[0]) > (head.page, head.ys[0]))]
        labels, values = classify(head, start=head.header_rows())
        if not values:
            for t in chain[1:]:
                labels, values = classify(t, start=t.header_rows())
                if values:
                    break
        if not values:
            continue
        roles = {role: col for role, col in zip(spec.values, values)
                 if role is not Role.IGNORED}
        return Resolved(spec=spec, roles=roles, labels=tuple(labels),
                        tables=tuple(chain))
    return None


def select_any(tables: Iterable, specs: Sequence[TableSpec] = SPECS) -> Resolved | None:
    """The first spec that resolves against this document."""
    tabs = list(tables)
    for spec in specs:
        got = select(tabs, spec)
        if got:
            return got
    return None
