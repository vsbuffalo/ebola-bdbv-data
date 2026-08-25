# Reference PDFs

Fetched 2026-08-24. Source URL and what each is for.

| file | source | why it is here |
|---|---|---|
| `roddy_2012_bundibugyo_uganda_plosone_e52986.pdf` | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0052986 | Bundibugyo, Uganda 2007–08. In-care fatality 11/26 = 0.42. One of only two published in-care series for this virus. CC-BY. |
| `kratz_2015_isiro_drc_plosone_e0129333.pdf` | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0129333 | Isiro, DRC 2012. ETC fatality 9/18 = 0.50. The other in-care series. Roddy is a co-author, so these two are not independent clinical groups. CC-BY. |
| `who_iris_18c72e11.pdf` | https://iris.who.int/server/api/core/bitstreams/18c72e11-6540-4d75-8657-c3bef29f9404/content | WHO *Weekly Epidemiological Record* No. 33, 21 Aug 2026. Feature article comparing all three BDBV outbreaks; carries the independent 5021/2378 figure at 2026-08-16. |
| `virological/1045_*.txt` | https://virological.org/t/1045 (INRB Kinshasa and partners, 9 Jul 2026) | 139 genomes. tMRCA 15 Mar 2026 (95% HPD 9 Feb – 12 Apr); doubling time 11.7 d (6.8–17.5). The analysis WHO cites. |
| `virological/1042_*.txt` | https://virological.org/t/1042 (Cuomo-Dannenburg & Ghafari, 4 Jun 2026) | 10 genomes. R₀ 1.31–1.55; generation time 9.6 d from `{epireview}`. Explicitly informal. |
| `virological/1032_*.txt` | https://virological.org/t/1032 (18 May 2026) | First outbreak genomes; identifies a new spillover event and the Kampala imported case. |

Read alongside `notes/2026-08-24-who-wer-and-genomic-priors.md`, which records
what each contributes to priors and where the estimands differ.

## What is committed here, and what is not

The two PLOS ONE papers are **CC-BY** and are committed. The WHO *Weekly
Epidemiological Record* is WHO copyright, redistributable with attribution,
and is committed.

**Akilimali et al. is NOT committed.** NEJM correspondence is copyright the
Massachusetts Medical Society and is not open access; this repository has a
public remote, so the PDF is gitignored and only cited. Fetch your own copy
from nejm.org. Everything this project takes from it -- the onset-to-sample
delay distribution, the test-positivity trajectory, the death proportions --
is quoted with its numbers in `notes/2026-08-22-rho-reporting-and-priors.md`
(sections 6.1, 6.3, 6.4, 8), so no conclusion here depends on holding the file.
