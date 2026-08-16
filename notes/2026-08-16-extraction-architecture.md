# The extraction architecture

Date: 2026-08-16
Project: ebola-bdbv-data
Status: implemented, tested, and measured; 8 reports unread
Tags: architecture, pdf-extraction, table-geometry

## The one design decision everything follows from

**A heading identifies a table. It cannot index the table's columns.**

Word merges and centres heading cells, so a heading's text sits wherever its own
cell centres — which is not above the data column it labels. Sitrep 080's
heading block reads

    col0 `Province / Zone de santé`   col2 `Cas (n)`   col5 `Décès`  col6 `(n)`

while the data row beneath it is `Ituri | 3 317 | 1 382 | …`, cases in column 1.
Indexing by heading read every zone's death count as its case count.

Indexing by fixed position fails too: sitrep 090's table carries a leading
spacer column and the early layout carries two label columns.

So vocabulary answers *which table this is*, and geometry read from the **data
rows** answers *which column is which*.

## Layers

| Layer | File | Knows | Does not know |
| --- | --- | --- | --- |
| Geometry | `scripts/lib/pdftable.py` | PDF rectangles, lines, curves; turning drawn rules into a cell grid | French, Ebola, what any column means |
| Vocabulary | `scripts/lib/tablespec.py` | French headings; the left-to-right order each layout prints its quantities in | PDFs; what the numbers imply |
| Domain | `scripts/extract_zone_table.py` | Provinces, subtotals, unallocated rows, the page's own identity | Geometry |
| Aggregation | `scripts/aggregate_provinces.py` | The province carry, the closed province set, what must sum to what | How anything was read |

`pdftable` is project-agnostic and could be lifted out as a package. Its whole
public surface is `read(pdf) -> list[Table]`.

### Types

```python
# Layer 1 — geometry
@dataclass(frozen=True)
class Table:
    page:  int
    xs:    tuple[float, ...]          # column boundaries, ncols = len(xs) - 1
    ys:    tuple[float, ...]          # row boundaries
    cells: dict[tuple[int, int], str] # (row, col) -> text; absent means no ink
    def row(i) -> list[str]; def header_rows() -> int; def header() -> list[str]

def read(pdf: Path) -> list[Table]

# Layer 2 — vocabulary
class Role(StrEnum): ZONE; PROVINCE; CUM_CASES; CUM_DEATHS; LETALITY; …; IGNORED

@dataclass(frozen=True)
class TableSpec:
    name:     str
    requires: tuple[re.Pattern, ...]  # phrases the heading block must contain
    forbids:  tuple[re.Pattern, ...]  # phrases that rule this table out
    values:   tuple[Role, ...]        # LEFT-TO-RIGHT ORDER of the value columns

@dataclass(frozen=True)
class Mapped:                          # one PAGE, with its own columns resolved
    table: Table; roles: dict[Role, int]; labels: tuple[int, ...]

@dataclass(frozen=True)
class Resolved:  spec: TableSpec; pages: tuple[Mapped, ...]
```

### How a table is delimited

Not by a title — table numbers are not stable across reports, the same table
being Table 2, 4 or 5 by vintage. Word draws every border as a thin rectangle,
so rules are grouped by whether they touch (union-find over intersections) and
each connected component is one table.

**A rule drawn in pieces is one rule**, and this matters at two very different
scales. The macOS Quartz re-encoder stipples every rule into half-point squares
— 8,419 on one page of sitrep 026 — and a banded table draws its column rules
only inside shaded banner rows, leaving sitrep 018's borders in 94 disconnected
islands. Collinear pieces within 36 pt are joined before components form; a
coalesced run still shorter than 10 pt is dropped, which removes isolated dots
without removing the rules they compose. 36 pt rather than 30 because a
double-height row — one whose name wraps, like `Autres ZS (données non
ventilées)` — is 32 pt tall and otherwise falls in the crack, taking its 94
unallocated Ituri cases with it.

### How columns are indexed

`classify()` reads the data rows. A column whose non-empty cells are mostly
numbers is a value column; labels are the non-numeric columns to its left. A
sentinel (`ND`, an em-dash) counts as neither — a column that is mostly
em-dashes is still a value column, and calling it a label would shift every
later column one place.

Value columns are then zipped, left to right, against the spec's declared
`values` order. Order within a layout is stable even though *count* is not: the
daily block appears from 13 July and extends the sequence rather than reordering
it, so shorter tables stop early. That absorbs the spacer column and the
two-label case without a special case for either.

**Columns are mapped per page, not once per table.** On sitrep 090 the heading
page has ten columns and its continuation eight, because the title text laid
across the heading row creates boundaries the data rows do not have. Resolving
once on the head indexed the continuation wrongly; requiring an exact match
orphaned it and lost 61 rows. Per-page mapping is safe precisely because the
spec declares an order rather than indices.

### How pages are joined

Candidates are **ranked, not taken in order**. Heading vocabulary does not
single this table out and no tightening of it did: the provincial summary sits
above this table on the same page and states the same things about itself,
because it *is* a summary of it. Every phrase that excluded the summary also
excluded some vintage of the real table, since the title text bleeds across the
heading row into arbitrary cells. The difference that holds is structural — the
summary has one row per province, this table one per health zone — so candidates
are chained and the chain with the most data rows wins.

A continuation must be **headless, share both page edges within 8 pt, and be on
the next page**. All three are load-bearing. Extent alone linked the page-2
summary to the page-4 zone table to the page-7 laboratory table. The 8 pt
tolerance was tuned end to end: 10 pt takes province-reports reconciling from
198 down to 180, and an overlap-fraction test is worse still at 146, because
nearly every table spans most of the text width and containment scores a perfect
match. Sitrep 090's two pages begin 8.5 pt apart and are therefore left
unjoined — buying that one report costs eighteen others.

## Measured state

Against the reference `pdftotext` extraction, on the **64 reports where the
page's own arithmetic closes**:

| | |
| --- | --- |
| rows matched on (report, row name) | 2,353 |
| values disagreeing | **0** |
| reports returning rows | 74 of 82 |
| health-zone rows | 2,464 |

Aggregation: **218 of 238 province-reports reconcile**, 10 disagree, 10 print no
total to check against.

Tests: 58 passing, 1 strict xfail. Every case names the report it came from.

## What the tests found immediately

Writing them turned up three live defects, one of which no identity could catch.

**The thousands separator had been flattened.** `SPACES` is meant to hold ASCII
space, no-break space and narrow no-break space. It had become three ordinary
spaces — indistinguishable in any editor or diff — so every count of a thousand
or more printed with a no-break separator was rejected. Now written as escapes.

**An empty row was ending the heading.** `Province /` and `Zone de santé` are
two rows of one heading with a blank between them. The scan stopped at the
blank, the heading truncated to `Province /`, and the table failed to identify
itself — sitrep 080 returned five province rows and no zones. Fixing it took
province-reports reconciling from 198 to 221.

**The early layout was being read as the cumulative one.** This is the one worth
remembering. Dropping the letality requirement let the cumulative spec match the
early table, so sitrep 005's Mongbwalu was recorded with **309 confirmed cases
where the page prints 309 suspected and 13 confirmed**. The figures were
plausible, the columns internally consistent, and the page's own arithmetic
closed — the whole table had simply been read one concept to the left. Nothing
in the pipeline could see it.

The rule that follows: **each relaxation of the heading vocabulary has to be
paid for with a discriminator.** Sitrep 091, whose heading names no case column
at all, is left unread and marked strict-xfail rather than bought with another
relaxation.

## What is left

**Eight reports unread.** Sitreps 12, 14 and 16 print no zone table anywhere —
a source fact, and the reference route returns nothing for them either. Sitrep
15 and 83–86 are live gaps; 83–86 are the vintage that lays narrative prose
across the heading row.

**Ten province disagreements.** Two kinds. Sitreps 20, 33, 90 and 91 recover
only a fragment of their table — ours, and the same class as the unread reports.
Sitreps 34 (+1), 53 (+5), 55 (−3) and 81 (−2 deaths) are the size the reference
pipeline carries as hand-verified exceptions after a page read. That register
mechanism is not ported yet, and should be: a residual that has been read and
understood is a different object from one that has not.

**Not yet built**, and deliberately downstream: zone alias resolution, the
rejected-values register, and the weekly stream construction the models consume.

## Interface

```
make check    # networked: is the archive current, and has the source moved?
make fetch    # networked: fetch anything new
make verify   # every held PDF hashes to what the manifest records
make build    # PDFs -> zone extraction -> province aggregation
make test
```

`build` stops with exit 2 if a province total disagrees with the sum of its
parts, exit 1 if a report printed no total to check against. Nothing is clipped,
dropped or repaired: a province that does not reconcile is written out flagged,
and zone rows that carry no province at all are named on stderr.
