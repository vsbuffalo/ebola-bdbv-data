# ebola-bdbv-data

Extraction layer for the 2026 DRC Bundibugyo virus outbreak: from the INSP
situation-report PDFs to analysis-ready, per-health-zone case series — every
step a build target, every number checked against the page that printed it.

The companion modelling repository consumes exactly seven small TSVs from this
one (`data/build/streams/`). Everything else here exists to make those seven
files trustworthy, and to show the work.

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
  controls, per-report hover provenance on every mark, the per-stream flow
  grid, reporting-noise diagnostics, and a searchable report index.

`make serve` starts a detached `http.server` on port 8790 (it checks the port
first and tells you if something else holds it). After a re-render the pages
update in place — refresh the browser, no restart needed.

**Run `make check` first.** It is the only step that looks *outward* — every
other check asks whether the reports we hold are internally consistent, and
none of them can ask whether we hold the reports that *exist*. The reference
project once sat eleven days behind the source with every internal check green,
because the site renamed the series and the query silently stopped matching.

| exit | meaning | what to do |
| ---- | ------------------------------------------------ | ---------- |
| 0 | `CURRENT` — we hold everything the source lists | nothing |
| 1 | `BEHIND` — new reports published | `make fetch && make build` |
| 2 | `CHANGED` — the source moved under us | **look first** |
| 3 | `UNREACHABLE` — the API did not answer | retry |

`make build` touches no network, so a rebuild can never silently acquire
different inputs. Everything under `data/build/` is regenerable from the
committed inputs; delete it and `make build` returns it byte-identically.

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
`scripts/lib/tablespec.py`) decide *which table this is*, and columns are
indexed from the **data**: the numeric columns, left to right, zipped against a
declared order. Order is stable within a layout even when the column count is
not.

Three code layers, strictly separated:

| Layer | File | Knows | Does not know |
| --- | --- | --- | --- |
| Geometry | `scripts/lib/pdftable.py` | rects, lines, dot-stippled borders → a cell grid | French, Ebola |
| Vocabulary | `scripts/lib/tablespec.py` | French headings; each layout's column order | PDFs, epidemiology |
| Domain | `scripts/extract_zone_table.py`, `scripts/aggregate_provinces.py`, `scripts/build_streams.py` | provinces, subtotals, unassigned pools, the identities | geometry |

### The routes

Not every report prints the same thing, so there are four extraction routes,
and every held report is covered by the finest one its pages print:

| Route | Reports | What it reads |
| --- | --- | --- |
| zone table (three declared layouts) | 77 | cumulative cases & deaths per health zone; from 13 July the daily ascertainment split |
| provincial summary | 70 | one row per province — the only tabular data on the reports whose vintage dropped the zone table |
| prose sentence | 3 | `"121 cas dont 110 en Ituri, 10 au Nord-Kivu et 1 au Sud-Kivu"` — read only because the sentence checks itself |
| *(national dashboard)* | — | not yet read; the daily suspected inflow after 12 July is the known gap |

## How it is validated

Layered, from the page outward. Each check catches what the previous one
cannot.

**1. The page's own arithmetic.** Every report prints totals beside its parts:
zone rows plus unassigned rows must equal the printed province row, provinces
the printed national `Total`. The extraction is accepted only where this
closes. Currently 250 province-reports reconcile exactly, 7 carry a
hand-verified exception (below), and 2 remain open — named in the status
files, never dropped. These counts are as of the current build; the rendered
document reads them live and is the authoritative statement.

**2. What the identity cannot see, tests pin.** A table read one concept to
the left — suspected cases as confirmed — closes perfectly, because both sides
shift together. Failures of that kind were each caught once, then pinned to
the report that produced them: `tests/test_extraction.py` names sitreps 005,
015, 020, 048, 073, 080, 088, 092 in its docstrings, one behaviour each.

**3. The assembled series against every printed total.** The weekly streams
carry two gates: the emitted total must equal what the cumulative moved,
*exactly*, and the forward-filled grid is compared against every printed
province row — the check that caught duplicate zone spellings inflating both
sides of gate one at once. Every stream ends at a final gap of **zero**, and
the per-date tallies live in `data/build/streams/meta.json`.

**4. The registers.** When a page itself does not add up, that is a finding
about the document, and it is recorded — not silenced — in `registers/`: one
row per judgement, made after reading the rendered page, quoting what the page
says. Every entry is keyed on the PDF's **SHA-256**, so a revised report fails
the check and returns for a fresh judgement instead of inheriting one made
about its predecessor; every entry licenses **one exact value**, so a reading
that changes un-excuses itself. An unverifiable register (no archive to hash
against) is refused outright.

**5. The other lineages.** Two independent readings of the same PDFs exist:
INRB-UMIE's transcription (cloned by `make external`, pinned by commit) and the
epiforecasts scan. `make compare` sets ours against both — currently **2,118 of
2,127** zone-day case values agree with INRB exactly, **67 of 67** national
cumulatives agree with the scan, and every disagreement lands in a CSV with
both values. Agreement here is evidence about *transcription*, never
corroboration of the counts (all three lineages read the same pages); a
disagreement is always a finding. The largest one is upstream's: sitrep 032
prints Rwampara at 159 in both its table and its narrative, and the INRB file
carries 192.

**6. The archive itself.** The PDFs are not committed (~145 MB); what pins
them is a committed SHA-256 manifest, and `make verify` proves the copy on
disk is the copy the manifest describes — distinguishing *missing* from
*stray* from *corrupt*, because a hash mismatch can mean a damaged file or a
report the source revised in place, and the second is worth knowing about.

**7. The document.** `make doc` renders `analysis/data.html`, and every number
in its prose and every figure it embeds is read from a pipeline artefact at
render time through `analysis/_guard.py`. An artefact no rule produces, or one
not yet built, stops the render. There are no typed numbers to go stale.

## Layout

| Path | What |
| --- | --- |
| `data/raw/` | fetched inputs: the PDF archive (uncommitted, manifest-pinned), the INSP index, shapefile, populations, the hand-recorded Uganda series |
| `data/build/` | derived, regenerable: per-report series, the province panel, weekly streams, figures, comparisons |
| `registers/` | **hand-authored judgements** — the only unregenerable content. See `registers/README.md` |
| `scripts/` | everything the Makefile calls; `scripts/lib/` is the geometry and vocabulary substrate |
| `analysis/` | the data document and its fail-closed guard |
| `external/` | comparison sources, cloned by `make external`, gitignored, pinned by `.commit` files |
| `notes/` | dated lab notes: the architecture, the measured dead ends, the port rationale |

## Conventions

- **polars, not pandas; `uv` for packages.** No absolute paths in anything
  committed.
- **Every artefact has a rule.** A file under `data/build/` with no Makefile
  rule that regenerates it is a bug, and the document guard enforces the
  contrapositive.
- **A sum of nothing is null, not zero.** polars sums an all-null group to 0,
  which fabricates observations; every aggregation here guards it, after it
  bit this project a fourth time (the reference counts three).
- **Data dates come from each page's `Date de rapportage`, never the
  filename.** Upload filenames carry the publication date, no date, or (once)
  a timestamp that parses as the year 2022; the fetcher recognises documents
  by content hash so a renamed upload is never downloaded twice.
- **Flows and stocks never share a column.** The same French word heads both,
  in different vintages; the roles are distinct and tested.
