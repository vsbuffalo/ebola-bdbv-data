# How the extraction works

## Read the drawn rules, not the text

The situation reports are Microsoft Word exports, and Word draws every table
cell border as a vector rule. This pipeline reads those **drawn rules** rather
than a text rendering of the page: a cell's row and column are given by the
document, not inferred from character offsets, so a health-zone name too wide
for its column stays one row and an empty cell stays empty instead of shifting
its neighbours left.

One design decision carries the rest: **a heading identifies a table; it cannot
index the table's columns.** Word centres heading text over merged spans, so
`Cas (n)` routinely sits above the wrong data column — trusting it once read
every zone's death count as its case count. So headings (declared per layout in
`scripts/lib/tablespec.py`) decide *which table this is*, and columns are
indexed from the **data**: the numeric columns, left to right, zipped against a
declared order. Order is stable within a layout even when the column count is
not.

Three code layers, strictly separated:

| Layer      | File                                                                                          | Knows                                                  | Does not know      |
| ---------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------ |
| Geometry   | `scripts/lib/pdftable.py`                                                                     | rects, lines, dot-stippled borders → a cell grid       | French, Ebola      |
| Vocabulary | `scripts/lib/tablespec.py`                                                                    | French headings; each layout's column order            | PDFs, epidemiology |
| Domain     | `scripts/extract_zone_table.py`, `scripts/aggregate_provinces.py`, `scripts/build_streams.py` | provinces, subtotals, unassigned pools, the identities | geometry           |

## The routes

Not every report prints the same thing, so there are several extraction routes,
and every held report is covered by the finest one its pages print:

| Route                               | What it reads                                                                                                                                                                                                                          |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| zone table (three declared layouts) | cumulative cases and deaths per health zone; from 13 July the daily community/treatment-centre death split                                                                                                                             |
| zone daily table                    | sitrep 087 prints only the day's flows per zone, no cumulative anywhere — a fourth layout with its own declared column order                                                                                                           |
| provincial summary                  | one row per province — the only tabular data on the reports whose vintage dropped the zone table                                                                                                                                       |
| prose sentence                      | `"121 cas dont 110 en Ituri, 10 au Nord-Kivu et 1 au Sud-Kivu"` — read only because the sentence checks itself                                                                                                                         |
| national dashboard (page-1 tiles)   | the isolation census, cumulative recoveries and cumulative confirmed deaths. The suspected-case tile is deliberately not read: it is a running total, a stock and a daily flow in three vintages under near-identical wording          |
| prose pillars                       | the care ledger (admissions, exits, census, beds), the laboratory paragraph (tests and positives, licensed by the sentence's own printed positivity) and the safe-burial alerts, each refusing any sentence whose numbers do not check |
| onset figure                        | the symptom-onset bar chart, read from its pixels, each vintage gated against its own printed total and its neighbours                                                                                                                 |

The source's own caveats are read too: the first six weeks' reports footnote
their headline cumulative as undergoing harmonisation — from 9 June stating
outright that it omits confirmed cases still in the community and escapees, so
an undercount — and sitrep 011 footnotes the deaths as underestimated. One row
per statement in `provisional_caveat.csv`.

## What each lineage carries

Three machine-readable renderings of the INSP reports exist. This is what each
one holds, and it's why the comparison in [validation](validation.md) can only
run where coverage overlaps. The bold rows are the series no other lineage has.

| Series                                              | this repository                                                                                       | INRB-UMIE transcription                                             | epiforecasts scan                                    |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------- |
| cumulative confirmed cases and deaths               | health zone, every held report                                                                        | health zone, to its pinned commit                                   | national only                                        |
| daily new confirmed cases (24 h)                    | zone table and provincial summary                                                                     | zone, sparse                                                        | —                                                    |
| **daily community vs treatment-centre death split** | **province rows and zone breakdown, from 13 July**                                                    | **absent**                                                          | —                                                    |
| suspected cases and deaths (early vintage)          | zone; stock and flow kept as distinct roles                                                           | zone, sparse                                                        | —                                                    |
| province-level series                               | built from zone rows, checked against every printed province row                                      | none — zone or national only                                        | —                                                    |
| national cumulative                                 | via zone, summary and prose routes                                                                    | separate national files, including sitreps 001–004 (the first week) | cases for the reports it covers, with revision notes |
| the source's own caveats                            | per report, three kinds                                                                               | —                                                                   | partly, in free-text notes                           |
| **daily testing volume and positives**              | **licensed province-days from the laboratory prose**                                                  | free-text transcription only                                        | —                                                    |
| **care ledger**                                     | **census, admissions and exits per province from the care prose, each row's arithmetic checked**      | —                                                                   | —                                                    |
| model-ready streams                                 | one TSV per quantity × place × resolution; `data/build/streams/README.md` lists them for each release | —                                                                   | —                                                    |
