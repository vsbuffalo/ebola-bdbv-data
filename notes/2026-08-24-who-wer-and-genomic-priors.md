# WHO Weekly Epidemiological Record No. 33 and the genomic dating posts

Date: 2026-08-24
Project: ebola-bdbv-data
Tags: priors, literature, genomics, tmrca, validation

## Context / question

Hunting for external evidence that can inform priors or model structure. Four
documents acquired, all now in `pdfs/`:

| file | what it is |
|---|---|
| `pdfs/who_iris_18c72e11.pdf` | WHO *Weekly Epidemiological Record* No. 33, 21 Aug 2026, 5 pp. Carries a feature article comparing all three documented BDBV outbreaks. |
| `pdfs/roddy_2012_bundibugyo_uganda_plosone_e52986.pdf` | Roddy et al. 2012, PLOS ONE 7(12):e52986. Bundibugyo, Uganda 2007–08. 12 pp. |
| `pdfs/kratz_2015_isiro_drc_plosone_e0129333.pdf` | Kratz et al. 2015, PLOS ONE 10(6):e0129333. Isiro, DRC 2012. 18 pp. |
| `pdfs/virological/{1032,1042,1045}_*.txt` | Three virological.org posts on this outbreak's genomics, 18 May / 4 Jun / 9 Jul 2026. |

The genomic posts were not previously known to this project and are the most
consequential of the four.

## The genomic dating, and what it does and does not say

Two independent analyses of outbreak sequences.

**Post 1045** — INRB Kinshasa and partners, 9 July 2026, the one WHO cites.
139 BDBV genomes, sampling to 23 June.

- Evolutionary rate ≈ 1.1 × 10⁻³ substitutions/site/year.
- **tMRCA mean 15 March 2026, 95% HPD 9 February – 12 April 2026.**
  Root-to-tip regression independently puts it at 7 March, reported without
  intervals and described by the authors as a data-exploration tool only.
- **Doubling time 11.7 days, 95% HPD 6.8 – 17.5 days**, assuming fixed
  exponential growth between tMRCA and the last sample.
- The Skygrid reconstruction shows approximately exponential growth with *some
  evidence of slowing in early June*, which the authors flag as uncertain
  because the intervals widen where sampling thins.

**Post 1042** — Cuomo-Dannenburg and Ghafari, 4 June 2026. Only 10 sequences,
as of 28 May, and explicitly informal.

- Median posterior tMRCA ranges from late January to late March 2026 across
  six substitution-rate assumptions; **all place the median no later than
  23 March 2026**.
- **R₀ mean estimates 1.31 – 1.55**, from a **generation time of 9.6 days**
  taken from `{epireview}`'s systematically collected BDBV parameters.
- 23 unique mutations across 10 sequences — already diverse enough that the
  authors conclude the sampled viruses *do not represent the very beginning of
  transmission*.

### tMRCA is not the introduction time

The distinction is load-bearing and easy to lose. For a single introduction,
the most recent common ancestor of the *sampled* cases sits at or **after** the
introduction — every sampled lineage descends from it, but the introduction may
precede it by however long the early chain went unsampled. So

> introduction ≤ tMRCA

and the estimate is an **upper bound on how late the introduction can have
been**, not a point estimate of when it happened. Post 1042 says as much from
the mutation count. Treating 15 March as the seeding date would place the
introduction later than the evidence supports.

Against our `day0` of 2026-05-19: the tMRCA mean sits **65 days** before the
series starts, the HPD upper bound (12 Apr) **37 days** before, the lower bound
(9 Feb) **99 days** before. The model is estimating a seeding time for a
process whose common ancestor predates the first observation by two months.

### The two analyses disagree on growth, and the larger one is faster

Post 1042 reports R₀ 1.31–1.55 from 10 sequences. Post 1045 reports a doubling
time rather than an R₀. Applying 1042's own relation, R₀ = 2^(D·T_g/365) with
D doublings per year and T_g = 9.6 d, to 1045's doubling time gives:

| source | doubling time | growth rate r | implied R₀ |
|---|---|---|---|
| post 1045, mean | 11.7 d | 0.0592 /d | **1.77** |
| post 1045, HPD fast | 6.8 d | 0.1019 /d | 2.66 |
| post 1045, HPD slow | 17.5 d | 0.0396 /d | 1.46 |
| post 1042, direct | — | — | 1.31 – 1.55 |

*(The 1.77 and the bounds are derived here, not stated by either post.)*

So the 139-genome analysis implies a faster epidemic than the 10-genome one,
and 1042's range sits at or below 1045's slow end. Both are **early-phase**
estimates — sampling stops 23 June, our series runs to 22 August — and 1045
already sees possible slowing in early June. Neither should be used as a prior
on transmissibility over the whole period we fit.

**Generation time 9.6 days** is the cleanest single number here for structure:
it is a published BDBV-specific estimate, and it constrains the dwell-time
compartments directly.

## WHO WER No. 33 — the three outbreaks side by side

### Our national series reproduces WHO's figures exactly

WHO states **5021 confirmed cases and 2378 confirmed deaths as of 16 August
2026**. Our sitrep 094, data date 2026-08-16, carries **5021 / 2378**. Exact.

**This is corroboration of our reading, not of the measurement.** WHO cites the
WHO AFRO Weekly External Situation Report 14 and DON615, which draw on the same
DRC surveillance chain that produces the INSP situation reports we extract. Two
routes out of one system agreeing tells us our extraction is faithful; it says
nothing about whether the underlying count is right. WHO says so itself:
reported counts "underestimate the true burden, although the extent of
under-ascertainment remains uncertain."

Also matching: six provinces (Ituri, North Kivu, South Kivu, Haut-Uélé, Tshopo,
Bas-Uélé), and 15 imported cases in Uganda — which is exactly what
`uganda_exports.tsv` carries at 2026-06-21.

Two things WHO reports that we do **not** carry: **five secondary cases in
Uganda** (onward transmission outside DRC, beyond the importations we track)
and **one imported case detected in France**.

One minor unexplained difference: WHO counts **56 health zones** affected as of
16 August; we count **58** canonical zones with at least one confirmed case by
that date (60 by 22 August). Likely a definitional difference in what counts as
affected rather than an extraction fault, but it is unreconciled.

### Case fatality — three different estimands, routinely conflated

| outbreak | denominator | CFR |
|---|---|---|
| Uganda 2007–08 | all putative (93 putative, 56 confirmed, 37 deaths) | 25% |
| Uganda 2007–08 | laboratory-confirmed | ≈ 40% |
| Uganda 2007–08 | hospitalised confirmed (Roddy, 11/26) | 42% |
| Isiro 2012 | all cases (62: 5 suspected, 21 probable, 36 confirmed; 34 deaths) | 54.8% |
| Isiro 2012 | laboratory-confirmed | ≈ 34% |
| Isiro 2012 | reached the ETC (Kratz, 9/18) | 50% |
| DRC 2026 | exits from care (`make care-ledger`) | ≤ 0.456 |

Our `f_cfr` is fatality **among those who reach care**. Only the Roddy 42% and
Kratz 50% rows speak to it; the confirmed-case and crude rows are different
quantities and must not be pooled with them.

**A structural signal worth testing.** At Isiro the confirmed-case CFR was
≈ 34% while the treated (ETC) subset died at 50%. Care associated with *higher*
fatality is the signature of severity selection into care, not of care doing
harm. Any model in which entering care reduces the death hazard is implicitly
assuming that selection away, and our own `f_cfr = 0.4288` inherits the same
ambiguity. This is a testable structure question, not a prior question.

### Structure we do not represent

- **At least 155 health-care workers infected by mid-August 2026** (≈ 3% of
  confirmed cases). Health-care-associated transmission is a distinct route
  with its own contact structure; a single homogeneous transmission term
  absorbs it into the general force of infection.
- **Sex skew at Isiro 2012**: 85% of community cases and 61% of ETC cases were
  female — and note the *differential* between the two, which is a statement
  about ascertainment as much as exposure. In 2026 WHO reports adults 18–49 as
  the largest share with *broadly similar numbers among men and women*, so the
  2012 skew does not reproduce and should not be carried over.
- **Setting**: the 2026 outbreak began at Mongbwalu, a gold-mining area with
  high worker and trader mobility; Bunia is a commercial and referral hub.
  Roads, rivers and mining routes connect affected communities. Both earlier
  outbreaks stayed geographically localized (>97% of Uganda 2007 cases in four
  of ten subcounties; Isiro plus a secondary focus at Viadana 75 km away).
  Mobility is the stated reason this one is not simply a larger version.

### Recognition delay, for context

- Uganda 2007: ≈ 119 days from first alert to confirmation of a then-unknown
  virus.
- Isiro 2012: earliest confirmed case onset 28 June, alert 2 August (≥ 35 days
  unrecognized), confirmation 16 August (14 days).
- DRC 2026: alert 5 May, confirmation 10 days later. Initial GeneXpert for
  *Zaire ebolavirus* was negative; pan-*Orthoebolavirus* testing and sequencing
  at INRB were needed.

## Next

- **Fetch and read the 2012 Isiro line list.** `external/bdbv-linelist-analysis`
  is still absent — the submodule was never initialised, so nobody here has read
  the line list that our delay and CFR priors ultimately rest on. Re-derive the
  number before anything cites it, and cite it as software with a commit SHA.
  See [[isiro-line-list-provenance]].
- **Decide how the tMRCA enters the model**, if at all. It is an upper bound on
  the introduction date, from a process whose early chain is unsampled by the
  authors' own argument. A prior that treats it as a point estimate will place
  seeding too late.
- **Do not adopt the genomic R₀ as a whole-period prior.** Both estimates stop
  at 23 June and 1045 already sees slowing.
- Chase the references WHO cites that we do not hold: Wamala et al., *EID*
  2010;16(7):1087–1092; MacNeil et al., *EID* 2010;16(12):1969–1972; Hulseberg
  et al., *Cell Rep Med* 2021;2:100351; WHO DON615 (14 Aug 2026); WHO AFRO
  Weekly External Situation Report 14.
- Reconcile the 56-vs-58 health-zone count, or record it as definitional.
