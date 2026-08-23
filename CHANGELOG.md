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

## `data/2026-08-18-r4` — 2026-08-23 — fix

**Not breaking**: no column removed or renamed. Two stock series gain most of
their history, one weekly series gains an observation and moves one value,
and `banner.csv` gains a `cumul_deaths` column.

**The front-page dashboard was read in only one of the two layouts the source
draws.** A tile's value was located by scanning *downward* from its label. The
earlier vintage prints the row of values *above* the row of labels, so every
report in it refused, and the refusal was recorded honestly as "label with no
aligned number beneath it" — for fifty-one of the eighty-seven reports. The
reader now searches both ways and takes the nearer number; upward it requires
the line to be a row of nothing but tile values, so the report header above a
label cannot leak in. Two further defects were in the same path: a
one-character field was welded to everything after it on its line (every
single-digit tile value in the archive — sitreps 008, 013, 018, 021 — read as
`0                  16` and refused), and a value's column was matched only by
its starting position, which fails where the number is centred over a wider
label.

| stream | was | now |
|---|---|---|
| `cumul_recovered` | 36 obs, opens `2026-07-12` at **333** | **86 obs**, opens `2026-05-19` at **0** |
| `patients_isolated` | 61 obs, opens `2026-06-02` at 206 | **74 obs**, opens `2026-06-01` at 173 |
| `deaths_national` | 12 obs, first `2026-06-02` | **13 obs**, first `2026-05-26` |
| `deaths_daily_national` | 75 obs, opens `2026-05-31` | **86 obs**, opens `2026-05-20` |

**No previously published value in any stream changes except one**, and it
changes because its window did:

| stream | row | was | now |
|---|---|---|---|
| `deaths_national` | `2026-06-02` | `20`, `days_covered 4`, `n_report_days 3` | `45`, `days_covered 7`, `n_report_days 7` |

That bin previously began where the *tables* first printed a cumulative death
column (29 May, at 42), so 42 deaths sat outside every emitted row and the
opening bin covered four days. The front page prints the same cumulative from
the first held report, so the series now starts on 19 May at 4 and the bin is
whole. `deaths_national` emits 2,472 against 2,434 — **38 deaths that were
previously outside the series**, all in the growth phase. Every other stream
file is byte-identical.

**Two definitional questions were decided rather than assumed.**

*Is the early `Guéris` tile a running total or the day's recoveries?* The page
does not say — the wording `Nombre cumulé des guéris` appears only from sitrep
019. It is a running total, and `extract_banner._bare_label_is_cumulative` is
a build-time gate rather than a comment: sitrep 018 (`Guéris`) and sitrep 019
(cumulative wording) are consecutive days and both print **6**, and the
bare-label values never fall (0, 0, 0, 0, 0, 1, 1, 2, 2, 6, 6). The same pages
carry a separate per-zone `Guéris du jour` column, so the day's flow already
has its own home. If either condition ever stops holding the bare-label values
are dropped, not published.

*The suspected-case tile is not published, and this change does not start
publishing it.* It is `Cumul cas suspects` (a running total), `Cas suspects en
cours d'investigation` (a stock), and `Cas suspects du jour` (a flow) in three
vintages under near-identical wording. Splicing them into one column would
join a stock to a flow.

**Two reports are still refused, on purpose.** Sitreps 016 and 017 print `Cas
suspects en isolement` (101 and 104) — suspects inside the ward, beside a
separate `Cas confirmés actifs` tile — and print no ward total. The
all-patients wording appears from sitrep 018. Publishing 101 into a series of
ward totals would put a sub-count where a total belongs at the point the
series begins. The epiforecasts scan excludes those two reports for the same
stated reason. Sitrep 007's recovery tile prints `ND`.

**Cross-checks, now running on every build.** `make compare` gained
`banner_comparison.csv`: 187 report-values against the epiforecasts scan's
independent reading, **186 exact**. The one difference is sitrep 083's
cumulative confirmed deaths, where the page's headline tile prints 1 850 and
its own Table 1 `Total` prints 1 850 while the province rows sum to 1 851; we
publish the printed national row, the scan publishes the province sum. `make
streams` records `deaths_national_banner_vs_table` in `meta.json`: on the 76
dates where both the tile and a table print a national cumulative death count
they agree on **75**. The exception is sitrep 059, whose printed `Total` (718)
sits one below its own province rows and one below the tile (719) — the same
class of one-unit internal inconsistency, in the other direction.

Reading the tile also closed an over-refusal: sitreps 046, 053 and 058 print
unambiguous isolation censuses (609, 680, 753) that were discarded because a
*different* table's confirmed/suspect decomposition did not add up.

**Consumer action.** Re-vendor `cumul_recovered.tsv`, `patients_isolated.tsv`,
`deaths_national.tsv` and `deaths_daily_national.tsv`. Anything fitted to
`cumul_recovered` should be refitted: the stream previously entered at a level
of 333 with its whole prior trajectory unobserved.

**Two retractions in the `-r8` entry below.**

1. "Early reports print no such tile; the value is null, never inferred." The
   first clause is wrong — they print it, above the labels rather than below —
   and the coverage figures in that entry are the pre-fix ones. The second
   clause held throughout: nothing was ever inferred.
2. "One disagreement was resolved in our favour by reading the page — sitrep
   061 prints 737, the scan has 736." The reading of the page was right and
   the conclusion was backwards: `patients_isolated` for 14 July was published
   as **736** then and is published as 736 now, because the occupancy table
   supplies it and that table's own `Fin J` row reads 736, as does the tile's
   province breakdown (544 + 188 + 4). It is the front-page headline, 737,
   that stands alone. The disagreement was resolved in the *scan's* favour.
   The tile's 737 is now recorded per report in `banner_status.csv` instead
   of being invisible.

## `data/2026-08-18-r3` — 2026-08-23 — fix

**Not breaking**: no column added, removed or renamed. Two national daily
series gain a report-day; **no count changes**, only the interval a count is
attributed to.

**A printed national total was being lost to a page break.** Sitrep 085
(7 August) splits its provincial summary across two pages, with the national
`Total` row alone at the top of page 2, where the alerts table's title box is
drawn over it. The two grids touch, so they were read as one table whose
extent matched neither, and the continuation was refused — while
`province_summary_status` recorded the read as `ok`. The loss was silent.

| stream | was | now |
|---|---|---|
| `cases_daily_national` | `2026-08-08  174  days_covered 2` | `2026-08-07  89  1` + `2026-08-08  85  1` |
| `deaths_daily_national` | `2026-08-08  73  days_covered 2` | `2026-08-07  29  1` + `2026-08-08  44  1` |
| `cases_national` / `deaths_national`, week to 08-11 | `n_report_days 6` | `n_report_days 7` |

The two-day totals are conserved — 89 + 85 = 174, 29 + 44 = 73 — so a
consumer aggregating over any window wider than a day sees no change. What
changes is that 7 August is now its own observation rather than being folded
into the 8th, and the week to 11 August is fully covered.

Validated against the epiforecasts scan, an independent hand transcription of
the same PDFs: it records sitrep 085's national cumulative as 4,209, and all
71 comparable reports now agree. Across the provincial-summary route,
`not_checkable` goes from 1 to 0 — every report yielding summary rows now
prints a total we read and check.

---

## `data/2026-08-18-r2` — 2026-08-22 — new streams

**Not breaking**: three files added, nothing changed or removed.

    lab_daily_ituri.tsv       56 obs   9,038 tests   2,687 positives
    lab_daily_nord_kivu.tsv   47 obs   4,866 tests     406 positives
    lab_daily_haut_uele.tsv    5 obs      60 tests      19 positives

Same column convention as every other daily stream: `time`,
`positives_<slug>`, `tests_<slug>`, `days_covered`, `n_report_days`, `flags`.

**Why they exist.** `lab_daily_national` carries 0.77 laboratory positives per
new confirmed case, and that ratio was being read downstream as a laboratory
reporting probability. It is not one. The laboratory paragraph does not always
write out every province, and the ratio splits cleanly by the `n_provinces`
column already published beside the counts:

| provinces covered | report-days | ratio |
|---|---|---|
| 1 | 8 | 0.404 |
| 2 | 37 | 0.756 |
| 3 | 12 | **0.997** |
| 4 | 1 | **1.000** |

When the paragraph covers the country, laboratory positives and new confirmed
cases agree to within 0.3 %. A fitted "laboratory reporting probability" of
0.77 was therefore measuring how much of the country the paragraph described.

Matching province against province removes it without conditioning on
coverage at all. Excluding backlog-consolidation days, positives/cases is
0.972 in Ituri and 1.048 in Nord-Kivu — **0.979 combined**. (Nord-Kivu above 1
is repeat specimens from already-confirmed patients, *reprélèvements*, which
the reports count as positives and which no reporting probability below 1 can
produce.)

---

## `data/2026-08-18-r1` — 2026-08-22 — fix

**Not breaking**: no column added, removed, or renamed. Two national
laboratory series move, and a consumer that has fitted to them should refit.

**A death split was read as a test positivity.** Sitrep 080's Ituri passage
prints both a real laboratory line and a death split, and the death split
alone satisfies the licence: *"23 décès dont 14 communautaires (60,9 %)"*
offers the pair (14, 23), which reproduces 60,9 % exactly. It was accepted,
so 2 August recorded **14 positives out of 23 samples** in place of the
printed **53 out of 210** (*"210 échantillons … dont 53 positifs … soit une
positivité apparente de 25,2 %"*).

The licence-or-refuse rule asks whether a pair reproduces a printed
percentage. It cannot ask what the percentage *means*, and a death split has
the same arithmetic shape as a positivity — a subset, a total, and their
ratio. So the rule was necessary and not sufficient, and no tolerance change
would have caught it. Death-split clauses now leave the pool before the pair
is chosen; deaths and their community share come from the tables, which is
where they belong. One row of 134 was affected.

Moved series, both national:

| stream | was | now |
|---|---|---|
| `lab_daily_national` (2026-08-02) | 32 positives / 155 tests | **71 / 342** |
| `lab_national`, `lab_daily_national` (totals) | 3,076 / 13,914 | **3,115 / 14,101** |

Case, death, community-death, isolation and recovery streams are unchanged —
`lab_prose` feeds only the testing streams and `meta.json`, whose
`lab_national` reconciliation record also updates (`positives_vs_new_cases`
now 53 of 62 province-days equal, from 52).

**A note for anyone modelling ρ (registry → report).** The same sentence
states why laboratory positives run slightly *above* new confirmed cases:
*"(14) reprélèvements positifs ont également été rendus, portant à 53 du
jour"*, against 39 new confirmed cases — 39 + 14 = 53. (The same report's
laboratory sentence says *18* reprélèvements, which does not close; sitrep 080
contradicts itself, and its whole daily block is displaced by one row — see
`notes/2026-08-22-pipeline-audit.md`.) Re-swabs
of already-confirmed patients test positive again. Positives and new cases
are different events, and the gap is re-testing, not unreported cases.

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

> **Corrected in `-r4` above.** They do print it — above the labels rather
> than beneath them — and the reader searched only downward. The coverage
> figures here, and the sitrep 061 paragraph, are superseded.

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
