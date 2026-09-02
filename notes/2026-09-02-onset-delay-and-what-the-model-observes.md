# The onset-to-report delay, and why it is not the delay the model represents

Date: 2026-09-02 Project: ebola-bdbv-data Tags: onset, reporting-delay,
reporting-triangle, camdl, dwell_care, corrections

Continues
[2026-08-26-onset-curve-reporting-triangle.md](2026-08-26-onset-curve-reporting-triangle.md),
which built the triangle and asked whether onset → detection was recoverable. It
is, and this note is what it turned out to say once someone compared it to what
the model actually assumes.

## Context / question

The modelling side fits `cases_national` with

```
projected = incidence(confirm_die) + incidence(confirm_disch)
          + incidence(die_community)
```

Two questions came out of reviewing that block: is the sum the right thing to
compare to the data, and is there a lag between the two that nothing represents?

The first has a short answer. `confirm_die` and `confirm_disch` are transitions
*into* the confirmed compartment `C`, both firing at `gamma_care`, with `f_cfr`
choosing the destination. They are confirmations labelled by eventual fate, not
deaths and discharges — those are `die_facility` and `discharge`, which are
correctly absent from the sum. So the projected quantity is every route into the
confirmed register, exhaustive and non-overlapping.

The second is the rest of this note.

## The instants are different

`cases_*` is indexed by **report** date. The model's confirmation event is a
**sampling** event: `dwell_care` is priored on Akilimali's onset-to-sample
Gamma, and the model's own docstring says "laboratory turnaround unrepresented".

So the question is how far apart those two instants are, and the reporting
triangle can answer it, because it records when each onset cohort first appeared
in a published vintage.

## Two wrong answers before the right one

Worth recording because both were published to the cross-repo channel and both
had to be corrected there.

**First answer, 5–6 days.** Taken from an onset-to-report mean of 13.2 d across
the whole triangle, differenced against the 7.4 d onset-to-sample prior. Wrong
because it pools cohorts that are not comparable.

**Second answer, 1–3 days.** Taken from the July cohort's mean of 10.2 d against
the same 7.4 d. Better, but still differencing two means from different
populations, and still derived without looking at a figure this repository
already builds.

**The actual answer is ≈1.5 days at the median**, and it comes from
`data/build/onset/figures/onset_delay_vs_model.png`, which plots the three
distributions on one axis rather than comparing their summary statistics.

The lesson is the cheap one: check what the repo already computes before
recomputing it worse. The figure existed, was built by a committed target, and
answered the question directly.

## What the comparison figure shows

Three cumulative distributions over days since symptom onset:

| curve            | what it is                                                      |
| ---------------- | --------------------------------------------------------------- |
| Akilimali et al. | onset → sample, Gamma(k = 0.86, θ = 8.605), mean 7.4 d, n = 129 |
| camdl model      | two-phase hyperexponential, w = 0.1, means 1.5 / 8.06 d         |
| this extraction  | onset → appearance in the published figure, median with IQR     |

Three readings:

1. **The model's hyperexponential sits almost exactly on the paper's Gamma.**
   The approximation is good and is not where any error lives. (A Gamma with
   shape below 1 has a spike near zero that a single exponential cannot produce;
   a two-phase mixture can. Same device as the fate-splitting described below.)

2. **The administrative limb is ≈1.5 d at the median** — the horizontal distance
   between our publication curve and the paper's sampling curve. Over a 7-day
   emit schedule that is a fifth of a bin. Small.

3. **The tail is not small.** Our curve sits below the Gamma from about day 3
   out to day 55, where the Gamma has essentially completed by day 35. That gap
   is where the retrospectively-attached cases live.

## The cohort figure, and a claim that had to be withdrawn

Delay by onset month, from the triangle:

```
onset month      n      mean    median   p90
2026-04          3     115.0 d    115    117
2026-05         87      79.3 d     77    102
2026-06        161      39.1 d     37     67
2026-07      1,398      10.2 d      9     19
2026-08      1,002       7.1 d      7     13
```

The first reading of this was that the early cohorts are slow because "the
epidemic's early history was reconstructed retrospectively". **That is a claim
about INSP's behaviour and it is not supportable.** The real cause is
**left-truncation in our own archive**: our vintage series begins in July, so a
May onset date is first seen already part-reported, and the increments the
triangle observes for it are only its late tail. The apparent delay is a
property of when our archive starts.

`onset_delay_cohorts.png` states this outright — "May and June dates are first
seen already part-reported (left-truncation), so their short-delay limbs are
points, not curves" — and the open circles on that figure are precisely the
initial stock, everything the record holds of the left limb for dates before the
first held vintage.

The conclusion that pooled cohorts overstate the routine delay survives. The
reason first given for it does not.

**What does survive is measured in a matched window that controls for the
truncation.** Over days 12–21 since onset, June onsets reached 0.81 of their
eventual total and July onsets 0.89. Reporting genuinely sped up.

## The tail, quantified

Of the cases appearing in each report month — all of which land in that month's
`cases_*` bins regardless of when the person fell ill:

```
              <=14 d    15-30 d    >30 d    >60 d
July           77.7%      16.1%     6.2%     1.8%
August         77.8%      11.9%    10.3%     4.9%
```

About a tenth of each month's reported cases had onset more than a month
earlier, **and the share is growing**. This is the 22 July harmonisation
phenomenon running continuously rather than only on the days the source
announces it. `registers/retrospective_batches.tsv` records two declared days
and `cases_excluding_backlog` removes those; neither touches this.

## What this implies for the model

**The median shift is negligible and the tail is not.** A constant 1.5 d shift
would fit the centre and leave the tail, which is the part that carries the
backfill. A convolution with the published distribution handles both.

**The prior is anchored on the slowest era.** Akilimali's Gamma was fitted on
the May-era Ituri cohort. Reporting sped up after it and the fit window is
July–August, so `dwell_care`'s prior is anchored on the period least like the
one being fitted, and anchored slow.

**Two effects pull opposite ways, so the sign is not obvious.** The May-era
anchor is too slow for a July–August window; our publication tail is longer than
the paper's sampling Gamma. Which dominates is a question for the posterior, not
for this note.

**A citation question sits underneath it.** If `dwell_care` silently absorbs the
administrative limb, it is not the quantity Akilimali measures, and the citation
is doing work it cannot support. Either convolve the delay explicitly and let
the parameter keep its stated meaning, or re-anchor the prior and drop the claim
that the paper pins it. The diagnostic that distinguishes them is whether fitted
`dwell_care` presses against its 15.5 d ceiling.

**And one flag on the dispersion regime.** The model's `pre` indicator switches
at day 22, which is 2026-06-10. The reporting speed-up measured above sits
between the June and July onset cohorts — the same weeks. A dispersion parameter
that switches where reporting behaviour also changes is at risk of absorbing a
surveillance change as epidemiological over-dispersion, and the case series
alone cannot separate the two.

## An aside on the model's shape, since it came up

The model assigns fate at an instantaneous branch and then gives each fate its
own waiting time — `p_care`/`p_dcom`/`p_rec` at onset, `f_cfr` at confirmation.
The reason is a constraint of Markov compartments: if people leave one
compartment by dying at rate *a* or discharging at rate *b*, the fraction dying
is *a/(a+b)* and the mean stay is *1/(a+b)* **for both outcomes**. You cannot
have the people who die stay 4.8 days while the people who discharge stay 13.5.
Splitting at entry decouples the branching probability from the two durations
and makes all three free.

The cost, which is an assumption and not a free lunch: fate is fixed at the
moment of confirmation and does not depend on time already spent in care. In
reality someone who survives the first week has a better prognosis, so fate and
duration are coupled; this construction makes them independent.

## Artefacts

Built by `make onset`, under `data/build/onset/figures/`:

- `onset_delay_vs_model.png` — the three-distribution comparison
- `onset_delay_cohorts.png` — completion by onset month, with the matched window
- `onset_vintages.png`, `onset_delay.png`

Published in `data/2026-08-30-r5`:

- `data/build/streams/reference/reporting_delay.tsv` — the distribution, per
  onset cohort, as share and cumulative share
- `meta["reporting_delay"]` — the summary, naming the settled cohort

## Next

The triangle ends **2026-08-24** against a data date of 2026-08-30, because the
onset reader refuses four recent vintages: 103, 106 and 107 want an axis-anchor
row in `registers/onset_axis_anchors.tsv`, and sitrep 108's x ticks left the
weekly grid every earlier report used. The proof crops are not generated for
refused vintages, so registering the three needs the crops made first. 108 is
the one worth looking at rather than clearing — a changed axis is a change in
the source, not a gap in the reader.
