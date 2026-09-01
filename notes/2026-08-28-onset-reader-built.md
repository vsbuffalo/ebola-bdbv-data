# The onset reader, built: what it measured and what the stream shows

Date: 2026-08-28 Project: ebola-bdbv-data Tags: onset-curve, reporting-triangle,
digitisation, delay-distribution, results Design:
`notes/2026-08-28-onset-digitiser-design.md` (implemented as written, with one
recorded deviation, below). Requirements it answers:
`notes/2026-08-28-onset-digitiser-requirements.md`.

## What exists now

`make onset` reads the symptom-onset epidemic curve out of the sitrep figures'
pixels and publishes, under `data/build/onset/`, byte-identically reproducible:

- `vintages.csv` — one row per report from 059: identity (decoded-pixel
  SHA-256), calibration, read totals, printed-total reconciliation,
  deduplication, and a gate verdict with reasons. Refusals are rows.
- `snapshots.csv` — the levels: 3,203 rows of (vintage, onset date, alive, dead)
  with per-bar fit margin, two-reader agreement, the source's incomplete-band
  flag, and the render's resolution in cases.
- `triangle.csv` — derived, never primary: 3,039 increments between consecutive
  accepted vintages on the intersection of their axis extents, both endpoint
  hashes on every row.
- `images/` and `proof/` — the exact pixels each number was read from, and the
  reader's fitted outlines drawn onto them. The proof overlays are the
  date-registration check no CSV can express: the month rules land on the
  first-of-month bars.
- `figures/onset_vintages.png` and `figures/onset_delay.png` — the stream and
  its delay shape, drawn by registered functions in `scripts/plot_figures.py`
  with declared inputs.

The implementation follows the design note: reader one enumerates every integer
(alive, dead) pair per bar and scores it as a robust cost with the boundary rows
at zero weight; reader two reads the same two numbers from the dark desaturated
outline strokes; calibration measures everything from the figure being read
(legend-swatch palette, tick-regression day pitch, digit-recognition y axis
against the committed glyph atlas in `scripts/lib/onset/glyphs/`); the one
manual input is `registers/onset_axis_anchors.tsv`, a printed tick label per
distinct image, machine-checked three ways. Eleven regression tests in
`tests/test_onset.py` pin the design's fixtures; the full suite is 365 passing.

## How well it reads

Against each figure's own printed total, across all 24 titled renders: sixteen
exact or within one case, twenty within four, worst deficit −25 cases (−0.6%) at
the most compressed render — where a real share of the deficit is cases whose
onset falls past the axis end, printed in n but not plotted. The upstream
reader's committed results on these same images run −3.8% to −9.3%.

The design's central fixture — sitreps 087 and 088, one chart at two JPEG
encodings, which the upstream reader read 184 cases apart and which moved a
published reproduction number — reads 3362 (deficit zero) and 3355, with 145 of
146 aligned bars within one case. The two vintages then collapse in value-level
deduplication, which is the correct epidemiological statement: two readings of
one chart are one observation.

Deduplication also found a source behaviour nobody had recorded: INSP
republishes one data snapshot across consecutive reports far beyond the
byte-identical reprints. The 42 reports from 059 reduce to 24 genuine
observations — 087–091 are one chart, as are 098/099, 082/083, 062/063, 069–071,
073/074 and 079/080. The printed-n series itself (2,064 on 17 July to 4,372 on
24 August, strictly monotone across all 24 titled renders) is a new extracted
series, and its monotonicity is a validation cumulative counts must pass.

## Yes — this is an onsets data stream, and what it looks like

`snapshots.csv` is the stream: for every accepted vintage, the confirmed
epidemic curve by symptom-onset date, split alive/dead as of that report. It is
the only epi-dated observation in this outbreak's published data; everything
else we hold is report-dated.

`figures/onset_vintages.png` shows all of it. The upper panel overlays all 24
vintages: each line is the same epidemic curve as one report published it, and
the fan — early vintages peeling downward and rightward from the dark latest
curve — is late reporting made visible. Lines agree almost everywhere on the
left (settled dates) and separate over the trailing three to four weeks (dates
still filling in). The lower panel is what one vintage carries: the 24 August
snapshot stacked by vital status, with the source's own "données potentiellement
incomplètes" band carried through as the provisional flag.

Reading the latest vintage: onsets from late April, a climb through May and June
to a sustained plateau of roughly forty to sixty confirmed cases per onset day
through July and mid-August, and an apparent fall in the last two weeks that the
fan warns against reading as decline — the same visual fall appears at the right
edge of every earlier vintage and fills in later.

## The delay shape: measurable, and measured

`figures/onset_delay.png` answers whether the triangle can inform a delay
distribution: it already does, empirically. For each of 69 settled onset dates
(final count ≥ 10, at least 35 days old at the last report), the bar height at
every later vintage is expressed as a share of where it finally settled — 1,631
(onset date, vintage) observations of the cumulative distribution of the delay
from symptom onset to appearing in the published figure.

The shape: median completion is **55% by day 7, 82% by day 13, 93% by day 22**,
effectively complete by five weeks, with a tight interquartile band — the delay
process is stable across onset dates, which is exactly what a nowcasting model
needs it to be. The curve rises steeply through the first two weeks and carries
a long thin tail; the few percent arriving after a month is real and visible per
onset date.

Read against the one fitted delay from this outbreak: Akilimali et al. (NEJM
395(6):610) give onset → diagnostic sample a median of 4.8 days for confirmed
cases. Our curve crosses one half between days 6 and 8 — longer, as it must be,
because it stacks the laboratory turnaround, the DHIS2 entry with an onset date
recorded, and the figure's own publication on top of sampling. The gap between
the two is the administrative limb, now roughly measurable as a couple of days
at the median.

Three caveats travel with the shape, all from the 2026-08-26 note. An increment
cannot distinguish a late-reported case from an old case whose empty onset-date
field was back-filled; the two are conflated here. The figure plots only cases
with vital status and onset date recorded — 76–78% of the confirmed cumulative
where we measured it — so this is the delay of the *recorded-onset* subset. And
the overshoot above 1.0 on some lines is re-dating: a bar can settle below an
earlier reading because cases move between bars, so the "cumulative"
distribution is empirical, not enforced. The figure keeps the overshoot visible
rather than clipping it; 99 of the 3,039 triangle cells are negative, which is
the entire non-monotonicity budget of the stream as read.

## Loose ends, stated plainly

- **Sitrep 059 is refused**, loudly, at calibration: the earliest render places
  its bars 0.63 slots off its own tick grid, which no other render does. Its
  chart also draws no bar outlines the edge reader can find. Someone should look
  at the proof crop before anyone relaxes a tolerance.
- **The 25 July fixture reads 29 alive + 15 dead**, against the requirements
  note's 28 + 15. The dead cap — the component the 088 incident amputated —
  matches exactly; the bar top sits within half a pixel of both totals at 4.33
  px/case, both our readers agree on 29 at a confident margin, and our
  whole-figure total reconciles exactly where the 28 comes from a reader that
  ran 129 low on the same image. The test pins the dead cap exactly and the
  alive count to stated resolution.
- **G1 (render fingerprint) flags rather than refuses on its own** — the one
  deviation from the design note, recorded in `gates.py`. The note calibrated G1
  on a render-dependent reader; this one reconciles the 098 lossless outlier (−1
  case) and the 455-px 102 render (−0.6%) with their own titles. G1 still
  refuses jointly with a failed G2 or G3, which is the actual scenario the note
  describes.
- **Sitreps 060–062 print no title**, so printed-total reconciliation cannot run
  there; they pass on the neighbour gates alone and carry a caveat.
- **Not done, deliberately**: publishing model-ready streams under
  `data/build/streams/` (a contract decision — it needs `stream_families.tsv`
  sentences saying what levels, increments and the per-image common-mode error
  mean, and an owner's sign-off); the coverage-ratio series (figure n over our
  validated national confirmed — the backfill diagnostic); onset-to-death from
  the alive→dead conversions the vital-status split makes observable; and any
  CHANGELOG entry or tag.

## Next

1. The coverage-ratio series across all 24 vintages — one join against
   `province_series.csv`, and the diagnostic that bounds the backfill confounder
   before anyone fits the triangle.
2. Onset → recorded death from the Vivant→Décédé conversions on settled dates:
   the ΔN ≈ 0 windows are now queryable directly from `snapshots.csv`.
3. The contract decision on publishing, then the stream-family sentences.
4. Sitrep 059's geometry, from its proof crop.
