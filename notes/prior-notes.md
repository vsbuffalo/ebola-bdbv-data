# Priors for the national fit

Date: 2026-08-22
Project: ebola-bdbv-data
Tags: priors, identifiability, ascertainment, reporting, literature

Working notes on what the situation reports and the published literature say
about the parameters that are failing to identify in the national fit. The
first section is the strongest result and the one with the least borrowed
evidence: **ρ, the probability that a laboratory-confirmed case reaches the
published bulletin, deserves a strongly informative prior concentrated near
1**, and the situation reports say so in their own arithmetic.

---

## 1. ρ should be a strongly informative prior near 1

### What ρ is, and why it is currently doing damage

The model carries ρ = P(a laboratory-confirmed case reaches the published
report). It is estimated freely, and the fits put it at 0.47 in one arm and
0.76–0.85 in another. The pair plots show why that range is not a posterior in
any useful sense: ρ and ρ_lab are **exactly collinear**, and the log-posterior
rises monotonically towards the edge of ρ's prior. Two parameters are
competing to carry one quantity, and neither is pinned. Because ρ multiplies
straight into inferred outbreak size, that unidentified direction propagates
into every quantity anyone would actually want from the fit.

The usual move is to tighten the prior and hope. The better move here is to
notice that **ρ is not a latent quantity in these reports — it is
observable**, and the source publishes the accounting that fixes it.

### The evidence: the reports close the laboratory's books in public

The bulletins do not merely state a day's new confirmed cases. On the days
when the laboratory section is written out in full, they decompose the day's
**laboratory positives** into the categories that consume them, and print the
sum. The construction recurs verbatim — *"portant à N le nombre de résultats
positifs du jour"*, "bringing the day's positive results to N".

The identity is

    laboratory positives (day) = new confirmed cases + re-swab positives

where a *reprélèvement* is a repeat specimen from a patient **already
confirmed**, taken to document clearance before discharge. It tests positive
again and is counted as a positive result, but it is not a new case. This is
the entire reason a naive positives-versus-cases comparison shows a gap.

Every province-day on which the report prints all three numbers, the identity
closes **exactly**:

| sitrep | date | province | new confirmed | + re-swabs | = positives | closes |
|---|---|---|---|---|---|---|
| 078 | 31 Jul | Ituri | 53 | 11 | 64 | ✓ |
| 079 | 1 Aug | Ituri | 49 | 18 | 67 | ✓ |
| 080 | 2 Aug | Ituri | 39 | 14 | 53 | ✓ |
| 081 | 3 Aug | Ituri | 58 | 6 | 64 | ✓ |
| 082 | 4 Aug | Ituri | 85 | 6 | 91 | ✓ |
| 088 | 10 Aug | Ituri | 53 | 10 | 63 | ✓ |
| 089 | 11 Aug | Ituri | 98 | 21 | 119 | ✓ |

Seven closures, no failures. In the source's own words (sitrep 089): *"L'Ituri
a enregistré 119 résultats positifs, dont 98 nouveaux cas (59 vivants et 39
décès) et 21 reprélèvements"*.

**The corroboration that matters most is that the residual is not a residual.**
Comparing our extracted laboratory positives against our extracted new-case
counts leaves a discrepancy on nine of 62 province-days. Where the report also
prints a re-swab count, **the discrepancy equals that count exactly**:

| date | province | positives | new cases | gap | printed re-swabs |
|---|---|---|---|---|---|
| 1 Aug | Ituri | 67 | 49 | **18** | **18** |
| 3 Aug | Ituri | 64 | 58 | **6** | **6** |
| 4 Aug | Ituri | 91 | 85 | **6** | **6** |

On 2 August the same holds (53 − 39 = 14, printed 14) once the case count is
taken from the cumulative movement rather than that report's printed new-case
column, which is independently unreliable — sitrep 080's printed column
disagrees with its own cumulative totals on every province at once.

The gap between positives and cases is not leakage between the laboratory and
the bulletin. It is a named, counted, published category.

**And where the accounting does slip, it slips the wrong way for
under-reporting.** On 31 July the published new-case count for Ituri is 64,
which is the day's *positives* — the 53 new cases plus the 11 re-swabs —
rather than 53. That is the bulletin over-counting new cases by including
repeat specimens, not discarding confirmations. Across all 62 province-days,
positives exceed or equal new cases on 59. The three exceptions are a single
case in Haut-Uélé on 25 July and the two 2 August rows, both artefacts of that
report's printed column. Nowhere in this record does the published series fall
short of the laboratory's output in a way that under-reporting would produce.

Sitreps 088 and 089 go one step further and close a **second** identity
inside the first:

    new confirmed cases = confirmed alive + confirmed at death

    088:  32 + 21 =  53   ✓
    089:  59 + 39 =  98   ✓

So the day's laboratory output is partitioned, without remainder, into
categories the report names and counts. There is no bucket labelled "confirmed
but not yet published", and no arithmetic room for one.

### Why this justifies a strongly informative prior rather than a fixed value

Three separate arguments point the same way, and they fail differently, which
is what makes their agreement worth something:

1. **The accounting closes.** Positives are exhausted by new cases plus
   re-swaps, seven times out of seven.
2. **The direction of the residual is wrong for under-reporting.** Where
   positives and new cases differ, positives are *higher* on 59 of 62
   province-days. Under-reporting between laboratory and bulletin would push
   the other way. A ρ of 0.47 would require the bulletin to be discarding
   more than half the laboratory's confirmations while simultaneously
   publishing a total that *exceeds* its own new-case count.
3. **The publication step is not a reconciliation step.** The laboratory
   figures and the case figures appear in the same document, on the same day,
   from the same institution. There is no interval in which a confirmed case
   could be lost, because there is no hand-off.

What keeps this a *prior* rather than a hard constraint is that these are
national and Ituri-weighted observations of a process that could differ in a
province with weaker laboratory-to-coordination links, and the identity is
verified on the days the reports chose to write out in full, which is a
selected subset. Those are reasons for a little mass below 1, not for a flat
prior over [0, 1].

**Recommendation.** Either fix ρ = 1, or use **Beta(60, 2)** — mean 0.968,
with about 95 % of its mass above 0.90 and effectively none below 0.8. Fixing
it outright is defensible and has the advantage of deleting the ρ_lab–ρ
collinearity rather than merely penalising it.

**Whatever ascertainment is missing is missing before the laboratory.** A
person who never had a specimen taken never enters this accounting at all.
That loss is real and probably large, but it belongs to ρ_lab, and letting ρ
absorb any of it double-counts one quantity across two parameters — which is
precisely the collinearity in the pair plot.

---

## 2. Priors from the literature

Web access was blocked earlier in this project and has since recovered; the
following are verified against primary sources, with the two that could not be
verified named as such at the end.

### 2.1 ρ_lab — ascertainment before the laboratory

This is the genuinely unidentified parameter, and no national aggregate
measures it. The relevant external evidence:

**Capture–recapture, Montserrado County, Liberia, 1 June – 14 August 2014.**
Gignoux E, Idowu R, Bawo L, Hurum L, Sprecher A, Bastard M, Porten K,
*Emerging Infectious Diseases* 21(12):2265–2267, 2015.
Two independently maintained databases — the Ministry of Health case
investigation database (227 cases) and the ELWA Ebola treatment unit admission
database (99 cases), overlapping in 25 — give an estimated **876 cases (95 %
CI 608–1,143)**. Reported cases were therefore about **26 %** of the estimated
total: *"the number of cases in Montserrado County was at least 3-fold higher
than that reported"*.

**Contact-tracing completeness, Beni Health Zone, DRC, 31 July 2018 – 26 April
2020.** *Emerging Infectious Diseases* 27(12), 2021, over 923 confirmed and
probable cases. Contact tracing found ~99 % of case-patients who had *any*
listed contacts, but only **~48 % (95 % CI 43–55 %)** of case-patients who had
*infected* contacts — 24 % in the first wave, 48 % in the second. Roughly half
of onward transmission was not linked.

These bound the problem rather than solve it: Montserrado 2014 was an extreme
urban setting with overwhelmed capacity, and the DRC figure measures contact
tracing rather than case ascertainment. Taken together they say the plausible
range for ρ_lab is **wide and centred well below 1** — something like 0.3–0.8
— and that a fit implying 3 % of infections go unascertained is not in
contact with any of this evidence.

**Recommendation.** Keep ρ_lab as the single free ascertainment parameter with
a weakly informative prior, and state plainly in the write-up that absolute
outbreak size is prior-driven. Do not let ρ share this load.

### 2.2 f_cfr — fatality among those who reach care

Three independent estimates, two from the only previous Bundibugyo outbreaks
and one from our own data:

| source | setting | estimate |
|---|---|---|
| Roddy et al., *PLOS ONE* 2012 | Bundibugyo, Uganda 2007–08, hospitalised lab-confirmed | **11/26 = 0.42** |
| Kratz et al., *PLOS ONE* 10(6):e0129333, 2015 | Isiro, DRC 2012, treatment centre | **9/18 = 0.50** |
| our care ledger (`make care-ledger`) | DRC 2026, 664 exits from care | **≤ 0.456** |

They bracket **0.42–0.50** and our own figure sits in the middle. This
verifies the "Roddy 0.42" anchor exactly — *"Eleven of the 26 patients died
(CFR = 42%)"*.

**Recommendation: Beta centred 0.46, sd ≈ 0.05.** The fitted 0.310 is well
below all three.

### 2.3 Unisolated fatality — the first factor in q_comm

`q_comm` = (fatality of unisolated infection) × (probability the death is found
and swabbed), so a prior on q needs a prior on BDBV lethality without care.

**Bundibugyo is the least lethal of the human-pathogenic ebolaviruses.** Van
Kerkhove et al., *Scientific Data* 2, 2015, compiling parameters across
outbreaks, gives CFR by species: **Zaire 0.69–0.88, Sudan 0.53–0.69,
Bundibugyo 0.34–0.42**.

**And the commonly quoted BDBV figure is a denominator artefact.** MacNeil et
al., *EID* 16(12), 2010, report **17/43 = 40 %** among cases confirmed from
*acute-phase* specimens. The widely cited ~25 % uses a 56-case denominator
including 13 convalescent-serology-only cases — which are, by construction,
survivors. The 40 % figure is the right one for a model of confirmed cases.

Untreated fatality should exceed treated fatality, so a plausible range for
unisolated BDBV fatality is **0.5–0.7**. Multiplied by swab ascertainment
below 1, this gives **q ≈ 0.45**, and it makes the fitted 0.81–0.915
infeasible: at q = 0.915 the decomposition requires swab ascertainment above
1 even at 0.9 unisolated fatality.

**Recommendation: Beta with mean 0.45, sd ≈ 0.12** — better still, decompose
q explicitly and put priors on the two factors, so infeasibility shows up
during sampling rather than after.

### 2.4 The dwell in I is not exponential

This is the modelling side's stated factor-3-to-4 lever, and the literature is
clear on the direction even where it does not hand over a fitted shape.

**WHO Ebola Response Team, *NEJM* 371:1481, 2014**: incubation mean 11.4 d;
serial interval **15.3 ± 9.3 d, gamma with CV 0.66**; onset→hospitalisation
5.0 ± 4.7 d; admission→death 4.2 ± 6.4 d. A CV of 0.66 implies gamma **shape
≈ 2.3**; an exponential would give CV = 1.

**Van Kerkhove et al. 2015, BDBV-specific**: incubation mean 6.3 d (5.2–7.3),
median 7 (2–20); onset→hospitalisation median **3.5 d (0–8)**; onset→death
median **9–10 d**; onset→recovery median **10 d (2–26)**.

**Kratz et al. 2015, Isiro** (18 treatment-centre patients, 34 in the
community): duration from onset to outcome, survivors median **18 d** (8–26),
deceased median **15 d** (4–28).

**Roddy et al. 2012**: onset to admission mean **3.5 d (0–8)**; onset to
outcome approximately 9–10 d.

Two things follow. First, competing *exponential* hazards are wrong in a known
direction, and **Erlang shape 2–3** on the infectious compartment is
defensible where exponential is not. Second, BDBV reaches care faster than
EBOV did in West Africa (3.5 d against 5.0 d), which matters for τ.

A systematic review reports pooled onset-to-death **9.3 d (8.5–10.1)** and
onset-to-recovery **13.0 d (10.4–15.7)** — deaths resolve sooner than
recoveries, so a single dwell for both outcomes is a simplification worth
naming.

### 2.5 δ — the care exit rate

Two independent routes agree. Our care ledger (`make care-ledger`) gives a
mean stay of **8.9 d** from 664 exits against a mean confirmed census of
296.8; the modelling repository's confirmed-only census fit gives **8.8 d**.
One is a stock-and-flow division involving no fitting, the other is a
posterior; they agree to 0.1 d.

**Recommendation: Gamma centred 0.115/day (8.7 d), sd ≈ 0.02.** The model's
current 7.7 d is the number that should move.

Note our figure is a **lower bound on δ** because absconders leave care
without recovering or dying and were not in the ledger — though see §3, since
the source turns out to count them.

---

## 3. What the source prints that we do not yet extract

Found while checking a claim in this note, and it changes several of the
above. **54 to 59 of the 87 reports carry a daily per-province care-flow
table** that our pipeline does not read: patients in isolation split into
confirmed and suspect, total 24-hour exits, transfers to hospital, occupancy
rate, and — significantly — ***Sorties — évadés***, absconders, counted.

Two consequences for these priors. First, δ and f_cfr can become point
estimates rather than bounds, since `Total sorties (24 h)` measures exits
directly instead of by differencing stocks. Second, **Nord-Kivu runs at
120–160 % of isolation-bed capacity throughout**, with the source saying so in
prose (*"La saturation persiste au Nord-Kivu (120,6 %), déficit critique de
lits d'isolement"*, sitrep 060). The isolation census there is supply-censored,
not proportional to the confirmed compartment.

That last point may also explain the province heterogeneity in γq/τ — 0.51–0.60
in Nord-Kivu, 0.30–0.38 in Ituri, 0.21–0.31 in Haut-Uélé — which orders the
same way as bed pressure. If it holds, τ is not a national constant but a
function of an observed covariate. Three provinces is three points and this is
untested, but it is testable.

---

## 4. Summary table

| parameter | prior | basis | strength |
|---|---|---|---|
| **ρ** | fix 1, or Beta(60, 2) | the reports' own accounting identity, §1 | **strongly informative** |
| **ρ_lab** | weakly informative, centred ~0.5 | Montserrado 26 %, Beni ~48 % | weak — outbreak size is prior-driven |
| **q_comm** | Beta(mean 0.45, sd 0.12) | BDBV lethality 0.34–0.42 species-level, × swab ascertainment | moderate |
| **f_cfr** | Beta(mean 0.46, sd 0.05) | Roddy 0.42, Kratz 0.50, our ledger 0.456 | **strong — three lineages** |
| **δ** | Gamma(mean 0.115/day) | our ledger 8.9 d, census fit 8.8 d | **strong — two routes** |
| **p_h** | Beta(mean 0.80, sd 0.07) | ~20 % never-retained, compartment balance | moderate |
| **dwell in I** | Erlang shape 2–3 | serial-interval CV 0.66 ⟹ shape ≈ 2.3 | moderate |
| **γq/τ** | 0.41–0.54, or fit as binomial | our escape fraction, `make escape-fraction` | **measured** |

## 5. Not verified

Stated so that nobody, including me, later mistakes these for checked facts:

- **Funk & Abbott ≈ 0.59 [0.46, 0.72]** — searched and not found. No paper by
  those authors with that estimate surfaced. It may refer to a different
  quantity or be misattributed; do not cite it from these notes.
- **Any *fitted* onset-to-death distribution with a published shape parameter
  for an ebolavirus.** Medians, means and ranges are widely reported; a fitted
  gamma or Weibull with its shape for onset-to-outcome specifically was not
  located. The Erlang 2–3 recommendation rests on the serial interval's CV,
  which is an inference about the dwell, not a direct measurement of it.
- **Post-mortem swab coverage and safe-burial refusal rates** — the second
  factor in q_comm, unmeasured on both sides. The burial pillar's prose
  carries alert, swab and refusal counts against an all-cause denominator;
  extracting it is queued.

## Sources

- [MacNeil et al., *EID* 16(12), 2010 — BDBV proportion of deaths](https://wwwnc.cdc.gov/eid/article/16/12/10-0627_article)
- [Roddy et al., *PLOS ONE* 2012 — BDBV clinical management, Uganda 2007–08](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0052986)
- [Kratz et al., *PLOS ONE* 10(6):e0129333, 2015 — BDBV outbreak, Isiro, DRC 2012](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0129333)
- [WHO Ebola Response Team, *NEJM* 371:1481, 2014](https://www.nejm.org/doi/full/10.1056/NEJMoa1411100)
- [Van Kerkhove et al., *Scientific Data* 2, 2015 — parameter review](https://pmc.ncbi.nlm.nih.gov/articles/PMC4443880/)
- [Capture–recapture underreporting, Montserrado County, Liberia, *EID* 2015](https://pmc.ncbi.nlm.nih.gov/articles/PMC4672419/)
- [Contact-tracing completeness, Beni, DRC, *EID* 27(12), 2021](https://wwwnc.cdc.gov/eid/article/27/12/20-4958_article)
