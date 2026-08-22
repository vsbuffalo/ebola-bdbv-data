# Changelog

What changed in the **published data contract** — the files under
`data/build/streams/` that the modelling repository vendors — release by
release, newest first. Every entry names its tag, states whether it is
**breaking** for a consumer, and says what a consumer must do.

This file exists because the contract is consumed by code (and by coding
agents) that pin a tag and read fixed column names. A rename that a human
would absorb in a glance is a silent failure for a `columns { }` declaration,
so every schema change is dated, named, and given a migration line here.

Scope: stream files and `meta.json`. Extraction improvements that change
*values* are noted only where they move a published series; the commit log
carries the rest.

---

## `data/2026-08-18` — 2026-08-21 — data + fix

**Three new reports: sitreps 094, 095, 096** (data dates 16–18 August). INSP
published all three on 20 August as bare-numbered uploads (`94.pdf`,
`95.pdf`, `96.pdf`), which the fetch guard refused to classify — correctly,
and it blocked the modelling repo's vendor step until a human read them. Each
front page states its own identity ("SitRep N°094/MVEBDB/16/08/2026 · Date de
rapportage : 16 août 2026"); recorded in
`registers/sitrep_number_overrides.tsv` from the page, not the filename.

**Two extraction fixes that sitrep 095 exposed**, both in the handling of a
table whose first page outdents the province name into its own label column
while its continuation carries zones in one:

- The chain remap forced the continuation's single label column onto the
  first page, dropping the column the province row sat in. The report's
  national identity failed by exactly Ituri's 4,309 cases. Value columns must
  agree across a chain; label columns are per-page typography, and the page's
  own classified labels now win where it has them.
- `parent()` returned the leftmost label column whether or not the name came
  from that same column, so rows outdented into it were emitted as their own
  parent. The carry then read `Adja` and `Aru` as merged province labels,
  found no such province, and left all 55 of that report's zone rows
  unattributed. A row is not its own parent.

Both defects were caught by the page's own arithmetic, not by inspection.

Identities after the fixes: **278 province-reports reconcile, 10 carry a
verified exception, 0 disagree**; all three new reports close exactly. Stream
totals equal the source's cumulative movement as always; `cases_ituri` now
agrees with the printed province row on 69 of 71 dates. `deaths_ituri`'s
worst grid gap returns to the registered −66 (sitrep 059) after briefly
showing a spurious −37.

## `data/2026-08-15-r8` — 2026-08-19 — addition

Three national **stock** observations, read from the front-page banner and
the care-occupancy table (`extract_banner.py`, a new route — the "national
dashboard" the README listed as unread):

| file | what it is |
| --- | --- |
| `patients_isolated.tsv` | everyone in isolation or a treatment centre at that moment — **confirmed AND suspected** |
| `patients_isolated_confirmed.tsv` | of those, the confirmed ones |
| `cumul_recovered.tsv` | recoveries to date, national |

**Read the two isolation series carefully: only the second observes a
compartment of confirmed cases.** Sitrep 070 prints the banner headline as
766 and its own occupancy table splits that into 278 confirmed and 488
suspects, with the narrative saying so in words. Across the archive the
confirmed share runs 0.23–0.53 (median 0.39), and it moves with testing and
triage rather than with transmission — so fitting the headline census to an
isolated-*case* compartment would score a mostly-suspect population against a
confirmed-case state.

These are **stocks**: a reading at an instant, not a count accumulated over a
window, so like `uganda_exports.tsv` they carry neither `days_covered` nor
`n_report_days`. Absence of those columns is the marker of an instantaneous
observation.

Extracted from the pages, not adopted from the epiforecasts scan, which
carries the same two headline fields: the scan is a check and never a trunk,
and its series would also stop eight reports early. Cross-check where both
exist: **49/49 agree on the isolation census, 24/24 on recoveries.** One
disagreement was resolved in our favour by reading the page — sitrep 061
prints 737, the scan has 736, which is what that report's own province
breakdown (544 + 188 + 4) sums to; the page contradicts itself and we take
the printed total.

Coverage: isolation 58 reports (confirmed split on 49), recoveries 33. Early
reports print no such tile; the value is null, never inferred.

## `data/2026-08-15-r7` — 2026-08-19 — **BREAKING (schema)**

Column conventions, at the modelling repo's request. No value changes: every
count in every file is identical to `-r6`; only names and added columns
differ.

**1. Value columns name the observable, not the binning.**

| file | was | now |
| --- | --- | --- |
| `cases_daily_ituri.tsv` | `cases_daily_ituri` | `cases_ituri` |
| `deaths_daily_*.tsv` | `deaths_daily_*` | `deaths_*` |
| `community_deaths_daily_*.tsv` | `community_deaths_daily_*`, `deaths_split_daily_*` | `community_deaths_*`, `deaths_split_*` |
| `lab_daily_national.tsv` | `positives_daily_national`, `tests_daily_national` | `positives_national`, `tests_national` |

The weekly files are unchanged; the daily ones now use the same column names,
so one observable has one name and a model swaps resolution by changing a
path. The old names also asserted a cadence the data contradicts: a "daily"
row covers 2–3 days on 5 of 82, and a "weekly" row 4–8 (the lab stream, 2–9).

**2. Every file carries the interval each row covers.** New column
`days_covered`: the length in days of `(previous row's time, this row's
time]`, the window the count accumulates over. Previously only the daily
files stated it — which left it un-stated exactly where row spacing varies
most.

**3. One name for that column.** `days_since_prev_report` is gone; it is
`days_covered` everywhere.

**Also new: `n_report_days`** in every file — how many report days actually
contributed to the row. Distinct from `days_covered` and needed beside it:
`lab_national.tsv`'s first row covers 7 days but rests on 6 reports, and the
gap between the two numbers is the coverage a consumer should weigh.

**Unchanged on purpose:** `n_provinces` on the lab files and `flags` on the
daily files stay, and stay un-filtered. Publishing the coverage and letting
the consumer decide is what let the modelling repo withhold thin rows from
scoring while keeping them in the series; pre-filtering would have removed
that choice silently.

**Exempt: `uganda_exports.tsv`** takes neither new column. Its rows are
cumulative importation counts at two bulletin dates — a stock read at a
moment, not a count accumulated over a window — so a span column would
assert an interval that does not exist. The absence is the signal that this
file is a different kind of thing.

*Migration:* drop the `_daily_` infix from column names when reading the
daily files; read `days_covered` instead of `days_since_prev_report`. Values,
row counts and row order are unchanged from `-r6`.

## `data/2026-08-15-r6` — 2026-08-18 — fix

`-r5` wrote every stream file correctly and then crashed in its summary
printer (`KeyError` on the lab entry), so the tag could not be built from a
clean clone. Fixed; stream files byte-identical to `-r5`. New release gate
`make release-check` builds the committed state in a scratch clone, and now
runs before every tag.

## `data/2026-08-15-r5` — 2026-08-18 — addition

Daily companions for every stream: `cases_daily_*`, `deaths_daily_*`,
`community_deaths_daily_*` (four scopes each) and `lab_daily_national`. One
row per report day, the increment since the previous report day, negative
revisions preserved as printed, gated against the same cumulative movement as
the weekly files. Introduced `days_covered` / `days_since_prev_report` and the
`flags` column (`consolidating`, `harmonisation`,
`harmonisation_undercount`, `stale_distribution`, `-`).

## `data/2026-08-15-r4` — 2026-08-17 — addition

`lab_national.tsv`: weekly testing volume and positives, read from the
laboratory prose with every number licensed by the sentence's own printed
positivity. Also `data/build/series/lab_prose.csv` (province level, each
licensing sentence quoted).

## `data/2026-08-15-r3` — 2026-08-17 — addition

National streams — `cases_national`, `deaths_national`,
`community_deaths_national` — built from the printed national rows, never by
summing provinces. `meta.json` gains `vs_province_sum`, the per-bin identity
*national = emitted provinces + dropped provinces + orphan pool +
unattributed*.

## `data/2026-08-15-r2` — 2026-08-17 — data

INSP listed sitrep 063 (16 July) for the first time, filling a gap between
062 and 064. Stream totals unchanged (its increment had been carried into the
17th, inside the same bin); one new register entry.

## `data/2026-08-15` — 2026-08-17 — first release

Seven weekly stream TSVs plus `meta.json`, gated on: every accounting
identity holding, the full test suite passing, comparison figures rendering,
and the upstream check reporting current-or-behind.
