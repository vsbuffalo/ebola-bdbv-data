# How it is validated

Layered, from the page outward. Each check catches something the previous one
cannot. Live counts for every layer are in the rendered `analysis/data.html` and
in the build's own status files; the ones below are there to show what each
layer is for, so they're stated as examples, not as the current tally.

## 1. The page's own arithmetic

Every report prints totals beside its parts: zone rows plus unassigned rows must
equal the printed province row, and provinces the printed national `Total`. The
extraction is accepted only where this closes, and the same identity runs over
the daily death-split columns. The per-report verdicts are
`data/build/series/zone_table_status.csv` and
`province_series_reconciliation.csv`.

## 2. What the identity cannot see, tests pin

A table read one concept to the left — suspected cases as confirmed — closes
perfectly, because both sides shift together. Failures of that kind were each
caught once and then pinned to the report that produced them: the tests in
`tests/` name the sitrep each one is about in its docstring, one behaviour per
test.

## 3. The assembled series against every printed total

The streams carry two gates: the emitted total must equal what the cumulative
moved, *exactly*, and the forward-filled grid is compared against every printed
province row. That second check is the one that catches a zone filed under the
wrong province: sitreps 010–011 put Nord-Kivu's Kalunguta under Sud-Kivu, and
the forward fill carried that one case to the end of the series, so Sud-Kivu
disagreed with its own printed row on every date. Every province's case and
death stream must end at a gap of **zero** against its printed row, and a test
enforces it. Per-date tallies are in `data/build/streams/meta.json` under
`reconciliation`.

## 4. The registers

When a page itself does not add up, that's a finding about the document, and it
is recorded — not silenced — in `registers/`: one row per judgement, made after
reading the rendered page, quoting what the page says. Every entry is keyed on
the PDF's **SHA-256**, so a revised report fails the check and comes back for a
fresh judgement instead of inheriting one made about its predecessor, and every
entry licenses **one exact value**, so a reading that changes un-excuses itself.
See [`registers/README.md`](../registers/README.md).

## 5. The other lineages

Two independent readings of the same PDFs exist: INRB-UMIE's transcription
(cloned by `make external` at exactly the commit in the committed
`external.lock`) and the epiforecasts scan (a pinned copy under
`data/raw/scan/`). `make compare` sets ours against both, and every disagreement
lands in a CSV with both values. `data/build/compare/compare_meta.json` states
the current agreement figures together with two disclosures: the denominator is
the inner join, so our zone-days with no counterpart (everything after the other
lineage's last date) sit outside every agreement figure; and zones the lineages
spell differently are mapped onto one key precisely so a spelling divergence can
*disagree* instead of vanishing.

Agreement here is evidence about *transcription*, never corroboration of the
counts — all three lineages read the same pages. A disagreement is always a
finding. The largest so far is upstream's: sitrep 032 prints Rwampara at 159 in
both its table and its narrative, and the INRB file carries 192.

![The three lineages as series: our summed zone rows (line), INSP's own printed
totals (rings), and INRB-UMIE's transcription (dashed). The bottom row is the
differences — ours − INRB mixes value disagreements with row-coverage gaps in
their file; ours − printed is pure arithmetic against the page, zero except the
registered source self-disagreements.](../figures/comparison_series.png)

![Every zone-day on the identity line against INRB-UMIE, and the disagreements,
signed, over time.](../figures/comparison.png)

These figures are committed copies, refreshed by `make compare`. Every committed
figure has a caption in [`figures/README.md`](../figures/README.md) saying what
it shows and the caveats that belong with it, and a test fails if one doesn't.

## 6. The archive itself

The PDFs are not committed (about 200 MB). What pins them is a committed SHA-256
manifest, and `make verify` proves the copy on disk is the copy the manifest
describes, distinguishing *missing* from *stray* from *corrupt* — a hash
mismatch can mean a damaged file or a report the source revised in place, and
the second is worth knowing about. Three reports are committed, because INSP
serves neither them nor any URL they could be fetched from: SitReps 001, 002 and
004, the outbreak's first reports, held from a secondary archive and declared in
`registers/external_sitreps.tsv`. A PDF declared by neither the index nor that
register stops the build.

Revision is watched for in both directions the source can produce it. The
fetcher re-checks every held report's URL against the held byte count, because a
re-issued correction usually shares the data date and a name-based skip would
never fetch it. And `make check` spot-checks committed URLs across the whole
archive, comparing Content-Length against the manifest, for a revision in place
at an unchanged URL. Either finding stops the fetch and asks for a human.

The same discipline covers the documents behind the counts outside the DRC:
`make fetch-exports` snapshots every cited page with its sha256, and
`make check-exports` checks every quoted classification and total against the
bytes it was read from.

## 7. The document

`make doc` renders `analysis/data.html`, and every number in its prose and every
figure it embeds is read from a pipeline artefact at render time through
`analysis/_guard.py`. An artefact no rule produces, or one not yet built, stops
the render. There are no typed numbers to go stale.
