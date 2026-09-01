# Adversarial review of the pipeline, and the fix pass

Date: 2026-08-17 Project: ebola-bdbv-data Tags: review, extraction, streams,
registers, provenance

## Context

Seven independent adversarial reviewers were run over the whole pipeline, one
per attack surface: safety-net/build discipline, aggregation & registers, fetch
& provenance, stream mathematics, cross-validation, table geometry, and an
end-to-end reader who transcribed ~250 cells from eight adversarially chosen
reports by hand. Every claim below was re-verified against the repository or the
pages before anything was changed; the fixes then went in as one coherent pass.
All 96 tests pass; `make build/streams/figures/compare/
doc` all run clean.

## What was wrong, by consequence

**Extraction (the table-selection and role-zipping layer; the cell-reading
geometry was verified sound — 2,743 cumulative cells against an independent
pdftotext cross-check, zero disagreements).**

- Sitrep 087 prints a *daily* table and no cumulative one; the cumulative spec
  claimed it and stored the day's 57 new Ituri cases as `cum_cases` (true
  cumulative that day: 4,381). Fixed with a fourth declared layout
  (`zone_daily`, discriminated by "dont décès parmi les nouveaux confirmés") and
  a forbid on the cumulative spec; its identity now closes on `new_cases` (87 =
  57+15+15).
- Sitreps 090–093: the head page carries only the Ituri block, the intra-CTE
  deaths column has one numeric cell there, the classifier dropped it, and the
  ordered zip slid `Total décès` into `deaths_treatment_centre` leaving
  `deaths_total` null. Ituri's intra-CTE deaths for 12–15 Aug (15/14/15/17)
  existed in no artefact. Fixed by mapping any page that resolves a different
  column set than the chain's best page **by x-position against that reference
  page** — one table, one column set.
- Split labels: `Sous total`, `TOTAL NATIONAL`, `Haut Uélé` drawn across two
  label cells were read from the rightmost fragment — 013's subtotals became
  `national`, 087's national total became a zone named `NATIONAL`, the summary
  filed Haut-Uélé's 135 cases under a zone `Uélé`. Fixed: the joined text
  decides when it names a level.
- Wrapped names: `Echantillons sans fiche` (name split onto neighbouring grid
  rows) was silently dropped on 006/009/010/011/013 — exactly the −6 residuals
  sitting as `fails`. Recovered; both identities now close.
- Sitrep 058's page-5 continuation (two provinces + national total) sits above
  three paragraphs of prose that outvote its rows in the classifier; the page
  mapped to nothing and was silently dropped. Recovered via the same x-remap;
  identity closes at 1926.
- Sitrep 067's table opens with a heading plus ONE data row (the Ituri province
  row) at the foot of page 2; one row cannot classify, the head was excluded,
  and 29 zones/2,202 cases lost their province. (The source did NOT omit the row
  — my earlier claim, and one reviewer's, was wrong; the end-to-end reader had
  it right.) Recovered; identity closes.
- Sitreps 017 and 033 print no per-zone table; the provincial summary was
  emitted as `zone_cumulative`. A structural guard (row names majority
  provinces) now refuses the zone route; both fall to the summary route. The 033
  register entry stands as defence in depth.
- The provincial summary's `IGNORED` slot (meant for the never-numeric
  zones-touched column) swallowed `Nouveaux cas confirmés (24h)`: `new_cases`
  was null on all 348 summary rows. Fixed; 020 prints Ituri 18 and we now read
  it.
- A leading footnote marker (`* Haut Uélé`, sitrep 090) failed the
  starts-with-a-letter check and dropped a whole summary row (−119).

**Aggregation and registers.**

- The identity now runs over the four daily-flow columns too (it never did; 102
  daily disagreements sat under `reconciled = ok`, and the 090–093 column shift
  lived there). After the extraction fixes, 7 province-days disagree with their
  printed row — reported loudly, page reads pending.
- All register loaders are now fail-closed and repo-root-relative: a missing
  file, an absent or ambiguous document, an unknown province spelling, a
  duplicate entry, and an entry whose licensed gap no longer occurs are each
  hard failures. (Before: `rejected_routes` and `zone_province_overrides`
  silently loaded as empty from any other working directory — Nord-Kivu's early
  series off 6× with no message.)
- Register content: 059's Nord-Kivu deaths note quoted wrong absolutes (96 vs
  100 printed; the gap −4 was right) — corrected. New page-read entries for the
  two open disagreements: 083 Nord-Kivu deaths −1, 089 Ituri deaths −1 (both
  pages genuinely do not close). `Echantillons sans fiche` entries extended to
  006/009/010/011 as `none`; on 013 the page itself settles it — the printed
  Ituri subtotal 110 = zones 104 + the row's 6 — so from 013 the pool is Ituri's
  and the identity checks that placement.
- 256 province-reports reconcile exactly, 9 verified exceptions, 0 open.

**Streams (the modelling contract).**

- Every bin's observation `time` is now its **last report day**, not the nominal
  calendar end. The trailing bin held 4 days of data under a 7-day label: every
  stream's newest point read ~43% low in daily rate and all six showed a fall
  where five had risen — at exactly the point an R_t fit weighs most.
- The unassigned pool: summed within a report (sitrep 015 prints two pool rows;
  last-value-wins dropped one) and zeroed on any report day that prints the
  province without it (17 phantom Ituri cases forward-filled for 23 days, then
  retired as −17 inside the newest week). `cases_ituri` now agrees with the
  printed row on 65/67 dates; the remaining two are sitrep 059's registered
  self-disagreement.
- The ascertainment streams now read the **printed province rows** (whole by
  construction) with the zone breakdown as a per-date check in `meta.json` — the
  zone-summed route's both-columns-non-null row filter was a selection
  correlated with the quantity estimated, and under the column shift it emitted
  a final-week community fraction of 1.000 against a printed 0.55. Final week
  now: 75/136 = 0.55.
- `populations()` folds accents on both sides and refuses a zero; the
  printed-row join is sorted before `final_gap`; the `is_in` deprecation is
  gone.

**Diagnostics (a retraction).** The Ituri residual right-skew (+0.62) I
presented as a batching signature was an artefact: the smoother clipped the
source's two negative revisions to zero *inside its window*, lifting every
neighbouring residual. Excluded properly the skew is −0.12 — both provinces
near-symmetric. The figure, the dashboard, and their prose now say so, and the
dashboard imports the one smoother instead of carrying a copy.

**Caveats (the largest single omission).** 25 early reports footnote their
headline cumulative as under harmonisation — from sitrep 026 stating it *omits*
confirmed community cases and escapees (an undercount) — and sitrep 011
footnotes the deaths as underestimated. All were recorded `kind=none`. Now:
`harmonisation_pending` (18), `harmonisation_undercount` (7),
`deaths_underestimated` (2), flagged per report in the data document.

**Comparisons.** The INRB comparison's denominator is disclosed machine-readably
(`compare_meta.json`): 584 of our zone-day rows — the newest reports — have no
INRB counterpart and sit outside every agreement figure. Cross-lineage spelling
divergences are mapped onto one key so they can *disagree* instead of vanishing
— which surfaced a 14th disagreement no run had ever seen (064 Lubunga, deaths 0
vs 1, clustering with the two known 064 Tshopo disagreements). The prose route
now enters the national comparison: 70/70. `data.qmd`'s typed `2127` (which
rendered a wrong 2,114) is gone; every number is read from artefacts. The INRB
clone is pinned by a committed `external.lock` and checked out at that commit;
the epiforecasts scan is a committed copy with provenance.

**Fetch/provenance.** No damage had occurred (all 83 pick URLs verified live and
byte-exact), but the layer was structurally blind to revision. Now: the fetcher
HEAD-checks every held report's pick URL against the held byte count and stops
on a mismatch; `make check` spot-checks across the whole archive (not just the
newest five), compares Content-Length to the manifest, treats a network error as
UNVERIFIED rather than alive, runs its staleness clock on situation reports
only, and exits 4 (`STALE`) when the source goes quiet — visible to a `--quiet`
cron. `make refresh` exists (check's advice named a target that didn't). The
version-marker vocabulary covers `corrected`, `v2`, `rev`, `MAJ`, `bis`,
`update`; a later upload that loses on markers is announced. ISO filename dates
parse. Undated archive names are a hard failure in the fetcher *and* every
extractor. The French date parser accepts `1er` and month abbreviations.
`PROVENANCE.tsv` is pruned of 469 rows about files from abandoned layouts, and
its writer is append-only on (path, hash) — a revision now leaves a trace
instead of destroying one.

## Still open, deliberately

- Page reads for the 7 daily-block disagreements (80×3, 81, 83, 88, 89 — 81's is
  already explained by its register note) and the one row on 064 where
  community + intra-CTE ≠ total.
- The INRB disagreement adjudication session (14 rows now; alert upstream vs
  adopt) — deferred by Vince earlier, unchanged.
- Their upstream defects worth reporting when we do: the `2026-06-25]` date,
  `17-`/`1]` value cells, and a literal zone `"NA"` carrying 42 zone-days (it
  explains their persistent row-count offset). Also: the reference repo's Ituri
  population (13.6M) cannot be reconstructed from WorldPop and would exceed
  Nord-Kivu's; ours (6.32M) is the defensible value.
- Unported tables: laboratory (the ascertainment denominator), alerts, contacts,
  care occupancy — and sitrep 070's Tableau 8, a per-zone table of infected
  front-line personnel (123/36) nothing reads.
- Sitreps 006 and 008 print prose nationals that disagree with their own tables
  (64 vs 61; 88 vs 91) — source findings, not consumed anywhere.
- `_DATE8` beats `_DATE6` when a filename carries both an upload timestamp and
  the report's own DDMMYY (names files only; the data date comes from the page).
  Override register keys are basenames, not URLs.
- No dependency graph: `make streams` does not rebuild `build` first; whether to
  move to file-based rules or Snakemake is a design decision to take together.
- `uganda_exports.tsv` sits in `streams/` with a cumulative convention among
  weekly-incidence files; renaming it touches the modelling repo's contract.

## Next

Render pages are live on thuja:8790. The modelling repo should re-pull the
streams: the newest observation moved on every stream (time and value), and the
ascertainment series changed shape materially.

## Addendum (model-contract check, 17 Aug)

Verified against ../ebola-camdl: every observation stream the four models
consume exists here under the same name, column layout, and file shape
(including `deaths_split_*` as the beta-binomial denominator and
`uganda_exports`). All current fits use PMMH/PGAS, whose particle filter lands
EXACTLY on each observation time and scores `(previous obs, this obs]` --
confirmed against the camdl run spec (§14) -- so the last-report-day observation
times are not merely compatible, they are the convention the engine implements.
One caveat recorded: the ODE likelihood path requires the output schedule to
contain every observation time; a future ODE fit needs `output { at = [...] }`
aligned to the data. Obs counts are equal or better than the reference streams
everywhere (deaths gain one early bin per province), values differ only where
the reference disagreed with the printed series, and three Haut-Uele streams
plus the caveat/summary series are new.
