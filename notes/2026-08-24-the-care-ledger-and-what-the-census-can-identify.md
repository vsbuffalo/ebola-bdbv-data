# The care ledger the reports print in prose, and what the isolation census can and cannot identify

Date: 2026-08-24 Project: ebola-bdbv-data Tags: identifiability, tau, gamma,
census, extraction, care

## Context / question

The model cannot identify **τ** — the rate at which an infectious person is
confirmed and isolated — separately from **γ**, the rate at which infectiousness
ends without confirmation ever happening. τ appears only inside the routing
share `p_tau = τ/ν`, whose prior is `beta(2, 2)`, and inside the community-death
split, which identifies the ratio `χ = γq/τ` rather than either term. Nothing in
the fitted streams observes the transition itself.

The isolation census is the observation that could. Every stream we fit is a
**flow**; the census reads a **state**, and the state is what the flow
accumulates into. That is the degeneracy-breaking property, and the project's
own modelling note had already reached it.

## What the physics says, and why it is not enough

Under the A-compartment structure proposed upstream, confirmation *splits*
rather than being thinned:

```
confirm_retained : I --> C @ tau * p_retain * I
confirm_escapes  : I --> A @ tau * (1 - p_retain) * I
```

with A = confirmed but not in care, still transmitting.

Then the two observations are **complementary halves of one transition**:

| observation                   | constrains               |
| ----------------------------- | ------------------------ |
| isolation census (state of C) | `τ · p_retain · I`       |
| absconder flow (into A)       | `τ · (1 − p_retain) · I` |

Their **sum is τ·I**; their **ratio is `p_retain/(1 − p_retain)`**. So together
they identify τ *and* `p_retain`, and **neither alone identifies either**. With
ν anchored on the NEJM onset-to-sample delay, γ = ν − τ then follows.

This is exactly why binding the census to the *current* model fails, and it has
been measured: divergences 4.9% → 62.3%, chains refused 1/8 → 4/8, and 55.7%
even with `p_in_care` freed under `beta(8, 2)`. A model that routes every
confirmation into C is asserting `p_retain = 1`. The census contradicts that, so
the constraint is unsatisfiable and the sampler reports it. **The divergences
are the model failing, not the stream misbehaving.**

The scale of the contradiction, from our own build:

|                                                                                    | value     |
| ---------------------------------------------------------------------------------- | --------- |
| active confirmed on the books, 18 Aug (`cum_cases − cum_deaths − cumul_recovered`) | **1,617** |
| active confirmed on the books, 2 Aug                                               | 1,368     |
| confirmed actually in a bed, 2 Aug (last day the tile printed)                     | **335**   |

About a thousand people are confirmed and then absent from every ledger: not
dead, not recovered, not in a ward. `f_cfr` enters the split only as
`f_cfr · δ · C`, so an over-large C deflates `f_cfr` by exactly the same factor
— which is the standing tension in one line.

## The finding: the ledger is printed, and nobody had read it

The only isolation census we publish comes from a front-page dashboard tile, and
**the source stopped printing it after sitrep 080 (2 August)**.
`patients_isolated_confirmed` has 49 observations and dies there.

The same quantities appear in **prose**, per province, through sitrep 100 (22
August):

> *"En Ituri, 94 nouvelles admissions ont été enregistrées pour 87 sorties, dont
> 14 guéris et aucun évadé. Ainsi, 528 patients sont hospitalisés pour 965 lits,
> soit un taux d'occupation de …"*

> *"l'occupation atteint 438 patients pour 973 lits (45 %), soit 179 confirmés
> sur 496 lits (36,1 %) et 259 suspects sur 477 lits (54,3 %)"*

**Nobody had extracted it.** The sibling INRB repository's
`insp_sitrep__hospitalised`, `__in_bed_previous_day`, `__new_hosp_admissions`
and `__hosp_escaped` all stop at **2026-05-30** — the date the tabular format
they were reading changed. They never followed the data into prose. That is
roughly eighty-five reports of care-ledger data unread by anyone.

`scripts/extract_care_prose.py` now reads it into
`data/build/series/care_prose.csv`. Coverage, province-days:

| field                |    all | after 2 Aug |
| -------------------- | -----: | ----------: |
| census (total)       |    113 |          57 |
| **census confirmed** | **80** |      **31** |
| beds                 |     83 |          53 |
| admissions           |     77 |          51 |
| exits                |     59 |          28 |
| exits recovered      |     76 |          41 |
| **exits absconded**  | **24** |       **5** |
| contacts followed    |     49 |          49 |

## The census is validated, which was the open question

Sitreps 052–080 close the care section with a **national summary sentence** that
overlaps the tile on 40 days:

> *"Au total, 766 patients étaient en isolement, dont 278 cas confirmés et 488
> cas suspects … pour 893 admissions et 127 sorties (21 guéris, 24 décès, 78
> non-cas et 4 évadés)"*

- **confirmed census: agrees with the tile on all 24 days the tile prints one**
- total census: agrees on 25 of 27

Both exceptions are **the source contradicting itself, and the check says which
half is wrong**: on 2026-07-07 the sentence states 694 while its own split is
232 + 518 = 750, and the tile says 750. The stated total is the bad half; the
split is right.

Two further self-checks come free, and the tile never permitted either. The
printed occupancy percentage checks patients-over-beds: **76 of 80 pass**, and
all four failures are the source (sitrep 097 reprints 096's Haut-Uélé sentence
verbatim while changing the rate 40,8 % → 44,6 %). And because the prose gives
**flows beside the state**, `census(t) − census(t−1)` can be checked against
`admissions − exits` — a stock-flow closure a tile alone can never support.

## The exits gate, which this extraction was built to settle

Where do the deaths of confirmed-but-absconded people get recorded? They
**cannot** be in `deaths_community`: on all five province-days where the source
prints both, that column equals the newly-confirmed-at-death count **exactly**
(21/21, 39/39, 9/9, 5/5, 31/31 — excess 0 every time). The identity closes with
no remainder.

Comparing prose CTE deaths against the table's `deaths_treatment_centre` over 34
province-days: median excess **+2**, max +12, 19 positive, 14 exact, 1 negative.
The residual is **suspected-case deaths in the centre** — which a confirmed-only
split column structurally cannot hold. So exits decompose as expected, and
absconder deaths are not among them either; absconders are their own category
and the decomposition closes where all four components print.

**A naming trap, found in the same pass.** On sitrep 094 the prose reports a
confirmed Tshopo patient admitted to the CTE HC Kisangani who *died there*, and
the table books it `deaths_community = 1`, `deaths_treatment_centre = 0`. So
`deaths_community` means **"confirmed at or around death"**, not "died in the
community" — the column name misleads about location. The conclusion above
survives on firmer ground: an absconder is *already confirmed*, so is never a
new confirmation, and cannot enter that column wherever they die. One case;
worth a targeted look before it is leaned on.

## What is still blocked

**`p_retain` is the binding constraint, and the absconder count is thin** — 24
province-days, only 5 after 2 August, and 15 of the 24 national rather than
provincial. Since census and absconders are complementary halves, a
well-measured census with a poorly-measured absconder flow still leaves τ and
`p_retain` entangled.

The route is identified: **TABLEAU 6** (sitreps 059–080, and the equivalent in
018–058) prints this ledger per province including `Sorties — évadés`, and would
roughly triple absconder coverage. That needs a **table reader**, not prose
patterns.

One thing deliberately unread, and documented in the module docstring: the care
pillar's `Défis` subsection names absconders per centre and would double-count
against the bullet's own figure where both appear — sitrep 099 prints 14 in both
places.

## Next

1. **Read TABLEAU 6.** It is the gate on `p_retain`, and therefore on τ and γ.
2. **Then** build the A-compartment arm. Not before — `p_retain` would be
   inferred from a degeneracy rather than measured.
3. Settle the `deaths_community` semantics with a targeted read of the reports
   where a confirmed in-care death appears, since it determines where A's
   mortality is scored.
4. Decide separately whether the care ledger becomes a published stream. It is
   an extraction into `series/` today; promoting it is a contract change.

Related: [[2026-08-22-rho-reporting-and-priors]],
[[2026-08-22-too-many-people-in-care]],
[[2026-08-24-who-wer-and-genomic-priors]].
