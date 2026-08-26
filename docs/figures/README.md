# Figure captions

The PNGs beside this file are the **committed copies** of the figures the
repository publishes. `make figures` and `make compare` write them; `make
release-check` rebuilds them in a fresh clone and requires them to be
byte-identical to the ones in git, because the README embeds them and the
cross-repo channel links them, so a stale one is a wrong claim that travels.

**One section per figure, and the section is the caption.** It says what the
figure shows in a sentence or two, and then the caveats that must travel with
it wherever it is used — in a deck, in a paper, in a message to the modelling
side. Several of these figures are drawn at slide proportions and deliberately
carry very little text: what a reader can consult at leisure lives here, and
only what would make the figure *mislead* if removed stays on the figure
itself.

This is fail-closed. `tests/test_extraction.py` fails if a `.png` in this
directory has no section here, or if a section names a file that does not
exist, so a new committed figure cannot ship uncaptioned.

Numbers are deliberately scarce below. Every figure states its own current
values, read off the current build; a caption that repeated them would go stale
on the next report and be wrong in a way nobody would notice. The one date
stated outright — the last day the national ward census is published — is
pinned by a test, so it cannot drift here without the suite saying so.

---

## `epi_curve.png`

Confirmed cases per day and confirmed deaths per day, exactly as the situation
reports record them, over the whole archive. This is the outbreak itself, and
it is the opening slide.

- **A bar's height is a daily rate and its width is its own reporting window,
  so its area is the count.** A report covering several days is drawn as one
  wide, low bar rather than one tall one; reading heights alone would make a
  multi-day report look like a quiet day.
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
  makes dividing by the reporting window the right thing to do here. It is
  *not* right for the streams built by summing flows, where the same
  `days_covered` column means the gap since the previous observation instead.

## `outcomes.png`

Of everyone ever confirmed with Ebola, where the record of what happened to
them is. Cumulative confirmed cases are split across the three published
ledgers that could hold such a record — the death total, the cumulative
recoveries, and the census of confirmed patients in an isolation ward — and
what none of the three accounts for is the top band. The lower panel is that
band as a share of all confirmed cases.

The decomposition is arithmetic over four numbers the reports print — the case
total and the three ledgers. Nothing is fitted, nothing is a rate, and no
assumption about how long a patient stays in care enters. The four bands sum to
the published cumulative case total exactly,
which is the only reason the top band can be read as a count of people rather
than as a discrepancy between two estimates.

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
  value the source never printed. `outcome_gaps` computes the cause of each,
  and a test requires every span to carry one.
- **The hatching, and the dashed rule at the census's last day.** The national
  census of confirmed patients in isolation is published for the last time on
  the report of 2 August 2026; both routes this repository reads it by — the
  front-page tile and the care pillar's whole-response sentence — stop on that
  same report, and the per-province bullets that continue do not sum to a
  country (see `care_ledger.png`). After that day the boundary *between* the
  ward band and the top band is not drawn, because nothing published locates
  it, and the two are shown as one hatched region. Continuing the ward band at
  zero would draw every patient in a bed as unaccounted for; ending the figure
  there would imply the top band stopped growing. Neither is true. The same
  handover is why the lower panel switches from a solid measured share to a
  dashed upper bound at that date: after it, only *in a ward **or** with no
  record* can be asserted.
- **DO NOT READ THE JUNE FALL AS AN IMPROVEMENT.** The share drops from about
  two thirds to under a third across June and early July, for two reasons that
  have nothing to do with how many people the response was locating: a case
  confirmed last week has no outcome recorded yet whatever eventually happens
  to it, and the recovery and ward ledgers themselves only begin inside that
  window. What the panel argues is the FLAT STRETCH at the end — 14 report
  days at 27–29% while the count itself went 676 to 1,033 — not the slope into
  it.
- **The share line is broken, not truncated.** Every one of the 48 report days
  carrying all four counts is drawn; the line is cut where a day carries none,
  which is a day with no bulletin or no census and is marked in the panel
  above. The panel shares panel A's calendar, so the rule at the census's last
  day stands in the same place in both.

## `ascertainment.png`

Where confirmed deaths were found — in a treatment centre, or in the community
by post-mortem swab — and what share of them the surveillance system never had
in care. A death confirmed by post-mortem swab is a death the response never
isolated, so the community share is the closest thing the reports print to a
measurement of how much transmission is being missed. This is the quantity the
modelling side most needs.

- **The share is drawn per report day and unsmoothed, because its stability is
  the finding.** A smoother would manufacture the flatness; and an extraction
  defect that made the share climb toward 1.0 would read as collapsing
  isolation rather than as the parsing artefact it would be.
- **It is a share of *classified* deaths.** Deaths counted as confirmed but
  classified neither way are drawn separately in the upper panel and are not in
  the denominator.
- **The unclassified count is clamped at zero.** On three report days the
  printed classified split exceeds that day's movement in the cumulative death
  total. That is an inconsistency in the source, not a negative quantity.
- **Two backlog-consolidation reports put most of their deaths in the
  unclassified column**, and would set the vertical scale for the whole panel
  if left unclipped. Those bars are clipped and labelled with their true
  totals, so no number is lost.
- **The pale bands marking absence carry three different reasons, and the
  figure prints which.** INSP published no report; the report was published but
  its daily block is one this repository withdrew; or the report printed no
  health-zone table, which is the only place the community/treatment-centre
  split ever appears. The second of those is our own decision about a page, not
  a failure of the source, and it is labelled as ours.

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
- **Do not add the province bullets up to replace the whole-response
  sentence.** On most days only some of the affected provinces print a bullet,
  so the sum is a partial total that would read as a collapse in the census.
  `province_census_is_not_national` computes how partial.
- **Admissions and exits are faceted, not stacked, for the same reason in
  reverse.** On the report days where both the whole-response sentence and the
  province bullets print an exit count, the two passages cover the same
  patients at different levels of geographic detail (national versus province),
  so adding them would count the same discharges twice. The figure states how
  many days that affects.
- **Occupancy is a ratio of sums and cannot see a full centre inside a
  half-full province.** The reports name saturated individual treatment centres
  in a prose subsection this extraction deliberately does not read. Slack in
  this panel is not evidence of free beds where the patients are.
- **Absconder counts are drawn as isolated marks, never joined into a line**,
  because joining them would assert values on days no report printed one. A
  printed zero ("*aucun évadé*") is an observation and is drawn as one, with an
  open ring.
- **No row is dropped for failing a check.** Where a report's own numbers
  disagree — where the stated census contradicts the confirmed-plus-suspected
  split in the same sentence — the row is drawn and flagged. The disagreement
  is the source's, not the reader's.
- **The quantities drawn here are released as streams** (`care_*.tsv` in
  `data/build/streams/`, described in that directory's `README.md`). The
  figure is the argument for believing them; the streams are what a model
  should read.

## `release_grid.png`

What the release actually contains, report by report: one cell per released
stream per report day, grouped by quantity (cases, deaths, community deaths,
laboratory, stocks, the confirmed care census), with the report-format era
drawn as a band beneath.

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
  thirty further rows would cost the grid its legibility. The subtitle
  therefore says *streams drawn*, never *published streams*.
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
halves of the death split, and laboratory samples analysed — one column each
for Ituri and Nord-Kivu, the two provinces carrying most of the outbreak.

- **Grey points are one observation per report, at its reporting date; the line
  is a centred seven-day rolling geometric mean, broken across reporting
  gaps.** A line drawn across a gap asserts a level on days the source said
  nothing about: one report prints an early 24-hour figure and the next is six
  weeks later, and joining them drew a six-week plateau out of a single point.
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
  shaded period, because the sentence is a rolling statement about each
  report's own trailing edge. Shading the whole span would assert that late
  July is still provisional when most of it has since consolidated.
- **The x limits are the span of the archive, not of the data drawn.** A stream
  that starts in mid-July must show the empty weeks before it, or its late
  start reads as a full history.
- This figure and `national_detail.png` share one calendar, taken from the
  report index rather than from either figure's own data, so the two can be
  held side by side without silently comparing different spans.

## `national_detail.png`

The series the reports print for the country and for no smaller area, in four
panels: cumulative confirmed cases with cumulative confirmed deaths;
cumulative suspected cases; the isolation census; and cumulative recoveries.
Drawn on the same archive calendar as `streams_detail.png`.

- **Two of the four are stocks — a reading at an instant, not a flow over a
  day — so they are drawn as levels and never smoothed.** Differencing them
  would not give incidence.
- **The cumulative suspected series is a stock the source stopped printing
  early, and it is comparable to no flow.** Its panel title carries the date it
  stopped, read off the series rather than written in.
- **The headline isolation census counts suspected cases as well as confirmed
  ones** — a median of about three fifths of it — so only the confirmed part
  observes a confirmed-case compartment. The two are drawn separately for that
  reason.
- **The confirmed half stops before the rest.** The figure marks the date with
  a rule; `care_ledger.png` argues from the same date, derived the same way,
  that the care prose carries the quantity onward.
- The pink provisional strip means the same thing here as in
  `streams_detail.png`.

## `validation.png`

Three readings of the same situation-report PDFs set against each other — this
repository's geometric extraction, the epiforecasts hand transcription, and
INRB-UMIE's transcription — and, below, how much ground each one actually
covers.

**This is the caveat, not a footnote to it: agreement between two readings of
one document is evidence about *transcription*, never about whether the
document is right.** All three lineages read the same pages and inherit
whatever the source got wrong. The figure says so in its own subtitle, because
"validated" is otherwise read as "correct".

- **Agreement is cheap where the lineages overlap, and the overlap is the
  smaller part of the story.** The lower panel exists so the figure cannot be
  read as saying the lineages are interchangeable. They cover different spans
  and different numbers of zone-days.
- **The INRB side is a pinned snapshot, not INRB as it stands today.** The
  commit and date are in the committed `external.lock` and the figure prints
  them. Reporting "we run later" without saying so would compare our current
  data against a stale checkout and call the difference a coverage win.
- **The national series drawn is the printed national cumulative, not a running
  sum of the daily stream.** Summing increments from zero starts the curve
  tens of cases low, so the two are not interchangeable here.
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
  rows — the most recent and least reviewed part of the data — sit outside
  every agreement figure quoted. The unmatched counts are disclosed in
  `compare_meta.json`.
- **Zones the two lineages spell differently are mapped onto one key**, for the
  comparison only. That asserts the two spellings name one place, not that
  either spelling is correct. Without the mapping a spelling divergence would
  vanish instead of disagreeing.
- **A labelled disagreement is not automatically ours.** The largest one so far
  is upstream's: a report prints one zone's total identically in its table and
  in its narrative, and the INRB file carries a different value.
- The national cumulative check against the epiforecasts scan is stated in
  words rather than plotted, because a long run of exact zeroes draws as a line
  on the axis.

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
- A difference panel that is zero everywhere is given a small fixed range, so
  it reads as zero rather than as floating-point noise.

---

## `response_timeline.png`

Whether a claimed response scale-up can be checked against the situation
reports, and what the epidemic did over the window it is claimed for. The
shaded band is a timeline asserted outside this repository — a scale-up
beginning with the first situation report and complete three weeks later, on 8
June. Three panels share one calendar: daily confirmed cases on a log axis, the
first day each response quantity appears in the reports, and the isolation
census split into confirmed and suspected patients.

- **The first situation report is 14 May, not 18 May.** SitRep 001 is dated 14
  May and SitRep 002 17 May, and both are in the archive. Neither yields a
  machine-readable table — 001's health-zone counts sit inside an image the
  text layer does not carry, and 002's table is transposed out of any
  registered geometry — so both extract as `no_matching_table` and the national
  series starts at SitRep 004. **18 May is where the data starts, not where the
  response started**, and anyone anchoring a response milestone there is
  anchoring it to an artefact of extraction.
- **The middle panel is the honest limit of this figure.** A scale-up is a
  claim about capacity, and the reports print none of it during the window: of
  the six response quantities extracted here, only the case count exists before
  June. Beds first appear in mid-July and contacts followed in August. Any
  statement about a May scale-up is therefore inference from the epidemic's own
  behaviour, never a reading of reported capacity.
- **The top panel shows a change of regime, not a cause.** Incidence climbs
  steeply through the claimed window, holds near 40 cases/day for roughly four
  weeks after it, then rises again from early July. That the slowdown coincides
  with the claimed window is consistent with a response taking effect; it is
  equally consistent with any other change over the same weeks, and this figure
  distinguishes none of them.
- **Early growth is inflated by surveillance expanding.** Health zones under
  reporting go from 16 to 58 across the series, most steeply in the first
  weeks, so part of the early rise is the system finding cases rather than the
  epidemic making them. This biases the apparent slowdown *upward* and is the
  main reason not to read the top panel as an effect size.
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
- **The census split ends because the source stopped printing it**, after
  SitRep 080 on 2 August, not because the series ended. The total continues.
