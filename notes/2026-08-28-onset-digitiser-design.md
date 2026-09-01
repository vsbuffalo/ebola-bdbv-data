# Design: an onset-figure reader that cannot fail the way upstream's did

Date: 2026-08-28 Project: ebola-bdbv-data Tags: onset-curve, digitisation,
design, types, pipeline Requirements:
`notes/2026-08-28-onset-digitiser-requirements.md` (the measured failure
analysis this design answers) and
`notes/2026-08-26-onset-curve-reporting-triangle.md` (what the stream is and why
we want it). Every requirement label used below — G1–G7, A1–A5, P1–P4, S1–S4 —
refers to the requirements note.

## The design, plainly

Start from what is knowable before reading a single pixel. The figure is a
stacked bar chart: for each onset date, a blue rectangle (cases alive as of the
snapshot) with a red rectangle on top (cases dead). Bar heights are whole
numbers of cases — a bar holds 28 cases or 29, never 28.4. And the y-axis prints
the exchange rate between pixels and cases: if the gridlines sit 25 cases apart
and 108 pixels apart, one case is 4.32 pixels. So the entire content of one bar
is a pair of small integers — call them _a_ (alive) and _d_ (dead) — and the
resolution at which the image can express them is known exactly.

How upstream read a bar: start at the baseline and climb one pixel at a time,
asking each pixel "are you blue?" or "are you red?" against hard RGB thresholds
such as `R < 210`; after seven consecutive pixels answering neither, stop and
declare the bar finished. JPEG compression smears colours slightly, so in the
088 render a few pale-blue rows near one bar's top failed the rule — two of them
by a single unit on one channel — the climb hit seven misses one row below the
bar's red cap, and a 43-case bar read as 27. The structural flaw is not the
particular thresholds; it is that any one pixel is allowed to terminate the
measurement.

This design never asks a pixel to decide anything. It reads each bar twice, by
two methods that share no mechanism, and accepts the bar only when they agree.

**Reader one — discrete optimisation against a rendered bar.** Invert the
problem: instead of interrogating pixels, enumerate every admissible answer and
ask how well each explains the picture. For a candidate pair (a, d) we know
exactly what the bar should look like — blue fill for the first `a x 4.32`
pixels of height, red for the next `d x 4.32`, background above — so render that
hypothesis, score it against the observed pixels, and do this for _every_ pair
of whole numbers the panel could hold. Keep the best-scoring pair. This is
maximum-likelihood estimation by exhaustive enumeration: the integer lattice
makes the hypothesis space finite and small, so the global optimum is found by
sweeping it, with no optimiser and no thresholds. A smeared pixel now shifts one
candidate's score by a sliver; roughly two thousand pixels vote per bar; nothing
can truncate anything.

**Reader two — the outline-edge reader.** The chart draws every bar segment with
a thin dark outline, a much darker stroke than either fill. So the two
quantities of interest — the bar's top, and the internal blue-to-red boundary —
exist in the image a second time, as dark horizontal lines, findable by looking
for sharp darkness minima along each pixel column without ever classifying a
fill colour. Reader two measures the same (a, d) from those lines alone. It
fails in different circumstances than reader one (blur versus wash), which is
the point: agreement between two mechanisms that share no blind spot is
evidence; upstream's two implementations were ports of one algorithm and misread
088 identically.

Around that core, every vintage passes through whole-figure gates — the bars
must sum to the total the title prints; totals over onset dates old enough to be
settled may never fall between vintages — implemented as pure functions of the
published CSVs, so they run over all of history on every build. Upstream's
decisive check existed and lived in a comment beside one vintage; here the
checks are the build.

## Types first

The middle layer, as data types. Python dataclasses; polars at the edges;
everything below is a pure function of PDF bytes plus committed registers.

```python
@dataclass(frozen=True)
class FigureCandidate:
    """One embedded raster pulled from a sitrep page, before we know what it is."""
    sitrep: int
    report_date: date          # from data/raw/insp_sitrep_index.tsv, never from a tick
    page: int
    width: int
    height: int
    encoding: Literal["jpeg", "lossless"]
    compressed_bytes: int
    decoded_sha256: str        # hash of decoded RGB pixels: the vintage's identity (P1)

@dataclass(frozen=True)
class Identification:
    """What the raster is, decided from its content, never its caption (G6)."""
    kind: Literal["onset_daily", "notification_daily", "notification_weekly",
                  "map", "other"]
    evidence: str              # the matched title/axis text, verbatim

@dataclass(frozen=True)
class Refusal:
    sitrep: int
    reason: str                # "no onset figure: page 2 chart is by notification date"
    stage: Literal["identify", "calibrate", "read", "gate"]

@dataclass(frozen=True)
class Palette:
    """Calibrated from this image's own legend swatches (A2), plus the faded
    variants derived analytically from the incomplete-band overlay (A5)."""
    alive: tuple[float, float, float]        # sampled from the Vivant swatch
    dead: tuple[float, float, float]         # sampled from the Décédé swatch
    band: tuple[float, float, float]         # the incomplete-band pink
    alpha: float                             # band opacity, estimated from the image
    # faded fills are alpha-composites of the above, not free parameters:
    #   faded_alive = alpha*band + (1-alpha)*alive, likewise dead

@dataclass(frozen=True)
class Calibration:
    """Geometry asserted against allowed sets, each field carrying its evidence.
    A Calibration that cannot be established is a Refusal, before any bar is read."""
    panel: tuple[int, int, int, int]         # plot-area box (x0, y0, x1, y1)
    baseline_y: float
    px_per_case: float                       # from y gridline pitch / y_step
    y_step: int                              # asserted in {20, 25}  (G7)
    px_per_day: float                        # from x gridline pitch / 7
    bar_pitch: float                         # must equal px_per_day within tolerance
    anchor: tuple[date, float]               # (printed tick date, its x) — see the
                                             # anchor register below (G5)
    axis_extent: tuple[date, date]           # first and last onset date the axis reaches
    band_start: date | None                  # where the incomplete band begins
    palette: Palette

@dataclass(frozen=True)
class BarMeasure:
    onset_date: date
    alive: int                               # integer counts, by construction
    dead: int
    margin: float                            # fit score gap, best vs second-best (a,d)
    reader_agreement: bool                   # did the independent reader concur (A3)
    provisional: bool                        # inside the incomplete band (A5)
    resolution_cases: float                  # 1 / px_per_case, published always (A4)

@dataclass(frozen=True)
class VintageRecord:
    """One row per decoded image: the quality record the gates read and
    publish (P1). Keyed on decoded_sha256."""
    candidate: FigureCandidate
    calibration_summary: dict[str, float]
    printed_n: int                           # read from the title (G2)
    digitised_total: int
    stable_region_total: int                 # onset <= report_date - 28 d (G3)
    status: Literal["accepted", "accepted_with_caveat", "refused"]
    reasons: tuple[str, ...]
```

Published artifacts, each a `make` target:

- `data/build/onset/vintages.csv` — one `VintageRecord` per decoded image,
  including refusals. Refusals are rows, not absences (G6).
- `data/build/onset/snapshots.csv` — long format: one row per (vintage, onset
  date), columns
  `sitrep, report_date, decoded_sha256, onset_date,
  alive, dead, total, provisional, resolution_cases, margin`.
  This is the primary object. It carries levels, not increments.
- `data/build/onset/triangle.csv` — derived, never primary: increments between
  consecutive accepted deduplicated vintages, clipped to the intersection of the
  two axis extents (P3), every row carrying both endpoints' `decoded_sha256` and
  status (P2).
- `registers/onset_axis_anchors.tsv` — see below.
- `registers/onset_reader_overrides.tsv` — hand exclusions with reasons, in the
  style of the existing override registers. Empty until something earns a row.
- `data/build/onset/images/<date>-<sitrep>-<sha12>.png` — the extracted chart
  itself, one per distinct decoded image, named by the _earliest_ report date
  and sitrep that carried it plus the first 12 hex of the decoded-pixel SHA-256
  (so `2026-08-10-088-0f69d3208a41.png` also stands for the 089–091 reprints;
  `vintages.csv` holds the full mapping and the full hash). `pdfimages` pulls
  the embedded raster object directly, so these are the exact pixels the PDF
  carries, not a re-rendered crop; they are what every downstream number was
  read from, published so a human can look without opening a PDF.
- `data/build/onset/proof/<date>-<sitrep>-<sha12>.png` — the same chart with the
  reader's conclusions drawn on top: detected panel and gridlines, the date
  assigned to each bar, each bar's fitted alive/dead heights as outlines with
  the counts beside them, flagged bars in a warning colour. This is the human
  check built into the build: a one-day date misregistration that no CSV row
  reveals is instantly visible as every outline sitting beside its bar, and the
  anchor register's saved crops are cut from these. Same idea as the laboratory
  extraction carrying the sentence it read — the artifact ships its own audit.

## Module boundaries and seams

```
scripts/onset/
  locate.py      PDF -> [FigureCandidate]          (pdfimages the pages, hash)
  identify.py    FigureCandidate -> Identification (glyph match on title strip)
  calibrate.py   image -> Calibration | Refusal    (gridlines, ticks, legend)
  readers.py     image, Calibration -> [BarMeasure]  (the two readers + adjudication)
  gates.py       pure functions over vintages.csv / snapshots.csv  (G1-G5)
  assemble.py    snapshots -> dedup -> triangle
  glyphs/        committed digit atlas (see "reading printed numbers")
```

The seams, and what each buys:

- **identify / read.** The reader never sees a PDF and never sees a caption.
  Everything after `identify` operates on one decoded image plus its provenance.
  Reports 084–086 (notification charts under an onset caption) are refused at
  this seam with the axis title as evidence, and the refusal is a row in
  `vintages.csv`.
- **calibrate / read.** The reader consumes a `Calibration` and cannot run
  without one. A vintage whose gridline step or bar pitch cannot be established
  refuses _before_ a single bar is read — a wrong divisor rescaling every bar
  (G7) is unrepresentable because the divisor is asserted against `{20, 25}` at
  construction.
- **read / gate.** The gates take only the published CSVs, not images. This is
  deliberately the property upstream lacked: their stable-region test needed
  only the committed CSV and never ran. Ours are ordinary tests plus a build
  step; adding a vintage re-runs all of history because the gates' input is all
  of history.
- **snapshot / triangle.** Increments are derived from levels at assembly and
  carry both endpoints' identity. Nothing downstream can construct an increment
  across a refused vintage without forging a hash (S4, P2).

## Reader one: discrete optimisation against a rendered bar (the primary)

**Setup.** Calibration hands the reader, for one bar: the strip of pixel columns
the bar occupies, the baseline row it grows from, the exchange rate
`c = px_per_case`, and the palette (the fill colours sampled from this image's
own legend). The unknowns are two non-negative integers, the alive count _a_ and
the dead count _d_.

**The hypothesis space.** Every pair (a, d) with `(a + d) * c` no taller than
the panel is a candidate — at 4.32 px per case and a ~420 px panel, a few
thousand pairs. That finiteness is the gift of the integer lattice: because the
truth is a pair of whole numbers, the space of possible answers can be swept
exhaustively rather than searched.

**What one hypothesis predicts.** If (a, d) were the truth, the strip would look
like: alive fill from the baseline up `a * c` rows; dead fill for the next
`d * c` rows; background above (white, gridline dots, or the pink
incomplete-band overlay, whichever the calibration says is behind this bar); and
a one-pixel dark outline at each boundary. Inside the incomplete band the fills
are the alpha-composited faded colours — one compositing formula, not a second
code path (A5).

**Scoring a hypothesis is evaluating a likelihood.** Model each pixel as its
predicted class colour plus noise: the pixel's contribution is a clipped
distance to the palette colour of the class the hypothesis assigns it, which
makes the total a robust log-likelihood — Gaussian in colour space near the
palette, flattened in the tails so no single aberrant pixel dominates. One
refinement carries real weight: rows within one pixel of a hypothesised boundary
get weight zero. JPEG concentrates its worst smearing exactly at colour
transitions, so those rows carry almost no information about which class sits on
either side — down-weighting them is a heteroskedastic noise model, the
principled form of "ignore the smeared pixels". The seven washed rows that
killed upstream's read of the 25 July bar sat precisely at the blue-red
boundary: in this fit they are zero-weight rows, and even if scored they would
be seven votes among two thousand.

**Computation.** Compute, once per strip, three per-row aggregate scores — this
row's pixels scored as alive fill, as dead fill, and as background:
`S_alive[r]`, `S_dead[r]`, `S_bg[r]`. The objective for (a, d) is then the sum
of `S_alive` over the first `a*c` rows, `S_dead` over the next `d*c`, and `S_bg`
above — three contiguous ranges, so with prefix sums each candidate evaluates in
O(1) after O(H) preparation, and the full sweep is O(H²) per bar. Sweep
everything; take the argmax. Because the space is enumerated, the argmax is the
_exact global_ maximum-likelihood estimate: no optimiser, no initialisation, no
local minima, no convergence criterion, and bit-for-bit deterministic — which
the repository's byte-identical rebuild rule requires anyway.

**What is reported.** The argmax (a, d); `margin`, the log-likelihood ratio
between the best pair and the runner-up — so "confident" has a stated meaning:
the second-best hypothesis is implausible by a known factor — and
`resolution_cases = 1/c`, the physical limit of what this render can express
(A4). A bar whose margin is small is flagged, never guessed (A3's principle,
applied to the fit rather than to a percentile over columns).

**The lattice is also a calibration alarm.** The fit is only as good as `c` and
the date registration beneath it — miscalibrate either and every bar reads
confidently wrong by the same factor, which is the one failure a per-bar score
cannot see. But a wrong `c` leaves a fingerprint: fitted segment heights,
measured in raw pixels, stop sitting near integer multiples of `c`. The
residual-to-lattice distribution across the whole figure must be sharply peaked
near zero; if it is not, the calibration is wrong and the vintage refuses before
publishing a number. A wrong exchange rate cannot fail silently.

## Reader two: the outline-edge reader (the independent check)

The chart's renderer strokes every bar segment with a thin dark outline — in the
088 forensics the outline row reads around RGB (115, 64, 73) against fills near
(200, 229, 237) and (202, 38, 45). That stroke means the two quantities reader
one estimates exist in the image a second time, encoded differently: the bar's
top and the alive/dead boundary are _dark horizontal lines_, and finding a dark
line does not require classifying a single fill pixel.

**Mechanics.** For each pixel column in the bar's strip, take the luminance
profile from the panel top down to the baseline. Outline rows appear as sharp
local minima — a one-to-two-pixel dip far darker than either fill or the
background. Collect the minima that beat a contrast threshold relative to their
neighbourhood; the topmost is the bar-top edge, and a second minimum between it
and the baseline, if present, is the blue-red boundary (a bar with no red cap
has no second edge, so d = 0 falls out naturally rather than being a special
case). Convert the two edge heights to counts through the same `c` as reader
one. Then aggregate across the bar's handful of columns: the estimate is the
median, and — following A3 — the column-wise spread is reported alongside it. If
the columns disagree beyond tolerance, the bar is refused by this reader rather
than averaged into respectability: a large spread means the bar was not
measured, and upstream's 75th-percentile-over- columns is exactly the move that
converted five truncated columns and one good one into a confident wrong answer.

**Why two readers, and why these two.** Independence of mechanism is the
requirement, and upstream shows why: their Julia and Python implementations were
ports of one algorithm, agreed byte-for-byte, and misread 088 identically —
redundancy without diversity checks nothing. Fit and edge fail in _different_
renders: the fit is weakest when compression washes the two fills toward each
other (the colours blur but the outlines survive); the edge reader is weakest
when downsampling blurs the thin outlines away (the strokes fade but the fill
regions survive). A render bad enough to defeat both at once is a render the
gates should refuse anyway.

**Adjudication.** Agreement within `max(1 case, resolution)` on both components
→ accept reader one's value, `reader_agreement = true`. Disagreement → the bar
is flagged, and neither value is promoted — a disagreement is information about
the image, not a vote to be settled by averaging. More than a declared fraction
of flagged bars → the whole vintage refuses (gate G-R below), because per-image
error is the failure mode this entire design exists to catch.

## Calibration: everything from the figure, one register for dates

- **Panel and gridlines** from structure: the panel border rectangle, dotted
  gridline columns and rows by periodicity inside it. `px_per_day` from x pitch
  over 7; `px_per_case` from y pitch over the asserted step.
- **Palette from the legend swatches** the figure always prints (A2). No RGB
  constant appears anywhere in the reader; renders that shift colours
  recalibrate themselves. Band colour and its opacity are estimated from the
  band region above the bars; the faded fills follow by compositing.
- **Reading printed numbers** — the title's `n = 3 767`, the y tick labels — by
  template match against a small committed glyph atlas (digits and a few
  punctuation marks, extracted once per render family, normalised for scale).
  Deterministic, dependency-free, auditable: the atlas is data in the repo, not
  a system OCR binary whose version moves. The identification step's title
  matching ("date de debut des symptomes" vs "notification") uses the same
  machinery at word level.
- **The x anchor date is a register, not an inference.** G5's caution is sharp:
  the printed tick is sometimes the publication date rather than the report
  date, and froze for seven vintages while report dates advanced — so nothing
  may derive the axis dates from the sitrep's own date, and month words in two
  locales at five render scales are the one genuinely fragile OCR target.
  `registers/onset_axis_anchors.tsv` records, per decoded image hash: the
  leftmost labelled tick as printed (verbatim), its date, and the rightmost
  likewise. One row per _distinct image_ (reprints share theirs), human-entered
  against a saved crop, machine-validated three ways: the two anchors must be an
  integer number of weeks apart matching the gridline count; bar count must fit
  the implied extent; and the G5 shift test against neighbouring vintages must
  minimise at zero. A wrongly entered row cannot survive the gates. This is the
  one manual input, the same one upstream accepted, but held in a register with
  evidence instead of a script constant.

## Deduplication, then the triangle

Two-level, per P4, with one improvement a correct reader makes available:

1. **Byte level**: identical `decoded_sha256` → one vintage spanning the report
   dates (collapses 088–091 and 092–093).
2. **Value level**: identical digitised blocks within stated resolution → one
   vintage. For a render-robust reader this also collapses the 087/088 pair —
   the same chart re-encoded — which upstream's reader could not see _because
   its own values differed across the re-encode_. Two readings of one chart are
   one observation of the epidemic; treating them as two is the
   transcription-vs-measurement confusion this repository already refuses
   elsewhere.

The triangle then differences consecutive surviving vintages, clipped to the
intersection of the two axis extents — dates one figure does not plot are
unobserved, not zero (P3) — and refuses to emit any increment touching a
non-accepted endpoint (S4 becomes structural, not advisory).

## Gates, all of them pure functions over published rows

| gate                        | input           | fires on (calibrated from the requirements note)                                                                                                                                                                                |
| --------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G1 render fingerprint       | `vintages.csv`  | width/height/encoding departing from trailing five-vintage median beyond declared tolerance — catches 098 (1267×789 lossless) and 102 (455 px) before reading                                                                   |
| G2 printed-n reconciliation | `vintages.csv`  | digitised total outside a render-conditional band around printed n; two-sided, asymmetric floor for the axis-truncation deficit                                                                                                 |
| G3 stable region            | `snapshots.csv` | total over onset ≤ report − 28 d deviating from _both_ neighbours, same direction, > 3× local scatter (good vintages scatter 15–36; 088 sat 134–143 low; 098 ~280 high; 102 ~85–96 low — all caught, none of the good vintages) |
| G4 unabsorbed falls         | `triangle.csv`  | falls not paired against rises within ±2 days; a re-dated case absorbs, a wash does not (087→088: 49 falls, 4 one-unit rises, nothing absorbed)                                                                                 |
| G5 alignment                | `snapshots.csv` | L1 between consecutive vintages at shifts −1/0/+1 not minimised at 0                                                                                                                                                            |
| G-R reader disagreement     | `snapshots.csv` | flagged-bar fraction above threshold                                                                                                                                                                                            |

G6 and G7 live upstream of the gates, at the identify and calibrate seams, where
their failures are refusals by construction. All gates run in `make
test` over
every vintage on every build; a new sitrep re-runs history because history is
the input (the Part 3 requirement, made structural).

## The measurement contract travels with the stream

Per the repository's rule, the streams gate on `registers/stream_families.tsv`
sentences. The onset family's sentences must state: that levels are the
observation and increments are derived; that the read error is **per image,
common-mode across bars** (S1, S2 — a whole-figure misread is one error seen
~100 times, and any consumer treating cells as independent will understate it);
that `resolution_cases` bounds the per-bar read; and that the figure plots the
subset of confirmed cases with both vital status and onset date recorded —
76–78% of the confirmed cumulative in the vintages measured so far — so
increments conflate late reporting with onset-date backfill, and the coverage
ratio published beside the stream is the diagnostic. That last clause is this
repository's own finding (2026-08-26 note) and belongs in the contract, not in a
note nobody re-reads: upstream's worst process failure was a caveat and an
estimator living in different files.

## Fixtures, from documents we already hold

All five regression fixtures from the requirements note are in
`data/raw/sitrep_pdfs/` already; they become pinned tests:

- **087 vs 088**: same chart, two encodings — the reader must return equal
  totals within resolution, the 25 July bar must read alive 28, dead 15, and
  value-dedup must collapse the pair.
- **098**: refused by G1 (render fingerprint) before reading; if read anyway in
  a test harness, G3 must fire.
- **102**: 455 px render — must not read the stable region ~96 low; G3 is the
  backstop if it does.
- **084, 085, 086**: explicit refusals naming the notification axis.
- **081**: one-pixel tick marks — axis detection must find the full tick set or
  refuse; silently halving the tick pitch would double `px_per_day` and cannot
  pass the anchor register's integer-weeks check.

Plus one fixture upstream cannot have: two _synthetic_ renders of a known chart
(drawn by us, counts known exactly, re-encoded at JPEG qualities bracketing the
observed 4.8–11%), asserting exact recovery. That turns "the reader is
render-invariant" from an observed property into a tested one.

## Decisions left open (deliberately)

1. **Analytique-era vintages (059–083).** Same chart family at different render
   sizes and English ticks; the design covers them, but whether the first build
   ships them or starts at 087 is scope, not architecture.
2. **Gate thresholds.** The requirements note gives measured calibrations (3×
   scatter, five-vintage trailing median, ±2-day absorption). They should ship
   as named constants in one place with the measurement quoted — but whether any
   lives in a register instead of code is a taste call.
3. **The anchor register vs full OCR of month words.** The register is one human
   row per distinct image, triple-validated; full OCR removes the human but adds
   the fragile locale-dependent word matching G5 warns about. Design assumes the
   register; swapping later touches only `calibrate.py`.

## Next

1. `locate` + `identify` + the refusal rows for 084–086 — small, and immediately
   produces the vintage inventory.
2. `calibrate` with the glyph atlas and anchor register, gated by the
   integer-weeks and lattice checks.
3. Reader one, fixtures 087/088 first; reader two; adjudication.
4. Gates over the published CSVs; then the triangle.
5. `stream_families.tsv` sentences and the coverage-ratio series beside the
   stream.
