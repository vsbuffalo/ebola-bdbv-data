# Material for the onset-digitiser blog post: what we did, what we found, which figure shows it

Date: 2026-10-22
Project: ebola-bdbv-data
Tags: blog, onset-curve, digitiser, epiforecasts

These are working notes, not the post. Figures are built by
`scripts/blog_onset_figures.py` into `data/build/blog/onset/`. The upstream
reader at commit `bfe9014` is vendored unchanged, with its MIT notice, as
`scripts/vendor/epiforecasts_onset_bfe9014.py`.

## The setup: one chart, two compressions

Sitreps 087 (9 August) and 088 (10 August) carry the same onset chart.
- **Same chart:** both titles print n = 3,362, and the bars are the same
  apart from compression.
- **Different compression:** the 088 PDF is 651 KB against 2.63 MB for 087;
  it is the same image saved with heavier JPEG compression.
- **Figure 1** (`fig1_two_encodings.png`): both charts, the 25 July bar and its
  neighbours cropped from each, and the per-pixel difference.
- **Where the difference is:** it concentrates along colour boundaries, the bar
  tops and the alive/dead seam, which is exactly where a reader decides
  heights.

## Upstream's old reader: a greedy column climb

How the reader at `bfe9014` works:
- **The climb:** for each pixel column it starts at the baseline and climbs,
  classifying each pixel with fixed RGB thresholds:
  - blue: `B > 150, G > 150, R < 210, B ≥ R + 15`;
  - red: `R > 120, R ≥ G + 50, R ≥ B + 50`.
- **The stop:** the climb ends after 7 consecutive pixels match neither colour.
- **The answer per bar:** the 75th percentile of each colour's count across the
  bar's columns.
- **No closing check:** the total is never compared with the printed n.

What it read on the two encodings:

| | 087 | 088 |
| --- | --- | --- |
| total read, against printed n = 3,362 | 3,233 (−3.8%) | 3,049 (−9.3%) |
| 25 July bar (alive + dead) | 28 + 15 | 27 + 0 |

**What went wrong on 088.**
- The compression washed out pixels at the alive/dead seam. One reads
  RGB (211,225,238) and fails `R < 210` by one unit
  (notes/2026-08-28-onset-digitiser-requirements.md §1.2).
- Seven such misses in a row end the climb, so the whole red segment above the
  seam is never examined.
- **Even on 087** the reader came out 129 cases short, and it read 25 July one
  alive case short.

**Figure 2b** (`fig2b_upstream_window.png`) shows how the reader turns columns
into a day.
- **Per column:** each pixel column of the image is climbed separately.
- **Per day:** each day is then a window of ±0.45 days of columns, and its
  value is the 75th percentile of the window's climbs.
- **The 25 July window** is six columns, 793–798. Column 793 is the gap between
  bars and 794 the bar's dark outline, so two of the six are bad by design. The
  percentile is what tolerates them.
- **On 088,** four of the six columns stopped at the alive/dead boundary. Only
  column 796 counted any red: [0, 0, 0, 65, 0, 0] → 75th percentile 0 → dead = 0.
- **On 087,** the blue count is short too. The 2–3 outline pixels at the seam
  match neither colour and are never counted, so 122.75 px / 4.32 px per case
  = 28.4 → 28, where the bar is 29. That systematic shortfall is a likely
  contributor to the 129-case gap on 087; I have checked it only for this bar.

**Figure 2c** (`fig2c_day_placement.png`) shows how the reader places the days.
- **Day spacing:** each tick position is an integer, the cluster mean truncated
  with `int(...)`. So the median weekly gap is a whole number of pixels: 43 px
  on 087/088, giving 6.143 px per day. The true spacing is 6.090 px per day;
  ours comes from a regression over all the ticks.
- **Day centres:** placed back from the last tick at that spacing, so the error
  grows by 0.053 px per day.
- **The drift:** by late April a window is a whole day left of its bar. Across
  May it is 0.6–0.9 days off, so it is centred nearer the previous day's bar
  than its own.
- **Measured (087):** in May, 28 of 31 of the old reader's daily values match
  our reading of the *previous* day within one case, and only 11 match the same
  day. In June the windows straddle the gaps (11 and 8 of 30), and in July they
  are back on the right day (26 of 31).
- **The consequence:** the old series dated most of May's onsets one day late.
  That sensitivity is built into the method: a window is only 0.9 days wide,
  and nothing checks that it lands on a bar.
- **Their current reader** uses 6.090 px per day for 087 and records a
  `drift_days` column, so this is fixed at `7704956`. The commit that fixed it
  is not yet identified.
- **Figure 2a** below is kept unchanged, as the honest picture of the algorithm:
  it shows every column the climb runs, which is what the code does.

**Figure 2a** (`fig2a_upstream_climb_all_columns.png`):
- Yellow marks the pixels the climb examined and could not classify.
- Grey is everything above where each column stopped.
- The black ticks are the stopping rows.
- The third panel lays 088's stopping rows over the 087/088 difference map. The
  climb stops exactly where compression changed the pixels.

The figure's code restates the climb and asserts that the restatement
reproduces the vendored reader's output on every date, so the overlay is
upstream's algorithm and not our paraphrase of it.

**After their fix.** At `7704956`, epiforecasts:
- read the outlines of the bars;
- added `audit_onset_curve.jl`, which checks a chart's read total against the
  printed n within `GAP_TOLERANCE_PCT = 2.1`, the largest gap they had already
  seen;
- don't run that audit in CI, and it skips charts whose printed n is missing.

Their current readings put 25 July at 29 + 15 on both encodings, and read both
charts' totals as 3,362.

## Our first reader: score every whole-number bar

- **The method:** for one bar the truth is a pair of whole numbers
  (alive, dead). Reader one draws every admissible pair as a synthetic bar
  (alive colour up `a` cases, dead colour for the next `d`, background above),
  scores each against the observed pixels with a clipped per-pixel colour
  distance, and keeps the minimum. It tries every candidate, not just nearby
  ones, so the answer is the exact best fit.
- **The seam rows:** the row next to each hypothesised boundary carries no
  weight, because compression damage concentrates there.
- **No early stop:** nothing ends a column early. A washed-out pixel raises
  the cost of every hypothesis about equally and can't truncate a bar.

**Figure 3** (`fig3_our_reader.png`) shows, per encoding:
- the cost surface over (alive, dead), with its minimum (★) and the old
  upstream answer (✕);
- a slice through the surface.

What it shows:
- The minimum is 29 + 15 on both encodings.
- The surfaces are almost indistinguishable: the slice through dead counts
  falls in a clean V to 15 for both 087 and 088.
- On 088, upstream's 27 + 0 sits 5,142 cost units above the minimum. On 087,
  its 28 + 15 sits 615 above.
- **The diagonal valley** in each surface runs along hypotheses with nearly the
  same total height, trading alive for dead. The fit is sharpest across the
  valley, which is the bar top, and least sharp along it, which is where the
  seam sits. So the bar top is better determined than the split between alive
  and dead.

Our reader's totals: 3,362 on 087 and 3,355 on 088.

## The second reader, and refusing on disagreement

- **The second reader** reads the same two numbers from the dark outline
  strokes INSP draws around every segment, as luminance minima down each
  column, with no colour classification.
- **Why two readers:** they fail on different damage. Compression washes out
  fills but spares strokes; downsampling blurs strokes but spares fills.
- **The rule:** a chart is refused when the two readers disagree by more than
  one case on more than 25% of its bars, or when the read total falls outside
  2% under or 0.5% over the printed n.
- **The engineering point for the post:** code is cheap to generate, so write
  two readers that share no mechanism and refuse when they disagree, rather
  than tuning one reader until it looks right.

Figure 4 (planned): totals against printed n for both readers on both
encodings, and the per-bar change from 087 to 088.
Figure 5 (planned): the proof overlay.

## What this doesn't buy: two errors that got through

Both affected the published `reporting_delay.tsv`. Details are in
notes/2026-10-22-onset-reader-catch-up-and-epiforecasts-cross-check.md.

1. **The axis line read as a bar.**
   - 1–2 fake cases with March onset dates in four charts.
   - Within the tolerance on the total, so accepted.
2. **A bar under the "incomplete data" band read as 2 instead of 29**
   (sitrep 106, 24 August).
   - Within the tolerance on the total, so accepted.
   - **Found by comparing our per-day readings with epiforecasts' current
     ones:** 98.8% of 5,630 onset days agree within one case, and the largest
     disagreement was this bar.

**The lesson for the post:** a check on the whole chart's total cannot see a
single-bar error smaller than its tolerance. An independent reading of each
bar can. The comparison with epiforecasts is an outside second reader, and it
caught what our own pair of readers let through. That is a good reason to
publish readings, and to compare them openly.

**Tone:** their reader caught our bug as surely as our analysis found theirs.
The story is how two groups reading the same pixels make each other better,
not who was right.

## Open items before drafting

- [ ] Figures 4 and 5.
- [ ] The band-edge fix; then re-run the comparison and attribute every
      remaining difference.
- [ ] Email Sam Abbott before publishing anything that describes their reader.
- [ ] Cite their repository at specific commits (`bfe9014`, `7704956`) and the
      issue or PR where they found the problem.
