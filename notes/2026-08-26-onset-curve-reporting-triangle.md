# The symptom-onset epidemic curve as a reporting triangle

Date: 2026-08-26 Project: ebola-bdbv-data Tags: onset-curve, reporting-triangle,
digitisation, delay-distributions, dhis2

## Context / question

The INSP situation reports carry a figure we have never extracted: the epidemic
curve by **symptom-onset date**, drawn from the DHIS2 line list. (DHIS2 is the
routine health-information platform the response enters case records into; the
situation reports — "sitreps" — are the daily PDFs the Institut National de
Santé Publique publishes.) Every stream this repository currently publishes is
**report-dated**: it says what a cumulative total was on the day a report was
printed. The onset figure is the only thing in the source that is **epi-dated**
— it says when people actually became ill.

Two questions:

1. What exactly is this data stream, and do we hold what is needed to build it?
2. Does it yield a distribution of onset → detection, or onset → death?

Short answers: it is a _reporting triangle_, not a time series; we hold every
input, in more vintages than anyone has used; and yes to both distributions,
with specific censoring caveats that determine how it must be extracted.

## What a reporting triangle is

The onset curve is never final. A person who first felt ill on 25 July might not
be swabbed until 30 July, confirmed on 2 August, and entered into DHIS2 with an
onset date on 4 August. The 25 July bar therefore keeps growing every time the
figure is republished. Each published figure is a **snapshot** — a _vintage_ —
of the same underlying curve, taken on a different day.

Indexing by onset date _u_ (the column) and report date _s_ (the row), the cell
value is the increment

    y(s, u) = N_s(u) − N_{s−1}(u)

where `N_s(u)` is the bar height for onset date _u_ in the figure published at
report date _s_. That increment counts cases with onset _u_ that became visible
between one publication and the next, at delay _d = s − u_. The stack of these
cells over all (s, u) is the triangle, and it is a direct measurement of the
**reporting-delay distribution**.

Why anyone wants it: it is what makes _nowcasting_ possible. The last several
bars of any onset curve are always artificially low, because the cases that will
fill them have not been confirmed yet. Without a delay distribution you cannot
tell an epidemic that is genuinely turning over from one whose recent bars are
merely incomplete. With one, you inflate the recent bars by the expected
still-missing fraction.

It is also the only observation in this outbreak's data that separates three
otherwise-confounded effects. A change in true incidence moves a **column** of
the triangle; a change in reporting effort on a given day moves a **row**; a
change in the delay distribution itself moves a **diagonal**. Multiple snapshots
are what make those separable at all — a single onset curve cannot do it.

## What the source actually prints, and where it changes

We hold 96 of the 102 numbered sitreps as pinned PDFs with SHA-256 recorded in
`data/raw/sitrep_pdfs.manifest.tsv`, running to report 102 (24 August). The
missing numbers are **003, 029, 043, 045, 075 and 076**. The onset figure first
appears in report 059 (12 July). We hold **42 reports from 059 onward** (075 and
076 are the only gaps in that range); three of them — 084, 085 and 086 — carry
no onset figure, leaving **39 candidate vintages** before deduplication.

The document format changes at report 084, and this is the single most dangerous
feature of the source.

**Reports 059–083** use a long "analytique" layout (15 pages). Section _2.4
Analyse temporelle — courbes épidémiques_ carries two numbered figures:

- `FIGURE 3 — COURBE EPIDEMIQUE PAR SEMAINE DE NOTIFICATION` — weekly, by
  notification week.
- `FIGURE 4 COURBE EPIDEMIQUE PAR DATE DE DEBUT DES SYMPTOMES (LISTE LINEAIRE
  DHIS2)`
  — this is the onset curve, daily, stacked by vital status.

**Reports 084 onward** use a 6–7 page brief. The text above the chart reads
_"Évolution de cas par date de début des symptômes au cours de 21 derniers
jours"_, and that caption is **wrong, in three different ways, at three
different points in the series**:

| reports  | what the caption says | what the embedded figure actually is                                                                                                                                 |
| -------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 084, 085 | onset, last 21 days   | an Excel-style stacked bar whose own axis label reads **"Date de notification"**, 15 juil – 4 août, 21 bars, **values printed as data labels**                       |
| 086      | onset, last 21 days   | a **weekly notification-week** curve, `Cas confirmes vivants et decedes par semaine de notification (n = 3 757)`, 30 Mar – 03 Aug, **values printed as data labels** |
| 087–102  | onset, last 21 days   | the real daily onset curve, spanning **April to August** — not a 21-day window at all                                                                                |

An extractor that keys on the caption will silently ingest
**notification-dated** counts as **onset-dated** counts at reports 084–086, and
will also believe it is reading a 21-day window when it is reading a four-month
curve. The caption text is identical from 084 through 102 while the figure
underneath changes twice. This is the failure mode to design against.

### Vintages that are reprints, not new observations

Hashing the extracted images shows the same chart is republished across
consecutive report dates:

| reports            | figure SHA-256 (first 8) | dimensions | printed n                  |
| ------------------ | ------------------------ | ---------- | -------------------------- |
| 084, 085           | `0a47deae`               | 913×468    | — (notification chart)     |
| 086                | `a5a5b682`               | 988×543    | 3 757 (notification weeks) |
| 087                | `2a52ac52`               | 966×571    | not read                   |
| 088, 089, 090, 091 | `0f69d320`               | 966×571    | 3 362                      |
| 092, 093           | `b98b708e`               | 792×519    | 3 767                      |

Four consecutive report dates (088–091) carry one image. Differencing across a
reprint yields a row of exact zeros that is not evidence of anything — it must
be collapsed to the earliest vintage before any increment is formed.

### Rendering changes between vintages

The figures are re-rendered by the source with settings that drift:

- **Axis locale changes.** Report 083 and report 088 label months in English
  (`01 Apr`, `05 Aug`); report 092 labels them in French (`06 avr`, `10 aout`).
- **Y-axis gridline step changes.** Report 083 uses 0/20/40/60/80; reports 088
  and 092 use 0/25/50/75.
- **Tick phase changes.** Ticks are every 7 days in all vintages seen, but the
  phase moves — 083 starts on 01 Apr, 092 starts on 06 avr.
- **Bars overrun the rightmost printed tick.** In report 088 the last labelled
  tick is 05 Aug but bars continue past it. Any calibration that assumes the
  final bar sits at the final tick will misregister every date in the figure.

### The figure is raster, and carries no data table

All the onset figures are embedded raster images. There is no vector path data
and no accompanying table, so pixel digitisation is genuinely the only route —
this is not a case where a better PDF parser avoids the problem. The printed n
in the title is **not** in the PDF text layer either; it is part of the raster
and must be read out of the image.

Bar colours are clean and well separated: Vivant ≈ RGB (192, 227, 238), Décédé ≈
RGB (202, 38, 45), with the _données potentiellement incomplètes_ shading ≈
(250, 214, 216). The images are JPEG-compressed, so those colours spread and
exact matching will fail; nearest-centre classification with a distance
threshold is required.

## The finding that changes how the stream should be read

Every version of the figure prints its own denominator in the title, and the
footnote defines it: _"cas confirmés avec statut vital et date de début de
symptômes renseignés"_ — confirmed cases with **both** a recorded vital status
**and** a recorded onset date. That is not all confirmed cases.

Against our own extraction, which reproduces the sitrep's printed national
`Total` exactly (report 083 prints 4 053; our `province_series.csv` sums to 4
053):

| report date | sitrep | figure n | our national cumulative confirmed | coverage | confirmed cases absent |
| ----------- | ------ | -------: | --------------------------------: | -------: | ---------------------: |
| 5 Aug       | 083    |    3 092 |                             4 053 |   76.3 % |                    961 |
| 10 Aug      | 088    |    3 362 |                             4 449 |   75.6 % |                  1 087 |
| 14 Aug      | 092    |    3 767 |                             4 843 |   77.8 % |                  1 076 |

Roughly a thousand confirmed cases are absent from the onset curve at every
vintage, and the coverage fraction is not constant.

The consequence is specific. The increment `N_s(u) − N_{s−1}(u)` sums two
mechanisms that the figure cannot distinguish:

1. a genuinely new confirmation with onset _u_ — late reporting, the signal;
2. a case confirmed days earlier whose **onset-date field was only just filled
   in** — backfill of a missing field, not an epidemiological event.

Over 10 → 14 August the backfill component was small: the stock of absent cases
moved only 1 087 → 1 076 while the figure grew by 405 and confirmations grew by
394. But nothing constrains it to stay small. A DHIS2 data-cleaning pass that
populates three hundred empty onset dates would appear as a late-reporting surge
concentrated on recent onset dates, and would push R_t up with no change in
incidence whatsoever.

**The coverage ratio is therefore a required diagnostic, not an optional one.**
It is cheap: the figure's printed n against our own validated national
cumulative, per vintage. Any model fitting this triangle should carry the
completeness fraction explicitly rather than letting its drift leak into
whichever parameter is least constrained.

One gap to note: report 087 (9 August) does not print province-level cumulative
confirmed cases, so `cum_cases` is null for all provinces in our series at that
date and the coverage ratio cannot be formed there from province rows. A
national route may still reach it.

## Do we get onset → detection and onset → death?

Yes to both, with different censoring problems.

### Onset → appearance in the published figure

This is what the triangle measures directly. It is worth being precise that it
is _not_ the clinical ascertainment delay. It is the convolution of onset →
sample collection, sample → laboratory confirmation, confirmation → DHIS2 entry
_with an onset date recorded_, and DHIS2 → figure regeneration. It is an
administrative pipeline delay and is necessarily longer than onset → sample.

That gives a validation rather than a conflict. Akilimali et al., _NEJM_
395(6):610 (6 Aug 2026), fit onset → diagnostic sample collection on the
laboratory line list with `epidist`, correcting for double interval censoring
and right truncation: median **4.8 d** (95% CrI 3.46–7.84) and mean **7.4 d**
(5.3–13.5) for the 129 laboratory-confirmed cases, data as of 5 June 2026. The
triangle's delay distribution must be stochastically longer than that; the
difference is the laboratory-plus-data-entry limb. If it comes out shorter, the
digitisation or the date registration is wrong.

**The censoring problem is at the short end, which is where the mass is.** Each
figure stops its x-axis short of its own report date, so for onset date _u_ the
first vintage _s₀_ that plots it already contains an accumulated stock
`N_{s₀}(u)`, built up over all delays `d ≤ s₀ − u`, which was never observed as
an increment. Delay zero is never seen.

There is an identification argument that partly rescues this, and it matters for
how the stream should be extracted. For an onset date old enough that its bar
has stopped moving, the eventual total `N_∞(u)` is known. Then

    N_{s₀}(u) / N_∞(u)

is one point on the delay cumulative distribution, evaluated at `d₀ = s₀ − u`.
Because the axis end sits a _varying_ number of days short of the report date
across vintages, `d₀` differs between onset dates, so this yields the CDF at a
range of short delays rather than at a single point. That is a real short-delay
constraint, and it is stronger than extrapolating from a pooled baseline.

The practical consequence: **extract the initial stock `N_{s₀}(u)` and the
eventual total `N_∞(u)`, not only the consecutive-vintage increments.** A
pipeline that stores only differences throws away the information that
identifies the short end of the delay distribution.

### Onset → death

This is the more valuable one, and it is available because the bars are
**stacked by vital status**, with vital status recorded _as of the snapshot_
rather than as of confirmation.

Write `B_s(u)` for the Vivant (alive) count and `R_s(u)` for the Décédé (dead)
count, so `N = B + R`. A case counted alive at vintage _s−1_ who dies before
vintage _s_ moves from `B` to `R`. Therefore

    ΔR = R_s(u) − R_{s−1}(u)
       = (newly ascertained cases with onset u already dead)
       + (previously counted alive cases with onset u who died in the interval)

The two mechanisms separate cleanly whenever `ΔN = ΔB + ΔR = 0`: for an onset
date old enough that no new cases are arriving, any `ΔR > 0` is a pure
vital-status conversion — a death with a known onset date, recorded in a known
window. That is a direct observation from the onset-to-death distribution. More
generally the conversions are identified given a dead-on-arrival fraction for
newly ascertained cases, which is itself estimable from onset dates where
`ΔN ≈ 0`.

Caveats that must travel with any such estimate:

- It is onset → **recorded** death, not onset → death. The death-reporting delay
  still needs deconvolving, and the triangle constrains the _ascertainment_
  delay, not necessarily the death-reporting delay.
- "Vivant" means alive as of the snapshot, **not recovered**. A case-fatality
  ratio read off a recent vintage is biased downward by right censoring. That
  same property is what makes the conversions observable.
- Everything here is conditional on vital status being recorded, one of the two
  inclusion criteria. If the ~1 000 absent cases are death-enriched — plausible,
  since community deaths confirmed post-mortem are the hardest to interview for
  an onset date — the recovered distribution is biased. **This is untested and
  should be tested**: compare the red fraction of the plotted subset against the
  report's own printed national case-fatality ratio (45.7 % at report 083). I
  attempted this measurement and did not get a result I trust, so it is stated
  here as an open question, not a finding.
- Digitising the internal blue/red boundary is required, not just the bar top.
  This is likely _more_ accurate than the total, not less: the internal boundary
  is a hard transition between two saturated colours, whereas the bar top meets
  white background through an antialiased dark outline.

### Why this is worth the effort for this project

`notes/2026-08-22-rho-reporting-and-priors.md` records two open gaps that this
stream speaks to directly. First, that no _fitted_ onset-to-death distribution
with a published shape parameter for an ebolavirus was located — medians and
ranges are abundant, a fitted gamma or Weibull is not. Second, that our `gamma`
prior is anchored to the wrong pathway: it governs the never-confirmed-alive
route, but is taken from a convolution running _through admission_ (implied mean
≈ 13 d) rather than the separate community pathway (mean 8.17 d).

The onset curve is the only source in hand that could give an outbreak-specific,
community-inclusive onset-to-death distribution, on roughly 3 800 cases rather
than the 129 laboratory-confirmed in Akilimali et al., and running four months
later than that paper's 5 June data cut.

## Directions for the agent building this

The task is a new extraction: **raw sitrep PDFs → a digitised onset-curve
register → model-ready triangle streams.** Read `scripts/extract_lab_prose.py`
and `README.md` §"How it is validated" first; the refuse-rather-than-guess idiom
there is the standard this must meet.

### Non-negotiable: detect the figure by its content, never by its caption

The caption lies from report 084 onward. Identify the onset figure by the
embedded raster itself. The real onset curve has all of:

- a title inside the image beginning
  `Nombre des cas confirmes par date de debut
  des symptomes (n = …)`
- an x-axis title `Date de debut des symptomes`
- a red dashed vertical annotation reading
  `Premier resultat positif du
  laboratoire`
- a legend `Issue` with `Vivant` and `Decede`
- **no printed data labels on the bars**

Reject any candidate whose axis title contains `notification`, and reject any
candidate that prints data labels — both are the notification charts. Because
the title is in the raster, this needs either OCR of the image's top strip or
hashing against known-good exemplars. Prefer OCR: it also reads the printed n,
which is the checksum.

**Emit an explicit refusal, with a reason, for every report where no onset
figure is found.** Reports 084, 085 and 086 must land in that refusal list, and
the reason must say what was found instead. A silent skip here is
indistinguishable from a parsing failure, and this is precisely the boundary
where a future re-run will break.

### Order of operations

1. **Locate the candidate images per report.** The figure sits on page 5 in the
   analytique layout and on pages 2–4 in the brief, drifting with the length of
   the preceding tables; do not hardcode the page — find it.
2. **Deduplicate by image SHA-256 before anything else.** Collapse
   byte-identical reprints to the earliest report date that carried them.
   Reports 088–091 share one image and 092–093 share another; a triangle built
   without this step contains rows of structural zeros.
3. **Self-calibrate axes from the figure's own ticks.** Do not assume the last
   bar aligns with the last tick — in report 088 the bars overrun it. Derive
   pixels-per-day from the _gridline spacing_ and anchor on a labelled tick,
   then check that the implied first and last bar dates are consistent with the
   axis extent.
4. **Handle the rendering drift explicitly**: English and French month
   abbreviations, y-gridline steps of both 20 and 25, and shifting tick phase.
   Each should be _detected_, not configured per vintage where that can be
   avoided; where a per-vintage override is unavoidable, it belongs in a
   register file, not in the code.
5. **Digitise three quantities per bar**, not one: the alive count, the dead
   count, and the total. Classify pixels by nearest colour centre with a
   distance threshold — the images are JPEG-compressed and exact matching fails.
6. **Treat the faded bars inside the _données potentiellement incomplètes_ band
   as observed-and-flagged, not missing.** They are the same two colours
   alpha-blended over the pink shading; a mask tuned only to the saturated
   colours drops them, which silently deletes the most recent and most
   informative onset dates. Carry a `provisional` flag column instead.

### Validation, layered outward

- **Against the figure itself**: the digitised bars must sum to the printed n in
  the title. Report the residual per vintage; upstream's reproduction of this
  runs −5.0 % to +1.6 %, so anything much worse than that indicates a problem.
- **Against our own extraction**: the coverage ratio, figure n over our
  validated national cumulative confirmed. Publish this as a series in its own
  right — it is the diagnostic for the backfill confounder described above, and
  it is useful independently of the triangle.
- **Against monotonicity**: `N_s(u)` should be non-decreasing in _s_ for fixed
  _u_, because late reporting can only add cases. It will not be, in the scans.
  Count and report every violation with its magnitude rather than clipping it —
  the violations are the measurement error budget, and they are what tells us
  whether a heavy-tailed likelihood is warranted or whether the digitiser is
  misregistering dates.
- **Against the weekly notification curve**: reports 086 and Figure 3 of the
  analytique layout **print their values as data labels**. Read those labels
  rather than digitising them. That gives an exact second epidemic curve on a
  different clock, plus a second completeness denominator (`n = 3 757` for
  notification-date completeness at report 086 against `n = 3 767` for onset
  four days later). Differencing those denominators across vintages measures
  field completeness directly, with no pixels involved. This is cheap and should
  be built first.

### One open discrepancy to resolve, not inherit

An external reading of these figures reports the 25 July bar as 34 (report 083),
43 (087), **27** (088), 49 (092). The 27 should be impossible — late reporting
cannot remove cases — and on visual inspection there is no bar anywhere near 27
in that region of report 088, where bars run roughly 40–60, and the faded
incomplete band in that vintage begins around 4 August, well clear of 25 July. I
could not measure it rigorously enough to state a number.

Before accepting that value as source inconsistency, rule out **x-axis date
misregistration**: report 088 is exactly the vintage where bars overrun the
rightmost printed tick, and a calibration anchored on "rightmost tick =
rightmost bar" would shift every date in that figure. Resolving this decides
whether the heavy-tailed likelihood that external work uses to absorb negative
increments is modelling the source or absorbing a bug.

### Repository conventions this must meet

- Every artifact is a `make` target; re-running reproduces it byte-identically.
  Nothing under `data/build/**` without a rule that regenerates it.
- The networked fetch stays separate from the offline deterministic processing.
  The PDFs are already pinned with SHA-256 in
  `data/raw/sitrep_pdfs.manifest.tsv`; digitisation is offline and must not
  touch the network.
- No hardcoded absolute paths, anywhere.
- Any new published stream needs a sentence in `registers/stream_families.tsv`
  saying what it measures and how it is to be read, or `make streams` fails.
  That failure is the register working — do not route around it.
- Per-vintage overrides (a y-axis step that genuinely cannot be detected, a
  figure that must be excluded by hand) belong in a register TSV with a reason
  column, in the style of `registers/sitrep_number_overrides.tsv`.
- Tests in the style of `tests/test_extraction.py`, pinning at minimum: report
  084 and 086 are refused with the correct reason; reports 088–091 collapse to
  one vintage; the printed n reconciles for reports 083, 088 and 092.

### Scope boundary

Extract the register, publish the coverage-ratio series, and report the
monotonicity violations. **Whether the triangle is published as a fitted stream,
and whether the delay and onset-to-death distributions are estimated from it, is
a separate decision** that depends on what the coverage series and the violation
counts show. Do not cut a CHANGELOG entry or a tag for the modelling step.

## Next

1. The weekly notification curve with printed data labels — exact, no
   digitisation, and it yields the completeness denominator. Cheapest first
   step.
2. The coverage-ratio series across all 39 candidate vintages. This decides
   whether the triangle is worth extracting at all.
3. The digitiser proper, against the validation ladder above.
4. Only then: the delay and onset-to-death distributions, with the
   vital-status-completeness bias tested rather than assumed.
