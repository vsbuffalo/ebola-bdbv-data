# Adversarial audit of the extraction pipeline

Date: 2026-08-22 Project: ebola-bdbv-data Tags: audit, data-quality, validation,
streams, provenance

Five independent reviewers, each given a different failure-mode lens, a random
sample of situation reports, and instructions to work from the PDFs rather than
from our own documentation. Every finding below that changes a number or an
action was re-verified by hand before being written down.

---

## Executive summary

**The spine of the pipeline is sound. The defects are at the edges, and they are
mostly gaps rather than errors.**

Nothing in this audit found a wrong case or death count in the series the
modelling repo actually fits. Transcription was checked value-by-value against
the printed pages on a random sample and came back **608 of 608 zone-table
values and 78 of 78 province-summary values exact**, with row counts matching
the printed tables in every report. A reviewer independently re-implemented the
whole temporal construction — grid, bins, differencing, timestamps — and
reproduced **all 33 stream files row-for-row on every column**. Report-date
semantics are correct on **87 of 87** reports. The build is byte-identical on
re-run. The reconciliation gate, the missing-value handling, the unassigned
pool, and the zone→province mapping all held up under direct attack.

**How much did numbers move?** Very little, and in one direction only — slightly
_away_ from precision I had claimed:

| quantity                  | before the audit | after                           | consequence                                      |
| ------------------------- | ---------------- | ------------------------------- | ------------------------------------------------ |
| γq/τ (pins the γ–q ridge) | 0.41 – 0.54      | **0.39 – 0.54**                 | one corrupt report removed; conclusion unchanged |
| δ (care exit rate)        | 0.112 /day       | **unchanged**                   | the recovery gap sits outside the ledger window  |
| f_cfr (in care)           | 0.456            | **unchanged**                   | same reason                                      |
| ρ ≈ 1                     | ρ ≈ 1            | **unchanged, better supported** | see below                                        |
| laboratory totals         | 3,076 / 13,914   | 3,115 / 14,101                  | already shipped as `-r1`                         |

The one claim that genuinely weakened is one I made this morning and then
over-corrected this afternoon. A reviewer argued the laboratory licence rule
selects on the outcome and therefore biases the ρ evidence. Checked directly, it
does not: comparing positives against new cases _within the same sentence_,
accepted days give **1.194** and refused days **1.198** — indistinguishable. The
reviewer's contrary evidence traced to a single corrupt report (below). **ρ ≈ 1
stands.** What the licence rule _does_ bias is testing _volume_: accepted Ituri
days have a median of 156 samples against 290.5 on refused days, so anything
using testing effort as a denominator is biased low.

**How serious, overall?** Two findings are serious enough to change what should
be fitted today; three more are latent traps that will bite the next consumer;
the rest are documentation drift. Ranked by whether they change a decision:

1. **Sitrep 080 (2 August) is structurally corrupt and we publish from it
   anyway.** Its daily block cannot be aligned to its rows: `Adja` is printed
   with 11 cumulative cases but 49 new cases and 23 deaths in 24 hours, and the
   zone rows sum to 148 new cases against a printed national 58. Fifty of its 56
   rows have a letality figure inconsistent with their own cases and deaths; the
   next-worst report has four. Every anomaly I chased on 2 August today — the
   98-versus-39 new-case disagreement, the laboratory misread — is this one
   report. The pipeline _detects_ part of it (`meta.json` lists 2026-08-02 under
   `dates_disagree`) and publishes the rows regardless.
2. **Two series begin late because a printed front-page tile is never read.**
   `cumul_recovered` starts seven weeks after the source begins printing it (36
   of 87 report dates populated); the confirmed-death series opens ten days
   late, with 42 deaths already accumulated and outside every emitted row. Both
   gaps sit in the exponential-growth phase, which is exactly the window that
   identifies the growth rate and the deaths-per-case ratio.
3. **`days_covered` carries two incompatible meanings** under one documented
   definition — honest for the cumulative-differenced streams, overstated for
   the flow-summed ones by up to a factor of 20 on individual rows.
4. **Eight published observations are negative**, one of them in a _weekly_
   stream that carries no `flags` column at all. A negative count cannot be
   evaluated by any count likelihood.
5. **The modelling repo is fitting pre-fix laboratory data** — its vendored
   copies predate the `-r1` correction, and the `-r2` province streams are not
   vendored at all.

**Would any of this change the modelling conclusions reached so far?** The
priors work stands: ρ ≈ 1, f_cfr ≈ 0.46, δ ≈ 0.115/day, and the γ–q ridge
constraint all survive, with γq/τ shifting by 0.02 at the low end. What should
be treated as **provisional** is anything fitted to the recovery stream
(`rho_rec`, and δ where it leans on recoveries) and anything that leans on the
first ten days of the death series — not because those fits are wrong, but
because they were fitted to series with unannounced holes at the left edge.

---

## Method

Five reviewers, five orthogonal lenses, chosen so that redundancy would not be
mistaken for confirmation:

| lens                | question                                                        |
| ------------------- | --------------------------------------------------------------- |
| source fidelity     | does each published value equal the printed one?                |
| accounting closure  | do the source's own identities hold in our data?                |
| stream construction | are flows, stocks, windows and timestamps right?                |
| column semantics    | does a heading mean the same thing in sitrep 10 as in 90?       |
| silent omission     | what is dropped, and is the drop correlated with its own value? |

Sampling was a seeded random draw over all 87 reports. **Sitreps 77 and 18 were
anchors given to all five**, so agreement could be measured on identical
evidence rather than inferred; each reviewer also received four unique reports
spanning early and late vintages. All were told the PDF is primary, that
docstrings and comments are explicitly not to be trusted, that every finding
must be classified _our defect_ versus _source defect_, and that a clean result
is a real result that must be reported as such.

---

## What came back clean

Stating this first, because an audit that reports only failures misrepresents
the object. These are positive results, each from direct verification:

- **Transcription.** 608/608 zone-table values and 78/78 province-summary values
  exact across six reports; row counts match the printed tables exactly (55, 29,
  30, 39, 41); no row dropped or invented. Wrap hazards (`Boma\nMangbetu`,
  `Makiso-\nKisangani`, `Autres ZS\n(données non
  ventilées)`) all correctly
  aligned.
- **Temporal construction.** An independent reimplementation reproduced all 33
  streams row-for-row on every column. `days_covered` tiles the calendar exactly
  in all 30 files carrying it — no overlap, no hole, no off-by-one, including
  first rows and rows after every publication gap. Observation timestamps are
  the correct right edge for an engine accumulating over `(t_{k−1}, t_k]`.
- **Date semantics.** Filename date == printed _Date de rapportage_ == panel
  date on 87 of 87 reports. No data date carries two reports. The
  filename-vs-data-date defect recorded in `report_date.py` is genuinely fixed.
- **Flows versus stocks are correctly typed throughout.** Nothing is differenced
  that should not be; nothing that should be differenced is emitted as a level.
- **Missing markers never become zeros.** `ND`, `NA`, `N/A`, `N/D`, `—`, `–`,
  `-`, `*` and blank all become null at every level. No counter-example was
  found anywhere in the panel — this is the single most dangerous defect class
  in this kind of work and it is clean.
- **Backlog is handled honestly.** Traced end-to-end on sitrep 077: a three-day
  publication pause emits 245 cases at `days_covered = 3` with
  `flags = consolidating`, not 245 attributed to one day. Withdrawals and
  re-releases (Haut-Uélé −3 on 18 July, +7 on 30 July) both survive as signed
  increments with flags.
- **Column meanings are stable across 87 reports.** Cumulative cases are
  confirmed-only in all four table layouts; the death-split triple is verbatim
  stable from sitrep 060 to 096; the split identity _community + intra-CTE =
  total_ holds on **759 of 760** rows that print all three.
- **Zone→province mapping.** 59 of 60 canonical zones hold one province across
  all 87 reports; spelling variants fold correctly to one series.
- **The registers are accurate.** Every entry checked against its PDF in
  `reconciliation_exceptions.tsv`, `rejected_routes.tsv` and
  `zone_province_overrides.tsv` was correct and hash-pinned.
- **The build halts rather than guesses.** An unrecognised province name exits
  non-zero instead of dropping a row; all-null groups are prevented from summing
  to a fabricated zero; empty bins are dropped rather than emitted as zeros.

---

## Findings

### Converged — found independently by more than one reviewer

**C1. The front-page dashboard is read in only one layout. (4 of 5 reviewers)**
_Our defect. Verified._

`extract_banner.py` locates a tile's value by scanning **downward** from its
label. The early vintage draws the tile the other way up — the row of values
sits **above** the row of labels. Every report in that vintage refuses.

Measured consequence: `cumul_recovered` is populated on **36 of 87** report
dates and the stream opens 2026-07-12, although the source prints the figure
from at least 2026-05-22 (sitrep 008 prints 0, 013 prints 1, 038 prints 112, 051
prints 254). `patients_isolated` is missing on 15 report-days where the page
prints it.

`CHANGELOG.md` under `data/2026-08-15-r8` states _"Early reports print no such
tile; the value is null, never inferred."_ The pages contradict that.

**C2. A footnote digit welded to a province name demotes the row to a health
zone. (2 of 5) — _Our defect. Verified._**

Sitrep 033 prints its Nord-Kivu row as `Nord-Kivu1`, where `1` is a footnote
reference. `level_of()` strips `*†‡` as typography but not digits, so the row
classifies as `zone`. Values are correct (73 cases, 43 deaths); only the
classification is wrong. Same on sitrep 028 (40/24).

Consequences: a **false** `identity = fails` with residuals of exactly −73 and
−40, in a validation channel with only seven non-`ok` entries; and on sitrep
033, which prints no zone table at all, Nord-Kivu vanishes from the only
province-level extraction for that date. **No stream value moves** — verified:
the national series carries 13 and 38 on those dates, because streams read the
printed national row rather than summing provinces.

**C3. `days_covered` means two different things. (2 of 5) — _Our defect.
Verified._**

For cumulative-differenced streams (`cases_*`, `deaths_*`) the count genuinely
covers the whole declared window, because the cumulative absorbs unreported
days. For flow-summed streams (`lab_*`, `community_deaths_*`) it does not — the
count is the sum of the source's own 24-hour figures over report days only.
Worst rows verified:

| stream                | row        | declared | actually covers       |
| --------------------- | ---------- | -------- | --------------------- |
| `lab_daily_haut_uele` | 2026-08-15 | 20 days  | one day (3 positives) |
| `lab_daily_nord_kivu` | 2026-08-15 | 12 days  | one day               |
| `lab_daily_ituri`     | 2026-08-15 | 9 days   | one day               |

Whole-stream coverage (Σ`n_report_days` / Σ`days_covered`): `lab_national` 0.82,
`community_deaths_haut_uele` 0.62, against 0.93 for `cases_national`.

Currently harmless **by accident**: no fit binds the lab streams as counts, and
the community-death streams are fitted as a proportion, for which the window is
irrelevant. The guard is downstream and unwritten.

**C4. Sitrep 059's fifth column is notified deaths, stored as community deaths.
(2 of 5) — _Our defect, latent. Verified._**

Sitrep 059 is the only report whose zone table has five value columns, headed
`… Nouv. cas | Décès notif.`. `Décès notif.` is the day's _notified confirmed_
deaths — the later vintage's `Total décès confirmés`, not its
`Décès
communautaires (Swab+)`. Because the spec assigns the fifth value column
positionally to `DEATHS_COMMUNITY`, the wrong quantity lands in
`zone_table.csv`.

It does **not** reach the streams: the community-death builder requires both
columns non-null and sitrep 059 prints no total, so 12 July is filtered out.
That is luck, not design — a null in a neighbouring column, not the spec,
prevented publication.

**C5. Three isolation censuses discarded because a sibling row does not close.
(2 of 5) — _Our defect, over-refusal. Declared._**

Sitreps 046, 053, 058 print unambiguous censuses (609, 680, 753) that are thrown
away because the confirmed/suspect decomposition fails to add. These are the
three highest censuses in that window. The refusal is recorded in
`banner_status.csv`, so it is honest — but over-broad.

### Single-reviewer, verified by hand

**C6. Sitrep 080 (2 August) is structurally corrupt and published anyway. (2 of
5, independently) — _Source defect, our handling defect. Verified — the most
consequential finding in the audit._**

**The offset is exact and diagnosable**: the value printed on row _i_'s line
belongs to row _i−1_. One reviewer established it from pdfplumber word geometry,
and the arithmetic is decisive — the figures on the `Adja` line (49 new · 13
community · 10 intra-CTE · 23 total) are exactly the sum of the 27 Ituri zone
lines _below_ it, and the figures on the `Beni` line (22 · 7 · 4 · 11) are
exactly the sum of the 12 Nord-Kivu lines below it. The displacement hits all
four daily columns at once.

Verified directly: `Adja` carries 11 cumulative cases and 1 cumulative death,
yet the same row reports **49 new cases and 23 deaths in 24 hours**. The zone
rows sum to **148** new cases against a printed national **58**. The letality
column is displaced by one row _and_ stale — `Nord-Kivu` prints 58,5 %, which is
sitrep **077's** Tchomia figure.

Corpus-wide, 82 reports carry a letality column; only five have any inconsistent
row, and sitrep 080 has **50 of 56**. The next worst has four.

What we publish from it: `community_deaths_daily_national` 40 community / 72
split for 2 August, against a national cumulative-death movement of 50 and a
narrative of 47; Nord-Kivu and Haut-Uélé published as 0/0 while the page's own
footnote states 14 confirmed deaths in Nord-Kivu; Ituri contributing no
observation at all. The pipeline lists 2026-08-02 under `dates_disagree` in
`meta.json` and publishes the rows regardless. Three mechanisms exist for
exactly this case — `rejected_routes.tsv`, `reconciliation_exceptions.tsv`, and
the `flags` column — and none is used.

**Impact, measured:** removing sitrep 080 moves the escape fraction from e_obs
0.2883 to 0.2798, and γq/τ from 0.405 to 0.388. The clean-window figure (0.352 /
0.544) is untouched, because 2 August is already excluded there as a
consolidating day. So the published constraint becomes **γq/τ = 0.39 – 0.54**.

**S1b. Sitrep 060: Sud-Kivu's daily block carries a running subtotal of Ituri

- Nord-Kivu.** _Source defect, recorded by us as Sud-Kivu data. Relayed._

One text line prints `Sud-Kivu 3 1 33,3 % 47 8 14 22`, but Sud-Kivu has 3
cumulative cases and the page's own front matter says Miti-Murhesa is at its
48th day without a confirmed case. Those four numbers are Ituri + Nord-Kivu
(42+5, 5+3, 13+1, 18+4). Table 1 prints Sud-Kivu's 24 h new cases as 0. We
record 47/8/14/22 as Sud-Kivu. Contained — Sud-Kivu is a dropped province, so it
reaches no published stream — but the reconciliation labels it `no_parts`, which
is exactly the cover it sits under.

**S1c. The daily-block identity is computed, printed, and does not gate the
build.** _Our defect, process. Relayed._

`aggregate_provinces.py` derives `daily_reconciled` and prints failures to
stderr, but the exit code is driven by the cumulative tally alone, and the
Makefile absorbs exit 1. Seven daily-column failures are open. One of them
**moves a published number**: sitrep 083's Haut-Uélé row feeds
`deaths_split_haut_uele`, and the narrative says Haut-Uélé had exactly one death
that day (_"7 nouveaux cas… dont 6 vivants et 1 décès confirmé par swab"_)
against a printed province row of 2.

Related: `apply_exceptions` can only rescue _cumulative_ columns, so a daily
exception has nowhere to be registered even when it is genuine.

**S1d. The province→national identity runs on one column and gates nothing.**
_Our defect, coverage. Relayed._ `reconcile()` is called once, with `cum_cases`.
Three reports currently fail it on cases (053, 057, 089) and four on deaths
(053, 057, 059, 083), with no register entry and no build consequence.

**S1e. Sitrep 064's national `Total` row does not split correctly.** _Source
defect, detected, non-gating._ `18 + 18 = 36 ≠ 29`, and the province rows sum to
86 new cases against a printed 56. This is the single failure of the community +
intra-CTE = total identity in the corpus (759/760). It slips past the
community-death date check because that check never compares the intra-CTE
column.

**S2. The confirmed-death series opens ten days late.** _Our defect. Verified._

`deaths_national` opens 2026-06-02; `cases_national` opens 2026-05-26. The
front-page tile prints cumulative confirmed deaths well before that — sitrep 015
(29 May) prints **42** — from the same tile row the banner reader already
parses. Those 42 deaths, of 2,434 published nationally, sit outside every
emitted row, in the growth phase.

**S3. National-only laboratory sentences are invisible — not parsed, not
refused.** _Our defect. Verified._

The laboratory extractor anchors segments on province names, so a sentence with
no province name opens no segment. Sitreps 085–087 each print an explicit, fully
licensable national line — _"326 échantillons ont été analysés, confirmant 89
nouveaux cas de MVE (positivité : 27,3 %)"_ — and `lab_prose_status.csv` records
`n_parsed = 0, n_refused = 0`. **The status file asserts a clean read of a page
it never saw.** That is the difference between a declared gap and a silent one.

**S4. The laboratory licence applies a weaker standard to zero than to
nonzero.** _Our defect. Verified._

A nonzero result requires a printed positivity percentage; a zero result is
licensed on words alone (_"tous négatifs"_). When INSP stopped printing
per-province percentages in August, the only surviving province on three days
was Sud-Kivu at zero positives. `lab_daily_national` therefore records **0
positives / 4–5 tests** on 5, 12 and 13 August, when Ituri alone had ~250–300
samples at 20–32 % positivity.

The refused days state their numbers explicitly — sitrep 090: _"80 résultats
positifs (249 échantillons analysés), dont 67 nouveaux cas"_ — and are refused
only for lacking a percentage. **They are recoverable.**

**S5. Eight published observations are negative.** _Source revisions, our
handling. Verified._

`cases_ituri` −39, `deaths_ituri` −23, `cases_haut_uele` −6, `cases_nord_kivu`
−4, `deaths_haut_uele` −3 and −1, `deaths_nord_kivu` −2 and −1. Keeping source
revisions as signed increments is the right policy and is declared — but the
**weekly** files carry no `flags` column at all, so `deaths_haut_uele`'s −1
arrives unannounced, and no count likelihood can evaluate it.

**S6. Kalunguta is carried into Sud-Kivu on sitreps 010–011.** _Our defect.
Relayed, not independently re-verified._

The front page lists Kalunguta under Nord-Kivu; a merged label cell in Tableau
II hands it to Sud-Kivu. The same failure mode is already registered for
Rwampara on sitrep 009, but no entry covers Kalunguta. Because Sud-Kivu is a
dropped province the effect is confined to a phantom series in the
forward-filled grid and a 1-unit disagreement in `meta.json`'s
`dropped_provinces`. This is the only zone in the corpus attributed to two
provinces.

**S7. `deaths_split_*` and `deaths_*` are different death populations.** _Source
property, under-documented here. Relayed._

Between 12 July and 18 August national cumulative confirmed deaths moved 1,758
while the printed daily splits sum to 1,414 — **344 deaths (19.6 %) never enter
the daily split**, and they concentrate on consolidation and harmonisation days.
So the community fraction estimated on the split is conditional on
classification, not a simple subsample. Known downstream; absent from this
repo's `CHANGELOG.md` and `README.md`.

**C7. `LETALITY` is documented as a per-row check and is not implemented. (2 of
5, independently) — _Our documentation defect. Verified — and the recommendation
is good._**

`tablespec.py` states the letality column is _"a free per-row check on the two
columns that ARE used."_ It is read for positional alignment, never emitted, and
no code consumes it. Both reviewers reconstructed it independently and both
found it strong: it closes on **2,808 of 2,870 rows across 67 reports**, and of
the 62 failures, 50 are sitrep 080. The remaining twelve are almost all the
source carrying the _previous day's_ letality forward — sitrep 073's Beni prints
69,8 %, which is its own previous-report pair 30/43, against its current 34/44 =
77,3 % — plus two one-off typos.

**This check, had it existed, would have caught the worst finding in this audit
automatically**, and it is nearly free: the column is already parsed for
positional alignment and then discarded.

**S9. `README.md` route and coverage tables are stale.** _Documentation._ Zone
table "74" reports (actual 78); provincial summary "70" (actual 75); national
dashboard _"not yet read"_ (three streams ship from it); "all 83 held reports,
same-day (15 Aug)" (87 reports to 18 Aug); "13 TSVs" (33).

**S10. The modelling repo is fitting pre-fix laboratory data.** _Verified._ Its
vendored `lab_daily_national.tsv` and `lab_national.tsv` differ from the current
build — they predate the `-r1` death-split correction — and the `-r2`
province-level laboratory streams are not vendored at all, so the change that
would let them drop ρ_lab is not yet available to them.

### Disputed — a reviewer's claim that did not survive checking

**D1. "The laboratory licence selects on the positives-to-cases ratio."** _Not
supported._

A reviewer argued the licence rule excludes exactly the days where positives
most exceed new cases, and therefore biases the ρ evidence — reporting 1.028 on
accepted days against 1.199 on refused. Checked on the cleaner basis, where both
numbers come from the _same sentence_:

|                         | positives / new cases |
| ----------------------- | --------------------- |
| accepted by the licence | **1.194**             |
| refused by the licence  | **1.198**             |

Indistinguishable. The reviewer's accepted-side figure was depressed by a single
day — sitrep 080, the corrupt report of S1, where the panel records 98 new cases
against the sentence's 39. On the other four accepted days the panel and the
sentence agree exactly.

**The ρ ≈ 1 conclusion is unaffected.** What the licence _does_ bias is testing
volume: accepted Ituri days have a median of 156 samples against 290.5 on
refused days.

### The exceptions register: mechanism sound, framing wrong on two entries

_Relayed, with the arithmetic checked._

The mechanism held up under direct attack: entries are keyed on the file's
SHA-256, a stale hash stops the build, an entry licenses one exact residual, an
entry that stops firing raises an error, and a register that cannot be
hash-verified is refused rather than applied. **No entry was found that silences
a residual we caused.**

But two entries mis-describe their page. Sitrep 053's says _"The page simply
does not add up."_ It does add up — four ways, all on 149/88: the eleven zone
rows sum to it; Table 1 prints Nord-Kivu as 149/88; the narrative states _"Un
total de 149 cas confirmés et 88 décès"_; and Table 2's own `TOTAL` closes on it
(1,556 + 149 + 3 = 1,708). Only Table 2's Nord-Kivu row dissents. **Our value is
right and the page says so four times** — yet `meta.json` records this as a
`worst_gap` of 5 against the source. Sitrep 083 is the same shape.

The converse is also unstated: on sitreps 034, 055, 059, 063, 081 and 089 the
national `Total` sides with the _printed province row_, so our published figure
sits the registered gap away from the page's own national arithmetic. That is a
defensible consequence of building from zone rows, but the register never says
which side the rest of the page supports.

### Identities the source offers that we do not check

The audit's most useful structural result. Ordered by what they would have
caught:

1. **Province rows = national `Total`, on every column** — runs on `cum_cases`
   only today. Catches sitreps 060, 064 and 080 outright.
2. **Row-level letality** — already parsed, then discarded. The only per-row
   check that survives when a whole column is displaced.
3. **Table 1 = Table 2** — both are already extracted; nothing compares them.
   Closes on 306/309 and 307/309, and independently adjudicates 053, 060, 064
   and 080.
4. **24 h flow ≤ the same row's cumulative** — three failures each, all real.
5. **Front page's "_Province_ (n/N)" = number of zone rows** — 258/263.
6. **The care/occupancy table's own ledger** — census(J−1) + admissions − exits
   = census(fin J), closing on 39/46 reports; the exit components summing to
   `Total sorties`, 19/20; confirmed + suspects = census, 44/46.
7. **Laboratory prose against the tables** — positives = new confirmed +
   re-swabs; new confirmed = alive + confirmed-at-death; lab deaths = the
   table's `deaths_community`. The last is asserted in a `tablespec.py` comment
   and never computed.
8. **The alerts and contact-tracing tables**, both with printed totals and
   printed rates, neither extracted.

---

## Impact on published numbers

| published quantity                | audit effect                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------ |
| `cases_*`, `deaths_*` values      | **none** — transcription exact on every value checked                                |
| γq/τ (escape-fraction constraint) | 0.41–0.54 → **0.39–0.54** (sitrep 080 removed)                                       |
| δ = 0.112 /day                    | **none** — ledger window 13 Jul–2 Aug has 19 of 21 days; the recovery gap is earlier |
| f_cfr = 0.456                     | **none** — same window                                                               |
| ρ ≈ 1                             | **none**, and better supported after D1                                              |
| laboratory totals                 | already corrected in `-r1`; ~24 report-days still unread (S3, S4)                    |
| `cumul_recovered`                 | 36 of 87 report dates; seven weeks missing at the left edge                          |
| `deaths_*`                        | 42 deaths before the window opens                                                    |

## Implications for the modelling

**Safe to keep fitting:** the national and province `cases_*` and `deaths_*`
streams, weekly and daily. Construction verified by independent re-derivation;
windows tile the calendar; timestamps are the right edge; backlog is attributed
to declared multi-day windows.

**Treat as provisional:** anything fitted to `cumul_recovered` — the stream
observes only the last five weeks and enters at a level of 333 whose entire
prior trajectory is unobserved, so `rho_rec` and any δ leaning on recoveries
should not be read off it until C1 is fixed. Likewise the first ten days of the
death series (S2).

**Do not fit as counts against an accumulated flow:** the `lab_*` and daily
`community_deaths_*` streams, until C3 is resolved.

**Will crash or corrupt:** the first count likelihood that binds
`deaths_haut_uele` (S5).

**Re-vendor:** the modelling repo is on pre-`-r1` laboratory data (S10).

## Actions, in priority order

1. Quarantine sitrep 080's daily block (S1) — it has a mechanism waiting for it
   in `rejected_routes.tsv`.
2. Implement the letality check that `tablespec.py` already promises (S8). It
   catches S1 automatically and is nearly free.
3. Read the front-page tile in both layouts (C1), which also closes S2.
4. Rename or split `days_covered` for the flow-summed streams (C3).
5. Fix the footnote-digit strip (C2) and the sitrep 059 column role (C4).
6. License an explicit `(positives, samples)` pair without a printed percentage,
   and anchor national sentences (S3, S4).
7. Add a `flags` column to the weekly streams, and decide the negative-count
   policy (S5).
8. Make the daily-block identity gate the build, and allow daily-column entries
   in the exceptions register (S1c).
9. Run the province→national identity on every column, not just `cum_cases`
   (S1d).
10. Rewrite the sitrep 053 and 083 register entries, which mis-describe pages
    that do close.
11. Correct `README.md` and the `-r8` CHANGELOG claim (S9, C1).

## What this audit did not cover

Population denominators in `meta.json`; the Uganda export stream against WHO
bulletins (no network); whether the printed cumulative is as-of the report date
or the prior evening in the early layouts; and the contact, alert and
point-of-entry tables, which no route extracts.

All five reviewers reported; nothing here is pending.
