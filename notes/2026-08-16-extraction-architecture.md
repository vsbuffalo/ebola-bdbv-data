# The extraction architecture

Date: 2026-08-16
Project: ebola-bdbv-data
Status: implemented and measured; identification incomplete on 11 reports
Tags: architecture, pdf-extraction, table-geometry

## The one design decision everything follows from

**A heading identifies a table. It cannot index the table's columns.**

Both halves of that were learned by getting them wrong.

Word merges and centres heading cells, so a heading's text sits wherever its own
cell centres — which is not above the data column it labels. Sitrep 080's
heading block reads

    col0 `Province / Zone de santé`   col2 `Cas (n)`   col5 `Décès`  col6 `(n)`

while the data row beneath it is `Ituri | 3 317 | 1 382 | …`, with the cases in
column 1 and the deaths in column 2. Indexing by heading read every zone's death
count as its case count, on every report of that vintage.

The other direction fails too. Indexing by fixed position — name at 0, cases at
1, deaths at 2 — breaks on sitrep 090, whose table carries a leading spacer
column, and on the early layout, which carries two label columns (`Provinces`
and `Zones de santé`).

So the two jobs take different evidence. Vocabulary answers *which table this
is*. Geometry, read from the data rather than the heading, answers *which column
is which*.

## Layers

| Layer | File | Knows | Does not know |
| --- | --- | --- | --- |
| Geometry | `scripts/lib/pdftable.py` | PDF rectangles, lines, curves; how to turn drawn rules into a cell grid | French, Ebola, what any column means |
| Vocabulary | `scripts/lib/tablespec.py` | French headings; the order each layout prints its quantities in | PDFs; what the numbers imply |
| Domain | `scripts/extract_zone_table.py` | Provinces, subtotals, unallocated rows, the reconciliation identity | Geometry |

`pdftable` is genuinely project-agnostic and could be lifted out as a package.
It is 300 lines and its whole public surface is `read(pdf) -> list[Table]`.

### Types

```python
# Layer 1 — geometry
@dataclass(frozen=True)
class Table:
    page:  int
    xs:    tuple[float, ...]          # column boundaries, ncols = len(xs) - 1
    ys:    tuple[float, ...]          # row boundaries
    cells: dict[tuple[int, int], str] # (row, col) -> text; absent means no ink

    def row(i)         -> list[str]
    def header_rows()  -> int         # leading rows that are heading, not data
    def header()       -> list[str]   # per column, wrapped fragments joined

def read(pdf: Path) -> list[Table]

# Layer 2 — vocabulary
class Role(StrEnum):
    ZONE; PROVINCE; CUM_CASES; CUM_DEATHS; LETALITY; NEW_CASES
    DEATHS_COMMUNITY; DEATHS_CTE; DEATHS_TOTAL; SUSPECTED; …; IGNORED

@dataclass(frozen=True)
class TableSpec:
    name:     str
    requires: tuple[re.Pattern, ...]  # phrases the heading block must contain
    forbids:  tuple[re.Pattern, ...]  # phrases that rule this table out
    values:   tuple[Role, ...]        # LEFT-TO-RIGHT ORDER of the value columns

@dataclass(frozen=True)
class Resolved:
    spec:   TableSpec
    roles:  dict[Role, int]           # role -> column index
    labels: tuple[int, ...]           # label columns, outermost first
    tables: tuple[Table, ...]         # the head and its continuation pages

def classify(table, *, start) -> tuple[list[int], list[int]]   # labels, values
def select(tables, spec)      -> Resolved | None
```

### How a table is delimited

Not by a title and a terminator. Word draws every border as a thin rectangle, so
rules are grouped by whether they touch — a union-find over rule intersections —
and each connected component is one table with its own row and column edges.
That removes the title-regex-plus-lookahead-plus-terminator mechanism whose
failure twice ran the read on into the alerts table and returned its figures as
case counts.

Table numbers are not stable across reports (the same table is Table 2, 4 or 5
by vintage), which is why the title was never a safe key in the first place.

### How columns are indexed

`classify()` reads the *data* rows. A column whose non-empty cells are mostly
numbers is a value column; label columns are the non-numeric ones to its left.
A sentinel meaning "not reported" (`ND`, an em-dash) counts as neither — a
column that is mostly em-dashes is still a value column, and calling it a label
would shift every later column one place.

The value columns are then zipped, left to right, against the spec's declared
`values` order. Column *order* within a layout is stable even though the column
*count* is not: the daily ascertainment block appears from 13 July and extends
the sequence rather than reordering it, so a shorter table simply stops early.
This is what survives the vintages that a fixed index cannot, and it absorbs the
leading-spacer and two-label-column cases without a special case for either.

### How continuation pages work

The table is printed across two pages in most vintages — province rows on the
first, health zones on the second — and some vintages repeat the heading while
others do not. So a continuation is found by **column geometry**: a later table
whose column boundaries coincide with the head's is the same table continued.
Roles are resolved once and inherited, which is what makes a headingless
continuation page readable at all.

The head is the first candidate that both identifies *and* classifies. Requiring
both matters in each direction. Choosing the largest candidate made page two the
head and dropped page one, so sitrep 060 lost 1,808 of its 2,011 cases. Choosing
the first that merely identifies picked up stray caption fragments whose few
words satisfy the required phrases while holding no data, which rejected 30 of
82 reports.

## Where the failure classes went

Every failure in the first trial run was a table-selection failure, and each one
turned out to be an instance of the same root cause — column roles assumed by
position. What they looked like:

| Symptom | Reports | Cause |
| --- | --- | --- |
| Residual exactly ×2 the printed total | 13, 15, 21–32 | `Sous total Ituri` rows counted as zones as well as being the province total |
| Residual exactly +17 on 15 consecutive reports | 34–68 | unallocated rows added at national level, where they are already inside a province's total |
| Residual ≈ −1,800 | 60, 61, 62, 67 | both pages headed; the larger was taken as head, dropping the province page |
| Wrong values entirely (Bunia 35 against a printed 967) | 83 | the per-zone *outcomes* table selected instead — same heading vocabulary, plus `Guéris` and `En hospitalisation` |
| No columns resolved | 40–58 | the table's title is laid out across the heading row, so the heading cell reads `Tableau 2. Répartition … Province / Zone de santé` |
| Every heading truncated to `Nbre de`, `Zones de` | early layout | the heading block spans six rows; the scan cap was four |
| `cum_deaths` absent from the output entirely | all 82 | rows from two specs carry different keys, and the frame took its schema from whichever report sorted first |

The last one is worth naming separately: it was silent. The column simply was
not in the CSV, and nothing failed. The fix is a declared schema, and the
general rule is that a column absent from a table is not missing data — it is a
quantity that table does not report, and null says so.

## Measured state

Against the reference extraction (`sitrep_table2.csv` from the `pdftotext`
parser), on the **52 reports where the page's own arithmetic closes**:

| | |
| --- | --- |
| rows matched on (report, row name) | 1,638 |
| values disagreeing | **0** |
| level classification agreeing | 1,638 / 1,638 |
| rows only in the reference | 53 |
| rows only in the geometric read | 79 |

Reports returning rows: 71 of 82, against the reference's 63. Identity closes on
52, is not checkable on 13 (no printed total in the rows recovered), and fails on
6.

## The 11 unidentified reports, one by one

Each was diagnosed by measuring what geometry the page actually carries, and
they fall into four classes with nothing ambiguous between them. Two of the four
are not defects.

| Class | Reports | What the page carries | Fix |
| --- | --- | --- | --- |
| A. No zone table exists | 12, 14, 16, 17 | no `Province / Zone` heading anywhere in the document | none — a source fact. The reference route also returns nothing at zone level for all four. |
| B. Zone data is in prose | 33 | narrative text, no table | none here — this is the prose route's job. The reference recovers 37 rows from narrative. |
| C. No vertical rules | 18, 19, 20 | horizontal rules and row shading only; columns set by text alignment | rows from the horizontal rules, columns by clustering word x-positions |
| D. Borders drawn as dots | 26, 28 | ~8,400 rectangles of 0.5 × 0.5 pt, stippled along every rule | coalesce collinear runs of dots into segments before filtering |
| E. Narrative in the heading row | 89 | a correct grid; the heading holds three paragraphs of summary prose | identify structurally rather than by vocabulary |

Class A is the handoff's claim that some reports print no zone data in any form,
independently confirmed. Class B is the layering working as designed: a table
reader should return nothing for a document that prints no table.

**Class C** is the real limitation, and worth stating plainly: the geometric
approach assumes a table is ruled on both axes. Sitrep 018's table is *banded* —
alternating row shading with horizontal rules and no column separators at all.
The producer is `ilovepdf.com` for 018 and macOS Quartz for 020, so this
travels with the re-encoding rather than with the vintage. The fix is a hybrid
that keeps the part geometry answers well: rows still come from the horizontal
rules, so a wrapped zone name is still one row, and only the column boundaries
are inferred from text alignment. That is strictly better than the character-grid
approach, which has to infer both.

**Class D** is a pure geometry fix and should be done first — it is the cheapest
and it is entirely inside `pdftable`. Nothing about the table changed; the
re-encoder simply replaced each ruled line with a row of dots, and a run of
collinear dots is a rule.

## On using vision models to resolve these

Worth saying why I would not, for extraction.

Every one of the eleven turned out to be mechanically diagnosable — the page
either carries a grid or it does not, and measuring `len(rects)` by shape said
which in one pass. None of them needed a model to look at a picture. Having
found that out, adding a non-deterministic step to resolve cases that a
deterministic one already explains would be the wrong trade: a released data
artefact has to rebuild byte-identically, and a panel of model reads does not.
Agreement between several models is also weaker evidence than it appears — they
are not independent of each other, and all of them are reading the same document,
which is the same objection that applies to comparing our extraction against
INRB's.

There is a genuinely independent check available and it is deterministic. 67 of
the 82 reports carry a tagged structure tree with real `/Table`, `/TR`, `/TH`
and `/TD` markup — sitrep 080 declares 13 tables, 163 rows and 782 data cells.
That is the document author's own statement of which cell belongs to which row
and column, and comparing it against the grid we infer from drawn borders is two
genuinely different claims about the same page. Where they disagree, one is
wrong in a way neither can conceal. Harvesting the text per cell needs
marked-content mapping through the page content stream, which no mainstream
Python library does out of the box, so it is a day of work rather than an
afternoon — but it is the right cross-validation, and it is reproducible.

Where a vision model does earn its place is as a *triage* instrument on new
vintages: point it at a page and ask what changed, so the spec can be written.
That is a development aid, not a pipeline step, and nothing it produces gets
committed.

## What is left

**Identification on 11 reports** — 12, 14, 16, 17, 18, 19, 20, 26, 28, 33, 89.

**The 083+ vintage** prints prose into the heading row: sitrep 089's first
heading cell contains three paragraphs of narrative summary interleaved word by
word with the column names. Reports 90–92 currently resolve to the provincial
summary rather than the zone table and return 6–7 rows instead of ~60. This is
the hardest remaining case and probably wants a `forbids` pattern on narrative
length rather than more vocabulary.

**Six identity failures**, and they are not all ours. Sitreps 53 (−5) and 57
(+5) are small residuals of the kind the reference pipeline carries as
hand-verified exceptions — the page's own arithmetic does not close, and the
register records that as a claim about the document. Sitrep 48 (+1,333) and
90/92 (−119, −136) are ours.

**Not yet built**, and deliberately downstream of this: alias resolution, the
province carry, the exception and rejected-value registers. Those are claims
about the outbreak and its sources rather than about the page, and they belong
to steps that can be audited on their own.

## Interface

```
uv run python scripts/extract_zone_table.py \
    --pdfs data/raw/sitrep_pdfs \
    --out  data/build/series/zone_table.csv
```

Writes the trunk CSV and a `_status.csv` sibling carrying, per report: the
status, the row count, which spec matched, the identity verdict, the printed
total, the summed parts, the residual, and the basis the identity was taken on.
`--spec` restricts to named specs in order of preference, which is how a single
layout can be re-run in isolation while debugging one.
