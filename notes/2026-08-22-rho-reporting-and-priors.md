# What ρ actually measures, and why the laboratory stream is not a second look at it

Date: 2026-08-22 Project: ebola-bdbv-data Tags: priors, identifiability,
ascertainment, reporting, laboratory, literature

## Context / question

The national fits mix badly. The pair plots show ρ and ρ_lab perfectly
collinear, a log-posterior climbing monotonically towards ρ's upper prior edge,
and a hyperbolic ridge in (γ, q). The question put to me was whether the
situation reports support an informative prior on ρ near 1.

They do. But the more useful answer is that **this is not mainly a prior
problem.** One of the two reporting parameters is measuring an artefact of how
we built a stream, and the column needed to remove it is already published.

---

## 1. The vocabulary, in plain English

Three terms are load-bearing and two of them are French. Defining them properly
is most of the argument.

**Situation report (SitRep).** The daily bulletin published by INSP, the DRC
national public health institute. One PDF per day, numbered sequentially. It
contains tables of cases and deaths by health zone, plus prose sections written
by each response "pillar" — surveillance, laboratory, burial, and so on.

**Laboratory paragraph.** A prose section inside each SitRep, in which the
laboratory pillar reports the day's testing. A typical sentence (sitrep 089):

> *"L'Ituri a enregistré 119 résultats positifs, dont 98 nouveaux cas (59
> vivants et 39 décès) et 21 reprélèvements"*

which is: "Ituri recorded 119 positive results, of which 98 were new cases (59
alive and 39 deceased) and 21 were **re-swabs**."

**Reprélèvement — "re-swab", literally "re-sampling".** A repeat specimen taken
from a patient who is **already a confirmed case**. Ebola patients are re-tested
before discharge, because they may not leave a treatment centre until they test
negative. A patient still carrying virus tests **positive again**. That positive
is a real laboratory result and gets counted as one — but it is *not* a new
case. It is the same person, tested a second time.

So a day's laboratory positives contain two different kinds of event:

```
laboratory positives (day) = new confirmed cases + re-swab positives
                             └── new people ──┘   └─ people already counted ─┘
```

This is not my inference. The reports state it and print the sum, using the same
construction each time — *"portant à N le nombre de résultats positifs du
jour"*, "bringing the day's positive results to N".

---

## 2. What ρ means, precisely

The model carries two reporting probabilities against the same latent
confirmation flow:

```
cases_national             ~ neg_binomial(mean = rho     * projected, r = k_cases)
lab_confirmations_national ~ neg_binomial(mean = rho_lab * projected, r = k_lab)
```

- **ρ** — P(a laboratory-confirmed case reaches the published report). It is a
  *step in a pipeline*: the case exists in the laboratory register, and ρ is the
  chance it survives into the bulletin's case count. It is **not** overall
  ascertainment.
- **ρ_lab** — as the model documents it, P(a confirmation appears in the
  laboratory sentence of the situation report). The stated reason for a separate
  parameter is that the case series is a difference of published cumulatives and
  carries reconciliation backlogs, while the laboratory line is counted directly
  on the day.

Note what neither covers: a person who was infected and never had a specimen
taken at all. That loss happens **before** the laboratory and belongs to neither
ρ nor ρ_lab. Conflating it with them is the source of a lot of confusion,
including some of mine earlier in this project.

**The reporting chain, with the loss points named:**

```
infection
    │   ← most of the loss lives here: never sampled.
    │      Belongs to overall ascertainment, NOT to rho.
specimen taken
    │
laboratory result
    │   ← rho lives here: register -> published bulletin
published case count
```

---

## 3. Does the source support ρ ≈ 1? Yes, and it says so in arithmetic

**The accounting closes.** On every province-day where the report prints all
three numbers, new cases plus re-swabs equals positives exactly:

| sitrep | date   | province | new confirmed | + re-swabs | = positives |
| ------ | ------ | -------- | ------------- | ---------- | ----------- |
| 078    | 31 Jul | Ituri    | 53            | 11         | 64          |
| 079    | 1 Aug  | Ituri    | 49            | 18         | 67          |
| 080    | 2 Aug  | Ituri    | 39            | 14         | 53          |
| 081    | 3 Aug  | Ituri    | 58            | 6          | 64          |
| 082    | 4 Aug  | Ituri    | 85            | 6          | 91          |
| 088    | 10 Aug | Ituri    | 53            | 10         | 63          |
| 089    | 11 Aug | Ituri    | 98            | 21         | 119         |

Seven closures, no failures. Sitreps 088 and 089 close a second identity inside
the first — new cases = confirmed alive + confirmed at death, 32+21=53 and
59+39=98. The day's laboratory output is partitioned without remainder into
categories the report names and counts. **There is no bucket labelled "confirmed
but not published", and no arithmetic room for one.**

**Where our extraction shows a gap, the gap is exactly the re-swab count:**

| date  | province | positives | new cases | gap | printed re-swabs |
| ----- | -------- | --------- | --------- | --- | ---------------- |
| 1 Aug | Ituri    | 67        | 49        | 18  | **18**           |
| 3 Aug | Ituri    | 64        | 58        | 6   | **6**            |
| 4 Aug | Ituri    | 91        | 85        | 6   | **6**            |

**Where the accounting slips, it slips the wrong way for under-reporting.** On
31 July the published new-case count for Ituri is 64 — the day's *positives*,
re-swabs included — rather than 53. The bulletin over-counts by including repeat
specimens; it does not discard confirmations. Nowhere in this record does the
published series fall short of the laboratory's output.

A ρ of 0.47 would require the bulletin to be discarding more than half the
laboratory's confirmations while publishing totals that meet or exceed its own
laboratory line. That is not a hypothesis the source leaves open.

---

## 4. The more important finding: ρ_lab is a coverage artefact

Naively, our national laboratory stream carries **fewer** positives than the
case series — 2,951 against 3,820 over 58 span-matched report-days, a ratio of
0.77. Read as a reporting probability that says the laboratory line misses a
quarter of confirmations, which would justify ρ_lab ≈ 0.77.

It is nothing of the kind. **The laboratory paragraph does not always write out
every province.** Our stream publishes exactly the column needed to see this,
`n_provinces`. Splitting the same ratio by it:

| provinces covered | report-days | lab positives | new cases | ratio     |
| ----------------- | ----------- | ------------- | --------- | --------- |
| 1                 | 8           | 164           | 406       | 0.404     |
| 2                 | 37          | 1,939         | 2,564     | 0.756     |
| **3**             | **12**      | **745**       | **747**   | **0.997** |
| **4**             | **1**       | **103**       | **103**   | **1.000** |

**When the laboratory paragraph covers every province, the two series agree to
within 0.3 % — and on the one four-province day, exactly.** The apparent
shortfall is entirely the provinces whose paragraph was not written out that
day. It carries no information about reporting completeness whatsoever.

So ρ_lab ≈ 0.77 is not a measurement of a reporting pipeline. It is the mean
fraction of the country the laboratory paragraph happened to describe, absorbed
into a free parameter because the model was not told about coverage.

**Matching province against province confirms it, and exposes the one real
effect underneath.** With the per-province laboratory streams now published
(§7), comparing each province's laboratory positives against its own new-case
series:

| province  | days | positives / cases | exact |
| --------- | ---- | ----------------- | ----- |
| Ituri     | 49   | 0.832             | 37/49 |
| Nord-Kivu | 41   | 0.970             | 33/41 |
| Haut-Uélé | 2    | 1.000             | 2/2   |

Nord-Kivu and Haut-Uélé are already at 1. Ituri's residual is **not** spread
across days — it is concentrated in backlog releases: 22 July (347 cases against
73 positives), 30 July (188 against 62), 13 July (102 against 42), all carrying
the `consolidating` flag. On those days the case series, built by differencing a
published cumulative, absorbs a catch-up of earlier confirmations that the
laboratory paragraph never claimed to be reporting. This is precisely the effect
the model's own docstring names as its reason for a separate ρ_lab — and it is
real. It is simply not a *reporting probability*: it is a timing and allocation
artefact, and a constant multiplicative factor is the wrong shape for it.

Removing both coverage and backlog:

| province     | days   | positives / cases | exact |
| ------------ | ------ | ----------------- | ----- |
| Ituri        | 32     | 0.972             | 26/32 |
| Nord-Kivu    | 23     | 1.048             | 20/23 |
| **combined** | **55** | **0.979**         |       |

**0.979.** Nothing is left for a reporting probability of 0.77 to explain. And
Nord-Kivu's 1.048 — positives slightly *exceeding* new cases — is the re-swab
effect of §1 showing through, in the direction only re-swabs can produce.

This is why the pair plot shows the pathology it does. Both streams scale the
same latent `projected`, and the overall scale of `projected` is itself free
(set by I₀ and transmission). Only the **ratio** ρ_lab/ρ is pinned by the data;
the individual levels are not. That is the perfectly straight line. And because
ρ_lab is forced to absorb a coverage deficit rather than a real probability, it
drags the latent scale — and therefore inferred outbreak size — with it.

**Answering the question directly: this is not a prior problem. It is data we
already publish and are not using.**

---

## 5. What to change in the model

In descending order of value.

**5.1 Stop treating the laboratory stream as a second national observation.** On
full-coverage days it is not a second look at the confirmation flow — it is the
*same number*. Fitting both with independent reporting probabilities
double-counts one observation and manufactures a collinear direction. Three
options, best first:

- **Fit the laboratory stream at province level**, against the matching province
  case series, so coverage is exact by construction and no coverage parameter is
  needed. `lab_daily_{ituri,nord_kivu,haut_uele}.tsv` are now published for
  exactly this. Excluding backlog days, the two agree at 0.979.
- **Condition on `n_provinces`**: make the mean
  `rho_lab * projected *
  covered_fraction`, with `covered_fraction` a known
  quantity per day rather than something to estimate.
- **Restrict to full-coverage days** (13 of 58). Simplest and immediately
  available, at the cost of most of the data.

**5.2 Fix ρ = 1**, or `beta(alpha = 60, beta = 2)` — mean 0.968, roughly 95 % of
mass above 0.90. Currently `beta(2, 2)`, which is flat-ish over [0, 1] and
contributes nothing. This deletes the collinear direction outright rather than
penalising it.

**5.3 Let ρ_lab go entirely** once 5.1 is applied. If coverage is handled
structurally there is no residual quantity for it to measure, and its [0, 1] box
was in any case unable to represent a series that can exceed the new-case count
through re-swabs.

**5.4 Keep `k_lab` — that comparison is still valid and worth having.** The
model's stated purpose for this stream is to compare `k_lab` against `k_cases`,
testing whether the case series' excess variance is reconciliation artefact
rather than epidemiology. Nothing here undermines that; the two series being
near-identical in the mean on full-coverage days is what makes the dispersion
comparison clean rather than what spoils it.

**5.5 A caution on the case series itself.** On at least one day (31 July) the
published new-case figure includes re-swabs. The case series is therefore not a
pure count of new people on every day, and a small positive bias exists in it.
It is bounded by the re-swab rate, roughly 7–27 % of positives on the days where
both print, and it is a reason to prefer the province-level treatment in 5.1,
where the two can be reconciled directly.

---

## 6. Priors, with what each rests on

Verified against primary sources. Two anchors that could not be verified are
named in §8.

| parameter             | recommendation                       | basis                                                                                                  | strength                                                                                          |
| --------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| **ρ**                 | fix 1, or `beta(60, 2)`              | the reports' accounting identity, §3                                                                   | **strong**                                                                                        |
| **ρ_lab**             | remove; handle coverage structurally | §4                                                                                                     | **it was measuring an artefact**                                                                  |
| **γq/τ**              | 0.41 – 0.54, or fit binomially       | our escape fraction, `make escape-fraction`                                                            | **measured**                                                                                      |
| **f_cfr**             | Beta centred 0.42, sd ≈ 0.10         | Roddy 0.42 (n=26), Kratz 0.50 (n=18), our ledger ≤0.456 (n=664)                                        | **moderate — two outbreaks, one clinical group, n=44 published** — see §6.1, corrected 2026-08-22 |
| **δ**                 | Gamma centred 0.115/day (8.7 d)      | our care ledger 8.9 d, census fit 8.8 d                                                                | **strong — two routes**                                                                           |
| **q_comm**            | Beta mean 0.45, sd ≈ 0.12            | BDBV species CFR 0.34–0.42 × swab ascertainment                                                        | moderate                                                                                          |
| **p_h**               | Beta mean 0.80, sd ≈ 0.07            | ~20 % never-retained, compartment balance                                                              | moderate                                                                                          |
| **dwell in I**        | Erlang shape 2–3                     | serial-interval gamma CV 0.66 ⟹ shape ≈ 2.3                                                            | moderate                                                                                          |
| overall ascertainment | wide, centred well below 1           | Montserrado 26 % (Gignoux) — **Beni is not an ascertainment estimate, see §6.3, corrected 2026-08-22** | weak — one anchor, prior-driven                                                                   |

### 6.1 f_cfr — fatality among those who reach care

| source                                        | setting                                            | estimate         |
| --------------------------------------------- | -------------------------------------------------- | ---------------- |
| Roddy et al., *PLOS ONE* 2012                 | Bundibugyo, Uganda 2007–08, hospitalised confirmed | **11/26 = 0.42** |
| Kratz et al., *PLOS ONE* 10(6):e0129333, 2015 | Isiro, DRC 2012, treatment centre                  | **9/18 = 0.50**  |
| our care ledger (`make care-ledger`)          | DRC 2026, 664 exits from care                      | **≤ 0.456**      |

Roddy states it outright: *"Eleven of the 26 patients died (CFR = 42%)"*, and
the denominator is *"26 of the 30 hospitalised laboratory-confirmed EHF
patients"* — so it is genuinely an in-care fatality. Kratz: *"CFR of ETC cases
(all confirmed) was 50.0%"*, and *"The 18 patients who reached the ETC were all
confirmed cases."* The model's existing `beta(4, 5)` prior (mean 0.44) covers
both, so the fitted 0.310 is driven by structure or data, not by the prior.

**Updated 2026-08-24 — a current-outbreak death proportion now exists. It is not
an f_cfr and must not be used as one; and the historical in-care CFRs may be
biased upward.**

Akilimali et al. report **95 of 505 laboratory-confirmed patients (18.8%) had
died by the data cut-off**, against 65 of 635 test-negatives (10.2%). The
authors state plainly that this **"cannot be interpreted as the case fatality
rate owing to limited data on final outcome and unknown denominators"** —
outcomes are still open at cut-off, so this is a snapshot of a competing-risks
process, not a completed fatality proportion. It is recorded here so that nobody
finds 18.8% independently and reads it as a CFR. It does not enter the f_cfr
prior.

**The more consequential point is what the same paper implies about Kratz and
Roddy.** Hemorrhagic signs appear in only **10.4%** of confirmed patients here,
against "more than half" in an earlier BDBV description (MacNeil 2010). The
authors attribute the gap partly to *"case ascertainment bias in small outbreaks
where patients with more characteristic or severe clinical presentations are
more easily identified."* If that holds, then the 26-patient and 18-patient
in-care cohorts our f_cfr rests on were selected toward severe presentation —
and **42% and 50% are biased upward as estimates of in-care fatality in a large,
better-ascertained outbreak.** The `beta(4, 5)` prior (mean 0.44) is centred on
exactly those two numbers. This is an argument for widening it downward, not for
tightening it.

**Corrected 2026-08-22 — this evidence base is thinner and more tangled than the
row above originally claimed.**

- **These are not three independent lineages.** Kratz and the line-list
  reanalysis are the **same outbreak** (Isiro, DRC 2012), so agreement between
  them is evidence about one line list. And **Roddy P. is a co-author on
  Kratz**. What exists is two outbreaks, one clinical group, and **44 published
  in-care patients** — 26 in Uganda 2007–08 and 18 in Isiro 2012.
- **A fourth "source" was cited here and in a dozen model docstrings that is not
  a publication.** *"Funk & Abbott 2026, 0.59 [0.46, 0.72] (22/37)"* is
  `sbfnk/bdbv-linelist-analysis` — a GitHub repository carried as an
  uninitialised git submodule of `epiforecasts/BVDOutbreakSize`. No paper, no
  preprint, no DOI. **And the number is wrong**: the figure the upstream project
  itself quotes from that reanalysis is *"a baseline of 0.47 (95% CrI 0.31–0.65)
  for non-healthcare-worker (non-HCW) confirmed cases"*
  (`docs/examples/analysis.jl:731`), not 0.59 [0.46, 0.72]. Cite it as software
  with a commit SHA or not at all, and re-derive the number from the source
  before using it — the submodule is uninitialised, so nobody here has read it.
- **MacNeil's 17/43 = 40 % belongs to a different quantity** and should not be
  listed beside these. It is a fatality over everyone acutely confirmed, treated
  or not — a confirmed-case CFR, not an in-care one.
- **The anchors disagree with each other, in a direction that favours our fit.**
  Van Kerkhove Table 5 puts the BDBV *population* CFR at 0.34–0.42 (§6.2), while
  these two in-care series sit at 0.42 and 0.50 — in-care fatality at or above
  population fatality, which cannot hold if care does anything. The upstream
  project states the expected ordering explicitly: in-care fatality is *"a
  fatality conditional on admission rather than a causal treatment effect,
  **sitting below the infection case-fatality ratio** where care lowers
  mortality"*, and their own population prior is `Beta(6.6, 13.4)`, mean 0.33.
  Read that way the model's 0.310 is not an outlier.
- Our own ledger is the only estimate here with power behind it (664 exits
  against 44), and it is biased **upward** by the recovery under-recording
  documented elsewhere in this note — which moves it toward the fitted value,
  not away.

The recommendation is therefore weakened from *"Beta centred 0.46, sd ≈ 0.05,
strong"* to **Beta centred 0.42, sd ≈ 0.10, moderate**. A tight prior here would
be asserting more than 44 patients can support.

### 6.2 BDBV lethality — the first factor in q_comm

Van Kerkhove et al., *Scientific Data* 2, 2015, compiling across outbreaks,
gives species-level CFR: **Zaire 0.69–0.88, Sudan 0.53–0.69, Bundibugyo
0.34–0.42**. Bundibugyo is the least lethal human-pathogenic ebolavirus.

MacNeil et al., *EID* 16(12), 2010, give **17/43 = 40 %** among cases confirmed
from *acute-phase* specimens. The widely cited ~25 % uses a 56-case denominator
including 13 convalescent-serology-only cases — survivors by construction. The
40 % figure is the right one for a model of confirmed cases.

Untreated fatality should exceed treated, so unisolated BDBV fatality is
plausibly 0.5–0.7. Times swab ascertainment below 1, that gives **q ≈ 0.45**,
and makes the fitted 0.81–0.915 infeasible: at 0.915 the decomposition needs
swab ascertainment above 1 even at 0.9 unisolated fatality.

### 6.3 Overall ascertainment — one external anchor, not two

**Updated 2026-08-24 — still one external *fraction*, but now a within-outbreak
*trajectory*, on the right virus and the right response.**

Akilimali et al. report that since the outbreak was declared on 15 May 2026,
confirmed cases rose **while test positivity fell from roughly 70–80% in early
May to about 40% by early June**. Their denominators: of 2351 records in the
individual-level database between 3 May and 8 June, 505 (21.5%) were
laboratory-confirmed and 635 (27.0%) tested negative, the rest untested,
pending, or unresolved.

Falling positivity against rising confirmed counts is testing expanding faster
than transmission — i.e. **ascertainment improving over the period we fit**.
This is not an ascertainment fraction and cannot be used as one: positivity is a
function of who gets tested, and the early 70–80% reflects a narrow, severe,
highly selected testing pool as much as it reflects prevalence. But it does
constrain the *shape*: a model holding ascertainment constant across May–June is
contradicted by the source's own laboratory record. **If ascertainment is
time-varying in the model, this is the evidence that should discipline it, and
it is far closer to our setting than Montserrado 2014.**

Note the direction of the bias this introduces if ignored:
constant-ascertainment fits will attribute early under-detection to a smaller
epidemic rather than to less looking, biasing the seeding estimate late and the
early growth rate high.

**Corrected 2026-08-22: the Beni paper is not an ascertainment estimate and was
being used as one.**

Gignoux E, Idowu R, Bawo L, Hurum L, Sprecher A, Bastard M, Porten K. Use of
capture–recapture to estimate underreporting of Ebola virus disease. *EID*
2015;21(12):2265–2267, doi:10.3201/eid2112.150756 — Montserrado County, Liberia,
1 June – 14 August 2014: 227 reported against an estimated **876 (95 % CI
608–1,143)**, about **26 % ascertainment**, with the paper stating *"the number
of cases in Montserrado Country was at least 3-fold higher than that reported
during the study period."* Applies to all suspected, probable or confirmed
cases. Zaire ebolavirus. **This is a genuine ascertainment measurement and it is
the only one we have.**

Polonsky JA, Böhning D, Keita M, Ahuka-Mundeke S, Nsio-Mbeta J, Abedi AA, et al.
Novel Use of Capture-Recapture Methods to Estimate Completeness of Contact
Tracing during an Ebola Outbreak, Democratic Republic of the Congo, 2018–2020.
*EID* 2021;27(12):3063–3072, doi:10.3201/eid2712.204958 — Beni Health Zone, 31
July 2018 – 26 April 2020, 913 confirmed and 10 probable cases. 99 % of
case-patients with *any* contacts were identified; **49 % (95 % CI 43–55 %)** of
those with *infected* contacts — 24 % (11–38 %) in the first wave, 48 % (40–56
%) in the second.

**What that 49 % measures is contact-tracing completeness among already-
identified case-patients** — the sensitivity of detecting onward infections from
a case the response already had. It bounds how many transmission *links* were
seen, not how many cases existed, and it cannot be read as an ascertainment
fraction. It belongs in a discussion of R_eff and of the unaccounted-for
confirmed cases, not in this row.

So: one anchor, on a different species in a different response, at 26 %. That
still says a fit implying 3 % unascertained is not in contact with the evidence
— but it says it alone, and we should stop presenting it as though two
independent studies bracketed the answer.

### 6.4 Delays and the dwell

**Corrected 2026-08-24 — there is now a delay estimate from THIS outbreak, and
it is slower than the historical BDBV figure the τ argument below leans on.**

Akilimali et al., *NEJM* 395(6):610, 6 Aug 2026
(`pdfs/akilimali_et_al_2026.pdf`) report the interval from **symptom onset to
diagnostic sample collection**, fitted on the laboratory line list (data as of 5
June 2026) with `epidist`, which corrects for **double interval censoring** —
onset and sampling each recorded only to the day — and for **right truncation**.
Gamma won on LOOIC against lognormal and Weibull.

| population           |   N | median delay, d (95% CrI) | 25th pct | 75th pct |
| -------------------- | --: | ------------------------- | -------: | -------: |
| laboratory-confirmed | 129 | **4.8 (3.46 – 7.84)**     |     1.81 |    10.23 |
| test-negative        | 188 | 2.93 (2.22 – 4.27)        |     0.91 |      7.0 |
| all tested           | 634 | 5.39 (4.21 – 7.84)        |     1.69 |    12.91 |

Mean delay for confirmed cases is **7.4 d (95% CrI 5.3 – 13.5)**.

**This challenges the paragraph below.** That paragraph cites Van Kerkhove's
BDBV onset→hospitalisation median of **3.5 d** and concludes BDBV reaches care
faster than EBOV did, "which bears on τ". The current outbreak's
onset→**sample** median is 4.8 d and its mean 7.4 d. The two are not the same
interval — a sample can be taken at presentation, later in admission, or
post-mortem in the community, so onset→sample is not a clean substitute for
onset→hospitalisation — but if it is read as time-to-ascertainment, then τ in
*this* outbreak is **slower**, not faster, than the historical anchor. The
authors' own reading is that 7.4 d "might reflect a lack of diagnostic capacity
early during the outbreak" or genuine delay in presenting at a facility. Either
way, a τ prior built on 3.5 d is not in contact with the only current-outbreak
delay measurement we have. **Do not carry the 3.5 d forward without saying which
interval it is and why the 4.8 d does not displace it.**

Van Kerkhove 2015, **BDBV-specific**: incubation mean 6.3 d (5.2–7.3), median 7
(2–20); onset→hospitalisation median **3.5 d (0–8)**; onset→death median **9–10
d**; onset→recovery median **10 d (2–26)**. BDBV reaches care faster than EBOV
did in West Africa (3.5 d against 5.0 d), which bears on τ.

WHO Ebola Response Team, *NEJM* 371:1481, 2014: incubation 11.4 d; serial
interval **15.3 ± 9.3 d, gamma CV 0.66**; onset→hospitalisation 5.0 ± 4.7 d;
admission→death 4.2 ± 6.4 d. CV 0.66 implies gamma shape ≈ 2.3; exponential
would be CV = 1.

Kratz 2015, Isiro: onset to outcome, survivors median 18 d (8–26), deceased 15 d
(4–28). Pooled review estimates: onset-to-death 9.3 d (8.5–10.1),
onset-to-recovery 13.0 d (10.4–15.7) — deaths resolve sooner than recoveries, so
one dwell for both outcomes is a simplification worth naming.

---

## 7. What we can publish that would help

**Province-level laboratory streams — now published.** `lab_daily_ituri.tsv` (56
obs, 9,038 tests, 2,687 positives), `lab_daily_nord_kivu.tsv` (47 obs, 4,866
tests, 406 positives) and `lab_daily_haut_uele.tsv` (5 obs, 60 tests, 19
positives), each carrying `days_covered`, `n_report_days` and `flags` like every
other daily stream. These let §5.1 be done exactly, with no coverage parameter
and no loss of days.

**The care-flow table**, printed on 54–59 of 87 reports and not yet extracted:
patients in isolation split confirmed/suspect, total 24-hour exits, transfers,
occupancy rate, and ***Sorties — évadés*** (absconders, counted). This would
turn δ and f_cfr from bounds into point estimates. It also shows **Nord-Kivu
running at 120–160 % of isolation-bed capacity throughout** (*"La saturation
persiste au Nord-Kivu (120,6 %), déficit critique de lits d'isolement"*, sitrep
060), so the isolation census there is supply-censored rather than proportional
to the confirmed compartment.

---

## 8. Not verified

**Added 2026-08-24 — an individual-level database for THIS outbreak exists.**
Akilimali et al. analyse *"2351 recorded cases in the individual-level database
for BVD between May 3 and June 8, 2026"*, and separately a **laboratory line
list** (data as of 5 June 2026) carrying symptom-onset dates, sample-collection
dates, Ct values and outcomes. Ethics approval from the University of Kinshasa.
We do **not** hold either, and neither appears to be public — but the earlier
working assumption in this project, that the 2026 outbreak offers only aggregate
health-zone counts and no case-level data, is **wrong**. What is true is that
the case-level data exists, is held by the response, and reaches us only through
what papers like this one report. Worth asking whether it can be requested;
every delay and severity prior we have would otherwise keep coming from 2007
and 2012.

One quantity from it we cannot presently reproduce: **Ct value is associated
with death** — median Ct lower (higher viral load) among those who died, by −3.4
(95% CI −6.1 to −0.7) in the Kinshasa/Altona cohort and −3.7 (−5.2 to −2.3) in
the Bunia/RADIONE cohort. The cohorts used different assays and gene targets, so
only the within-cohort contrast is interpretable. Nothing in our aggregate
streams carries viral load.

- ~~**Funk & Abbott ≈ 0.59 [0.46, 0.72] (22/37)** — unsourced.~~ **RESOLVED
  2026-08-22, and it is not a paper.** It is `sbfnk/bdbv-linelist-analysis`, a
  GitHub repository (`sbfnk` = Sebastian Funk), registered as a git submodule of
  `epiforecasts/BVDOutbreakSize` at `external/bdbv-linelist-analysis`. The
  upstream repo's own bibliography records it as
  `@misc{bdbv_linelist_analysis_2026}`, *"Bundibugyo Ebola virus — Bayesian
  delay-distribution and stratified CFR estimation from the 2012 Isiro
  outbreak"*, authored Funk & Abbott in `refs.bib` but credited to Funk alone in
  the README. **The number 0.59 [0.46, 0.72] does not appear anywhere**; the
  figure upstream quotes is 0.47 (95 % CrI 0.31–0.65) for non-HCW confirmed
  cases. Cite as software — URL plus commit SHA plus access date — never in an
  author-year form. Our local pin is
  `epiforecasts/BVDOutbreakSize@90df658df2515314eceb4ac5e82dd4fe9fb894cd`,
  fetched 2026-08-17; **the submodule itself is uninitialised, so the analysis
  is unread.** `git submodule update --init` settles it.
- **A second epiforecasts citation in our models checks out.**
  `bvd_national_labdelay.camdl` cites *"Abbott, Brand & Funk 2026,
  epiforecasts/BVDOutbreakSize, `lab_delay_model` — mean 4.5 d, SD 4.0 d"*,
  which matches `analysis.jl` eq. (18): `μ_rec ~ Normal⁺(4.5, 1.0)`,
  `σ_rec ~ Normal⁺(4.0, 0.75)`. One caveat worth carrying: upstream says of that
  delay *"No per-sample outbreak data grounds this, so the prior is our own
  choice"* — it is a declared belief, not an estimate.
- **The onset-to-death prior our `gamma` uses is taken from the wrong pathway.**
  Upstream fits onset-to-death as a convolution of onset-to-admission and
  admission-to-death (`α_oa ~ Normal⁺(1.18, 0.28)`,
  `θ_oa ~ Normal⁺(3.69,
  1.20)`; `α_ad ~ Normal⁺(2.15, 0.60)`,
  `θ_ad ~ Normal⁺(3.91, 1.38)`), giving an *"implied mean about 13 d"* — a route
  **through admission**. It carries a **separate community-pathway**
  onset-to-death delay, `α ~ Normal(5.48, 2.0)`, `θ ~ Normal(1.49, 0.5)`, mean
  **8.17 d** (`docs/fits/registry.jl:263`). Our `gamma` governs the
  never-confirmed-alive route, so the community pathway is the one it should be
  anchored to. See the modelling repo's
  `notes/2026-08-22-where-the-estimates-are-in-tension.md` §5.
- **The 95 % CI on the incubation period is misattributed in our models.**
  MacNeil prints only *"an average incubation period of 6.3 days among
  laboratory-confirmed EHF case-patients (n = 24)"* — **no interval**. The
  *"(5.2, 7.3)"* is Van Kerkhove Table 5, which cites MacNeil for the point
  estimate. Split the citation.
- **Any *fitted* onset-to-death distribution with a published shape parameter
  for an ebolavirus.** Medians, means and ranges are abundant; a fitted gamma or
  Weibull for onset-to-outcome was not located. The Erlang 2–3 recommendation
  therefore rests on the serial interval's CV, which is an inference about the
  dwell rather than a measurement of it.
- **Post-mortem swab coverage and burial-refusal rates** — the second factor in
  q_comm, unmeasured on both sides.

## Next

1. Build `extract_care_table.py` (§7) — turns δ and f_cfr from bounds into point
   estimates and settles whether the isolation census is supply-censored.
2. Test whether τ tracks bed occupancy across provinces: γq/τ runs 0.51–0.60 in
   Nord-Kivu, 0.30–0.38 in Ituri, 0.21–0.31 in Haut-Uélé, which orders the same
   way as bed pressure. Three points, untested, but testable.

## Sources

**Added 2026-08-24.** Akilimali et al., "Clinical Characteristics of Patients
Infected with Bundibugyo Virus, DRC 2026", *New England Journal of Medicine*
395(6):610, 6 August 2026 (Correspondence) — `pdfs/akilimali_et_al_2026.pdf` and
`pdfs/akilimali_et_al_2026_supp.pdf`. The only current-outbreak clinical and
delay data we hold. See §6.1, §6.3, §6.4 and §8, and
`notes/2026-08-24-who-wer-and-genomic-priors.md` for the genomic dating and the
WHO comparison of all three BDBV outbreaks.

### Earlier sources

- [MacNeil et al., *EID* 16(12), 2010 — BDBV proportion of deaths](https://wwwnc.cdc.gov/eid/article/16/12/10-0627_article)
- [Roddy et al., *PLOS ONE* 2012 — BDBV clinical management, Uganda 2007–08](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0052986)
- [Kratz et al., *PLOS ONE* 10(6):e0129333, 2015 — BDBV, Isiro DRC 2012](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0129333)
- [WHO Ebola Response Team, *NEJM* 371:1481, 2014](https://www.nejm.org/doi/full/10.1056/NEJMoa1411100)
- [Van Kerkhove et al., *Scientific Data* 2, 2015 — parameter review](https://pmc.ncbi.nlm.nih.gov/articles/PMC4443880/)
- [Gignoux et al., *EID* 21(12), 2015 — capture–recapture, Montserrado](https://pmc.ncbi.nlm.nih.gov/articles/PMC4672419/)
- [Contact-tracing completeness, Beni DRC, *EID* 27(12), 2021](https://wwwnc.cdc.gov/eid/article/27/12/20-4958_article)
