"""Read tables out of a PDF from the rules the document draws, not from its text layout.

WHY NOT `pdftotext -layout`
The situation reports are Microsoft Word exports. Word draws every table border
as a thin filled rectangle, so the page carries an explicit statement of where
each row and column begins and ends. `pdftotext -layout` discards all of it and
renders the page as a character grid, which loses three things that then have to
be reconstructed by guesswork:

  * A cell taller than one line becomes several text lines. A health zone whose
    name does not fit its column emits the name on one line and its numbers on
    another, so the row no longer looks like a row.
  * An empty cell emits no characters, so splitting a line on whitespace shifts
    every later value one column to the left and a row silently acquires wrong
    values rather than missing ones.
  * Column membership has to be inferred from character offsets, which drift
    within a page, so the inference needs a ruler learnt per page from rows that
    happen to be complete.

Reading the drawn rules removes all three. A cell's row and column are given,
not inferred; a tall cell is one cell; an empty cell is empty.

WHAT THIS MODULE KNOWS
Geometry and nothing else -- no French, no epidemiology, no report vocabulary.
It answers "what tables are on this page, and what is in cell (i, j)". Choosing
WHICH table, and what its columns mean, belongs to the caller.

HOW A TABLE IS DELIMITED
A page can carry many tables, so the rules are grouped before they are read: two
rules belong to the same table when they touch. Horizontal and vertical rules
are unioned wherever they intersect, and each connected component becomes one
`Table` with its own column and row edges. This replaces searching the text for
a title and running to a terminator -- the mechanism whose failure elsewhere in
this problem sent a table read on into the next table and returned its figures
as case counts.

TOLERANCES, AND WHY THE TWO AXES DIFFER
`SNAP_X` and `SNAP_Y` collapse the several coordinates that describe one
boundary into a single edge. They are not the same number, and setting them
equal breaks the table in one direction or the other.

Word draws a shared vertical border as three things: the right face of the cell
to its left, the rule itself, and the left face of the cell to its right. Cell
padding puts about 4 pt between the outer two, so a horizontal tolerance below
that reports two column boundaries with a phantom empty column between them and
doubles the apparent column count. Real columns here are about 57 pt apart, so
`SNAP_X` sits comfortably between.

Rows have far less padding and are only about 12 pt apart. Applying the
horizontal tolerance vertically merges adjacent row boundaries -- which in this
corpus fuses the last heading row into the first data row, so a province row
gets read as part of the heading and its counts vanish. `SNAP_Y` is therefore
tight.

`TOUCH` is how near a horizontal and a vertical rule must come to count as
intersecting. Word's borders often stop a hair short of each other at a corner,
so this is deliberately loose.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Iterator

import pdfplumber

SNAP_X = 6.0
SNAP_Y = 2.5
SNAP = SNAP_X          # backstop for containment tests
TOUCH = 3.0
MIN_RULE = 2.0        # a rectangle shorter than this in both axes is not a rule
MIN_COLS = 2
MIN_ROWS = 2


@dataclass(frozen=True)
class Segment:
    """One drawn rule: a line of constant y (horizontal) or constant x (vertical)."""
    pos: float          # y for horizontal, x for vertical
    lo: float           # start along the other axis
    hi: float           # end along the other axis
    horizontal: bool

    def crosses(self, other: "Segment", tol: float = TOUCH) -> bool:
        if self.horizontal == other.horizontal:
            return False
        h, v = (self, other) if self.horizontal else (other, self)
        return (h.lo - tol <= v.pos <= h.hi + tol
                and v.lo - tol <= h.pos <= v.hi + tol)


@dataclass(frozen=True)
class Table:
    """A grid of cells recovered from one connected group of drawn rules.

    `xs` and `ys` are the column and row boundaries, so the table has
    `len(xs) - 1` columns and `len(ys) - 1` rows. `cells` maps (row, column) to
    the text found inside that cell, joined by spaces in reading order; a cell
    with no words is absent from the mapping rather than present and empty, so
    the caller can tell "no ink here" from "a cell holding an empty string".
    """
    page: int
    xs: tuple[float, ...]
    ys: tuple[float, ...]
    cells: dict[tuple[int, int], str]

    @property
    def ncols(self) -> int:
        return len(self.xs) - 1

    @property
    def nrows(self) -> int:
        return len(self.ys) - 1

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.xs[0], self.ys[0], self.xs[-1], self.ys[-1])

    def row(self, i: int) -> list[str]:
        return [self.cells.get((i, j), "") for j in range(self.ncols)]

    def rows(self) -> Iterator[list[str]]:
        for i in range(self.nrows):
            yield self.row(i)

    @cached_property
    def filled(self) -> int:
        return len(self.cells)

    def header_rows(self, *, max_scan: int = 8) -> int:
        """How many leading rows form the column headings.

        A heading is not reliably one row. `Province / Zone de santé` wraps onto
        a second row, and from 13 July the daily block adds a third in which
        `Décès communautaires` and `Décès confirmés intra-CTE` sit beneath a
        spanning `Décès (n)`. Reading only the first row would see `Cas (n)` and
        `Décès (n)` and miss every sub-heading that distinguishes a cumulative
        column from a daily one -- which is the distinction the caller needs to
        pick the right column.

        So the heading is a BLOCK: leading rows are taken while they carry text
        and no bare number. The first row holding a bare number is data, because
        a heading never is -- that test is the real stop, and `max_scan` only
        bounds a pathological table. It must be generous: the early layout wraps
        `Nbre de décès suspects` over three rows and prints the block over six,
        and a cap of four truncated every heading to `Nbre de` and `Zones de`,
        so no column resolved and the whole vintage was rejected.
        """
        n = 0
        for i in range(min(max_scan, self.nrows)):
            cells = [c for c in self.row(i) if c.strip()]
            if any(_numeric(c) for c in cells):
                break
            if cells:
                n = i + 1
            elif n:
                break
        return n

    def header(self, *, look_below: int = 4) -> list[str]:
        """Column headings, with each column's wrapped fragments joined.

        A COLUMN'S HEADING CAN SIT BELOW THE FIRST DATA ROW. Word lays the
        heading block out as a unit, and when a heading wraps onto more lines
        than the block reserves, the overflow is placed after the first data
        row instead of before it. In this corpus that happens whenever the
        first province row is short: the report prints

            Province / Zone de santé | Cas (n) | Décès (n) |    |    |
            Ituri                    | 3 317   | 1 382     |    |    |
                                     |         |           | Létalité | Nouv. cas | ...

        so the five columns of the letality and daily block have no heading in
        the block and would be unidentifiable, while `Ituri`'s counts sit in a
        row that looks like data because it is.

        The scan therefore continues PER COLUMN, and only for columns the
        heading block left empty. A column that already has a heading stops
        immediately, which is what keeps the first data row's name cell from
        being appended to the name column's heading. A column still empty looks
        a few rows further for text that is not a number.
        """
        n = self.header_rows()
        if not n:
            return []
        out: list[str] = []
        for j in range(self.ncols):
            parts = [p for p in (self.cells.get((i, j), "") for i in range(n)) if p]
            if not parts:
                for i in range(n, min(n + look_below, self.nrows)):
                    cell = self.cells.get((i, j), "").strip()
                    if cell and not _numeric(cell):
                        parts.append(cell)
            out.append(" ".join(parts).strip())
        return out

    def header_index(self) -> int | None:
        n = self.header_rows()
        return n - 1 if n else None


def _numeric(s: str) -> bool:
    t = s.strip().replace(" ", "").replace(" ", "").replace(" ", "")
    t = t.rstrip("%*†‡").replace(",", ".")
    if not t:
        return False
    try:
        float(t)
    except ValueError:
        return False
    return True


def _snap(values, tol: float) -> list[float]:
    """Collapse near-equal coordinates, keeping the mean of each cluster."""
    out: list[float] = []
    run: list[float] = []
    for v in sorted(values):
        if run and v - run[-1] > tol:
            out.append(sum(run) / len(run))
            run = []
        run.append(v)
    if run:
        out.append(sum(run) / len(run))
    return out


def _segments(page) -> list[Segment]:
    """Every drawn rule on the page, from rectangles, lines and straight curves.

    Word emits borders as filled rectangles; `ilovepdf` re-encodes some of them
    as lines; a few pages carry them as two-point curves. All three are the same
    thing geometrically and all three appear in this corpus, so all three are
    read rather than assuming one producer.
    """
    segs: list[Segment] = []
    for obj in (*page.rects, *page.lines, *page.curves):
        x0, x1 = obj["x0"], obj["x1"]
        y0, y1 = obj["top"], obj["bottom"]
        w, h = x1 - x0, y1 - y0
        if h < MIN_RULE <= w:
            segs.append(Segment((y0 + y1) / 2, x0, x1, True))
        elif w < MIN_RULE <= h:
            segs.append(Segment((x0 + x1) / 2, y0, y1, False))
        elif w >= MIN_RULE and h >= MIN_RULE:
            # A filled cell body: its four sides are rules.
            segs.append(Segment(y0, x0, x1, True))
            segs.append(Segment(y1, x0, x1, True))
            segs.append(Segment(x0, y0, y1, False))
            segs.append(Segment(x1, y0, y1, False))
        else:
            # A DOT. Too small to have a direction of its own, so it is emitted
            # on both axes and left for coalescing to resolve: a dot in a
            # horizontal run joins a horizontal rule, one in a vertical run
            # joins a vertical rule, and one in neither is dropped afterwards
            # for being too short to be a rule. This is what makes the
            # dot-stippled re-encodes readable at all -- sitrep 026 draws every
            # border as 8,419 squares of half a point.
            segs.append(Segment((y0 + y1) / 2, x0, x1, True))
            segs.append(Segment((x0 + x1) / 2, y0, y1, False))
    return segs


#: How large a gap along a rule still counts as the same rule. A rule is
#: routinely drawn in pieces, and the two ways it happens here are far apart in
#: scale but identical in kind:
#:
#:   * The macOS Quartz re-encoder stipples every rule into a run of 0.5 pt
#:     squares -- sitrep 026 carries 8,419 of them on one page -- with
#:     essentially no gap between the pieces.
#:   * A banded table draws its column rules only where a row is shaded, so the
#:     rule exists inside each banner row and stops across the unshaded data
#:     rows between them. On sitrep 018 that leaves the table's own borders in
#:     94 disconnected islands, none more than six rows tall.
#:
#: In both cases the drawn pieces lie on one line at one position, and treating
#: them as separate rules is what prevents the table from forming. The gap must
#: therefore exceed a data row's height (about 16 pt here) and stay well below
#: the distance between genuinely separate tables.
COALESCE_GAP = 30.0


def _coalesce(segs: list[Segment], gap: float = COALESCE_GAP) -> list[Segment]:
    """Merge collinear pieces that lie on one line into single rules."""
    out: list[Segment] = []
    for horizontal in (True, False):
        axis = [s for s in segs if s.horizontal is horizontal]
        if not axis:
            continue
        axis.sort(key=lambda s: (s.pos, s.lo))
        cluster: list[Segment] = []
        for s in axis:
            if cluster and s.pos - cluster[-1].pos > (SNAP_Y if horizontal else SNAP_X):
                out.extend(_merge_run(cluster, horizontal, gap))
                cluster = []
            cluster.append(s)
        if cluster:
            out.extend(_merge_run(cluster, horizontal, gap))
    return out


def _merge_run(cluster: list[Segment], horizontal: bool, gap: float) -> list[Segment]:
    """Join pieces at one position whose spans touch or nearly touch."""
    pos = sum(s.pos for s in cluster) / len(cluster)
    spans = sorted((s.lo, s.hi) for s in cluster)
    out: list[Segment] = []
    lo, hi = spans[0]
    for a, b in spans[1:]:
        if a - hi <= gap:
            hi = max(hi, b)
        else:
            out.append(Segment(pos, lo, hi, horizontal))
            lo, hi = a, b
    out.append(Segment(pos, lo, hi, horizontal))
    return out


def _components(segs: list[Segment]) -> list[list[Segment]]:
    """Group rules into tables: two rules are connected when they intersect."""
    parent = list(range(len(segs)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    horiz = [i for i, s in enumerate(segs) if s.horizontal]
    vert = [i for i, s in enumerate(segs) if not s.horizontal]
    for i in horiz:
        for j in vert:
            if segs[i].crosses(segs[j]):
                union(i, j)

    groups: dict[int, list[Segment]] = {}
    for i, s in enumerate(segs):
        groups.setdefault(find(i), []).append(s)
    return list(groups.values())


#: A coalesced rule shorter than this is not a rule. Applied AFTER coalescing,
#: so it removes the isolated dots and stray marks that survive as degenerate
#: segments while leaving every run that actually forms a border.
MIN_RUN = 10.0


def tables(page, *, min_cols: int = MIN_COLS, min_rows: int = MIN_ROWS,
           gap: float = COALESCE_GAP) -> list[Table]:
    """Every table on one page, as a cell grid."""
    segs = [s for s in _coalesce(_segments(page), gap) if s.hi - s.lo >= MIN_RUN]
    comps = _components(segs)
    words = page.extract_words()
    out: list[Table] = []

    for comp in comps:
        xs = _snap([s.pos for s in comp if not s.horizontal]
                   + [s.lo for s in comp if s.horizontal]
                   + [s.hi for s in comp if s.horizontal], SNAP_X)
        ys = _snap([s.pos for s in comp if s.horizontal]
                   + [s.lo for s in comp if not s.horizontal]
                   + [s.hi for s in comp if not s.horizontal], SNAP_Y)
        if len(xs) - 1 < min_cols or len(ys) - 1 < min_rows:
            continue

        cells: dict[tuple[int, int], list[tuple[float, float, str]]] = {}
        for w in words:
            mx = (w["x0"] + w["x1"]) / 2
            my = (w["top"] + w["bottom"]) / 2
            if not (xs[0] - SNAP_X <= mx <= xs[-1] + SNAP_X
                    and ys[0] - SNAP_Y <= my <= ys[-1] + SNAP_Y):
                continue
            j = _bucket(xs, mx, SNAP_X)
            i = _bucket(ys, my, SNAP_Y)
            if i is None or j is None:
                continue
            cells.setdefault((i, j), []).append((w["top"], w["x0"], w["text"]))

        joined = {
            k: " ".join(t for _, _, t in sorted(v))
            for k, v in cells.items()
        }
        out.append(Table(page.page_number, tuple(xs), tuple(ys), joined))

    out.sort(key=lambda t: (t.ys[0], t.xs[0]))
    return out


def _bucket(edges: list[float], v: float, tol: float) -> int | None:
    """Index of the interval of `edges` containing `v`, or None if outside."""
    if v < edges[0] - tol or v > edges[-1] + tol:
        return None
    lo, hi = 0, len(edges) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if v < edges[mid]:
            hi = mid
        else:
            lo = mid
    return min(lo, len(edges) - 2)


def read(pdf: Path, **kw) -> list[Table]:
    """Every table in a document, in page then reading order."""
    out: list[Table] = []
    with pdfplumber.open(str(pdf)) as doc:
        for page in doc.pages:
            out.extend(tables(page, **kw))
    return out
