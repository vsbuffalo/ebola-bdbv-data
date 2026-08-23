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

import bisect
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

    `rules` is the component this grid was recovered from, kept because the
    edges alone cannot say which of two overlapping tables drew a given
    boundary -- see `subgrid`.
    """
    page: int
    xs: tuple[float, ...]
    ys: tuple[float, ...]
    cells: dict[tuple[int, int], str]
    rules: tuple[Segment, ...] = ()

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

    def subgrid(self, xs: tuple[float, ...], tol: float) -> "Table | None":
        """The sub-table this component draws between the column edges `xs`.

        TWO TABLES THAT OVERLAP ON THE PAGE BECOME ONE COMPONENT. Rules are
        grouped by touching, and touching is the right test for a table drawn
        on its own -- but Word does not guarantee that two tables occupy
        disjoint areas. When a page break leaves a table's last rows at the top
        of the next page, the box of the table that begins that page is laid
        out over them: on sitrep 085 the provincial summary's national `Total`
        row is drawn from y=72 to y=91 and the alerts table's title box from
        y=87 to y=115, so the title box's top rule crosses the summary's
        column borders and the two grids union into a single component. That
        component's outer edges are the union of both tables' edges, so it no
        longer looks like a continuation of anything, and its column
        boundaries are both tables' boundaries interleaved -- `4 209` lands in
        a column whose centre is 17 pt from the summary's own cases column.
        Nothing caught this: the report simply reported five province rows and
        no national total, and the printed 4 209 / 1 916 / 45,5 % / 89 was
        lost.

        The rules say which table drew what, which the edges cannot. A
        horizontal rule running from `xs[0]` to `xs[-1]` was drawn by the table
        those edges describe, so the rows that table occupies here are the ones
        between its own outermost such rules, and its columns are `xs` rather
        than the component's. Cells are re-bucketed into `xs` by their centre,
        the same rule by which words were bucketed into cells in the first
        place.

        WHERE THE TWO TABLES OVERLAP, THE INK IS GENUINELY AMBIGUOUS and this
        cannot resolve it: the band between y=87 and y=102 lies inside both
        boxes, so the alerts title comes back as a row of this sub-table. It
        carries no number in any of the caller's value columns, and a row with
        no values is not a row -- which is the existing rule, not a new one.
        Attributing that ink would need to know what the words say, and this
        module knows only where they are.

        None when this component draws no rule spanning `xs`, which is the
        ordinary case: an unrelated table shares no boundary with the one the
        caller is asking about.
        """
        edges = [s for s in self.rules if s.horizontal
                 and abs(s.lo - xs[0]) <= tol and abs(s.hi - xs[-1]) <= tol]
        if len(edges) < 2:
            return None
        top, bottom = min(s.pos for s in edges), max(s.pos for s in edges)
        band = [i for i in range(self.nrows)
                if top <= (self.ys[i] + self.ys[i + 1]) / 2 <= bottom]
        if not band:
            return None

        cells: dict[tuple[int, int], str] = {}
        for (i, j), text in sorted(self.cells.items()):
            if i < band[0] or i > band[-1] or not text.strip():
                continue
            j2 = _bucket(list(xs), (self.xs[j] + self.xs[j + 1]) / 2, SNAP_X)
            if j2 is None:
                continue
            k = (i - band[0], j2)
            cells[k] = f"{cells[k]} {text}".strip() if k in cells else text
        if not cells:
            return None
        return Table(self.page, tuple(xs),
                     tuple(self.ys[band[0]:band[-1] + 2]), cells,
                     rules=tuple(edges))

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

        AN EMPTY ROW DOES NOT END THE HEADING. `Province /` and `Zone de santé`
        are two rows of one heading with a blank row between them on sitrep 080,
        because the heading cell is taller than its text. Treating the blank as
        a terminator stopped the block at `Province /`, and the table then
        failed to identify itself for want of the words `zone de santé` -- so a
        report whose grid reads perfectly returned only its province rows.

        TWO NUMBERS END THE HEADING, NOT ONE. A single number in a heading row
        is usually part of the title: from sitrep 083 the table's title is laid
        across the heading, and `Cas et décès confirmés par province et zone de
        santé (situation du 14 août 2026)` puts the bare `14` in a cell of its
        own. Ending the heading at the first number stopped it at row 0, the
        table lost its heading entirely and stopped identifying itself.

        A data row carries at least two numbers -- a count and a count. That is
        what separates it from a heading holding a date fragment, and it still
        terminates on the rows that matter: sitrep 080's `Ituri | 3 317 | 1 382`
        interleaved into its heading block has two.
        """
        n = 0
        for i in range(min(max_scan, self.nrows)):
            cells = [c for c in self.row(i) if c.strip()]
            if sum(1 for c in cells if _numeric(c)) >= 2:
                break
            if cells:
                n = i + 1
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


#: How far one filled rectangle may stick out of another and still count as
#: lying inside it. The shading boxes this separates are inset about 5 pt from
#: their cell on every side, so the test needs no slack to speak of; the
#: tolerance is here only for coordinates that agree to within rounding.
NEST_TOL = 0.5


def _nested(boxes: list[tuple[float, float, float, float]],
            tol: float = NEST_TOL) -> set[int]:
    """Indices of the filled rectangles that lie inside a LARGER filled rectangle.

    A filled rectangle is normally a cell body, and its four sides are that
    cell's borders -- which is why they are read as rules. A filled rectangle
    drawn INSIDE another one is not a cell; it is shading laid over part of a
    cell, and its edges are where the paint stops rather than where the table
    divides.

    The distinction is not academic. From sitrep 094 the province rows are
    printed on a coloured band, and Word draws that band as one filled box per
    cell PER PRINTED LINE, inset within the cell body. On a province row whose
    name fits one line every cell has one such box and they all share the same
    top and bottom, so they add two rules that coincide with nothing and change
    nothing. On a province row whose name WRAPS -- `Nord-Kivu` and `Haut-Uélé`,
    the only two names long enough -- the label cell gets two stacked boxes
    while the value cells keep their single vertically-centred one, and the
    value cells' box edges fall in the middle of the row: on sitrep 098 at
    y=168.7 and y=178.1 inside a row running 164.2 to 182.6.

    Those two edges run the width of the table, so they became row boundaries
    and cut the province row in half. `Nord-` kept the counts and `Kivu` was
    left alone in a row of its own, which carries no value and is therefore not
    a row -- so the tail was dropped and the province was published as a health
    zone called `Nord-`. Both provinces' totals left the province level and
    were double-counted at zone level, and sitrep 098's national identity
    failed by exactly their 680 + 165 = 845 cases.

    THE PAGE'S OWN BACKGROUND IS NOT A CONTAINER, and it has to be excluded by
    the caller before this runs. Some producers wash the whole page with a
    filled rectangle -- sitrep 099 carries one at 0,0 to 612.25,792.25 -- and
    it contains every cell on the page, so a containment test that admits it
    calls every cell shading and the grid disappears entirely. Which producer
    does this is not a property we can lean on: sitrep 098, the same vintage
    and the same layout, has no such rectangle.

    A BOX INSIDE A MERGED CELL IS THAT CELL'S ROW STRUCTURE, NOT PAINT, and
    this is the limit of the rule above. Where a label cell is merged down the
    page -- the early layout prints the province once against a cell spanning
    its zones -- the line boxes inside it are the only record of where one
    printed row ends and the next begins. Sitrep 080 draws `Province /`, `Zone
    de santé` and `Ituri` as three line boxes inside ONE cell running y=362.8
    to 413.6, while every other column divides that same span into cells at
    379.8 and 380.8. Suppressing those three boxes merged the heading's second
    line into the first data row, the heading block no longer said `zone de
    santé`, and the report matched no spec at all.

    So the question is not whether a box sits inside another box but whether
    the table has a row boundary THERE. A container that some other column
    divides is a merged cell, and its boxes are kept; a container that spans
    exactly one row of the table is a single cell, and its boxes are paint.
    That is decided from the cell bodies alone -- the boxes with no container
    of their own -- so it does not depend on the answer it is computing.
    """
    order = sorted(range(len(boxes)),
                   key=lambda i: ((boxes[i][2] - boxes[i][0])
                                  * (boxes[i][3] - boxes[i][1])), reverse=True)
    parent: dict[int, int] = {}
    for pos, i in enumerate(order):
        ax0, ay0, ax1, ay1 = boxes[i]
        for j in order[:pos]:                  # strictly larger by area
            bx0, by0, bx1, by1 = boxes[j]
            if (bx0 - tol <= ax0 and ax1 <= bx1 + tol
                    and by0 - tol <= ay0 and ay1 <= by1 + tol):
                parent[i] = j
                break

    # The horizontal edges of every CELL BODY -- a box no other box contains.
    edges = sorted(e for k in range(len(boxes)) if k not in parent
                   for e in (boxes[k][1], boxes[k][3]))
    out: set[int] = set()
    for i, j in parent.items():
        top, bottom = boxes[j][1], boxes[j][3]
        lo = bisect.bisect_right(edges, top + SNAP_Y)
        hi = bisect.bisect_left(edges, bottom - SNAP_Y)
        if lo >= hi:                           # nothing divides the container
            out.add(i)
    return out


#: How far a filled rectangle may fall short of the page and still be a wash
#: over the whole of it.
PAGE_TOL = 2.0


def _covers_page(obj, page, tol: float = PAGE_TOL) -> bool:
    """A filled rectangle spanning the page in both directions: a background wash."""
    x0, top, x1, bottom = page.bbox
    return (obj["x0"] <= x0 + tol and obj["x1"] >= x1 - tol
            and obj["top"] <= top + tol and obj["bottom"] >= bottom - tol)


def _segments(page) -> list[Segment]:
    """Every drawn rule on the page, from rectangles, lines and straight curves.

    Word emits borders as filled rectangles; `ilovepdf` re-encodes some of them
    as lines; a few pages carry them as two-point curves. All three are the same
    thing geometrically and all three appear in this corpus, so all three are
    read rather than assuming one producer.
    """
    objs = [*page.rects, *page.lines, *page.curves]
    bodies = [i for i, o in enumerate(objs)
              if o["x1"] - o["x0"] >= MIN_RULE and o["bottom"] - o["top"] >= MIN_RULE
              and not _covers_page(o, page)]
    shading = {bodies[k] for k in _nested(
        [(objs[i]["x0"], objs[i]["top"], objs[i]["x1"], objs[i]["bottom"])
         for i in bodies])}

    segs: list[Segment] = []
    for idx, obj in enumerate(objs):
        x0, x1 = obj["x0"], obj["x1"]
        y0, y1 = obj["top"], obj["bottom"]
        w, h = x1 - x0, y1 - y0
        if h < MIN_RULE <= w:
            segs.append(Segment((y0 + y1) / 2, x0, x1, True))
        elif w < MIN_RULE <= h:
            segs.append(Segment((x0 + x1) / 2, y0, y1, False))
        elif w >= MIN_RULE and h >= MIN_RULE:
            if idx in shading:
                continue          # paint inside a cell, not a cell of its own
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
#: the distance between genuinely separate tables. Measured end to end: at 30 pt
#: a DOUBLE-height row -- one whose name wraps, such as `Autres ZS (données non
#: ventilées)` -- is 32 pt tall and falls in the gap between two components,
#: taking its 94 unallocated Ituri cases with it. 36 pt bridges it.
COALESCE_GAP = 36.0


def _coalesce(segs: list[Segment], gap: float = COALESCE_GAP) -> list[Segment]:
    """Merge collinear pieces that lie on one line into single rules."""
    out: list[Segment] = []
    for horizontal in (True, False):
        axis = [s for s in segs if s.horizontal is horizontal]
        if not axis:
            continue
        axis.sort(key=lambda s: (s.pos, s.lo))
        # MEASURED FROM THE CLUSTER'S ANCHOR, NOT ITS LAST MEMBER. Comparing
        # against the previous element chains: on a dot-stippled page the
        # positions are dense enough that each is within tolerance of the next,
        # so every rule on the page collapses into one cluster spanning it.
        # Sitrep 083's Table 2 page carries 2,233 dots and 5,206 raw segments,
        # of which exactly 13 survived -- the table did not form at all and the
        # report read as having no zone table.
        cluster: list[Segment] = []
        anchor = 0.0
        tol = SNAP_Y if horizontal else SNAP_X
        for s in axis:
            if cluster and s.pos - anchor > tol:
                out.extend(_merge_run(cluster, horizontal, gap))
                cluster = []
            if not cluster:
                anchor = s.pos
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

#: A vertical piece shorter than this is not a cell's side. A dot is half a
#: point and a stippled page carries thousands of them; a cell side is a row
#: tall, twelve points or so here.
MIN_SIDE = 5.0

#: How many COLUMNS must stop their rule at one y before that y is taken for a
#: row boundary the page never drew. Two would be met by the two sides of a
#: single cell; three means the agreement crosses the table.
MIN_SIDE_SUPPORT = 3


def _implied_rows(segs: list[Segment], tol: float = SNAP_Y) -> list[float]:
    """Row boundaries the page states only by where its column rules stop.

    A ROW BOUNDARY IS NOT ALWAYS DRAWN. Word emits a cell's left border as its
    own object, so a column rule arrives as one piece per row, and `_coalesce`
    joins the pieces into the single rule the reader sees. That is right for
    the rule -- but the joins it dissolves are the only record of the row
    divisions on a page that draws no horizontal border between two rows.

    Sitreps 099 and 100 both end that way. Bas-Uélé's two health zones, Buta
    and Viadana, are separated by no horizontal rule at all; nine column rules
    stop and restart together at y=633.1 and nothing else marks it. The two
    rows fused, and the damage was not a missing row but a WRONG NUMBER: the
    fused cell reads `1 1`, and because a space is this source's thousands
    separator, `to_int` returned ELEVEN. Bas-Uélé's two cases were published as
    eleven and its province total missed by nine, on both reports.

    So the endpoints are kept where several columns agree on them. One column
    stopping proves nothing -- a rule is drawn in pieces for its own reasons --
    but three columns stopping at one y is the table dividing. Pieces shorter
    than `MIN_SIDE` are excluded so that a stippled page, whose every rule is a
    run of half-point dots, does not propose a row boundary every half point.
    """
    seen: list[tuple[float, float]] = []          # (y, x) of each piece's ends
    for s in segs:
        if s.horizontal or s.hi - s.lo < MIN_SIDE:
            continue
        seen.append((s.lo, s.pos))
        seen.append((s.hi, s.pos))
    if not seen:
        return []
    out: list[float] = []
    for y in _snap([y for y, _ in seen], tol):
        xs = {round(x / SNAP_X) for yy, x in seen if abs(yy - y) <= tol}
        if len(xs) >= MIN_SIDE_SUPPORT:
            out.append(y)
    return out


def tables(page, *, min_cols: int = MIN_COLS, min_rows: int = MIN_ROWS,
           gap: float = COALESCE_GAP) -> list[Table]:
    """Every table on one page, as a cell grid."""
    raw = _segments(page)
    implied = _implied_rows(raw)
    segs = [s for s in _coalesce(raw, gap) if s.hi - s.lo >= MIN_RUN]
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
        # Row boundaries this component states only by where its column rules
        # stop (see `_implied_rows`). Added INSIDE the component's own extent
        # only, and re-snapped, so one that coincides with a drawn rule merges
        # into it instead of splitting a row in two.
        inside = [y for y in implied if ys[0] + SNAP_Y < y < ys[-1] - SNAP_Y]
        if inside:
            ys = _snap(ys + inside, SNAP_Y)

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

        joined = {k: _join(v) for k, v in cells.items()}
        out.append(Table(page.page_number, tuple(xs), tuple(ys), joined,
                         rules=tuple(comp)))

    out.sort(key=lambda t: (t.ys[0], t.xs[0]))
    return out


#: How far two words' tops may differ and still be on one printed line. Lines
#: within a cell here are 9-12 pt apart, so this separates them with room to
#: spare while tolerating the sub-point jitter within a line.
LINE_TOL = 4.0


def _join(words: list[tuple[float, float, str]]) -> str:
    """A cell's words in reading order, rejoining a name broken at a line end.

    A NAME BROKEN ACROSS TWO LINES AT ITS HYPHEN MUST NOT GAIN A SPACE. Word
    wraps a label too long for its column, and it wraps at a hyphen the name
    already contains: `Nord-Kivu` prints as `Nord-` above `Kivu`,
    `Makiso-Kisangani` as `Makiso-` above `Kisangani`. Joining every fragment
    with a space published those as `Nord- Kivu` and `Makiso- Kisangani` --
    spellings the page does not print.

    For the health zones that was a transcription error carried into the panel
    (`zone_reported` is the name AS PRINTED, and it was not). For the provinces
    it changed the reading of the table: `Nord- Kivu` matches no province, so
    `level_of` filed Nord-Kivu and Haut-Uélé as health zones.

    `pdftotext` reading the content stream directly -- an independent extraction
    that never sees our geometry -- returns `NordKivu` and `MakisoKisangani`:
    one word, no space. That is the confirmation that the break is typography
    rather than content.

    The hyphen must end a LINE, not merely a word. Within one line a lone `-`
    is a "not reported" sentinel and a hyphen between words is a real one, and
    closing either gap would fuse text the source kept apart.
    """
    out: list[str] = []
    prev_top: float | None = None
    for top, _x, text in sorted(words):
        wrapped = (out and prev_top is not None
                   and top - prev_top > LINE_TOL and out[-1].endswith("-"))
        if wrapped:
            out[-1] += text
        else:
            out.append(text)
        prev_top = top
    return " ".join(out)


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
