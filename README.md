# ebola-bdbv-data

A reproducible, automated extraction layer for the 2026 DRC Bundibugyo virus
outbreak. This pipeline processes the raw INSP situation-report PDFs to
analysis-ready, per-health-zone case series. Every step a build (`make`)
target, every number checked against the page that printed it.

The companion modelling repository consumes seven small TSVs from this one
(`data/build/streams/`); three more, for Haut-Uélé, are built and waiting on a
modelling decision. Everything else here exists to make those files
trustworthy, and to show the work.

## The approach

The situation reports are, at heart, ledgers: almost every table prints its
totals beside the parts they summarise — health-zone rows beneath a province
row, province rows above a national total. This pipeline takes an
**accounting-based approach**: no number is accepted merely because it parsed;
a number is accepted because the books balance around it, and a number the
books reject is investigated, not repaired. The pipeline's approach is roughly:

- **Read the drawn geometry, not the text.** Word draws every table cell as a
  vector rule; cells are read from those rules, so a wrapped name stays one
  row and a blank cell stays blank instead of shifting its neighbours.
- **Balance every page's books.** Health zones plus the source's unassigned
  pool must equal the printed province row; provinces must equal the printed
  national total; the same check runs over the daily death-split columns. A
  page that fails is a build failure, not a warning.
- **A discrepancy is a finding, never noise.** Where a page genuinely does
  not add up — the source disagreeing with itself — a human reads it and the
  judgement is recorded in a register, keyed to the document's SHA-256 and
  licensing exactly one residual. A revised document, or a gap that moves,
  voids its own excuse.
- **Check against independent readings.** Every zone-day is compared against
  INRB-UMIE's manual transcription and every national total against the
  epiforecasts scan, with disagreements recorded rather than resolved.
- **Reproducible and current.** The archive is fetched same-day and pinned by
  a hash manifest; every build artefact has a rule; a rebuild is
  byte-identical; the rendered documents refuse to embed anything the
  pipeline did not produce.

And what these files carry that no other machine-readable rendering of the
reports does (the full lineage-by-lineage table is below):

- **The ascertainment split** — each day's confirmed deaths divided into
  community versus treatment-centre, the series the ascertainment models fit.
  Absent from every other lineage.
- **Province-level series that are *derived*, not transcribed** — built from
  the zone rows and checked against every printed province row, so a missed
  row is a loud failure instead of a quiet undercount.
- **The source's own caveats as data** — the harmonisation footnotes
  declaring the early cumulative an undercount, per report, in three kinds.
- **Model-ready weekly streams** — observation times and counts shaped for an
  accumulate-between-observations likelihood, every stream ending at an
  exactly-zero gap against the source's cumulative movement.

## Why this much care

The quantity the models most need from these reports is not the case count, it
is the _fraction of confirmed deaths found in the community rather than in a
treatment centre_, the closest thing the source prints to a measurement of how
much transmission the surveillance system is missing.

In mid-August, a plausible-looking extraction of that fraction read **1.00**
for the most recent week — every death found in the community, isolation
effectively over. But a closer inspection of the pages shows they print
**0.55**. The mechanism of this disagreement was small, subtle, entirely
silent: on four consecutive reports the zone table breaks across a page,
the first page carries too few rows for a column-detection heuristic, and
one column's values slid into their neighbour. Every surviving row then had
community deaths equal to total deaths _by construction_. Nothing looked
wrong from outside — the values were plausible integers, every cumulative
total still balanced, and the emitted series didn't jump but _climbed_,
over six weeks, exactly the way a real signal of collapsing isolation
would. The error was caught one way only: by summing each page's daily
columns against the totals the same page prints. An epidemiological
conclusion of the first order — _isolation has collapsed_ — would have been
a parsing artifact, at maximum leverage on the most recent data.

That is the failure class this repository is built against. The stream files
are small; the claim that they say what the source said is the product.

## Running it

```sh
make check      # is the archive current, and does the source still look the same?
make fetch      # NETWORKED: fetch the index and any new PDFs
make build      # OFFLINE: PDFs -> zone extraction -> province aggregation
make streams    # OFFLINE: the weekly observation series the models fit
make figures    # OFFLINE: the EDA figures
make compare    # ours vs the two other extraction lineages (see `make external`)
make doc        # render analysis/data.html + explore.html, fail-closed
make serve      # serve both pages (default port 8790; PORT=n to override)
make test       # the tests, each pinned to a named report
```

Two rendered pages, both self-contained single files:

- **`data.html`** — the document of record: what exists, what reconciles, and
  every number read from an artefact at render time.
- **`explore.html`** — the interactive companion: shared province/log/caveat
  controls, per-report hover provenance on every mark, the per-stream flow grid,
  reporting-noise diagnostics, and a searchable report index.

`make serve` starts a detached `http.server` on port 8790 (it checks the port
first and tells you if something else holds it). After a re-render the pages
update in place — refresh the browser, no restart needed.

**Run `make check` first.** It is the only step that looks _outward_ — every
other check asks whether the reports we hold are internally consistent, and none
of them can ask whether we hold the reports that _exist_. The reference project
once sat eleven days behind the source with every internal check green, because
the site renamed the series and the query silently stopped matching.

| exit | meaning                                                                      | what to do                      |
| ---- | ---------------------------------------------------------------------------- | ------------------------------- |
| 0    | `CURRENT` — we hold everything the source lists                              | nothing                         |
| 1    | `BEHIND` — new reports published                                             | `make refresh`                  |
| 2    | `CHANGED` — the source moved under us                                        | **look first**                  |
| 3    | `UNREACHABLE` — the API did not answer                                       | retry                           |
| 4    | `STALE` — current, but the source has published no situation report for days | worth knowing; nothing to fetch |

`make build` touches no network, so a rebuild can never silently acquire
different inputs. Everything under `data/build/` is regenerable from the
committed inputs; delete it and `make build` returns it byte-identically.

### The modelling contract

The eleven files of `data/build/streams/` — ten stream TSVs plus `meta.json`
(whose `population` and `day0` fields are read too) — are vendored by the
modelling repository, pinned to a commit of this one and verified by
per-file sha256 against a byte-identical rebuild. That makes their shape a
**contract, not an implementation detail**: file renames, column changes,
and the `uganda_exports` convention (cumulative counts at bulletin dates,
deliberately unlike the weekly-incidence streams beside it) are coordinated
changes, announced across both repositories — never refactors. Releases are
tagged `data/<data-date>` (the newest report's data date), gated on: every
accounting identity holding, the comparison figures rendering, and
`make check` returning current-or-behind. A re-release whose newest data
date is unchanged — a mid-series report the source listed late, a register
judgement revised — appends `-r2`, `-r3`, …

## How the extraction works

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
`scripts/lib/tablespec.py`) decide _which table this is_, and columns are
indexed from the **data**: the numeric columns, left to right, zipped against a
declared order. Order is stable within a layout even when the column count is
not.

Three code layers, strictly separated:

| Layer      | File                                                                                          | Knows                                                  | Does not know      |
| ---------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------ |
| Geometry   | `scripts/lib/pdftable.py`                                                                     | rects, lines, dot-stippled borders → a cell grid       | French, Ebola      |
| Vocabulary | `scripts/lib/tablespec.py`                                                                    | French headings; each layout's column order            | PDFs, epidemiology |
| Domain     | `scripts/extract_zone_table.py`, `scripts/aggregate_provinces.py`, `scripts/build_streams.py` | provinces, subtotals, unassigned pools, the identities | geometry           |

### The routes

Not every report prints the same thing, so there are four extraction routes, and
every held report is covered by the finest one its pages print:

| Route                               | Reports | What it reads                                                                                                                |
| ----------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------- |
| zone table (three declared layouts) | 74      | cumulative cases & deaths per health zone; from 13 July the daily ascertainment split                                        |
| zone daily table                    | 1       | sitrep 087 prints only the day's flows per zone, no cumulative anywhere — a fourth layout with its own declared column order |
| provincial summary                  | 70      | one row per province — the only tabular data on the reports whose vintage dropped the zone table                             |
| prose sentence                      | 3       | `"121 cas dont 110 en Ituri, 10 au Nord-Kivu et 1 au Sud-Kivu"` — read only because the sentence checks itself               |
| _(national dashboard)_              | —       | not yet read; the daily suspected inflow after 12 July is the known gap                                                      |

The source's own caveats are read too: the first six weeks' reports footnote
their headline cumulative as undergoing harmonisation — from 9 June stating
outright that it omits confirmed cases still in the community and escapees, i.e.
is an undercount — and sitrep 011 footnotes the deaths as underestimated. One
row per statement in `provisional_caveat.csv`.

### What each lineage carries

Three machine-readable renderings of the INSP reports exist; this table is what
each one holds, and it is why the comparison below can only run where coverage
overlaps. The bold row is the series no other lineage has — and the one the
ascertainment models fit.

| Series                                              | this repository                                                             | INRB-UMIE transcription                                                                                 | epiforecasts scan                         |
| --------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| cumulative confirmed cases                          | health zone; all 83 held reports, same-day (15 Aug)                         | health zone; ends 11 Aug                                                                                | national only                             |
| cumulative confirmed deaths                         | health zone, from 29 May                                                    | health zone                                                                                             | —                                         |
| daily new confirmed cases (24 h)                    | zone table + provincial summary column                                      | zone, sparse (212 zone-days)                                                                            | —                                         |
| **daily community vs treatment-centre death split** | **province rows + zone breakdown, from 13 Jul — the ascertainment streams** | **absent**                                                                                              | —                                         |
| suspected cases & deaths (early vintage)            | zone; stock and flow kept as distinct roles                                 | zone, sparse                                                                                            | —                                         |
| contact-tracing indicators (early vintage)          | zone                                                                        | zone, sparse                                                                                            | —                                         |
| province-level series                               | built from zone rows, checked against every printed province row            | none — zone or national only                                                                            | —                                         |
| national cumulative                                 | via zone, summary and prose routes                                          | separate national files, **including sitreps 001–004** (14–18 May; no other lineage has the first week) | cases for 70 reports, with revision notes |
| the source's own caveats                            | per report, three kinds                                                     | —                                                                                                       | partly, in free-text notes                |
| hospitalisation & point-of-entry blocks             | not yet ported                                                              | zone, sparse (6–8 facility zones)                                                                       | —                                         |
| weekly model-ready streams, accounting-checked      | 10 TSVs (Ituri, Nord-Kivu, **and Haut-Uélé**) + Uganda exports              | —                                                                                                       | —                                         |

## How it is validated

Layered, from the page outward. Each check catches what the previous one cannot.

**1. The page's own arithmetic.** Every report prints totals beside its parts:
zone rows plus unassigned rows must equal the printed province row, provinces
the printed national `Total`. The extraction is accepted only where this closes.
Currently 256 province-reports reconcile exactly, 9 carry a hand-verified
exception (below), and none remain open; the same identity now runs over the
four daily-flow columns too, where 7 province-days disagree with their printed
row — reported loudly, page reads pending. These counts are as of the current
build; the rendered document reads them live and is the authoritative statement.

**2. What the identity cannot see, tests pin.** A table read one concept to the
left — suspected cases as confirmed — closes perfectly, because both sides shift
together. Failures of that kind were each caught once, then pinned to the report
that produced them: `tests/test_extraction.py` names sitreps 005, 015, 020, 048,
073, 080, 088, 092 in its docstrings, one behaviour each.

**3. The assembled series against every printed total.** The weekly streams
carry two gates: the emitted total must equal what the cumulative moved,
_exactly_, and the forward-filled grid is compared against every printed
province row — the check that caught duplicate zone spellings inflating both
sides of gate one at once. Every stream ends at a final gap of **zero**;
`cases_ituri` now agrees with the printed row on 65 of 67 dates, and the two
that differ are the source's own registered self-disagreement (sitrep 059's
note). Each bin's observation `time` is its **last report day**, so an engine
that accumulates between observations scores every window against exactly the
days its count covers — the trailing partial week included. The unassigned pool
is summed within a report and zeroed when a report stops printing it; the
ascertainment streams read the printed province rows and carry a per-date check
against the zone breakdown. Per-date tallies live in
`data/build/streams/meta.json`.

**4. The registers.** When a page itself does not add up, that is a finding
about the document, and it is recorded — not silenced — in `registers/`: one row
per judgement, made after reading the rendered page, quoting what the page says.
Every entry is keyed on the PDF's **SHA-256**, so a revised report fails the
check and returns for a fresh judgement instead of inheriting one made about its
predecessor; every entry licenses **one exact value**, so a reading that changes
un-excuses itself. An unverifiable register (no archive to hash against) is
refused outright.

**5. The other lineages.** Two independent readings of the same PDFs exist:
INRB-UMIE's transcription (cloned by `make external` at exactly the commit in
the committed `external.lock`) and the epiforecasts scan (a pinned copy under
`data/raw/scan/`). `make compare` sets ours against both — currently **2,130 of
2,139** zone-day case values agree with INRB exactly and **70 of 70** national
cumulatives agree with the scan — and every disagreement lands in a CSV with
both values. Two disclosures travel with those numbers, in `compare_meta.json`:
the denominator is the inner join, and 584 of our zone-day rows (the newest
reports — INRB's series currently ends four days before ours) have no
counterpart and sit outside every agreement figure; and zones the lineages spell
differently are mapped onto one key precisely so a spelling divergence can
_disagree_ instead of vanishing. Agreement here is evidence about
_transcription_, never corroboration of the counts (all three lineages read the
same pages); a disagreement is always a finding. The largest one is upstream's:
sitrep 032 prints Rwampara at 159 in both its table and its narrative, and the
INRB file carries 192.

![The three lineages as series: our summed zone rows (line), INSP's own
printed totals (rings), and INRB-UMIE's transcription (dashed). The bottom
row is the differences — ours − INRB mixes value disagreements with
row-coverage gaps in their file; ours − printed is pure arithmetic against
the page, zero except the registered source
self-disagreements.](docs/figures/comparison_series.png)

![Every zone-day on the identity line against INRB-UMIE, and the
disagreements, signed, over time.](docs/figures/comparison.png)

These two figures are committed copies (`docs/figures/`), refreshed by
`make compare` so they always show the current build's comparison; a diff in
them is a change in what the comparison shows.

**6. The archive itself.** The PDFs are not committed (~145 MB); what pins them
is a committed SHA-256 manifest, and `make verify` proves the copy on disk is
the copy the manifest describes — distinguishing _missing_ from _stray_ from
_corrupt_, because a hash mismatch can mean a damaged file or a report the
source revised in place, and the second is worth knowing about. Revision is
watched for in both directions the source can produce it: the fetcher re-checks
every held report's pick URL against the held byte count (a re-picked correction
usually shares the data date, so it maps to a name we already hold and a
name-based skip would never fetch it), and `make check` spot-checks committed
URLs across the whole archive comparing Content-Length against the manifest — a
revision in place at an unchanged URL. Either finding stops the fetch and asks
for adjudication, because every hash-keyed register judgement is about one
version of a document.

**7. The document.** `make doc` renders `analysis/data.html`, and every number
in its prose and every figure it embeds is read from a pipeline artefact at
render time through `analysis/_guard.py`. An artefact no rule produces, or one
not yet built, stops the render. There are no typed numbers to go stale.

## Layout

| Path          | What                                                                                                                                    |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `data/raw/`   | fetched inputs: the PDF archive (uncommitted, manifest-pinned), the INSP index, shapefile, populations, the hand-recorded Uganda series |
| `data/build/` | derived, regenerable: per-report series, the province panel, weekly streams, figures, comparisons                                       |
| `registers/`  | **hand-authored judgements** — the only unregenerable content. See `registers/README.md`                                                |
| `scripts/`    | everything the Makefile calls; `scripts/lib/` is the geometry and vocabulary substrate                                                  |
| `analysis/`   | the data document and its fail-closed guard                                                                                             |
| `external/`   | comparison sources, cloned by `make external`, gitignored, pinned by `.commit` files                                                    |
| `notes/`      | dated lab notes: the architecture, the measured dead ends, the port rationale                                                           |

## Conventions

- **polars, not pandas; `uv` for packages.** No absolute paths in anything
  committed.
- **Every artefact has a rule.** A file under `data/build/` with no Makefile
  rule that regenerates it is a bug, and the document guard enforces the
  contrapositive.
- **A sum of nothing is null, not zero.** polars sums an all-null group to 0,
  which fabricates observations; every aggregation here guards it, after it bit
  this project a fourth time (the reference counts three).
- **Data dates come from each page's `Date de rapportage`, never the filename.**
  Upload filenames carry the publication date, no date, or (once) a timestamp
  that parses as the year 2022; the fetcher recognises documents by content hash
  so a renamed upload is never downloaded twice.
- **Flows and stocks never share a column.** The same French word heads both, in
  different vintages; the roles are distinct and tested.
