# Priors for the unidentified directions in the national fit

Date: 2026-08-22
Project: ebola-bdbv-data
Tags: priors, identifiability, ascertainment, literature

## Context / question

The modelling repo's national fits mix badly. The pair plots show four
distinct problems, and only one of them is a sampler problem:

1. **A hyperbolic ridge in (γ, q)** — the classic signature of a product
   being identified while its factors are not.
2. **ρ_lab and ρ perfectly collinear** — a straight line in the pair plot,
   so the two reporting probabilities are one direction, not two.
3. **log-posterior rising monotonically with ρ** — the likelihood is still
   improving at the edge of the prior, i.e. ρ is prior-dominated and its
   posterior is essentially its prior.
4. **Chain-separated clusters in q, p_h, δ** — two modes, not one.

Priors alone will not fix (1) or (2). What fixes them is *measurement* where
we have it, and *reparameterisation* where we do not.

## The strongest result: the ridge is already measured

The share of confirmed cases first ascertained **at death** rather than alive
is directly observable in our data, and it is exactly the quantity the (γ, q)
ridge is missing.

**First, a denominator that must not be collapsed.** Two different quantities
are both being called the escape fraction, and they differ by exactly q:

- what is **observable** — among *confirmed* cases, the share confirmed at
  death: `e_obs = γq / (τ + γq)`;
- what the **model wants** — P(never confirmed alive), over *all* infections:
  `e_model = γ / (τ + γ)`.

They coincide only if q = 1, i.e. only if every unisolated fatal infection is
found and swabbed. Since the observable's denominator excludes the infections
that were never confirmed at all, **e_obs ≤ e_model always**, with the gap
widening as swab ascertainment falls.

The reports state a day's new confirmations and decompose them into living
and dead positives (*"89 nouveaux résultats positifs (59 vivants et 30
décès)"*, sitrep 093 Ituri), and `deaths_community` is the dead half — equal
on 24 of 26 province-days where both are printed. So

    e_obs = deaths_community / new_cases

is measurable without any assumption about the disease course, which is what
makes it worth more than the factor-3-4 dwell-shape sensitivity.

**It is not a single number, and the spread is not noise.** Two features of
the source both bias the naive sum-ratio downward, so `scripts/escape_fraction.py`
(target `make escape-fraction`) reports it under four exclusion rules:

| rule | days | e_obs | γq/τ |
|---|---|---|---|
| all overlapping days | 32 | 875/3004 = 0.291 | 0.411 |
| span-matched | 31 | 841/2917 = 0.288 | 0.405 |
| span-matched, no backlog dump | 30 | 800/2548 = 0.314 | 0.458 |
| no consolidation backlog | 10 | 322/914 = **0.352** | **0.544** |

The two contaminants: 22 July publishes **369** new confirmations against a
same-week national norm near 80 — a backlog release, people infected earlier
entering the register late, so they belong in earlier days' denominators; and
on 9 August the community-death figure covers **4 days** while the case figure
covers **1**, so dividing them compares a four-day numerator to a one-day
denominator. Both inflate the denominator alone. The `consolidating` flag
marks the whole backlog period, and the ratio rises monotonically as that
period is excluded, which is the direction the mechanism predicts.

**So: γq/τ = 0.41 – 0.54, national.** That is the ridge, pinned — free of any
disease-course assumption. The remaining free direction is **q alone**:

| q | e_model = P(never confirmed alive) | share of infections ending unascertained |
|---|---|---|
| 0.915 | 0.307 – 0.373 | **0.026 – 0.032** |
| 0.810 | 0.333 – 0.402 | 0.063 – 0.076 |
| 0.589 | 0.408 – 0.480 | 0.167 – 0.197 |
| **0.45** | **0.474 – 0.547** | **0.261 – 0.301** |
| 0.30 | 0.575 – 0.645 | 0.402 – 0.451 |

**A claim I have to withdraw before it does damage.** I expected this to
falsify the current fit and it does not. The fit's escape fraction of 0.308
sits inside the 0.307–0.373 band that its own q ≈ 0.915 implies, so it is
internally consistent with the measurement. The case against q ≈ 0.915 rests
entirely on the **decomposition** — q = unisolated fatality × swab
ascertainment, and 0.915 demands near-perfect swabbing of a near-universally
fatal unisolated infection, for the least lethal human ebolavirus. That
argument stands on its own; the escape fraction does not reinforce it.

**What this constraint adds that the 0.619 death split does not.** The
community share of confirmed *deaths* (875/1414 = 0.619) has confirmed deaths
in its denominator, so it is entangled with facility fatality and the share
reaching care: roughly γq/(γq + τ·p_h·f_cfr). The ratio here has confirmed
*cases* in its denominator, so it pins γq/τ **without** f_cfr or p_h. Same
numerator, different denominator, and the second is the clean one. Imposing
both is strictly more informative than either.

**Province heterogeneity is real and argues against a single national τ.**
γq/τ runs 0.51–0.60 in Nord-Kivu against 0.30–0.38 in Ituri and 0.21–0.31 in
Haut-Uélé — a factor of about 1.7. Either case-finding differs sharply by
province or swab ascertainment does; both are reasons not to pool.

## The second result: one of the two reporting parameters is measured

ρ is defined as P(a laboratory-confirmed case reaches the published report).
We can measure that step directly, because the reports print the laboratory
positives and the new confirmed cases in the same document. Over the 62
province-days where both appear:

- **positives = new cases on 53 of 62 province-days** (0.855), from the
  pipeline's own `positives_vs_new_cases` record in `meta.json`;
- national totals **3,115 positives over 14,101 tests**.

**The direction of the discrepancy is explained by the source, not by
under-reporting.** Sitrep 080 prints the mechanism outright: *"210
échantillons … dont 53 positifs … 39 nouveaux cas confirmés et 18
reprélèvements"*. A positive result is not the same event as a new case,
because **re-swabs of already-confirmed patients test positive again**. So
positives run slightly *above* new cases by construction, and the published
new-case count is a register of distinct confirmations rather than a
reconciled subset of the laboratory's output.

So ρ ≈ 1. Fixing it, or giving it a prior tight against 1, removes the
ρ_lab–ρ collinearity outright — a measurement, not a prior choice. Whatever
ascertainment is missing is missing *before* the laboratory, and ρ_lab should
carry all of it.

## Data-derived anchors from our own pipeline

Measured here, so they are checkable rather than borrowed. Two carry a
circularity warning: they come from the outbreak being fitted, so they belong
in the likelihood or in validation, **not** in a prior that the same data
then updates.

| quantity | measured | source | use |
| --- | --- | --- | --- |
| e_obs (confirmed-at-death share) | **0.288 – 0.352** | 32 national report-days, four exclusion rules | pins γq/τ = 0.41 – 0.54 |
| ρ (registry → report) | **≈ 1** | positives = new cases, 44/53 | fix, do not estimate |
| δ (care exit rate) | **0.141 /day (7.1 d mean stay)** | 727 itemised exits over 17 d against a mean confirmed census of 303 | prior centre |
| f_cfr (facility) | **0.524**, or 0.470 counting absconders as non-death exits | 339 deaths, 308 recoveries, 75 absconded | prior centre |
| absconder share of exits | **0.103** | same ledger | supports an explicit non-recovery exit |
| never-retained-in-care | **~0.20** of new confirmations | compartment balance, 16 Jul – 2 Aug | bounds p_h below 1 |
| bed occupancy | **0.84–0.89** | 15 reports printing patients/beds | the census may be censored, not proportional |

## Literature anchors (verified against the primary sources)

Only these were verified before web access was blocked mid-session; the rest
of the review is outstanding (see Next).

**BDBV is not EBOV, and the commonly-quoted BDBV CFR is a denominator
artefact.** MacNeil et al., *Emerging Infectious Diseases* 16(12), 2010,
"Proportion of Deaths and Clinical Features in Bundibugyo Ebola Virus
Infection, Uganda": the 2007–08 Uganda outbreak gives **17/43 = 40 %** among
cases confirmed from *acute-phase* specimens. The widely-cited ~25 % uses a
56-case denominator that includes 13 convalescent-serology-only cases, which
the authors themselves flag as *"by definition surviving case-patients …
a biased sample"*. For a model of confirmed cases the 40 % figure is the
right one.

**The only other BDBV outbreak, and it was in DRC.** Kratz et al., *PLOS
ONE*, 2015, "Ebola Virus Disease Outbreak in Isiro, Democratic Republic of
the Congo, 2012": overall **53.8 % (34/62)**; **treatment-centre CFR 50.0 %
(9/18)**; community confirmed 22.2 % (2/9); community *probable* 93.8 %
(17/18) — the last is circular, since a probable case is *defined* in this
series as a death without a swab. Incubation mean 11.3 d (n = 3 only).
Disease duration: survivors median **18 d** (8–26), deceased median **15 d**
(4–28).

This verifies the "Kratz ≈ 0.50" anchor as a **facility** CFR, and it sits
almost exactly on our own ledger's 0.524. Two independent lineages agreeing
at ~0.50 is a strong argument that the fit's **f_cfr = 0.310 is too low**,
not that the data are wrong.

**The dwell in I is not exponential, and this is the factor-3–4 lever.** WHO
Ebola Response Team, *NEJM* 371:1481, 2014, "Ebola Virus Disease in West
Africa — The First 9 Months": incubation mean 11.4 d (gamma-fitted); serial
interval **15.3 ± 9.3 d, gamma with CV 0.66**; onset→hospitalisation 5.0 ±
4.7 d; admission→death 4.2 ± 6.4 d. A CV of 0.66 implies a gamma **shape
≈ 2.3** — decisively not exponential (which would be CV = 1). Kratz's
15–18 d median durations with 4–28 d ranges point the same way.

## Recommended priors

| parameter | recommendation | basis |
| --- | --- | --- |
| **ρ** (registry→report) | **fix at 1**, or Beta(60, 2) | measured: positives = published, 44/53 |
| **ρ_lab** (true ascertainment) | keep as the single free ascertainment parameter; weakly informative | nothing in the national data measures absolute size; do not let two parameters carry it |
| **q_comm** | Beta with mean **0.45**, sd ≈ 0.12 (≈ Beta(7.3, 8.9)) | q = (unisolated fatality) × (swab ascertainment); BDBV untreated fatality plausibly 0.5–0.7 against Isiro's 53.8 % overall, times swab coverage < 1 |
| **f_cfr** (facility) | Normal/Beta centred **0.50**, sd ≈ 0.06 | Kratz ETC 9/18 = 0.500 and our ledger 0.524, two independent lineages |
| **δ** (care exit rate) | Gamma centred **0.14 /day** (7.1 d), sd ≈ 0.03 | our exit ledger; consistent with WHO admission→death 4.2 d plus longer recoveries |
| **p_h** (share reaching care) | Beta centred **0.80**, sd ≈ 0.07 | the ~20 % never-retained balance |
| **dwell shape in I** | **Erlang shape 2–3**, not exponential | serial-interval gamma CV 0.66 ⟹ shape ≈ 2.3 |
| **I₀** | tighten hard | posterior tail to 3,000 is prior-driven, not data-driven |

## The reparameterisation that actually fixes the mixing

Priors will narrow the ridge; they will not remove it. Three structural
changes would:

1. **Fix ρ = 1** and let ρ_lab alone carry ascertainment. Removes the exact
   collinearity — one dimension deleted, not merely penalised.
2. **Sample (e_obs, q) instead of (γ, q).** Give e_obs a tight prior on the
   measured 0.29–0.35 — or better, fit it as an observation with a binomial
   likelihood on the 800/2548 counts, which propagates its uncertainty
   honestly instead of asserting a point. Then γ and τ follow from e_obs, q
   and the growth rate, and the sampler explores one interpretable direction
   instead of traversing a hyperbola. This is the change most likely to fix
   the mixing.
3. **Decompose q explicitly** as `q = fatality_unisolated × swab_ascertainment`
   and put priors on the two factors. It makes the infeasibility visible
   during sampling rather than after: at q = 0.81 the decomposition already
   requires swab ascertainment > 1.

## Next

Web access was blocked mid-session by a permission classifier — first for
delegated agents, then for this session — so the literature review is
partial. Outstanding, in priority order:

1. Whether **any** study reports a *fitted* onset-to-death distribution with
   its shape parameter for an ebolavirus (yes/no before it is a number).
2. The ascertainment fraction: capture-recapture, serosurvey, or
   burial-registry estimates of under-reporting from West Africa 2013–16 and
   North Kivu 2018–20; the WHO Ebola Response Team's own under-reporting
   correction factor and how it was derived.
3. Verify or refute the **Roddy ≈ 0.42** and **Funk & Abbott ≈ 0.59
   [0.46, 0.72]** facility-CFR anchors. Kratz ≈ 0.50 is now verified.
4. Post-mortem swab coverage and safe-burial refusal rates — the second
   factor in q, and currently unmeasured on either side.

Re-run in the default permission mode or a fresh session.
