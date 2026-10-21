# A province's flow file starts after its first report, so its first cases are not in it

## Done: the openings are in `meta.json`, and Sud-Kivu was a misfiled zone

`meta.json` now carries `opening`: for each province, the date and value of the
first case and death cumulative, read from the same zone-summed cumulative the
streams difference, so opening plus emitted equals the final cumulative for
every province. A test asserts it.

Sud-Kivu's failure to close (1 + 3 ≠ 3, below) was not a quirk of the opening.
Sitreps 010 and 011 filed Kalunguta, a Nord-Kivu zone, under Sud-Kivu, and the
forward fill kept that one case in Sud-Kivu's stream on every later day.
`meta.json` had recorded it all along: `cases_sud_kivu` disagreed with the
printed province row on all 131 dates, by exactly 1, but `vs_printed` was
recorded and never asserted. The front pages state the membership («NORD-KIVU :
Butembo, Goma, Oicha, Kalunguta et Katwa»), and two rows in
`registers/zone_province_overrides.tsv` now apply it. Sud-Kivu agrees with its
printed row on 131 of 131 dates, and every province's case and death stream ends
at a zero gap, which is now a test. The published Sud-Kivu stream loses one case
it never had; Nord-Kivu's Kalunguta case is counted from 24 May instead of 27
May.

Date: 2026-10-20 Project: ebola-bdbv-data Tags: stream-contract, differencing,
provinces

## Context / question

The case and death flow files (`cases_<province>.tsv`, `deaths_<province>.tsv`
and their daily, community-death and excluding-backlog companions) are built by
*differencing* the source's printed cumulative: each row is how far the
cumulative moved since the previous report. Differencing needs a previous value,
so the first report on which a province appears supplies its *opening level*,
and the file's first row is the movement from there to the next report. The
opening level itself is in no row. The question is what that omits, and whether
a consumer can see it.

## Measurements

The opening level per province, against what its daily case file emits, as of
the archive through sitrep 157 (data date 2026-10-18). "Opening" is the first
printed cumulative in the zone-table panel
(`data/build/series/
province_series.csv`); "emitted" is the sum of
`cases_daily_<province>.tsv`.

| Province    | First printed | Opening cases / deaths | Emitted cases | Final cumulative | Opening + emitted |
| ----------- | ------------- | ---------------------- | ------------- | ---------------- | ----------------- |
| Ituri       | 2026-05-18    | 30 / —                 | 6 930         | 6 960            | 6 960             |
| Nord-Kivu   | 2026-05-18    | 3 / —                  | 2 081         | 2 084            | 2 084             |
| Haut-Uélé   | 2026-07-10    | 1 / 1                  | 414           | 415              | 415               |
| Tshopo      | 2026-07-10    | 4 / 2                  | 69            | 73               | 73                |
| Bas-Uélé    | 2026-08-12    | 1 / 1                  | 12            | 13               | 13                |
| Sud-Ubangi  | 2026-09-10    | 1 / 1                  | 1             | 2                | 2                 |
| Nord-Ubangi | 2026-10-16    | 2 / 1                  | 0             | 2                | 2                 |
| Sud-Kivu    | 2026-05-21    | 1 / —                  | 3             | 3                | 4                 |
| National    | 2026-05-18    | 33 / —                 | 9 519         | 9 552            | 9 552             |

For the national file the omitted opening is the 33 cases the first reports
already held, which is a statement about when the archive starts rather than
about any one day's incidence. For a province that joins mid-outbreak it is the
province's arrival: Tshopo's first 4 cases and 2 deaths, Nord-Ubangi's entire
record to date.

**Sud-Kivu does not close** (1 + 3 ≠ 3). Its stream opens on a reading the
zone-table panel does not show, most likely a 0 from another route on
2026-05-21, which would put all three cases in the flow file. That is inferred,
not traced; it needs checking before it is stated as fact.

## Interpretation

This is correct differencing and not a defect: a first report says how many
cases a province has, not how many arrived that day. Some of Tshopo's 4 may have
been confirmed over several earlier days, and nothing on the page says when.
Emitting the opening level as one row would invent an interval.

It does have two consequences that a consumer cannot see from the province file
alone.

1. **The province files do not sum to the national file over a province's
   arrival.** On the day a province joins, its cases move the national
   cumulative but appear in no province row. `meta.json` records the per-bin
   identity *national = emitted provinces + dropped provinces + orphan pool +
   unattributed*, and these openings should land in the unattributed term. That
   follows from the construction; I have not checked it bin by bin.
2. **A model fitting a province's incidence from the province file misses the
   seeding cases.** For the large provinces this is negligible. For a province
   whose record is a handful of cases it is most or all of the signal: Nord-
   Ubangi's file has one row, and it is a zero.

## Options

- **Leave the files alone and publish the openings.** Add each province's
  opening level, its date and its sitrep to `meta.json` (or a small reference
  table beside the streams), so a consumer can add a seeding term at the right
  date. Nothing in any stream file changes, so this is not breaking.
- **Emit the opening as a row** whose window starts at the outbreak's first
  report day (or at a declared earlier date). This puts the cases in the file
  but asserts an accumulation window the source never stated, and changes the
  first row of nine files, so it is a breaking contract change.

**Recommendation: publish the openings in `meta.json`. Solid.** It adds the
missing fact without inventing a window, and it is additive.

## Next

- Trace Sud-Kivu's opening reading.
- If the recommendation stands: add `opening` to each province's `meta.json`
  entry, generated from the same panel the streams difference, and a sentence to
  each case and death family in `registers/stream_families.tsv`.
