# The extraction architecture

Date: 2026-08-16
Project: ebola-bdbv-data
Status: all 83 held reports contribute data; 3 residuals open
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
| rows matched on (report, row name) | 2,403 |
| values disagreeing | **0** |
| reports returning rows | 74 of 82 |
| health-zone rows | 2,514 |

Aggregation: **226 of 247 province-reports reconcile**, 7 carry a verified
exception, 4 disagree, 10 print no total to check against.

Tests: 73 passing, 1 strict xfail. Every case names the report it came from.

## The exception register

`data/raw/reconciliation_exceptions.tsv` holds judgements about specific
documents. An entry asserts: *I opened this page, added the printed rows, and
the source does not agree with itself.* Seven entries so far, each read against
the rendered page before being written.

Three design properties make it a record rather than a mute button.

**Keyed on the PDF's SHA-256, not the report number.** INSP revises reports and
republishes under the same number; a hash mismatch stops the build, so a
corrected report returns to the failing set instead of inheriting the exception
its predecessor was granted.

**`expected_gap` is exact.** An entry licenses one residual, not a report. If
our reading changes the number, the report fails again.

**Unverifiable means refused.** Without the archive the hashes cannot be
checked, so the register is rejected outright rather than applied on trust: an
exception not tied to a document is a suppression.

The strongest entry is sitrep 059, where the page explains its own gap. The note
beneath its zone table reads *"Ituri : la répartition cumulée par zone de santé
correspond à la dernière distribution consolidée (10/07) ; le total provincial
(1 772 cas / 608 décès) est le cumul du 12/07, l'écart avec la somme des ZS
reflétant les cas et décès accumulés depuis cette distribution"* — the zone rows
are the 10 July distribution and the province row the 12 July cumulative. Where
an entry infers rather than quotes, it says so: the same report's Nord-Kivu and
Tshopo gaps have the same shape, but the note names only Ituri.

## What the tests found

Writing them turned up four live defects, one of which no identity could catch.

**The early layout was being read as the cumulative one.** Dropping the letality
requirement let the cumulative spec match the early table, so sitrep 005's
Mongbwalu was recorded with **309 confirmed cases where the page prints 309
suspected and 13 confirmed**. Figures plausible, columns internally consistent,
page arithmetic closing — the whole table had been read one concept to the left.
The rule that follows is now in the code: *each relaxation of the heading
vocabulary has to be paid for with a discriminator.*

**The thousands separator had been flattened** from ASCII + no-break + narrow
no-break to three ordinary spaces, invisible in any diff, rejecting every count
of a thousand or more with a no-break separator. Now written as escapes.

**An empty row was ending the heading**, truncating `Province / Zone de santé`
to `Province /` so the table failed to identify itself. Sitrep 080 returned five
province rows and no zones. Fixing it took province-reports reconciling from 198
to 221.

**A numbered row was not a row.** Some reports print `1- Bunia`, `2- Rwampara`;
the name test required a letter first, so sitrep 020 kept five rows out of
twenty-eight and Ituri came up 265 cases short.

## Approaches tried and reverted, with the cost of each

- **Overlap-fraction page matching** instead of two-edge: 146 province-reports
  against 216. Nearly every table spans most of the text width, so containment
  scores a perfect match.
- **Edge tolerance of 10 pt** instead of 8: measured 180 reconciling against
  198 — and that conclusion was WRONG. Two defects elsewhere (a heading
  truncated by an empty row, and numbered rows discarded) were doing the damage
  and the looser tolerance was being blamed. With both fixed, 10 pt gives 238
  against 226 and is now the value in use. A tuning parameter measured against
  a buggy pipeline gives the wrong answer confidently.
- **Forbidding `Zones de santé touchées`** to exclude the provincial summary:
  gains two reconciling province-reports, loses four whole reports, because the
  phrase also lands in this table's own heading where the title bleeds.
- **Requiring the LABEL column specifically to name a zone** — the precise form
  of the same discriminator: costs 55 reconciling province-reports, because
  label headings are too often truncated.

What worked instead was comparing the label heading between two candidates
before chaining them, which separates a table from its own summary without
forbidding any vocabulary.

## What is left

**All 83 held reports now contribute case data, by the finest route each one
prints.** 77 carry a per-zone table and all 77 are read. Sitreps 084–086, whose
vintage dropped the zone table, and 033, whose zone data is narrative, are
covered at province level by the provincial-summary route. Sitreps 012 and 016
print their breakdown only in a prose sentence and are read by a route built for
exactly that sentence — which is safe because the sentence checks itself, a
total and its parts, and a breakdown that does not close is refused whole.
Sitrep 014 states only a national cumulative, so that is what it contributes:
`national_only` is what the page says, not a gap in the reading.

The provincial summary also runs on every report that has one (70 of 83) as an
independent within-document check: where it and the zone-derived sums both
exist they agree exactly on 57 of 66 reports, and most of the differences are
already in the exception register at the same values.

Three layouts are in use, and each is a declared spec rather than a code path:

| Spec | Reports | What it carries |
| --- | --- | --- |
| `zone_cumulative` | 68 | cumulative confirmed cases and deaths, letality, and from 13 July the daily ascertainment block |
| `zone_early` | 8 | suspected cases and deaths, confirmed cases, contacts — no letality, no cumulative deaths |
| `zone_mixed` | 1 | both at once: new suspected, new confirmed, THEN cumulative cases and deaths |

The mixed layout is the reason order is declared rather than inferred: `Nouveaux
cas confirmés` and `Cumul de cas Confirmés` are adjacent columns and only their
sequence tells them apart.

**Three residuals open**, all ours. Sitrep 033 recovers one part of Ituri; 083
and 089 are each one death short.

**Not yet built**, deliberately downstream: zone alias resolution, the
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
