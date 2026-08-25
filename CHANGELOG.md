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

## `data/2026-08-22-r6` — 2026-08-25 — where the record of a confirmed case is

**No stream changes and no value changes. Figures only**, so nothing a
consumer reads moves: no file under `data/build/streams/` is added, removed,
renamed or rewritten, and `meta.json` is untouched. A consumer pinned to `r5`
needs to do nothing.

**What is new** is a tenth committed figure, `docs/figures/outcomes.png`,
built by `make figures` from `--figure outcomes` and gated by `release-check`
like the other nine. It asks one question of the published series — of
everyone ever confirmed, where is the record of what happened to them — and
answers it as an arithmetic identity over four printed counts:

    unaccounted = cum_cases − cum_deaths − cumul_recovered
                  − patients_isolated_confirmed

with the first two from the health-zone table's national row and the last two
from the front-page dashboard tiles. Nothing is fitted, no rate enters, and no
assumption about how long a patient stays in care enters. On **2 August**, the
last report day all four exist, that is **1,033 people — 27% of the 3,802
ever confirmed** — in none of the four ledgers, and the count grows over the
same fourteen report days on which the *share* sits flat between 27% and 29%
(676 on 18 July to 1,033 on 2 August).

**The one thing worth a consumer's attention** is not the figure but what it
draws attention to in the series: `patients_isolated_confirmed` **stops on
2026-08-02** and the other three run to the end of the archive. Any
decomposition of confirmed cases by outcome therefore has a different arity
before and after that date, and code that carries the census forward as zero
would show every patient in a bed as unaccounted for. Past 2 August only the
undivided residual `cum_cases − cum_deaths − cumul_recovered` is available:
1,672 on 22 August, against 1,368 when the census stopped. This was already
pinned by
`test_the_confirmed_tile_and_the_national_sentence_stop_on_the_same_day`;
three further tests now pin the decomposition's closure and its headline
values.

**Read the band for what it is.** "No record" means no record in these four
published counts. It is not a claim that anyone is untraced — the response
works from a case line list that is not published. Recorded exits from care
are incomplete (an absconder is booked as neither recovered nor dead, per
`scripts/care_ledger.py`), so the recovery ledger is a floor and unrecorded
recoveries inflate this residual by an unknown amount. Absconding, unrecorded
recovery, unrecorded death and reporting lag all sit inside it in unknown
proportion, and nothing in these four series separates them.

**Where those limits are now written down: `docs/figures/README.md`**, new in
this release. It holds one section per committed figure — what the figure
shows, and the caveats that must travel with it wherever it is used. Two tests
make it fail-closed, in the same shape as the stream register that gates the
data dictionary: a committed figure with no section fails the suite, and a
section naming no figure fails it too. A new published figure can no longer
ship uncaptioned.

`outcomes.png` was then cut back to what a room can read in three seconds and
**changes bytes in this release**; the other nine committed figures do not. It
loses a two-line subtitle, a two-line panel header, a two-line headline
explainer, eight rotated labels on the breaks, three inline band labels with
their leader arrows, a two-line note inside the share panel, and a three-line
footer — all of which moved to `docs/figures/README.md`. It gains **a legend**,
which is what it was actually missing: the four bands, the hatch that means no
ward census was published that day (so the top two bands are not separable),
and the pale span that means no national cumulative was published. The share
panel now starts at the first day of the final unbroken run of report days
carrying all four counts, because the earlier slope falls for reasons that are
not the response finding people — recent cases have no outcome recorded yet,
and the recovery and ward ledgers begin inside that window — and a slope drawn
out of that reads as improvement. Everything that would make the figure
mislead if removed stayed: the hatching, the rule at 2 August, and the share
panel's switch from a measured share to an upper bound there.

---

## `data/2026-08-22-r5` — 2026-08-25 — every flow stream claims the window it sits in

**Breaking for a reader, not for a value.** Twenty-seven files change: 22 gain
rows carrying the literal token `NA` in their observation columns, and five
gain no row but restate one `days_covered`. **No
scored observation changed its value and none changed its `time`**, measured
rather than asserted: the `r4` vintage was rebuilt from this commit's base
against the same `data/build/series/`, and joined file by file on `time` the
two agree on every observation, every file, with no row present before and
absent now. `revisions.tsv` is byte-identical. So is every stock file, every
weekly file, and every `cases_*` and `deaths_*` file at both resolutions.

**What a consumer must do**, in one line: **read these files with `NA`
declared as the null token** — in polars, `pl.read_csv(..., separator="\t",
null_values="NA")`. `NA` is not a null token by default there, so one hole
turns an integer column into a string column; a reader asserting `Int64`
fails, and a plotting library draws the strings at the axis baseline, which
renders a hole as an observed zero in a figure that looks entirely plausible.
Beyond that, a model reading only the columns it names keeps working: no file
is renamed or removed, no observation column is renamed, and the one column
added is metadata.

### The defect

An engine accumulates a modelled flow **from the previous row of that stream**
to this one, and a row carrying no observation still resets the accumulator,
because what resets it is the row being present and not the row being scored.
`r4` published the care ledger's flows, the daily laboratory files and the
daily community-death split holding **only the report days the source stated
the quantity on**. Each next row's accumulation window was therefore as wide
as the silence behind it, while its count still covered a single day. Nothing
in the release said so: the counts were right, every stream's total still
equalled what the source's cumulative moved, no value was negative, and every
column was populated. `days_covered = 1` was documented as the protection and
protected nothing, because no engine reads that column to decide the window.

`care_admissions_nord_kivu.tsv` carried 1 June and 19 July in **consecutive
rows** — 48 days of modelled admissions to be explained by one day of observed
ones. `lab_daily_haut_uele.tsv` held nine observations up to 20 days apart.
The same defect at 13 days, measured downstream on a stream built there,
refused 23 of 24 chains at initialisation.

### The invariant, now a build gate

```
for every SCORED row:  time - (time of the previous ROW, NA or scored) == days_covered
```

`make streams` fails and names every offending row if it does not hold on any
flow file. A scored row whose `days_covered` understates its gap makes the
model accumulate over a window the row does not claim. It is stated in the
"Reading any row" section of `data/build/streams/README.md` as a property of
every published flow file, and enforced in the same spirit as the existing
non-negativity and carry-discharge gates — read back off disk, because what a
consumer fits is the file. Two further gates ship with it: an unscored row is
unscored in **every** observation cell (nothing half-scored), and a file
publishing two observation columns must have declared which of them is the
denominator before it can ship.

### What changed in the files

The three families the source states as **a single 24-hour figure per report**
now carry a row on every report day they span. The days the source stated the
quantity carry it unchanged; the days it did not carry `NA` with
`n_report_days` **0**, which is what marks a row as unscored.

| family | files | rows gained | widest gap between consecutive rows, before → after |
|---|---:|---:|---|
| care ledger flows (`care_admissions_*`, `care_exits*`) | 20 | +219 | 48 d → 3 d |
| `lab_daily_*` | 4 | +64 | 20 d → 3 d |
| `community_deaths_daily_*` | 4 | +25 | 8 d → 3 d |

308 rows in total, across 27 changed files. Per file:

| file | scored obs | rows before | rows after | widest gap before → after |
|---|---:|---:|---:|---|
| `care_admissions_nord_kivu.tsv` | 24 | 24 | 78 | 48 d → 3 d |
| `care_exits_absconded_ituri.tsv` | 8 | 8 | 36 | 14 d → 3 d |
| `care_exits_deaths_ituri.tsv` | 19 | 19 | 44 | 11 d → 3 d |
| `care_exits_noncase_ituri.tsv` | 6 | 6 | 29 | 14 d → 3 d |
| `lab_daily_haut_uele.tsv` | 9 | 9 | 31 | 20 d → 3 d |
| `lab_daily_nord_kivu.tsv` | 50 | 50 | 67 | 12 d → 3 d |
| `lab_daily_ituri.tsv` | 60 | 60 | 76 | 9 d → 3 d |
| `care_exits_nord_kivu.tsv` | 18 | 18 | 33 | 11 d → 3 d |
| `care_admissions_haut_uele.tsv` | 7 | 7 | 21 | 10 d → 1 d |
| `care_exits_ituri.tsv` | 23 | 23 | 36 | 8 d → 3 d |
| `community_deaths_daily_haut_uele.tsv` | 26 | 26 | 39 | 8 d → 3 d |
| `care_exits_deaths_haut_uele.tsv` | 2 | 2 | 12 | 11 d → 1 d |
| `care_exits_noncase_nord_kivu.tsv` | 10 | 10 | 20 | 7 d → 3 d |
| `lab_daily_national.tsv` | 67 | 67 | 76 | 6 d → 3 d |
| `care_admissions_ituri.tsv` | 28 | 28 | 35 | 4 d → 3 d |
| `care_exits_deaths_nord_kivu.tsv` | 16 | 16 | 22 | 6 d → 3 d |
| `care_exits_recovered_nord_kivu.tsv` | 21 | 21 | 27 | 5 d → 3 d |
| `care_exits_recovered_haut_uele.tsv` | 5 | 5 | 10 | 4 d → 1 d |
| `community_deaths_daily_{ituri,nord_kivu,national}.tsv` | 35 each | 35 | 39 | 4 d → 3 d |
| `care_exits_recovered_ituri.tsv` | 36 | 36 | 39 | 3 d → 3 d |

Five files gain no row and still change: `care_exits_national.tsv`,
`care_exits_{absconded,deaths,noncase,recovered}_national.tsv` already had a
row on every report day they span, and their `days_covered` at 30 July moves
from 1 to 3 — see the residual below.

`care_exits_absconded_nord_kivu.tsv` is byte-identical and still holds a single
scored row. **It has no predecessor at all**, so its accumulation window runs
from wherever the model's conditioning boundary sits; no grid can fix that,
because the source states the quantity once.

### The grid is report days, never calendar days

A row asserts a bin. A row on a day the archive holds no report for would
assert a bin the source never licensed — and, the reset being row-based, would
manufacture a reset point out of nothing. The grid is therefore the report
days the archive holds, bounded by the stream's own first and last
observation: a row before the first would claim the quantity was under
observation and empty, a row after the last would claim the series is still
running.

**The residual, stated because it is real.** Where the source published no
report at all the gap widens and `days_covered` widens with it — an honest
wide bin rather than a silent one. The archive holds no report for 28 and 29
July, so **25 of 611 scored rows (4.1%)** on these families claim a window of
2 or 3 days while the figure they carry covers 24 hours; `n_report_days` is 1
on every one of them, and says so. That is the whole of the remaining
mismatch, down from a factor of 48.

### `NA`, zeros, and denominators

An `NA` contributes no likelihood term and **is not an observed zero**. A
report that does not mention absconders is silent about them, not reporting
none; a published `0` is the source having looked and counted none, and those
are still there and still scored.

An unscored row keeps everything that describes it — `n_report_days_silent`,
`checks` and `flags` are populated, because a row that says why it is empty is
strictly better than a bare hole. `n_report_days_silent` changes meaning
slightly as a consequence: a scored row now reads 0 where it used to carry the
tally of the silence behind it, because each silent report day is a row of its
own reading 1.

Two denominator columns exist in the release, and they are treated
differently, which is deliberate:

| column | what a model does with it | on an unscored row |
|---|---|---|
| `tests_{national,ituri,nord_kivu,haut_uele}` | **divides by it** | a placeholder of **1**, never empty and never 0 |
| `deaths_split_{national,ituri,nord_kivu,haut_uele}` | passes it as a **binomial size**, never divides | empty, together with the `community_deaths_*` beside it |

A division can be evaluated on a row that is never scored, so an empty or zero
`tests_*` would be a division by zero in a term nobody meant to compute.
`binomial(n = NA)` cannot be constructed at all, so an engine turns such a row
into a hole — which is what an unscored row should be — and a placeholder
there would be a fabricated trial count for no gain. **A pre-existing hazard
worth naming while you are here:** `deaths_split_haut_uele` is `0` on five
*scored* rows of `community_deaths_daily_haut_uele.tsv`. Those are real
observations (0 classified deaths of 0), unchanged by this release, and a
model dividing by that column rather than passing it as a size will divide by
zero on them.

### Schema

| file | column added | position |
|---|---|---|
| `community_deaths_daily_{ituri,nord_kivu,haut_uele,national}.tsv` | `n_report_days_silent` | between `n_report_days` and `flags`, matching every other file that carries it |

Nothing is renamed or removed. `n_report_days` takes the new value **0** on
unscored rows; it was always 1 on these files before. The new column is
inserted rather than appended, so a reader indexing columns by POSITION rather
than by name needs its offsets moved on those four files; a reader looking
columns up by name needs nothing.

`meta.json` gains `n_rows` beside `n_obs` on every gridded stream's
reconciliation entry — `n_obs` is the scored count and `n_rows` the file's
height, and the two differing by exactly the number of holes is the property
this release exists to protect. `data/build/streams/README.md` gains an `NA
rows` column beside `Obs` for the same reason, and its stated spans are now
measured over scored times.

### Stocks are untouched, and that is a decision

`care_census_*`, `care_census_confirmed_*`, `care_census_suspect_*`,
`patients_isolated`, `patients_isolated_confirmed` and `cumul_recovered` carry
no `days_covered` and accumulate over no window, so a gap in one is a reading
taken later and costs nothing. `care_census_confirmed_nord_kivu.tsv` still has
its 46-day gap, deliberately: rows across it would assert that a census was
taken and came back empty, which no report says. Every one of these files is
byte-identical to `r4`.

---

## `data/2026-08-22-r4` — 2026-08-24 — the care ledger published, and coverage stated on every prose-derived stream

**Additive, and not breaking.** No stream file is renamed or removed, no
observation column is renamed, and **no published value changes**: every
observation in `data/2026-08-22-r3` is present here with the same value at the
same `time`, and `revisions.tsv` is byte-identical. Thirty-two new stream files
are added, and five existing files gain metadata columns beside their unchanged
counts. `meta.json` gains a `reconciliation` entry per new stream and a
coverage field on the laboratory ones; nothing in it is removed or revalued.

**What a consumer must do.** Nothing, to keep working. A model pinned to
`r3` reads every file it read before, with the same columns present and the
same numbers in them, and can move the pin to `r4` without touching a
`columns { }` declaration. To pick the new streams up: re-vendor, then read
`data/build/streams/README.md`, whose per-family **How to read it** block is
new in this release and states the construction and the limits of every
stream, not only the new ones. If your reader validates a file's column set
exactly rather than by name lookup, the five laboratory files below will need
that list extended.

### The care ledger becomes observation streams

`data/build/series/care_prose.csv` shipped at `r2` and was drawn at `r3`;
nothing was published from it. It is now the source of nine stream families,
one file per quantity per place, written only where the source states that
quantity for that place at all. **The priority quantity is the confirmed
isolation census** (`care_census_confirmed_*`): unlike every count stream in
this release it reads a **state** rather than a thinned flow, so a compartment
model relates it to the latent infectious pool with no reporting fraction free
in front of it. It is validated against an independent reader in this
repository — on all 24 report days where the front-page ISOLEMENT/CTE tile and
the care prose both print a confirmed census, they agree exactly — and it is
what carries that census past 2 August, where `patients_isolated_confirmed`
stops because the source stopped printing the tile.

| family | files | what it is | Ituri | Nord-Kivu | Haut-Uélé | national |
|---|---|---|---:|---:|---:|---:|
| `care_census_confirmed` | 4 | confirmed people in care, a stock | 23 | 17 | 6 | 27 |
| `care_census_suspect` | 4 | suspected people in care, a stock | 23 | 16 | 6 | 27 |
| `care_census` | 4 | both together, a stock | 37 | 23 | 9 | 27 |
| `care_admissions` | 3 | admitted over the report day | 28 | 24 | 7 | — |
| `care_exits` | 3 | left care by any route | 23 | 18 | — | 14 |
| `care_exits_recovered` | 4 | discharged as recovered | 36 | 21 | 5 | 14 |
| `care_exits_noncase` | 3 | discharged after testing negative | 6 | 10 | — | 14 |
| `care_exits_absconded` | 3 | absconded | 8 | 1 | — | 14 |
| `care_exits_deaths` | 4 | died in care | 19 | 16 | 2 | 14 |

Observation counts are at this data date and are regenerated into
`data/build/streams/README.md` on every build. The census families are
**stocks** — readings at the end of the report day, with no accumulation
window, so they must not be differenced into an incidence. The exit and
admission families are **flows the report states for the report day itself**,
so `days_covered` is 1 on every row whatever the gap to the previous one: the
source prints one 24-hour figure and this build never spreads it. The gap is in
`n_report_days_silent` instead, where it cannot be mistaken for a window.

**Absconders are published despite being the thinnest thing here**, because
they are the only observation of a route back into the community while still
infectious: 24 province-days in the whole archive, five of them after 2 August,
and `care_exits_absconded_nord_kivu.tsv` holds a single row. The scarcity is in
the files rather than left to be discovered — the `Obs` column of the
dictionary, `n_report_days_silent` per row, and an explicit warning that a
report which does not mention absconders is **silent, not reporting none**.

**What was extracted and deliberately not published**, so a consumer does not
go looking: the confirmed/suspected split of admissions (Ituri prints it on 0
of its 28 admission days, so the family would exist for two provinces only);
the confirmed subset of deaths in care (7 and 2 province-days); transfers to a
general hospital (2 and 1); readmissions (Ituri only, 5); installed bed
capacity and the printed occupancy percentage, which are capacity and a check
rather than observations of the epidemic; and the contact-tracing proportion.
All remain in `data/build/series/care_prose.csv`.

### Every prose-derived stream now states its coverage in a column

The rule this encodes: **a stream that aggregates over a population must
publish how much of that population it saw.** It is written into the "Reading
any row" section of the data dictionary as a stated contract.

It comes from a real failure. Read without `n_provinces`, the national
laboratory stream carries about 23 % fewer positives than the case series over
the report days both cover, and that shortfall was very nearly fitted as a
probability of publication. Split by coverage it is not reporting at all:
report days whose laboratory paragraph covers three or four provinces agree
with the case series to within about a percent, two-province days sit near
0.76, one-province days near 0.30, and the average of those is the 0.77 that
was almost taken for a parameter.

| file | columns added |
|---|---|
| `lab_national.tsv` | `n_report_days_silent`, `n_provinces`, `n_province_days` |
| `lab_daily_national.tsv` | `n_report_days_silent` |
| `lab_daily_ituri.tsv`, `lab_daily_nord_kivu.tsv`, `lab_daily_haut_uele.tsv` | `n_report_days_silent` |

`lab_national.tsv` is the weekly file and had no coverage column at all, though
its daily companion has carried `n_provinces` since it was written; its per-bin
province-day counts existed only inside `meta.json`. `n_provinces` is how many
distinct provinces appear in the bin and `n_province_days` how many
province-days were summed, so `n_province_days / n_report_days` is the mean
breadth a bin's total rests on.

`n_report_days_silent` is the coverage statement for a **single-place** prose
stream, where `n_provinces` would say 1 on every row and mean nothing: it
counts the report days that fell in the row's window and said nothing of that
quantity for that place. Zero means the previous observation was the previous
report day. It is on all thirty-two care files and all five laboratory files.
The per-province laboratory files were adequate on the province axis by
construction and now state the report-day axis too; the table-derived case,
death and community-death streams are unchanged, because a table prints every
province or does not exist.

**`checks`** is also new, on the care files only: the source's own arithmetic
on the passage a value came from, as `closes`, `contradicts` or `unchecked`.
No row is dropped for failing a check — a report contradicting itself is a
finding about the source — but `contradicts` marks the rows where it does, and
`unchecked` marks a passage that offered nothing to check against, which is
unverified rather than wrong.

### The data dictionary now says how to read each stream, and fails closed on it

`registers/stream_families.tsv` gains an `interpretation` column beside
`measures`, rendered under each family's table as **How to read it**, and a
family with either sentence blank now stops the build. Saying what a stream
measures is not saying how to read it, and the traps are not visible in a span
or a column name: that `days_covered` means an accumulation window in a
differenced stream and only a calendar gap in a summed-flow one; that
laboratory positives include post-mortem confirmations and re-swabs of already
confirmed patients (6.6 % to 26.9 % of positives across the seven reports that
print the decomposition), so they are not new live confirmations; that the
community-death column counts only deaths **first confirmed at death**, so an
already-confirmed person's death cannot enter it and it does not observe a
transition out of the confirmed-case compartment; that weekly and daily files
are one quantity at two resolutions and
fitting both double-counts; that the national files are the source's printed
national row and are not meant to equal the sum of the provinces.

The dictionary's "Streams with no observation at the data date" section now
distinguishes **sparse from stopped**, by comparing each stream's trailing gap
against the widest gap inside it. The care streams are intermittent by nature
and would otherwise all have read as failures; the four whose trailing gap is
genuinely unusual are the `_national` care files and
`patients_isolated_confirmed`, which stop together on 2 August because the
source stopped printing both the tile and the whole-response summary sentence.

### One figure changed

`docs/figures/release_grid.png` gains a `care census (confirmed)` group of four
rows, so the figure that says what the release contains shows the stream this
release is about, and its subtitle now says *streams drawn* rather than
*published streams* — the release ships more files than the grid has rows. The
rest of the care ledger is documented but not drawn; thirty more rows would
cost the grid its legibility.

---

## `data/2026-08-22-r3` — 2026-08-24 — figures only: the care ledger drawn, and one panel split in two

**Also in this tag, and the reason a consumer may need it:** `make check` no
longer refuses on two legitimate acquisition routes. It compared the archive
against the live media listing and flagged anything held that the listing
lacked — which is now the normal signature of reports recovered by
`probe_gaps` (served at a bare URL, never listed: sitrep 097) and of reports
declared in `registers/external_sitreps.tsv` (not served by INSP at all: 001,
002, 004). It blocked a downstream vendoring run. Externals are now
subtracted because the register declares them; everything else unlisted is
PROBED, so still-served means the listing never carried it and not-served is
still the alarm. Verified benign: 097 returns 200, and the 052 CORRIGE link
the spot-check flagged returns 200 on retry.

**Not breaking, and nothing to refit.** No stream file changes. No column is
added, renamed or removed; no published value moves; `meta.json` and
`revisions.tsv` are byte-identical to `data/2026-08-22-r2`. A consumer that
vendors `data/build/streams/` can ignore this release entirely — it exists
because the figures are published artefacts too, and two of them changed.

### `streams_detail.png` is now two figures

It carried six per-province flow rows and, concatenated beneath them, four
national-only panels, at eleven by twenty-six inches. `streams_detail.png`
keeps the province rows; `national_detail.png` takes the four national panels
at two-by-two. Both are committed under `docs/figures/` and both are inside the
`release-check` gate, which requires every committed figure to rebuild
byte-identically from a fresh clone.

The two figures share one calendar, derived from the report index rather than
from whichever series a panel holds, so they can still be read against each
other. Every caveat the national panel titles carried is kept. Two dates those
titles stated in words are now read off the series instead, and **one of them
was wrong**: the cumulative-suspected panel said "printed to 1 June only" when
the national suspected series' last observation is **27 May**.

### `care_ledger.png` — the first figure to draw `care_prose.csv`

`data/build/series/care_prose.csv` shipped at `r2` with nothing reading it.
The new figure draws it in four bands, and states in words only numbers it
computes, each pinned by a test:

- **A, the validation.** The front-page ISOLEMENT/CTE tile and the care
  pillar's whole-response sentence are two readings of the same page by two
  different readers in this repository. They print a confirmed isolation census
  on the same 24 report days and **agree on all 24**; they print a total census
  on 27 days and agree on 25. Both exceptions are the source contradicting
  itself, and the split says which half: on 2026-07-07 the sentence states 694
  against its own 232 + 518 = 750, and on 2026-07-14 it states 753 against
  270 + 466 = 736 — the tile agrees with the split on both.
- **A, corrected framing.** The tile does *not* stop after SitRep 080. Its
  **total** census is printed to the end of the archive; only the **confirmed**
  half stops there — and the whole-response sentence stops on the same report.
  After that the confirmed census exists only in the per-province bullets, and
  those are **not summable to a national total**: a median of one of the six
  affected provinces prints a bullet on a given day, at most three, and where
  the sentence is also printed the sum falls short of it on 15 of 17 days, by
  up to 279 patients.
- **B, occupancy against capacity.** Province occupancy runs 15 % to 139 %
  over 68 province-days and exceeds capacity on one (Nord-Kivu, 3 August,
  196 patients for 141 beds). It is a ratio of sums over a whole province and
  cannot resolve a full centre inside a half-full one; the panel says so rather
  than letting the slack read as free beds.
- **C, the ledger flows,** faceted by the passage that printed them and never
  summed across facets: on 11 report days both the whole-response sentence and
  a province bullet print an exit count.
- **D, the absconder counts** — 24 province-days in the whole archive, 5 after
  the handover, 14 of them national rather than provincial — drawn as isolated
  marks and stems, never joined.

No row is dropped for failing a check. A rug at the head of each panel says
whether a row's own arithmetic closed, failed to close, or had nothing to close
against; the last two are different claims and the figure keeps them apart.

---

## `data/2026-08-22-r2` — 2026-08-24 — the outbreak's first three reports

**Not breaking — but refit anyway.** Nothing is renamed, removed or revalued:
every observation published at `data/2026-08-22-r1` is present here with the
same value, and `revisions.tsv` is byte-identical. Nine stream files gain one
or two rows **at the start of the series**. Schema-wise a consumer needs to
change nothing. Scientifically a consumer should refit, because the rows added
are the earliest ones there are, and the earliest rows are what identify **when
the outbreak was seeded**. If you fit a seeding time on
`data/2026-08-22-r1`, that estimate was made without them.

### Three reports INSP does not serve

Our series began at SitRep 005 (19 May) because that is the earliest report
INSP's media library lists. SitReps 001, 002 and 004 exist and were never
listed, and are not at the bare-numbered URL the other unlisted reports sit
behind, so neither the index fetch nor its gap probe could reach them. They
were obtained from the INRB-UMIE/BDBV2026-Data repository, which stores the
PDFs it transcribes in git-lfs.

**Their PDFs are committed**, alone among the ninety-four, because nothing this
project controls can fetch them again and the repository that has them has
already withdrawn a different dataset without notice. ~7 MB.
`registers/external_sitreps.tsv` declares them — number, date, hash, upstream
repository, path, commit and retrieval date — and the build verifies the
committed bytes against it on every run.

### What the three actually add

Only one of them yields a case observation, and it is worth being precise about
why:

    2026-05-19   cases_national             18   (Ituri 18, Nord-Kivu 0)
                 cases_ituri, cases_nord_kivu, and the three daily companions
    2026-05-19   deaths_national             0
    2026-05-18   deaths_daily_national       0   over 4 days
    2026-05-17   cumul_recovered             0

SitRep 004 (18 May) prints a health-zone table the extraction reads: seven
zones plus a national total of 33 confirmed cases, and the zone rows sum to the
printed total exactly. That gives the 19 May row a level to be differenced
against — 51 − 33 = 18 — where before, 19 May was the first reading and so
became the base rather than an observation.

SitReps 001 (14 May) and 002 (17 May) print **no table of any geometry this
project reads**. 001 is narrative; its per-zone figures are inside an image.
002's `Tableau 1` does break the counts down by health zone but transposed,
with indicators as rows and zones as columns. Both are recorded as
`no_matching_table`. What they contribute is through the front-page banner:
001's four confirmed deaths become the base of the national death series (four
days earlier than before), and 002's zero recoveries extend `cumul_recovered`.

**Still not read:** the front-page `Cas Confirmés` tile. SitRep 001 prints 8
confirmed cases and 002 prints 13, both plainly on the page, and neither
reaches any stream — the national case series is built from health-zone tables,
and this project does not read that tile on any report. Those two national
figures remain visible in the source and absent from the data.

### SitRep 004 is filed against its own printed date

SitRep 004's front page prints `Date de rapportage: 19 mai 2026` and `Date de
publication: 20 mai 2026`. **SitRep 005's front page prints exactly the same
two dates**, while the two reports carry different cumulative counts (33 and
51). Data dates in this project come from the page and not from the filename,
so under the printed dates these two reports collide on one day.

Only one assignment gives each report its own day with a non-decreasing
cumulative: 002 = 17 May (13), 004 = 18 May (33), 005 = 19 May (51), 006 =
20 May (61). Moving 004 forward collides it with 005, and moving 005 forward
collides it with 006, up the series. So 004 is filed as **18 May, against its
printed date**. INRB's independently published national series dates that
report 18 May as well — corroboration of the placement from a second reader of
the same page, not independent evidence about the count.

The full argument, and the printed date recorded beside the filed one, are in
`registers/external_sitreps.tsv`. The build checks the page against the
register on every run: if SitRep 004 ever stops printing `19 mai 2026`, the
judgement was made about a different document and the build stops.

### Two extraction corrections that came with them

- **SitRep 004's `Ituri` label falls between two table rows and is lost.** The
  early layout prints the province as a merged cell spanning its zones; here it
  centres in the gap between `Rwampara` and `Bunia`, so the grid records it on a
  row with no zone name and no counts, which the extraction drops. Only
  `Nord-Kivu` survived, and a carry with one anchor cannot split a two-province
  table: all 33 cases went to Nord-Kivu. Four entries in
  `registers/zone_province_overrides.tsv` state what the page states in prose;
  the result, Ituri 30 and Nord-Kivu 3, is what the report's own page-1 province
  table prints.
- **`?` is now recognised as a missing-value marker** in the front-page banner,
  alongside `ND` and the dashes. SitRep 001 writes `?` in the three tiles it had
  no figure for; without that, its value row was not recognised as a value row
  at all and the `Décès confirmés` tile beside them refused. It changes no other
  report in the archive. The `?` is still never read as a number, so 001's
  recoveries tile still refuses: a report that says it does not know has not
  said zero.

### Checked against INRB

Seven new zone-day comparisons at 2026-05-18, and all seven agree. Total
disagreements across the archive are unchanged at 14. Note that INRB's own two
files date SitRep 002 differently — their national series puts it at 17 May,
their zone-level series at 15 May, which is the as-of date printed inside that
report's table rather than its reporting date. We file it under 17 May, the
date its front page gives.

---

## `data/2026-08-22-r1` — 2026-08-24 — new file

**Not breaking.** Nothing is renamed, removed or revalued: no stream file, no
column and no number changes. One file is added. **If you have fitted anything
on `data/2026-08-22`, you do not need to refit.**

### Which streams stop early is now stated, not left to be noticed

A stream that stopped weeks ago looks exactly like a current one unless the
reader compares two dates in a table, which is the comparison a consumer
skips. The dictionary now carries a section listing every stream with no
observation at the data date, and how far behind it is. At this release that
is `patients_isolated_confirmed.tsv`, 20 days behind: **INSP stopped printing
that front-page tile after sitrep 080 (2 August)** and none of the twenty
reports since carries it. The stream ends because the source ended it, not
because extraction failed. It is derived on every build rather than written
down, so it stops being true the day the source resumes.

### The streams now ship a data dictionary

Until now a consumer holding `data/build/streams/` could not answer *what is
`community_deaths_daily_ituri`, and what dates does it cover?* without reading
`build_streams.py`. `meta.json` carries only global fields, and its
`reconciliation` block — which does hold `first_date` / `last_date` for the
streams built by differencing a cumulative — carries no dates at all for the
eight `community_deaths_*` or the five `lab_*` files, so it could not have
answered the second half of that question for thirteen of the thirty-four
published files.

    data/build/streams/README.md      one row per published file: what it
                                      measures, its resolution, its place, how
                                      many observations, first and last `time`

Every span in it is read back off the file it describes, not out of
`meta.json`. It is generated by the run that writes the streams, so it travels
with the vendored data and describes that vintage. It also states, once, the
conventions a consumer needs: that a weekly row is scored over its 7-day bin
and a daily row covers `(previous report day, this report day]`, that days
with no report are absent rather than zero, that no published count is
negative, and which columns are observations and which (`days_covered`,
`n_report_days`, `flags`, `n_provinces`) describe the row.

The one thing no build can generate — the sentence saying what a quantity
measures — is hand-written in the new register `registers/stream_families.tsv`,
keyed on the observation **family** rather than on the file, so the four
province variants of one quantity cannot come to be described in four
different ways. A stream this pipeline writes whose family has no sentence
there now **stops the build and names the file**: a new stream cannot ship
undocumented.

### Three laboratory files were outside the non-negativity gate

`lab_daily_ituri.tsv`, `lab_daily_nord_kivu.tsv` and `lab_daily_haut_uele.tsv`
were written directly rather than through the build's `write_stream`, so they
never entered the list the build reads back to assert that no published count
is negative. They now do. Nothing was wrong with the three files — the gate
finds nothing in them at this release — but the assertion the other
thirty-one carry had a hole in it exactly where a new stream is most likely to
be added.

Consumers need do nothing. The three files are unchanged.

---

## `data/2026-08-22` — 2026-08-23 — coverage, new file, and a wrong number

**Not breaking for existing columns**: nothing renamed or removed. One file is
added, four observation days are added, and three days of Ituri's history
move. **If you have fitted anything on 20–22 August, refit.**

### A stream never publishes a negative count again

The source revises downward. When it does, differencing its cumulative gives a
negative increment, and a negative was being published into streams whose whole
purpose is to be read by an observation model that cannot represent one. Both
the weekly and the daily companions now **carry the deficit forward**: the day
of the revision emits `0`, and the shortfall is held against subsequent days
until it is discharged.

Nothing is silently smoothed. Every carried day is recorded in a **new file**:

    data/build/streams/revisions.tsv     stream, column, time, raw, emitted,
                                         carry_after, flags

`raw` is what the source published, `emitted` is what the stream carries, and
`carry_after` is the deficit still outstanding. It is generated by the same
run that writes the streams and is never hand-maintained. Twenty-two rows at
this release, eight of them where `raw` is negative, all between 11 June and
22 July. Two build assertions now fail the build if any stream carries a
negative or if a carry is left undischarged at the end of a series.

Consumers who need the unadjusted series should read `revisions.tsv` alongside
the stream and add `raw - emitted` back.

### 19 August existed and we did not have it

`97.pdf` is served by INSP, returns 200, and is a complete SitRep N°097 for
19 August — but **no `wp/v2/media` entry lists it**, so the index jumped from
096 to 098 and the archive held no report for that day. Nothing downstream
would have said so: every check the pipeline has asks whether the reports we
*hold* reconcile, and a day never fetched reconciles by being absent. The
ascertainment figure would have drawn 19 August as a day INSP published
nothing.

`fetch_sitrep_index.py` now probes the numbers its listing skips, at the
bare-numbered URL and in the directory the reports either side were uploaded
to. A hit is reported as unresolved for someone to read the front page, not
guessed at.

**Five earlier report-days remain absent** — 29 (12 Jun), 43 (26 Jun), 45
(28 Jun), 75 and 76 (28–29 Jul). Each is a real missing day rather than a
skipped number: the reports either side step two or three days. They are not
in the media listing under any name and not at the bare-numbered URL, so they
need a different channel.

### Bas-Uélé was published as 11 cases against a printed 2

Three extraction defects, all in the geometry layer, all from the coloured
band the province rows have been printed on since sitrep 094. Word draws that
band as one filled rectangle per cell per printed line, and every filled
rectangle was being read as a cell whose four sides are rules.

The one that matters most for a consumer produced **a wrong number rather than
a missing row**. Bas-Uélé's two health zones are divided by no horizontal
rule; the rows fused, and because a space is this source's thousands
separator the fused `1 1` parsed as **eleven**. Sitreps 099 and 100 both
published Bas-Uélé as 11 cases and 10 deaths. It is 2 and 1.

The other two: on a row whose label wraps (`Nord-Kivu` and `Haut-Uélé` are the
only names long enough) the shading cut the row in half, `Nord-` kept the
counts, matched no province, and both provinces were filed as health zones —
sitrep 098 failed its national identity by exactly their 845 cases. And on
sitrep 099 the same paint welded the table to the page-footer bar, so page 3
chained to nothing and the report yielded 25 rows and no national total.

All four new reports now reconcile with residual 0.

### What moved

Four new observation days, 19–22 August, each `days_covered = 1`. The daily
national series runs contiguously to 22 August. Ituri's 098–100 values are
corrected — its cumulative had been read as spiking to 6,200 and falling back,
and the carry-forward that absorbs a downward revision published the spike.
Nord-Kivu and Haut-Uélé totals are unchanged, because their 098 values were
*missing* rather than wrong, and a gap does not move a total that is
final − initial.

**A note on report 100, uncorrected.** It states 55 new confirmed cases
twice, and its zone table's national row prints 55, but its cumulative moves
+56. Localised, the whole gap is one case in Haut-Uélé, whose own daily figure
is one short of its own cumulative movement. The streams difference the
cumulative and carry 56; the printed 55 is retained as `new_cases` in
`zone_table.csv`. No gate currently compares a printed daily flow against a
cumulative movement.

---

## `data/2026-08-18-r5` — 2026-08-23 — coverage

**Not breaking**: no column added, removed or renamed. Three stock and flow
series gain substantial history at the left edge, and one published value
moves. **If you have fitted the recovery stock or anything leaning on the
first two weeks of deaths, refit.**

**The front-page dashboard was only readable in one of its two layouts.** The
reader took a tile's value by scanning *downward* from its label. Sitreps
005–058 print the tiles the other way up — a row of bare numbers with the
label block beneath — so every one of them refused. It now searches both
directions and takes the nearer aligned number, with no branch on report
number or date; where a label has candidates both ways (sitreps 060, 061)
the arbitration is recorded.

Two further defects sat in the same path and cost as much as the direction
did. A regex welded a **one-character field to everything after it on its
line**, which lost *every single-digit tile value in the archive* — sitrep
008's recovered count read as `'0                  16'`. And column matching
used the label's start column only, which fails where a value is centred over
a wider label.

| stream | before | after |
|---|---|---|
| `cumul_recovered` | 36 obs, opens 2026-07-12 at 333 | **86 obs, opens 2026-05-19 at 0** |
| `patients_isolated` | 61 obs | **74 obs** |
| `deaths_daily_national` | 75 obs, 2,434 deaths | **86 obs, 2,472** |
| `deaths_national` | 12 obs, opens 2026-06-02 | **13 obs, opens 2026-05-26** |

**One previously published value changes**: `deaths_national`'s opening bin.
Its window used to start where the *tables* first print a cumulative death
column (29 May, already standing at 42), leaving those deaths outside every
emitted row; the front page prints them from 19 May. **38 deaths enter the
series**, all in the growth phase. Every other stream file is byte-identical.

**Validated against the independent hand transcription**, which had been
claimed in a docstring and never actually computed: `make compare` now writes
`banner_comparison.csv` — **186 of 187 report-values identical**
(`cumul_recovered` 57/57, `patients_isolated` 62/62, `cumul_deaths` 67/68).
The single difference is sitrep 083, where the tile and Table 1 both print
1,850 while the province rows sum to 1,851; we publish the printed national
row, the scan sums the rows. A convention difference, not a transcription
error. `build_streams` also now checks tile against tables on every run: 76
shared dates, 75 agree.

**Two refusals kept deliberately.** Sitreps 016 and 017 print `Cas suspects
en isolement` — suspects *inside* the ward, beside a separate confirmed-active
tile — and no ward total, so publishing that number would put a sub-count
where a total belongs at the point the series begins. Sitrep 007's recovery
tile prints `ND`. The bare `Guéris` label of the early vintage is established
as cumulative by a build-time gate, not an assumption: sitreps 018 and 019
are consecutive days printing the same 6 under different labels, the values
never fall, and those pages carry a separate per-zone `Guéris du jour` column,
so the day's flow already has its own home.

---

## `data/2026-08-18-r4` — 2026-08-23 — fix

**Not breaking**: no column added, removed or renamed. One report's daily
death split is withdrawn. **If you have fitted δ, f_cfr, or the community
share, refit** — those move, and by more than the audit predicted.

**Sitrep 080 (2 August) is structurally corrupt, and we were publishing from
it.** Its daily block is displaced by one printed row: the values on row *i*'s
line belong to row *i−1*. `Adja` carries 11 cumulative cases against 49 new
cases and 23 deaths in 24 hours; the zone rows sum to 148 new cases against a
printed national 58. Three independent lines of evidence agree — word
geometry, the zone sums, and the report's own provincial summary, which on the
same page closes on all six letality figures and prints a national 44,9 %
where the zone table prints 44,2 %, that being *sitrep 079's* pair.

The daily block only is rejected, via `registers/rejected_routes.tsv`. The
report's cumulative columns are sound and its national identity closes, so
the rest of it still ships.

| stream | was | now |
|---|---|---|
| `community_deaths_daily_national` | 2026-08-02: 40 / 72 | row withdrawn |
| `community_deaths_daily_nord_kivu` | 2026-08-02: 0 / 0 | row withdrawn |
| `community_deaths_daily_haut_uele` | 2026-08-02: 0 / 0 | row withdrawn |
| `community_deaths_national` (wk to 08-04) | 158 / 262, 6 report-days | **118 / 190**, 5 |
| `community_deaths_nord_kivu` | 20 / 33, 6 report-days | 20 / 33, **5** |
| `community_deaths_haut_uele` | 3 / 7, 6 report-days | 3 / 7, **5** |

Every `cases_*` and `deaths_*` file, weekly and daily, is byte-identical.
`community_deaths_daily_ituri` is unchanged — Ituri never had a 2 August
observation, because the displacement moved its values onto Adja's line.

**Quantities a consumer derives from these, all of which move:**

| quantity | before | after |
|---|---|---|
| δ, care exit rate | 0.1119 /day (8.9 d stay) | **0.1065 /day (9.4 d)** |
| f_cfr, fatality in care | 0.4563 | **0.4288** |
| γq/τ, span-matched | 0.405 | **0.382** |

`notes/2026-08-22-pipeline-audit.md` predicted δ and f_cfr would be
*unchanged*, on the grounds that the affected window lay outside the care
ledger. It does not: the ledger window ends on 2 August, the very report
withdrawn. The audit was wrong on that row and the figures above supersede it.

**A new check now catches this class automatically.** `tablespec.py` had
documented the printed letality column as "a free per-row check" since the
beginning without anyone implementing it. It now runs over 3,182 checkable
rows and closes on 3,113; of 54 unexplained, **47 are sitrep 080** and the
worst other report is 3 of 40. Results land in `zone_table_letality.csv` and
five new columns of `zone_table_status.csv`. The build fails only when a
column disagrees with more than half its own rows — isolated failures are the
source's own rounding or a figure carried forward from the previous report,
neither of which is our defect.

---

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
