# The onset reader catches up, and epiforecasts' readings find a bar it lost

Date: 2026-10-22
Project: ebola-bdbv-data
Tags: onset-curve, digitiser, epiforecasts, reporting-delay, source-format

## After the band fix (9765dec)

**Why the readers lost bars under the band.** The pink band is a see-through
overlay drawn over the last week of bars.
- **Reader one:** under the band the fills match neither legend colour, so it
  fitted most of each such bar as background.
- **Reader two:** the outlines there are too faint to count as strokes, so it
  returned nothing.
- **Result:** a band bar had one reader and no disagreement to flag it.
- **The band's left edge was also wrong** in 106, 123 and 124. It was taken
  from the leftmost pink pixel, and a stray pink column of the «premier
  résultat positif» box at x = 174 put it there. In 106 that marked 133 of 160
  bars provisional.

**The fix:**
- The band is the largest pink cluster.
- Its transmission is measured on each render and the overlay inverted.
- The pixels of the band's label are masked.
- Renders that draw the bars over the band, 059–062, are recognised as such.

Verified here:
- 106's 24 August bar now reads 19 + 10 = 29.
- No accepted chart has a non-zero day before April.
- The full suite passes: 443 passed, 1 skipped, 1 xfailed.

| | 19f0dc0 | 9765dec |
| --- | --- | --- |
| charts accepted, with caveat, refused | 65 / 9 / 24 | 66 / 9 / 23 |
| read total against printed n, distinct accepted renders | median −0.24%, −1.36% to +0.06% (52) | median −0.19%, −0.70% to +0.09% (53) |
| onset days within 1 case of epiforecasts | 98.8% of 5,630 | 99.2% of 5,785 |
| onset days more than 2 cases apart | 58 (29 in the band) | 36 (6 in the band) |

Status changes:
- 140 is now accepted: −0.62%, and all 155 of its days are within one case of
  epiforecasts.
- 149 now reads 1.0% over its printed n and is refused. That is the correct
  outcome for a render where a 0.4% change of scale moves the total by 2.7%.

**Whose error the remaining 36 days are.** Each was judged by the bar's
stability across neighbouring reports; a few were checked on the images.

| Count | Whose | What |
| --- | --- | --- |
| 11 | ours | 059–062: the alive/dead split. See below. |
| 15 | probably theirs | the 14 May bar, crossed by INSP's red dashed «premier résultat positif» line; ours reads 10–13 steadily across reports, theirs swings 5–15 |
| 7 | theirs | single-report blips while both our readers agree: 112 (4 May), 113 (2 Sep), 115 (26 Jun), 116 (5 Sep), 129 (21 and 30 Aug), 132 (11 May) |
| 1 | ours | 092, 11 August |
| 2 | unclear | 122 (10 Sep), 143 (4 May) |

**A third defect, not yet fixed: in 059–062 the dead segment is at the bottom of
each bar.** Reader one assumes alive starts at the baseline.
- **Totals (correct):** ours 1,792 for 060, theirs 1,817.
- **Deaths (wrong):** ours reads 27–30; epiforecasts reads 482–507.
- **Why no gate caught it:** these renders print no n, so the closure check
  does not run, and a wrong split leaves the total unchanged.
- **Who is affected:** nobody downstream. `scripts/build_reporting_delay.py`
  uses only `d_total`, so the published `reporting_delay.tsv` is unaffected.
  The split is wrong only in `data/build/onset/snapshots.csv`, which is not
  published.
- **Fix:** read the stacking order from the render, or refuse the split for
  those four.

## Context / question

Each INSP situation report prints a bar chart of confirmed cases by date of
symptom onset, alive cases in blue and deceased cases in red stacked above them,
titled with the total n. Our reader (`scripts/extract_onset_curve.py`, with
`scripts/lib/onset/`) turns each chart into one (alive, dead) count per onset
day. Those counts feed the reporting-delay table published as
`streams/reference/reporting_delay.tsv`, which gives the distribution of days
between a case's symptom onset and its first appearance in a chart.

After sitrep 127 (18 September) the reader refused every new chart. The two
questions here are:

- why it refused, and what fixing it changes in the published data;
- how its readings compare with epiforecasts' readings of the same charts.

Epiforecasts' readings come from the `BVDOutbreakSize` repository. We only
compare against them; they never feed our data.

## Two defects in the published reporting-delay table

**Fake March cases (fixed on branch `onset-long-axis`, 19f0dc0).**
- Release `data-2026-10-20-r0` has a "2026-03" onset cohort of two cases with
  delays of 164 and 169 days.
- They come from four accepted charts, sitreps 100, 117, 119 and 122, which read
  1–2 cases on 28 or 29 March.
- The first bar slot overlapped the chart's dark y-axis line, and reader one
  scored that line as a short bar.
- A crop of sitrep 100's chart shows no bars before late April.
- The extra 1–2 cases fall within the tolerance against the printed n, so the
  closure check could not catch them.
- On the branch, the slots start clear of the axis line. The March cases are
  gone, and each of the four totals drops by 1–3.

**A bar under the pink "incomplete data" band read near zero (fixed in 9765dec; found by the
comparison below).**
- In sitrep 106 we read the 24 August bar as 2 cases; epiforecasts reads 29.
- The proof image `data/build/onset/proof/2026-08-28-106-edfca627ae94.png` shows
  the bar under the pink "Données potentiellement incomplètes" band, at the
  band's left edge, next to the band's rotated label.
- That one bar accounts for 27 of our 32-case shortfall against the printed
  n = 4,628. Epiforecasts' total for 106 is 4,629.
- The shortfall stayed within our closure tolerance (a read total up to 2% below the printed n, or 0.5% above it, is accepted), so the chart was
  accepted.
- The reporting-delay table is built from how a bar grows between successive
  charts. A bar read as 2 and then correctly as 29 in a later chart adds 27
  cases that were never reported late.

## The reader catch-up

The refusals after 127 were caused by changes in how INSP draws the chart:
- the y axis became a light-grey line, which the reader did not recognise as
  the panel's left edge;
- the x axis became long enough that a tick spacing rounded to half a pixel
  drifted by a whole slot across it;
- new tick-label images had no row in `registers/onset_axis_anchors.tsv`.

Results on the branch, with no check loosened:

| Charts with an onset figure (sitreps 59–159) | main | branch |
| --- | --- | --- |
| accepted, or accepted with a caveat | 50 | 74 |
| refused | 45 | 21 |
| accepted charts, read total against printed n | | −1.36% to +0.06%, median −0.24% |

**Still refused:**
- 140 and 153–155 read short.
- 138, 149, 153–155 and 159: the two readers disagree on more than 25% of bars.
- 108, 109 and 141: too few x-axis ticks were found.
- 146, 151 and 152: the printed n was not read.
- 135 and 150: the y axis was not read.

## Comparison with epiforecasts' current readings

Source: `data/onset_curve_scanned.csv` and `data/onset_curve_figures.csv` in
BVDOutbreakSize at `7704956` (committed 22 October). Compared with the branch.

| | |
| --- | --- |
| charts both groups read | 67 |
| chart totals equal | 8 |
| chart totals, median absolute difference | 8 cases |
| chart totals, largest difference | 1.63% |
| our read total against printed n (64 charts) | median −0.23%, −1.36% to +0.06% |
| their read total against printed n | median −0.13%, −2.09% to +0.10% |
| closer to the printed n | ours 25, theirs 31, equal 8 |
| onset days both read | 5,630 |
| onset days equal | 4,396 |
| onset days within 1 case | 5,561 (98.8%) |
| onset days differing by more than 2 | 58 |

- 29 of the 58 large differences are onset days 1–4 days before the report
  date, which is where the pink band sits. Only sitrep 106 was confirmed by
  looking at the image; the others are inferred from their position.
- The other 29 are scattered at lags of 21–103 days and have not been examined.
- **Coverage:**
  - they read 11 charts we refuse: 59, 104, 105, 108, 109, 111, 114, 140, 141,
    146, 149;
  - we read 7 they don't: 63, 98, 147, 148, 156, 157, 158;
  - their per-day series stops 7–12 days before each report date, where ours
    runs up to it and marks the band days provisional.

## Interpretation

The comparison did what it is for. Both groups transcribe the same pixels, so
agreement says nothing about whether INSP's counts are true. A disagreement,
though, points to a place where one of the two readings is wrong. Here the
first one examined was ours.

Our gates could not catch it, for a structural reason. The closure check
compares a chart's whole total with the printed n, and a 27-case loss is within
the tolerance on a 4,628-case chart. A check over the whole chart is blind to a
single-bar error smaller than its tolerance. An independent per-bar reading is
not.

## Next

- Fix the band-edge undercount on the branch, with a regression test pinned to
  106's 24 August bar.
- Re-run this comparison, and attribute each remaining difference above 2 cases
  to one reading or the other.
- Merge, with a changelog entry for the corrected `reporting_delay.tsv`.
- Make the comparison a `make compare` target, so every future chart is checked
  bar by bar against their readings.
