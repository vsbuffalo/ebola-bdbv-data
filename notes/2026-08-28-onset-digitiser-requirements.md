# Building an onset-curve digitiser that does not repeat the upstream failures

Date: 2026-08-28 Project: epiforecast-repro Tags: onset-curve, digitisation,
pipeline-design, handoff, ebola-bdbv-data Audience: whoever implements the
onset-figure reader in institutefordiseasemodeling/ebola-bdbv-data Companion:
notes/2026-08-26-onset-curve-jpeg-digitisation.md (the investigation this is
drawn from — read that for the evidence, this for the requirements)

## Why this note exists

Upstream (`epiforecasts/BVDOutbreakSize`) reads the INSP symptom-onset bar chart
out of the PDF's pixels and fits the result as a model stream. On 2026-08-10
that reader returned 3049 cases from a chart that its own predecessor had read
as 3233 — from _the same chart_, re-published a day later at heavier JPEG
compression. The 184-case difference entered the likelihood as evidence that
recent onsets had stopped accumulating, and the published reproduction number at
the cut-off sat at 1.02 instead of ~1.15.

That is one incident. Running upstream's own stable-region invariant across
every vintage (below) shows **three under-reads and one over-read in the last
fourteen vintages**, two of which are in the released data today.

Their design spec for our reader
(`notes/2026-08-26-onset-curve-reporting-triangle.md`, in that repo) already
gets several things right. This note is the additional set of requirements that
fall out of what actually went wrong, with the thresholds measured rather than
guessed.

## Part 1 — what we found, briefly

### 1.1 The reading depends on the render, not just the chart

|                          | SitRep 087               | SitRep 088                |
| ------------------------ | ------------------------ | ------------------------- |
| report date              | 9 Aug                    | 10 Aug                    |
| PDF                      | 2.63 MB                  | 651 KB                    |
| embedded chart           | 966x571, JPEG, ratio 11% | 966x571, JPEG, ratio 4.8% |
| printed n (in the title) | **3 362**                | **3 362**                 |
| digitised total          | **3233**                 | **3049**                  |

The two images agree on the chart: mean per-pixel difference 3.08/255, only
0.27% of pixels differing by more than 30, per-date bar-top row difference
median **0 px** with 88% of dates within 2 px, and summed bar-top extent
differing by **+0.07%**. Verified by running upstream's own
`extract_onset_image()` + `digitize()` on both PDFs: it reproduces the committed
CSV cell for cell, 97/97 and 98/98. The chart is the same; the reader disagrees
with itself by 5.7%.

### 1.2 The mechanism: a run-length rule meeting a hard colour cut

Their reader climbs each bar column from the baseline, counting pixels that
match a blue mask or a red mask, and **breaks after 7 consecutive rows matching
neither**:

```python
blue = (B > 150) & (G > 150) & (R < 210) & (B >= R + 15)
red  = (R > 120) & (R >= G + 50) & (R >= B + 50)
...
else:
    miss += 1
    if miss > 6:
        break
```

Column 797 of the 25 July bar, in both images:

```
row   087                     088
307   blue (200,229,237)      MISS (211,225,238)   R=211 fails "R < 210" by one
306   blue (200,229,237)      MISS (211,225,238)
305   blue (200,229,237)      MISS (212,224,238)
304   blue (199,229,237)      MISS (219,221,233)
303   blue (198,231,238)      MISS (237,222,227)
302   MISS (219,223,232)      MISS (250,214,218)
301   MISS (115,64,73)        MISS (119,58,66)     R=119 fails "R > 120" by one
                                                   7 misses -> break
300   RED  (133,36,45)        RED  (124,36,50)     the red cap starts here
```

Compression lightened four rows of pale blue past `R < 210`; two of the seven
rows fail their threshold **by a single unit**. The climb halts one row below
the red segment. Per-date value is the 75th percentile over the bar's ~6
columns, and in 088 only one of six columns reaches the red, so the percentile
flips from 65 px to 0. The bar reads 27 instead of 43: 28 blue + 15 red became
27 blue + 0 red.

### 1.3 It is a common-mode error, not a set of outliers

Composition of the 184-case fall across the whole figure:

```
alive (blue)  2106 -> 1989   (-117)
dead  (red)   1127 -> 1060   ( -67)

49 bars lower · 45 unchanged · 4 higher by 1
red cap wiped entirely:            1 bar   (25 July, -16)
blue-only change:                 31 bars  (-1 x 21, -2 x 3, -3 x 2, -4 x 2, -6, -8, -14)
mixed alive+dead:                 24 bars  (e.g. 8 Jun -5/-9, 9 Jun -8/-1)
```

One cause, ~98 simultaneous measurements, magnitude per bar set by where the
washed rows fall relative to two hard cuts and a run-length rule. This is the
single most important property to design against: **the error is per-image, not
per-bar.** Any error model that treats bars as independent will under-state it,
and any likelihood that absorbs outliers one at a time will absorb it while its
mean moves.

### 1.4 It keeps happening

Their stable-region invariant — the total over onset dates old enough that late
reporting can add at most a case or two — must be flat and slowly rising.
Computed over every committed vintage, on the common window "onset date on or
before 12 July":

| SitRep      | report    | digitised  | printed n | deficit | stable <= 12 Jul | vs baseline |
| ----------- | --------- | ---------- | --------- | ------- | ---------------- | ----------- |
| 083         | 5 Aug     | 3033       | 3033      | —       | 2255             | +23         |
| 087         | 9 Aug     | 3233       | 3362      | -3.8%   | 2219             | -13         |
| **088-091** | 10-13 Aug | 3049       | 3362      | -9.3%   | **2085**         | **-147**    |
| 092-093     | 14-15 Aug | 3525       | 3767      | -6.4%   | 2228             | -4          |
| **094-096** | 16-18 Aug | 3559       | 3838      | -7.3%   | **2180**         | **-52**     |
| 097         | 19 Aug    | 3886       | 4084      | -4.8%   | 2250             | +18         |
| _098_       | _20 Aug_  | _excluded_ | _4140_    | _+3.4%_ | _(~ +280)_       | _excluded_  |
| 099         | 21 Aug    | 3959       | 4140      | -4.4%   | 2238             | +6          |
| 100         | 22 Aug    | 4066       | 4238      | -4.1%   | 2235             | +3          |
| 101         | 23 Aug    | 4084       | 4287      | -4.7%   | 2221             | -11         |
| **102**     | 24 Aug    | 4024       | 4372      | -8.0%   | **2136**         | **-96**     |

Baseline ~2232. That total cannot fall, so every fall is a bad read: 087->088
(-134), 093->094 (-48), 101->102 (-85). 092's +143 is not a drift up, it is the
return to baseline after 088 — the artefact being paid back, and the same +143
that moved the model.

The renders are also shrinking: 571 px tall at 087/088, 534 at 101, **455 at
102**, 501 at 103. Fewer pixels per case means a washed row costs a larger
fraction of a case, so sensitivity is _increasing_ over time. SitRep 101 and 102
are the same encoder at the same quality (JPEG ratio 5.7% and 5.8%); 102 is
simply 79 px shorter, and reads 96 cases low.

### 1.5 What upstream knows, and what they do about it

- Issue **#594 (open)**: "Onset digitiser over-counts ~10% when INSP embeds the
  figure at a larger render (SitRep 098 excluded)". The general principle —
  render changes the reading — is known and logged.
- Issue **#617 (open)**: a date-alignment anomaly at 102->103.
- Issue **#488 (closed)**: the two-sided per-scan error. Closed by _re-
  including_ a scan that had been excluded for failing monotonicity, on the
  grounds that the committed data fails that property worse. That is why a
  184-case fall did not stop anything.
- The algorithm is **unchanged**. Their workaround is data-level: exclude the
  offending vintage (098 only), documented in a `CONFIG` comment.
- Their stable-region test was invented for 098 on 24 August, two weeks after
  088 was ingested, and has never been run retrospectively. Applied to 088 it
  fires immediately: 134 below 087 and 143 below 092, against a 36-case scatter
  among the other three vintages.
- #594's framing is directional — over-counting at a _larger, lossless_ render.
  088 is the mirror case (under-counting at a smaller, more compressed render)
  and is not covered by the issue.

## Part 2 — requirements for our reader

### 2.1 Gates that must fail the build

**G1. Render fingerprint, recorded and compared.** For every vintage record the
embedded image object's width, height, encoding (jpeg / lossless), compression
ratio, and the SHA-256 of the _decoded_ pixels. Refuse the vintage if width,
height or encoding departs from the trailing median of the last five by more
than a declared tolerance. SitRep 098 (1267x789 lossless against ~830x510 jpeg)
and SitRep 102 (455 px tall against 534) are both caught by this alone, before a
single bar is read.

**G2. Read against the figure's own printed total.** Both the title and the
source note print `n = N`. Parse it, compare, and gate on a band. Two cautions
learned the hard way: the band is **render-conditional**, not a scan-noise band,
so a single global band will keep admitting bad reads; and a deficit against n
is expected (the axis truncates), so the gate must be two-sided with an
asymmetric floor.

**G3. Stable-region neighbour test — the decisive one.** For onset dates at
least 28 days before the report date, compare the total against **both**
temporal neighbours on a common window. Refuse if it deviates from both in the
same direction by more than 3x the local neighbour scatter. Calibration from the
observed data: good vintages scatter by 15-36 cases; 088 sits 134-143 low; 098
sits ~280 high; 102 sits ~85-96 low. A 3-sigma rule catches all three and admits
every good vintage.

**G4. Falls are investigated, never averaged.** A per-bar fall is _not_ on its
own evidence of scan error — a re-dated case moves one bar down and another up
(upstream's #488 correction, and they are right). The test is a fall with
nothing nearby absorbing it: pair each falling day against rises within +/-2
days, and escalate the unabsorbed residual. Across 087->088 the whole figure has
49 falls and 4 rises of 1, absorbing nothing.

**G5. Date-alignment shift test.** L1 distance between consecutive vintages at
shifts -1/0/+1 days must minimise cleanly at 0. Read `last_tick` off the
rendered figure, never infer it: the printed tick is sometimes the _publication_
date rather than the report date, and it can freeze for seven vintages while
report dates advance.

**G6. Detect the figure by content, never by caption.** SitReps 084-086 print a
weekly notification-date chart under an onset-labelled caption; 081-083 carry
the onset figure under a notification-week caption. Reject any candidate whose
axis title contains "notification". Where no onset figure is found, **emit an
explicit refusal with a reason** — a silent skip is indistinguishable from a
parse failure.

**G7. Axis calibration asserted, not assumed.** The y-axis gridline step changed
from 0/20/40/60 to 0/25/50/75 at SitRep 087; a wrong divisor rescales every bar.
Detect the step from the printed tick labels and assert it against the allowed
set, per vintage.

### 2.2 Algorithm choices that delete whole failure classes

**A1. Do not flood-fill upward with a fixed miss tolerance.** This one rule
produced the 25 July amputation. Better: the bars carry a dark outline — find
the bar top as an _edge_, and find the blue/red boundary as an edge, so a gap in
the fill cannot terminate the measurement. Failing that, scan _downward_ from
the top of the plot for the first mask pixel, which cannot truncate early.

**A2. Do not use hard RGB thresholds.** Two of the seven fatal rows missed their
cut by one unit of the red channel. Classify each pixel by nearest palette
colour in a perceptual space with an explicit rejection radius, and **calibrate
the palette per image from the legend swatches**, which every figure prints
("Vivant" / "Décédé"). That removes the render dependence at its source rather
than tuning a threshold per vintage.

**A3. Take the bar height as a robust statistic over columns, but report the
spread.** The 75th percentile over six columns flipped from 65 px to 0 because
five columns truncated. If the column-wise spread within one bar is large, the
bar is not measured — flag it rather than percentile over it.

**A4. Publish per-bar uncertainty from the geometry.** Pixels per case is known
(4.32 at the 087/088 render, ~3.5 at 102's). Emit +/- half a pixel per edge as a
per-bar interval so downstream sees the resolution shrinking as renders shrink.

**A5. Read the faded bars, or refuse the dates they cover.** The bars inside the
"données potentiellement incomplètes" band are printed but their lightened fill
falls outside a naive colour mask, so those dates silently vanish. Either extend
the palette to the faded fills or record those dates as explicitly uncovered.

### 2.3 What to publish alongside the numbers

**P1. A per-vintage quality record**, keyed on the decoded-image SHA-256: render
fingerprint, deficit against printed n, stable-region deviation from both
neighbours, alignment-test result, and a status of accepted /
accepted-with-caveat / excluded with a reason string.

**P2. Never emit an increment without both endpoints' quality flags.** An
increment spanning a flagged vintage is not an observation.

**P3. Coverage as a column**, consistent with the pipeline's existing rule: how
many onset dates the figure actually printed, and which dates the axis did not
reach. Dates past the axis are unobserved, not zero. When differencing two
vintages, clip to the intersection of their printed extents.

**P4. Deduplicate on the decoded image hash _and_ on the digitised block.**
Neither is sufficient alone. Value-dedup collapses 088-091 correctly but misses
that 087 and 088 are the same chart; image-hash dedup catches byte-identical
reprints but not a re-encode of one chart. Only G2/G3 catch the re-encode.

### 2.4 The statistical requirement, if anyone fits this stream

**S1. The error is per-image. Model it that way.** Give each vintage a
multiplicative scale nuisance with a tight prior, so a whole-figure misread has
somewhere to go that is not the latent onset curve. Upstream's own source
concedes the point (`observations.jl:2914-2917`: "the ~4% scan-level error is
measured per vintage ... Treating it per cell is a tractability choice") and
then treats it per cell anyway.

**S2. Heavy tails are not a substitute.** A Student-t with nu = 4 absorbs each
of 49 correlated residuals as individually plausible while the mean of the set
drags. Fat tails buy tolerance for one misread bar, not for one misread image
seen 49 times.

**S3. Scoring increments does not neutralise a per-scan level error.** It
converts it into a spurious increment. Upstream chose increments over levels
precisely because of the "~4% per-scan level error [that] revises the total both
ways" (`docs/src/news.md:233-235`) — the mitigation is aimed at the wrong end of
the same problem.

**S4. If a vintage is flagged, drop the increments that span it** rather than
down-weighting them.

### 2.5 Regression fixtures — use these exact documents

These are golden tests with known answers:

- **087 vs 088** (`SITREP_MVEBDB_087_09_08_2026_VF.pdf`,
  `SITREP_MVEBDB_088_10_08_2026_11.pdf`): the same chart at two encodings. **A
  correct reader returns the same totals from both, within its stated per-bar
  resolution.** Upstream's returns 3233 and 3049. Assert on the 25 July bar
  specifically: 28 alive + 15 dead.
- **098**: a lossless 1267x789 render of the same chart family; must not
  over-count by 10%, and must be caught by G1 and G3 if it does.
- **102**: a 455 px-tall render; must not read 96 cases low on the stable
  region.
- **084-086**: no onset figure. A correct reader refuses explicitly and names
  the reason.
- **081**: JPEG tick marks 1 px tall; axis detection must not silently drop
  every other tick.

## Part 3 — process, not code

Two failures here were not algorithmic.

**The caveat and the estimator lived in different files.** The digitiser's
header still reads "The values are approximate and are not fitted by the model;
they are captured for later use" — written 2026-07-20, stale by 2026-07-21 when
the stream was fitted, and still stale today. Requirement: a stream cannot ship
without a machine-checked statement of what it measures and how it may be used,
in the same artefact the model reads.

**The check existed and did not run.** Their stable-region test is about twenty
lines, needs only the committed CSV, and would have flagged 088, 094 and 102. It
lives in a `CONFIG` comment beside the one vintage it caught. Requirement: every
gate in 2.1 runs over **every** vintage on **every** build, and adding a vintage
re-runs history.

## Sources

- notes/2026-08-26-onset-curve-jpeg-digitisation.md (this repo) — the
  investigation, with the full evidence chain and the independent review
- epiforecasts/BVDOutbreakSize at `777083b` and `main`:
  `scripts/digitize_onset_curve.py` (masks at :140-141, climb at :324-340),
  `src/onset_curve.jl`, `src/models/observations.jl`, `data/README.md`,
  `docs/src/news.md`, issues #488, #555, #594, #617
- INSP PDFs fetched from insp.cd per that repo's own WordPress recipe: SitReps
  087, 088, 101, 102
- `data/onset_curve_scanned.csv` at `f83b8e9`, `777083b` and `main`
