# The data contract

What the files in `data/build/streams/` guarantee to the downstream models that
read them. If you're fitting these files, read this once, and then keep the
generated dictionary,
[`data/build/streams/README.md`](../data/build/streams/README.md), open beside
your model: this page says what the files *promise*, and the dictionary says
what each one *is* for the release you built.

## The files are a contract, not an implementation detail

The stream files — weekly TSVs, a **daily companion for each** (one row per
report day), the stock readings, the care ledger the reports state in words, the
exports counted outside the DRC, and `meta.json` (whose `population`, `day0` and
`opening` fields are read too) — are vendored by downstream models, pinned to a
release tag and verified by per-file sha256 against a byte-identical rebuild. So
file renames, column changes, and the stock-file conventions (`uganda_exports`,
`exports_*`: cumulative counts at the dates a source prints them, deliberately
unlike the incidence streams beside them) are coordinated changes, announced in
the [CHANGELOG](../CHANGELOG.md) — never refactors.

The national streams are built from the printed national rows, never by summing
the province streams. The per-bin identity *national = emitted provinces +
dropped provinces + orphan pool + unattributed* is recorded in `meta.json`, and
a nonzero unattributed term is a finding.

## Three readings of a case count, and you fit one

- **Differenced** (`cases_*`, `deaths_*`): the movement of the source's printed
  cumulative, so a row spans the interval since the previous row.
- **Notified** (`cases_notified_*`, `deaths_notified_*`): the count the
  front-page banner states *for the report day itself*. The source printed it
  only for sitreps 059–083, the stretch it was reconciling, when its cumulative
  stopped being safe to difference.
- **Excluding backlog** (`cases_excluding_backlog_*`,
  `deaths_excluding_backlog_*`): the differenced series with the days the source
  *says* hold records from earlier days replaced by its own same-day count.
  Which days those are is `registers/retrospective_batches.tsv`, quoting the
  source.

They measure the same events three ways: fit one. The same caution applies to
recoveries, which appear in three places in the report, one of which ends early;
see the `care_exits_recovered` and `cumul_recovered` entries in the dictionary.

The care census has the same shape of trap in Nord-Kivu: from sitrep 124 the
reports print a total and the part of it in dedicated treatment structures, and
`care_census_nord_kivu` and `care_census_dedicated_nord_kivu` publish both. One
is a subset of the other, so fit one against an isolation compartment, never
both ([note](../notes/2026-10-20-nord-kivu-census-two-counts.md)).

## Two resolutions, one construction

`cases_ituri.tsv` is weekly; `cases_daily_ituri.tsv` is the same quantity per
report day. Both come from the same panel, the same registers and the same gate
— a stream's total equals what the source's cumulative moved, exactly — so the
two resolutions cannot disagree about what a report said. Fit one or the other,
never both.

## Every flow file states the window each row covers

Report days are irregular, so a flow row carries `window_start` and
`window_stop`, the half-open interval `[window_start, window_stop)` its count
accumulated over, and nothing is spread across it. The build fails unless:

```
window_stop > window_start                        (positive width)
window_stop - window_start == days_covered        (no drift)
window_start == the previous row's window_stop    (tiles exactly)
```

Half-open means `[window_start, window_stop)` covers every calendar day from
`window_start` up to but not including `window_stop`, so its width is exactly
`window_stop - window_start` and two adjacent rows share a boundary value
without overlapping — the BED convention for genomic intervals, for the same
reasons. So `window_stop` is **one day after the day the source spoke**: a
report stating figures for 13 July closes a window at 14 July. Anything dating
an observation should read `window_start`, or `window_stop` minus a day;
`scripts/lib/streams.py` does this in one place for everything in this
repository.

Why both ends are stated: when a row's window was inferred from the gap to the
row before it, deleting an interior row silently widened its neighbour — the
model accumulated over one interval and compared the result against a count
covering another, and nothing in the file said so. Stating both ends leaves only
two failure modes, and the gate catches both: an **overlap**, where two rows
claim a day and its count is scored twice, and a **gap**, where a day belongs to
no row.

## `NA` is a hole, not a zero

The families the source states as a single 24-hour figure per report — the care
ledger's admissions and exits, the daily laboratory files, the daily
community-death split — carry **a row on every calendar day they span**, holding
`NA` where the source said nothing. A row carrying `NA` asserts only that the
day existed and nobody reported this quantity. It contributes no likelihood term
and is **not an observed zero**: a report that does not mention absconders is
silent about them, not reporting none.

Read these files with the token declared (in polars, `null_values="NA"`),
because `NA` is not a null token by default and one hole otherwise turns a count
column into a string column.

In a file with a denominator (`tests_*` beneath `positives_*`), the denominator
on an unscored row is set to 1, never empty or zero, so a model dividing by it
never meets a hole. That 1 means "nothing to divide here", not one test.

**Stocks are outside all of this.** `care_census_*`, `patients_isolated*`,
`cumul_recovered`, `uganda_exports` and `exports_*` are readings at an instant:
they keep a plain `time` column, carry no `days_covered`, accumulate over no
window, and a 46-day gap in one of them is a reading taken 46 days later.

## A stream states how much of its population it saw

Where a row's value is a total over provinces or over report days, the file
publishes the coverage beside the count:

- `n_report_days` — how many reports fed the row;
- `n_report_days_silent` — reports in the row's window that said nothing of this
  quantity for this place (prose bullets skip provinces);
- `n_provinces`, `n_province_days` — for a national total assembled from a
  paragraph that does not always write out every province.

This exists because of a real failure. Read without `n_provinces`, the national
laboratory stream carries about 23% fewer positives than the case series, and
that shortfall was very nearly fitted as a probability of publication. Split by
coverage, report days whose paragraph covers three or four provinces agree with
the case series to within about a percent: the deficit is entirely the provinces
that went unwritten.

Streams read out of prose also carry `checks`, the source's own arithmetic on
the passage a value came from: `closes` (the passage's numbers reproduce the
value), `contradicts` (they disagree with each other — the source, not the
reader), `unchecked` (nothing on the page could verify it — including rows whose
only check was a bound such as recoveries ≤ exits, which almost any reading
passes). And `flags` carries the source's own caveats about that day
(`consolidating`, `harmonisation`, `harmonisation_undercount`,
`stale_distribution`, `-` for none), with `consolidating` repeated as a 0/1
column, so a model can down-weight batch consolidation rather than absorb it in
dispersion.

## No published count is negative, and no case is lost making it so

INSP revises its own cumulative downward — Nord-Kivu goes 44 cases / 26 deaths
on 10 June to 40 / 24 on 11 June — and differencing turns that into a negative
increment, which Poisson and negative binomial are both undefined on. So the
deficit is **carried forward**: the row emits 0 and the remainder comes out of
subsequent rows until it discharges. Every emitted value is a non-negative
integer and every stream still totals exactly what the source's cumulative
moved. Clipping to zero would do neither: it would keep the cases the source
withdrew and break that identity by the size of the revision.

The correction is applied to the rows a model fits, so the daily and weekly
files can attribute one revision to different rows and both still total the
source's movement. `data/build/streams/revisions.tsv` is the generated record:
one row per published row a deficit was open at, keyed on
`(stream, column, time)`, with the raw increment, the value emitted, the carry
outstanding and the source's flag for that day. A carry still outstanding at the
end of a series stops the build.

## A province's flow file starts after its first report

A flow file is the cumulative differenced, so a province's first printed
cumulative — the cases it already had the day it entered the reports — is in no
row. For Ituri that's 30 cases; for a province that joined mid-outbreak it's its
arrival. `meta.json` carries each one under `opening` (date and value, for cases
and deaths), read from the same cumulative the streams difference, so opening
plus emitted is the province's final cumulative exactly. Add a seeding term at
that date if your model needs one
([note](../notes/2026-10-20-province-opening-level.md)).

## Which file is which

[`data/build/streams/README.md`](../data/build/streams/README.md), generated by
the run that writes the streams. One row per published file: what it measures in
a sentence, its resolution, its place, how many observations it holds and the
span it covers, read off the file itself. It also says **how each family is to
be read** — the construction its rows come from, what the quantity is not, and
what a model must condition on — because none of that is visible in a span or a
column name. The sentences come from `registers/stream_families.tsv`, keyed on
the observation family, and a stream whose family has no sentence stops the
build: a new stream cannot ship undocumented.

Row-level tables that are not streams — the burial-alert ledger, the
onset-to-report delay, and the per-case and reconciliation tables for cases
outside the DRC — are published in `data/build/streams/reference/` and described
under `reference` in `meta.json`.
