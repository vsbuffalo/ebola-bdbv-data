# Published figures, and their captions

## Why this directory exists at all

Nothing else this pipeline derives is committed. `data/build/` holds every
extracted series, every observation stream and every figure, and it is
gitignored in full: a release is a **git tag**, and everything a consumer needs
is reproducible from that tag by `make build && make streams && make figures`,
because `data/raw/` pins the inputs and the manifest pins which of them a
release read. The modelling repository consumes it exactly that way — it clones
this repository at a tag, rebuilds, and commits the result on its own side
against a lock file.

Committing a derived artefact creates a second source of truth that can drift
from the rule that produces it, so it needs a reason. There is exactly one: **an
image that has to render for someone who is not running the pipeline** — the
README on a web page, a caption in the cross-repo channel, a figure pasted into
a deck. That is what these are, and it is the whole of the exception.

`make figures` and `make compare` write the full set into
`data/build/figures/<release>/`, named for the release that produced it, and
copy this subset here. `make release-check` rebuilds them in a fresh clone and
requires them to be byte-identical to the ones in git, so a committed figure
cannot fall behind the data it claims to show.

**They are not put inside `data/build/`.** That directory means *derived and
disposable* — it must stay safe to delete at any moment, and this pipeline does
delete it. A tracked file living inside it would make `rm -rf data/build` a
destructive act on the repository, which is precisely the property that makes
the layer boundary worth having.

## The layers, in one table

| directory     | what it holds                                                | committed?                                                            |
| ------------- | ------------------------------------------------------------ | --------------------------------------------------------------------- |
| `data/raw/`   | inputs, pinned by `sitrep_pdfs.manifest.tsv`                 | the manifest and the small unrecoverable sources; not the PDF archive |
| `registers/`  | the human judgements the build reads, each with its evidence | yes                                                                   |
| `data/build/` | everything derived, per release                              | **never** — reproducible from a tag                                   |
| `figures/`    | the images documents outside the pipeline link to            | yes, gated by a byte-identical rebuild                                |
| `notes/`      | dated working notes                                          | yes                                                                   |

## The captions

**One section per figure, and the section is the caption.** It says what the
figure shows in a sentence or two, and then the caveats that must travel with it
wherever it is used — in a deck, in a paper, in a message to the modelling side.
Several of these figures are drawn at slide proportions and deliberately carry
very little text: what a reader can consult at leisure lives here, and only what
would make the figure *mislead* if removed stays on the figure itself.

This is fail-closed. `tests/test_extraction.py` fails if a `.png` in this
directory has no section here, or if a section names a file that does not exist,
so a new committed figure cannot ship uncaptioned.

Numbers are deliberately scarce below. Every figure states its own current
values, read off the current build; a caption that repeated them would go stale
on the next report and be wrong in a way nobody would notice. The one date
stated outright — the last day the national ward census is published — is pinned
by a test, so it cannot drift here without the suite saying so.

---

## `epi_curve.png`

Confirmed cases per day and confirmed deaths per day, exactly as the situation
reports record them, over the whole archive. This is the outbreak itself, and it
is the opening slide.

- **A bar's height is a daily rate and its width is its own reporting window, so
  its area is the count.** A report covering several days is drawn as one wide,
  low bar rather than one tall one; reading heights alone would make a multi-day
  report look like a quiet day.
- **The tallest bar in the case panel is not a day's incidence.** One report
  released a backlog of earlier confirmations, and the figure labels that bar
  with its true count and says so. The same happens, smaller, in the death
  panel. Any analysis that treats those bars as incidence on their nominal date
  will put a spike where there was none.
- **Both panels use a cut (broken) vertical axis**, drawn with break marks and
  with the two segments forced to the same units per pixel. A broken axis whose
  halves run at different scales is a second, hidden distortion on top of the
  break; this one does not have that.
- **Bar colour is the caveat the source printed on that report** — data still
  consolidating, may be revised, revised and stated to be too low, zone
  breakdown out of date. A coloured bar is not a bad number. It is the source
  saying the number may move.
- Both series are built by differencing a published cumulative, which is what
  makes dividing by the reporting window the right thing to do here. It is *not*
  right for the streams built by summing flows, where the same `days_covered`
  column means the gap since the previous observation instead.

## `outcomes.png`

Of everyone ever confirmed with Ebola, where the record of what happened to them
is. Cumulative confirmed cases are split across the three published ledgers that
could hold such a record — the death total, the cumulative recoveries, and the
census of confirmed patients in an isolation ward — and what none of the three
accounts for is the top band. The lower panel is that band as a share of all
confirmed cases.

The decomposition is arithmetic over four numbers the reports print — the case
total and the three ledgers. Nothing is fitted, nothing is a rate, and no
assumption about how long a patient stays in care enters. The four bands sum to
the published cumulative case total exactly, which is the only reason the top
band can be read as a count of people rather than as a discrepancy between two
estimates.

**What "no record" means, and what it does not.** It means no record in these
four published counts. It is **not** a claim that anyone is untraced: the
response works from a case line list, which is not published, and this figure
cannot see it.

**Recorded exits from care are incomplete.** A patient who absconds — leaves
care while still infectious — is booked as neither recovered nor dead (see
`scripts/care_ledger.py`), so the recovery ledger is a floor, and unrecorded
recoveries land in the top band instead.

**Absconding, unrecorded recovery, unrecorded death and reporting lag all sit
inside the band in unknown proportion.** Nothing in these four series separates
them, and neither the figure nor this caption asserts which it is.

Three things the figure draws that the legend can only name:

- **The pale vertical spans are report days with no national cumulative, and
  they have three distinct causes** that absence alone cannot tell apart: INSP
  published no report that day; a report appeared but printed no health-zone
  table; or a health-zone table appeared but printed only its 24-hour columns.
  The composition is drawn segment by segment between these spans rather than
  across them, because a cumulative band carried over a hole is an observed
  value the source never printed. `outcome_gaps` computes the cause of each, and
  a test requires every span to carry one.
- **The hatching, and the dashed rule at the census's last day.** The national
  census of confirmed patients in isolation is published for the last time on
  the report of 2 August 2026; both routes this repository reads it by — the
  front-page tile and the care pillar's whole-response sentence — stop on that
  same report, and the per-province bullets that continue do not sum to a
  country (see `care_ledger.png`). After that day the boundary *between* the
  ward band and the top band is not drawn, because nothing published locates it,
  and the two are shown as one hatched region. Continuing the ward band at zero
  would draw every patient in a bed as unaccounted for; ending the figure there
  would imply the top band stopped growing. Neither is true. The same handover
  is why the lower panel switches from a solid measured share to a dashed upper
  bound at that date: after it, only *in a ward **or** with no record* can be
  asserted.
- **DO NOT READ THE JUNE FALL AS AN IMPROVEMENT.** The share drops from about
  two thirds to under a third across June and early July, for two reasons that
  have nothing to do with how many people the response was locating: a case
  confirmed last week has no outcome recorded yet whatever eventually happens to
  it, and the recovery and ward ledgers themselves only begin inside that
  window. What the panel argues is the FLAT STRETCH at the end — 14 report days
  at 27–29% while the count itself went 676 to 1,033 — not the slope into it.
- **The share line is broken, not truncated.** Every one of the 48 report days
  carrying all four counts is drawn; the line is cut where a day carries none,
  which is a day with no bulletin or no census and is marked in the panel above.
  The panel shares panel A's calendar, so the rule at the census's last day
  stands in the same place in both.

## `ascertainment.png`

Where confirmed deaths were found — in a treatment centre, or in the community
by post-mortem swab — and what share of them the surveillance system never had
in care. A death confirmed by post-mortem swab is a death the response never
isolated, so the community share is the closest thing the reports print to a
measurement of how much transmission is being missed. This is the quantity the
modelling side most needs.

- **The share is drawn per report day and unsmoothed, because its stability is
  the finding.** A smoother would manufacture the flatness; and an extraction
  defect that made the share climb toward 1.0 would read as collapsing isolation
  rather than as the parsing artefact it would be.
- **It is a share of *classified* deaths.** Deaths counted as confirmed but
  classified neither way are drawn separately in the upper panel and are not in
  the denominator.
- **The unclassified count is clamped at zero.** On three report days the
  printed classified split exceeds that day's movement in the cumulative death
  total. That is an inconsistency in the source, not a negative quantity.
- **Two backlog-consolidation reports put most of their deaths in the
  unclassified column**, and would set the vertical scale for the whole panel if
  left unclipped. Those bars are clipped and labelled with their true totals, so
  no number is lost.
- **The pale bands marking absence carry three different reasons, and the figure
  prints which.** INSP published no report; the report was published but its
  daily block is one this repository withdrew; or the report printed no
  health-zone table, which is the only place the community/treatment-centre
  split ever appears. The second of those is our own decision about a page, not
  a failure of the source, and it is labelled as ours.

## `ascertainment_provinces.png`

The same split as `ascertainment.png`, one row per province, because the
national share is not one quantity. It is a weighted average over provinces that
run 51% to 68%, over weights that move as the outbreak shifts between them:
Ituri 59%, Nord-Kivu 68%, Haut-Uélé 51%, against a national 61%.

- **Why that matters for a model.** A single national ascertainment probability
  is fitting that average. When the outbreak's centre of mass moves between
  provinces, the national share moves with it, and a model with no province
  structure will read that as a change in how deaths are *found* rather than in
  *where they happen*.
- **Counts and share are two columns, not one panel with two scales.** They are
  different measures, and drawing the share on a second y-axis over the bars is
  the standard way to make a chart nobody can read.
- **The counts column is what stops the share column being over-read.**
  Haut-Uélé carries 71 classified deaths in total against Ituri's 1,273, so its
  share swings between 0% and 100% on days when two deaths were classified. The
  bars say which points carry weight; the dotted line per row is that province's
  pooled share over the whole window, which is the number to quote.
- **The province order is fixed in code, not derived from the data.** A panel
  that changed place between releases could not be compared across them.
- **Only three provinces appear**, because only three publish the split.
  Sud-Kivu and Tshopo report confirmed deaths without ever classifying where
  they were found, and Bas-Uélé is too recently affected to have any.

## `zone_spread.png`

Where the outbreak was at the end of each fortnight, and which health zones
reported their first confirmed case during it. 60 of the 151 health zones in the
six affected provinces have now reported one.

- **Two encodings answering two questions.** The fill is the zone's cumulative
  confirmed cases; the orange outline marks zones reporting their *first* case
  in that fortnight. The outline exists because the fill cannot show arrival — a
  zone going from 0 to 3 cases barely changes colour, and that arrival is the
  most consequential thing on the panel.
- **The fill is logarithmic.** Bunia ends near 700 cases while half the affected
  zones never pass ten. On a linear ramp every zone but three would be the same
  colour.
- **Unaffected zones are drawn, in grey.** A map of only the affected zones
  would make the outbreak look as though it covers the region. The unaffected
  ones are the denominator, and 60 of 151 is the number worth carrying away.
- **Fortnightly, not weekly.** Fifteen weekly panels at this size are each too
  small to find a zone in. The quantity is cumulative so no interval is hidden,
  but the exact week a zone first reported is not readable here — that is in
  `data/build/series/zone_table.csv`.
- **The panels do not date an arrival more finely than a fortnight**, and a zone
  whose first case was retrospectively attributed appears when the report
  published it, not when the case occurred. The 22 July harmonisation moved
  roughly 272 cases into the books at once; zones first appearing in the 6-19
  July and 20 July-2 August panels should be read with that in mind.
- **Boundaries come from `data/raw/health_zones.geojson`** (151 zones, the six
  affected provinces), whose per-province zone counts match the denominators the
  reports themselves print — Ituri 36, Nord-Kivu 34, Sud-Kivu 34, Tshopo 23,
  Haut-Uélé 13, Bas-Uélé 11. 75 of the 76 zone names our extraction has ever
  seen resolve to a geometry through the same alias registers the streams use;
  the one that does not, `Bambu-mine`, appears once and carries no cases.

## `province_overview.png`

Every province the reports have ever recorded a confirmed case in, one panel
each. It exists because its absence caused a mistake: `streams_detail.png` drew
two provinces, and the other four being invisible in it was read as the source
not reporting them. It was reporting all six the whole time, and they were
extracted the whole time — they simply were not published as streams.

- **Each panel has its own vertical scale, deliberately.** Ituri runs to about
  90 confirmed cases a day and Bas-Uélé to one. A shared scale answers "which
  province is biggest", which nobody needed to ask; a free scale answers "is
  this province active", which is the question that went wrong.
- **The three numbers in each heading are the ones that separate a finished
  province from a quiet one**: cumulative cases, deaths and case fatality, and
  how many days since the province last reported a case. A province with no case
  for more than three weeks is greyed.
- **It draws the published streams, not the printed daily column.** That column
  exists only in some vintages and left Ituri blank from June to mid-July. It
  also makes this figure a check on publication: a province that stops being
  published loses its panel, and the missing input stops the build.
- **The excluding-backlog family is drawn**, so the 22 July harmonisation — 347
  cases on one Ituri day — does not set the scale. See the CHANGELOG entry for
  `data/2026-08-29-r2`.
- **Days since a case is not days since transmission.** Sud-Kivu shows 93 days
  and still holds two dozen suspected cases in isolation, contacts of a death
  imported from Tshopo.

## `care_ledger.png`

The treatment-centre ledger the reports state in **words**: whether it can be
believed, and what it says. Four panels — the isolation census read two ways,
occupancy against beds per province, admissions and exits, and the absconder
counts.

The leading panel is the argument rather than the payload. Two readers in this
repository take the isolation census off different parts of the same page — the
front-page dashboard tile and the care pillar's whole-response sentence — and
they agree. **Agreement here is evidence about transcription, not about the
counts.** It is one organisation's numbers on one page, read twice. What it
rules out is a misreading, which is the failure this route is actually exposed
to.

- **The census is published in a form that changes partway through.** The
  front-page tile stops printing the confirmed half, and the whole-response
  sentence stops, on the same report; after that only the per-province bullets
  carry the confirmed census. The figure marks that handover and shades what
  follows it.
- **Do not add the province bullets up to replace the whole-response sentence.**
  On most days only some of the affected provinces print a bullet, so the sum is
  a partial total that would read as a collapse in the census.
  `province_census_is_not_national` computes how partial.
- **Admissions and exits are faceted, not stacked, for the same reason in
  reverse.** On the report days where both the whole-response sentence and the
  province bullets print an exit count, the two passages cover the same patients
  at different levels of geographic detail (national versus province), so adding
  them would count the same discharges twice. The figure states how many days
  that affects.
- **Occupancy is a ratio of sums and cannot see a full centre inside a half-full
  province.** The reports name saturated individual treatment centres in a prose
  subsection this extraction deliberately does not read. Slack in this panel is
  not evidence of free beds where the patients are.
- **Absconder counts are drawn as isolated marks, never joined into a line**,
  because joining them would assert values on days no report printed one. A
  printed zero ("*aucun évadé*") is an observation and is drawn as one, with an
  open ring.
- **No row is dropped for failing a check.** Where a report's own numbers
  disagree — where the stated census contradicts the confirmed-plus-suspected
  split in the same sentence — the row is drawn and flagged. The disagreement is
  the source's, not the reader's.
- **The quantities drawn here are released as streams** (`care_*.tsv` in
  `data/build/streams/`, described in that directory's `README.md`). The figure
  is the argument for believing them; the streams are what a model should read.

## `release_grid.png`

What the release actually contains, report by report: one cell per released
stream per report day, grouped by quantity (cases, deaths, community deaths,
laboratory, stocks, the confirmed care census), with the report-format era drawn
as a band beneath.

**Coverage is not a rectangle, and the holes are the argument.** The laboratory
rows stop where the reports' prose stops naming provinces; the two stock rows
begin late because the early dashboard prints its tiles above their labels
rather than below, which the banner reader could not follow.

- **This is what survives into the release, which is a smaller thing than what
  the source states.** The `availability` figure shows the latter; it is an EDA
  figure under `data/build/figures/` and is not committed, so it is not
  captioned here.
- **The rows drawn are a chosen subset, not the release.** The weekly files are
  the same quantities re-binned, and most of the care ledger is published and
  documented in `data/build/streams/README.md` but not drawn here, because
  thirty further rows would cost the grid its legibility. The subtitle therefore
  says *streams drawn*, never *published streams*.
- **A cell is an observation, not a row.** Streams with no observed report day
  are left out rather than painted, because painting them would claim a datum
  the release does not contain.
- **Cell colour is the report's own caveat**, from the same vocabulary
  `epi_curve` uses. Where a report day carries several caveats the first
  recognised one wins, so the grid under-reports multi-caveat days.
- **The triangles above the grid are reconciliation exceptions** — report days
  whose own arithmetic does not close — labelled with the signed residual,
  because "does not close" covers both a single miscounted case and a
  sixty-six-case provincial discrepancy. Where a date carries several, the
  largest is shown, so it bounds the rest.
- **A report with no health-zone table is not a gap in the format record; it is
  a format.** Three reports dropped the zone table but kept the provincial
  summary, and the earliest reports carried prose only.

## `streams_detail.png`

The per-province daily flows, as small multiples: confirmed cases, the source's
own 24-hour case figure, confirmed deaths, the community and treatment-centre
halves of the death split, and laboratory samples analysed — one column each for
Ituri and Nord-Kivu, the two provinces carrying most of the outbreak.

- **Grey points are one observation per report, at its reporting date; the line
  is a centred seven-day rolling geometric mean, broken across reporting gaps.**
  A line drawn across a gap asserts a level on days the source said nothing
  about: one report prints an early 24-hour figure and the next is six weeks
  later, and joining them drew a six-week plateau out of a single point.
- **One point per report, never one per calendar day.** Differencing a
  forward-filled daily grid manufactures a zero on every day with no report. A
  zero that survives here is real — a report that printed an unchanged
  cumulative.
- **Negative increments are excluded from the rolling window, not clipped to
  zero.** A revision is not an observation of zero incidence; it is the source
  editing its past. The vertical axes are symmetric-log so those revisions stay
  visible rather than being flattened out.
- **The pink strip at each panel's foot is one bar per report whose source
  cautions that its recent data are still consolidating** — a bar rather than a
  shaded period, because the sentence is a rolling statement about each report's
  own trailing edge. Shading the whole span would assert that late July is still
  provisional when most of it has since consolidated.
- **The x limits are the span of the archive, not of the data drawn.** A stream
  that starts in mid-July must show the empty weeks before it, or its late start
  reads as a full history.
- This figure and `national_detail.png` share one calendar, taken from the
  report index rather than from either figure's own data, so the two can be held
  side by side without silently comparing different spans.

## `national_detail.png`

The series the reports print for the country and for no smaller area, in four
panels: cumulative confirmed cases with cumulative confirmed deaths; cumulative
suspected cases; the isolation census; and cumulative recoveries. Drawn on the
same archive calendar as `streams_detail.png`.

- **Two of the four are stocks — a reading at an instant, not a flow over a day
  — so they are drawn as levels and never smoothed.** Differencing them would
  not give incidence.
- **The cumulative suspected series is a stock the source stopped printing
  early, and it is comparable to no flow.** Its panel title carries the date it
  stopped, read off the series rather than written in.
- **The headline isolation census counts suspected cases as well as confirmed
  ones** — a median of about three fifths of it — so only the confirmed part
  observes a confirmed-case compartment. The two are drawn separately for that
  reason.
- **The confirmed half stops before the rest.** The figure marks the date with a
  rule; `care_ledger.png` argues from the same date, derived the same way, that
  the care prose carries the quantity onward.
- The pink provisional strip means the same thing here as in
  `streams_detail.png`.

## `validation.png`

Three readings of the same situation-report PDFs set against each other — this
repository's geometric extraction, the epiforecasts hand transcription, and
INRB-UMIE's transcription — and, below, how much ground each one actually
covers.

**This is the caveat, not a footnote to it: agreement between two readings of
one document is evidence about *transcription*, never about whether the document
is right.** All three lineages read the same pages and inherit whatever the
source got wrong. The figure says so in its own subtitle, because "validated" is
otherwise read as "correct".

- **Agreement is cheap where the lineages overlap, and the overlap is the
  smaller part of the story.** The lower panel exists so the figure cannot be
  read as saying the lineages are interchangeable. They cover different spans
  and different numbers of zone-days.
- **The INRB side is a pinned snapshot, not INRB as it stands today.** The
  commit and date are in the committed `external.lock` and the figure prints
  them. Reporting "we run later" without saying so would compare our current
  data against a stale checkout and call the difference a coverage win.
- **The national series drawn is the printed national cumulative, not a running
  sum of the daily stream.** Summing increments from zero starts the curve tens
  of cases low, so the two are not interchangeable here.
- The agreement counts on the figure are read live from
  `data/build/compare/compare_meta.json` at draw time.

## `comparison.png`

Every zone-day value this repository extracted, set against INRB-UMIE's
transcription of the same reports: the identity plot on the left, and the
disagreements, signed, over time on the right. Disagreements larger than a few
cases are labelled with the zone and the report they come from.

**Two extractions of one source are not independent evidence.** Agreement is
about transcription. A *disagreement*, though, is always a finding: one of the
readings is wrong, or the two read different versions of a report the source
revised in place, and either is worth knowing. That asymmetry is the point of
the comparison.

- **The denominator is the inner join, and the inner join is a survivorship
  set.** Our newest reports have no counterpart in their file yet, and those
  rows — the most recent and least reviewed part of the data — sit outside every
  agreement figure quoted. The unmatched counts are disclosed in
  `compare_meta.json`.
- **Zones the two lineages spell differently are mapped onto one key**, for the
  comparison only. That asserts the two spellings name one place, not that
  either spelling is correct. Without the mapping a spelling divergence would
  vanish instead of disagreeing.
- **A labelled disagreement is not automatically ours.** The largest one so far
  is upstream's: a report prints one zone's total identically in its table and
  in its narrative, and the INRB file carries a different value.
- The national cumulative check against the epiforecasts scan is stated in words
  rather than plotted, because a long run of exact zeroes draws as a line on the
  axis.

## `comparison_series.png`

The same three lineages as time series rather than as a scatter, for Ituri,
Nord-Kivu and the country, with the differences beneath. The line is our summed
zone rows; the rings are INSP's own printed provincial row in the two province
panels and the epiforecasts scan in the national one; the dashed line is
INRB-UMIE's transcription.

- **The two difference rows do not mean the same thing.** *Ours − INRB* mixes
  value disagreements with row-coverage differences: a zone-day absent from
  their file lowers their sum without anyone having read a number differently.
  *Ours − printed* is pure arithmetic against the same page, and is zero
  everywhere except the source self-disagreements recorded in `registers/`.
- **INRB rows are placed into provinces via the health-zone geojson**, because
  their file carries no province column. Rows whose zone is literally `NA`
  cannot be placed and are excluded, which is one visible reason their
  provincial sum can sit below the printed row.
- **Their file carries one malformed date**, a bracket artefact of their own
  build. It can never join anything and cannot be plotted.
- **A few early days exist only in their file.** Those are the outbreak's first
  reports, which INSP's site no longer lists; theirs is the only lineage that
  has them, and nothing can check it.
- A difference panel that is zero everywhere is given a small fixed range, so it
  reads as zero rather than as floating-point noise.

---

## `response_timeline.png`

Whether a claimed response scale-up can be checked against the situation
reports, and what the epidemic did over the window it is claimed for. The shaded
band is a timeline asserted outside this repository — a scale-up beginning with
the first situation report and complete three weeks later, on 8 June. Three
panels share one calendar: daily confirmed cases on a log axis, the first day
each response quantity appears in the reports, and the isolation census split
into confirmed and suspected patients.

- **The first situation report is 14 May, not 18 May.** SitRep 001 is dated 14
  May and SitRep 002 17 May, and both are in the archive. Neither yields a
  machine-readable table — 001's health-zone counts sit inside an image the text
  layer does not carry, and 002's table is transposed out of any registered
  geometry — so both extract as `no_matching_table` and the national series
  starts at SitRep 004. **18 May is where the data starts, not where the
  response started**, and anyone anchoring a response milestone there is
  anchoring it to an artefact of extraction.
- **The middle panel is the honest limit of this figure.** A scale-up is a claim
  about capacity, and the reports print none of it during the window: of the six
  response quantities extracted here, only the case count exists before June.
  Beds first appear in mid-July and contacts followed in August. Any statement
  about a May scale-up is therefore inference from the epidemic's own behaviour,
  never a reading of reported capacity.
- **The top panel shows a change of regime, not a cause.** Incidence climbs
  steeply through the claimed window, holds near 40 cases/day for roughly four
  weeks after it, then rises again from early July. That the slowdown coincides
  with the claimed window is consistent with a response taking effect; it is
  equally consistent with any other change over the same weeks, and this figure
  distinguishes none of them.
- **Early growth is inflated by surveillance expanding.** Health zones under
  reporting go from 16 to 58 across the series, most steeply in the first weeks,
  so part of the early rise is the system finding cases rather than the epidemic
  making them. This biases the apparent slowdown *upward* and is the main reason
  not to read the top panel as an effect size.
- **The 7-day line is a median, because the series carries backlog releases.**
  22 July prints 369 confirmed cases against a neighbourhood of 50 to 100, and
  30 July prints 245 covering three days. On a mean the week of 20 July reads
  about 120 cases/day; on the median it reads 68.
- **The census plateau is not a bed shortage.** The isolation census stops
  rising in the same week incidence resumes rising, which means a falling share
  of cases is in a bed. Over the weeks the reports print both, national capacity
  grows from about 850 beds to 1,050 while occupancy falls from 89% to 66%. The
  ledger points to throughput instead: in Ituri admissions rise from about
  70–86/day in mid-July to 90–138/day by late August while the census holds near
  500, which is a shorter stay at a steady stock rather than a ward that filled.
- **Neither marked date is a fitted change point.** The band is the external
  claim as stated, and the 6 July line is the week the weekly mean census stops
  climbing. No change-point test was run on either series, and the figure
  asserts none.
- **The census split ends because the source stopped printing it**, after SitRep
  080 on 2 August, not because the series ended. The total continues.

---

## `test_positivity.png`

The share of laboratory samples returning positive, over time, and what the
positives were. Upper panel: one grey point per province-day with area
proportional to samples, and a 7-day pooled line. Lower panel: samples analysed
each report day, with the positives drawn inside them and split, where the
source permits, into confirmations made on a living patient and confirmations
made at or around a death.

- **The numerator splits and the denominator does not, and that is the answer to
  the obvious question.** There is no separate positivity rate for suspected
  cases and for community deaths, because the laboratory paragraph prints **one
  pool of samples** per province with no indication of where any of them came
  from. Two rates would need two denominators. **The lower panel is a
  composition, not a second rate**, and reading it as one would invent a
  quantity the reports do not contain.
- **What the positives are can be decomposed**, because confirmations made at or
  around a death are printed separately. Lab positives equal the day's new
  confirmations on 70 of the 78 province-days where both appear, which is what
  licenses treating one as the other.
- **The at-death count begins in mid-July**, so the positives before it are
  drawn as a single band. A day is treated as split only if *every* province
  reporting laboratory volume that day also carries the at-death count; the
  handful of partial days are shown unsplit, because a national composition
  built from some provinces is not one.
- **Bodies swabbed post-mortem would be the missing denominator, and it is not a
  series.** A count appears in roughly ten reports, clustered in early August,
  sometimes national and sometimes provincial, sometimes for the day and
  sometimes cumulative. It could support a handful of point estimates and not a
  curve.
- **The pooled line is a ratio of sums, not a mean of ratios.** Provinces report
  very unequal volumes on the same day — six samples against ninety-four — and
  averaging the daily percentages would give a six-sample province-day the
  weight of a large one.
- **The pooled line is interrupted where this series has no observation**, so it
  is never drawn across days it does not cover. A break is not evidence the
  laboratory went quiet — it can equally be a sentence this pipeline could not
  read, or a row excluded for carrying a different numerator (see
  `positivity_provinces.png`).
- **The rate agrees with the source's own printed percentage** on 153 of 154
  province-days to within 0.15 percentage points, so the upper panel is a
  reading of the page rather than a recomputation that could drift from it.
- **High positivity is expected here and is not evidence of undertesting on its
  own.** Sampling is targeted at symptomatic suspects and at deaths, not drawn
  from the population, so this rate cannot be compared with the
  population-screening benchmarks used for other diseases. What it does carry is
  its *stability*: the level has stayed near 20% since mid-June while daily
  confirmations roughly doubled, meaning testing volume grew with the epidemic
  rather than falling behind it.

---

## `positivity_provinces.png`

The same laboratory samples as `test_positivity.png`, split by the province the
source reports them under. **These two are a pair and the second is only
meaningful against the first**: the grey dashed line here is the blue line
there. Upper panel: each province's own pooled positivity, with one faint point
per province-day sized by samples. Lower panel: samples analysed per report day,
stacked by province.

- **The national rate is a weighted average of provinces that differ three-fold,
  over weights that swing every week.** Ituri returns about 28% positive and
  Nord-Kivu about 9%, and Ituri's share of all samples moves between 52% and 94%
  depending on the week. The pooled line tracks neither province: it follows
  Ituri closely in early June, when Ituri was almost every sample, and separates
  from it as Nord-Kivu's share grows.
- **Sud-Kivu is the clearest case that these are not one population.** It
  returns zero positives on 129 samples across 25 report-days. That is a
  province testing for an introduction it has not found, and those samples enter
  the national denominator exactly like Ituri's.
- **The shape mostly survives pooling; the level does not.** Standardising to
  fixed province weights leaves the weekly spread almost unchanged, 19.7 points
  observed against 20.1 standardised — so the national line is not purely a
  composition artefact. But in the week of 29 June Ituri sits at 38.7% while the
  pooled line reads 22.9%. **Reading the pooled level as "the positivity in this
  outbreak" is reading a dilution.**
- **The finding the pooling hid.** Ituri's own rate holds between 25% and 39%
  from June to mid-August, then falls to 18.9% over the last two report-weeks
  against 31.2% in the four before — 459 positives of 2,433 samples against
  1,085 of 3,478. Over the same period Ituri's testing rises from about 80
  samples per report-day to about 347. Testing expanding while positivity falls
  is what case-finding catching up looks like, and none of it is visible in the
  national line.
- **A break in a line means this series has no observation, not that the
  laboratory went quiet.** Across the archive 35 candidate laboratory rows are
  refused against 163 kept, 24 of them because neither the sample noun nor the
  positive noun could be pinned uniquely in the sentence. **These figures draw
  only the 154 rows whose numerator is comparable** (see below), so their breaks
  are wider than the extraction's own coverage. The August interruption is the
  source's: 6 to 10 August print no sample count anywhere in any report.
- **The figures draw validated rows only, and that is why a gap sits over
  mid-August.** `lab_prose.csv` carries two kinds of row. Where the report
  printed its own positivity, the positive count is the one reproducing it, and
  it equals the day's new confirmations on 70 of the 78 province-days where both
  appear — median excess zero. Where no rate was printed, the count is the total
  positive results, **re-tests of already-confirmed people included**, running a
  median +8 above new confirmations and as high as +16. Both are real and each
  answers a different question, but a line switching between them mid-August
  would show a step this reader introduced. The unvalidated rows stay in the
  extraction for whoever wants total yield.
- **A province gets a line only with at least 15 province-days**; below that a
  line through a handful of points would read as a trend. Tshopo prints
  laboratory volume twice in the whole series, ten samples in total. Those
  provinces appear as points only.
- **The lower panel is samples *printed*, not samples taken.** A province
  contributes zero on days its report carries no laboratory paragraph, which is
  a silence rather than a measured absence of testing. The number of provinces
  reporting on a day ranges from one to five.
- **Province is as fine as this gets.** The laboratory paragraph is written per
  province; there is no health-zone testing data anywhere in the reports, so a
  positivity map at health-zone level cannot be built from this source.

---

## `positivity_provinces_annotated.png`

`positivity_provinces.png` with the laboratory-capacity marks added, and
identical in every other respect. The two are meant to be shown in sequence —
the plain figure first, then this one — because the difference between them is
exactly what reading the reports for capacity statements bought.

- **The plain figure is not a doctored version of this one.** It declares fewer
  inputs: it does not read `registers/lab_capacity_events.tsv` at all, so it is
  genuinely what the pipeline produces without that extraction.
- **The marks name the provinces they belong to**, which matters here: the two
  recorded events are Nord-Kivu's and Haut-Uélé's, and **Ituri — whose testing
  actually rose by two thirds — has no capacity statement in any report read so
  far**. The annotation must not be taken as explaining Ituri.
- Every caveat on `positivity_provinces.png` applies here unchanged.

---

## `lab_effort.png`

The two parts of the positivity ratio drawn apart: samples analysed and
positives found, per report day, for the two provinces that carry the testing.
Ituri and Nord-Kivu on one shared count axis.

- **This figure exists because a ratio cannot answer the question its own
  movement raises.** Positivity falling is compatible with less disease among
  those tested and with more people tested, and the ratio alone cannot separate
  them when both its parts have moved. The parts drawn separately do separate
  them.
- **What the panels say.** In Ituri, samples per report day rise from about 206
  to about 297 between mid-July and late August while positives hold near 64 and
  then 61 — testing up about two fifths, cases found essentially unchanged, and
  a positivity falling by a third as arithmetic rather than as epidemiology. In
  Nord-Kivu, testing is flat near 127 and positives rise from about 11.9 to
  14.3. **The provinces are the control on each other: the one whose testing did
  not change is the one that got worse.**
- **The gap between the lines is the negatives, not the positivity.** Positivity
  is the lower line as a share of the upper. The figure says so on its face
  because the looser reading is the easy one to reach for.
- **Per report day, and a mean rather than a sum.** The source does not publish
  every day; a week carrying four reports and one carrying seven both span seven
  calendar days, so a weekly sum falls when reports thin and rises when they
  resume — a fact about publication, not about testing.
- **What this does not license.** Positives per report day fell about 5% in
  Ituri, which is not evidence transmission rose; and the later window is ten
  report days, which is short. The claim supported here is narrow and negative —
  that Ituri's falling positivity cannot be read as falling incidence — not that
  incidence is known to be flat.
- **Validated rows only**, for the reason given under
  `positivity_provinces.png`: the excluded rows count re-tests among their
  positives and would put a step in the lower line that the reader introduced.
- **Only the two provinces with sustained volume are drawn.** The other four
  contribute a few samples a day at most and would be four flat lines against
  the axis.
