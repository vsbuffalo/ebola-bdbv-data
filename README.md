# ebola-bdbv-data

[![daily update](https://github.com/vsbuffalo/ebola-bdbv-data/actions/workflows/daily-status.yml/badge.svg)](https://github.com/vsbuffalo/ebola-bdbv-data/issues?q=is%3Aopen+label%3Agate-failure)

Analysis-ready case data for the 2026 Bundibugyo virus outbreak in the
Democratic Republic of the Congo (DRC), extracted from the national public
health institute's (INSP) daily situation reports — down to the health zone,
with every number checked against the page that printed it.

**Website:** <https://vsbuffalo.github.io/ebola-bdbv-data/>: every release, its notes and its figures.

**How to cite:** use GitHub's "Cite this repository" button (it reads
[`CITATION.cff`](CITATION.cff)), and please name the release tag you used, such
as `data/2026-10-20-r0`, so anyone can rebuild exactly the data you had.

**Found a problem?** Please [open an issue](https://github.com/vsbuffalo/ebola-bdbv-data/issues).
A suspicion is enough; I'd rather check a false alarm than miss a real error.

**Using these data?** I'd love to hear about it. Knowing who relies on this
helps me decide what to keep up and what to add next, and an issue is a fine
way to say hello.

## About this repository

**This is independent work.** It was built by me, Vince Buffalo, guiding
Anthropic's Claude Code agents, which wrote most of the code, extraction rules
and documentation under my direction and review. It began as work at the
Institute for Disease Modeling (IDM) and is now released publicly. It is not an
official product of IDM, of the DRC's Institut National de Santé Publique
(INSP), of WHO, or of any ministry of health, and none of them has reviewed it.
It was built on the outbreak's schedule — a report a day, each needing to be
read within hours of publication — and that pace was only possible with agents
doing the reading, the code and much of the writing, which I directed and
checked.

**What it reads.** The primary source is INSP's situation reports on the 2026
Bundibugyo virus outbreak, fetched from insp.cd and pinned by SHA-256. Two
independent machine-readable renderings of the same reports serve only as
checks: INRB-UMIE's BDBV2026-Data transcription and the epiforecasts scan.
Health-zone geography and WorldPop populations come from the INRB-UMIE
repository. Case counts outside the DRC are transcribed by hand from WHO Disease
Outbreak News and national health authorities, each quote checked against a
hashed snapshot of the page it came from. The inputs are pinned by hash: the PDF
archive in `data/raw/sitrep_pdfs.manifest.tsv`, the downloaded geography and
populations in `data/raw/PROVENANCE.tsv`, and the pages behind the counts
outside the DRC in `data/raw/exports/snapshots.manifest.tsv`. The two renderings
we only compare against are pinned separately: INRB-UMIE's transcription at the
commit in `external.lock`, and the epiforecasts scan as a committed copy in
`data/raw/scan/`.

**Why it is built this way.** Errors in other groups' extraction and processing
of these reports have already been found, and they have moved published
estimates in this outbreak. One group's digitisation of the reports'
symptom-onset figure read below each figure's own printed total, by 4–9% in
August and 10–23% from SitRep 108. Estimates released through mid-September
rested on it, and when the reader was fixed, that group's own audit attributed a
27% fall in its headline outbreak-size estimate to the re-read
([epiforecasts/BVDOutbreakSize#875](https://github.com/epiforecasts/BVDOutbreakSize/pull/875),
[#886](https://github.com/epiforecasts/BVDOutbreakSize/issues/886)). They found,
fixed and documented the problem in public, which is an open and admirable way
to handle it.

I had measured the August under-reads on 28 August
([notes](notes/2026-08-28-onset-digitiser-requirements.md)) while at IDM, and
built our own reader to check every figure against its printed total and refuse
any that does not close. A similar error had happened in this data processing
pipeline before any release: an early version read the share of confirmed deaths
found in the community as 1.00 where the pages print 0.55, because a table
broken across a page had slid one column into its neighbour. Neither this error
nor the digitisation error above looks wrong from the outside, but both can be
caught the same way: by checking an extraction against the totals the same page
prints. That "bookkeeping" or "accounting" approach is the design of this
pipeline. Numbers are read from the cells the situation reports draw, and are
accepted only when the page's own totals balance around them; when they do not,
they are refused rather than guessed. Every place the source disagrees with
itself is recorded, and every value is compared with the two other renderings.

**What that does and does not buy.** These checks make reading errors loud; they
cannot make the source's own counts true, and refusing costs coverage. The onset
reader currently refuses every chart since 19 September. Read
`data/build/streams/README.md` and `registers/` before fitting anything.

## Getting the data

You won't find the data files in this repository — `data/build/` is gitignored,
on purpose. Everything in it rebuilds byte-identically from the committed
inputs, so a release is a git tag rather than a pile of files, and committing
the outputs would create a second copy free to drift from the code that makes
them. To get the files, check out a release and build it:

```sh
git checkout data/2026-10-18-r0     # or the newest: git tag -l 'data/*' --sort=-creatordate | head -1
make fetch-pinned                   # network: exactly the PDFs that tag read (~200 MB)
make build streams                  # offline from here on
```

`make fetch-pinned` downloads the reports the tag's committed index names and
nothing newer, so you rebuild that release rather than today's data. For the
latest reports instead, stay on `main` and run `make refresh`.

You'll need [uv](https://docs.astral.sh/uv/) and `pdftotext` (poppler); Quarto
only if you want the rendered documents (`make doc`). The files downstream
models fit land in `data/build/streams/`, and the first thing to read there is
the generated [`data/build/streams/README.md`](data/build/streams/README.md):
one entry per file, saying what it measures, its span, and how it misleads.

## How it works

The situation reports are, at heart, ledgers: almost every table prints its
totals beside the parts they summarise — health-zone rows beneath a province
row, province rows above a national total. So this pipeline takes an accounting
approach. A number is accepted because the books balance around it, not because
it parsed, and a number the books reject gets investigated, not repaired.

- **Read the drawn geometry, not the text.** Word draws every table cell as a
  vector rule, and cells are read from those rules, so a wrapped name stays one
  row and a blank cell stays blank instead of shifting its neighbours.
- **Balance every page's books.** Health zones plus the unassigned pool must
  equal the printed province row, and provinces the printed national total. A
  page that fails is a build failure, not a warning.
- **A discrepancy is a finding.** Where a page genuinely doesn't add up — the
  source disagreeing with itself — a human reads it and records the judgement in
  `registers/`, keyed to the document's SHA-256, so a revised document comes
  back for a fresh look.
- **Check against independent readings.** Every value is compared with
  INRB-UMIE's transcription and the epiforecasts scan, and disagreements are
  recorded rather than resolved.
- **Reproducible and current.** The archive is fetched same-day and pinned by a
  hash manifest; every build artefact has a `make` rule; a rebuild is
  byte-identical.

For the short, non-technical version of why this was built the way it was,
see [how this was built](docs/engineering.md). The details live in three pages: [how the extraction works](docs/extraction.md),
[how it is validated](docs/validation.md), and
[the data contract](docs/data-contract.md) — what the stream files guarantee to
downstream models, and the traps (three readings of one case count, `NA` versus
zero, half-open windows) worth knowing before you fit anything.

## What's in the data

What these files carry that no other machine-readable rendering of the reports
does:

- **The treatment center vs community ascertainment split.** Each day's
  confirmed deaths divided into those found in the community and those in a
  treatment centre — the closest thing the source prints to a measure of how
  much transmission surveillance is missing, and the quantity downstream models
  most need.
- **Province series that are derived, not transcribed.** Built from the zone
  rows and checked against every printed province row, so a missed row is a loud
  failure instead of a quiet undercount.
- **The care ledger, testing and burial alerts**, read out of the reports' prose
  and kept only where each passage's own arithmetic checks.
- **Cases counted outside the DRC** (Uganda, Kenya, Nigeria, France), from WHO
  and national ministries, with each source's classification kept verbatim:
  imported, linked, or origin still under investigation.
- **The source's own caveats as data**, so a model can down-weight the days the
  source itself called provisional.

## Running it

```sh
make check      # is the archive current, and does the source still look the same?
make refresh    # network: fetch new reports, then rebuild everything offline
make build      # PDFs -> zone extraction -> province aggregation
make streams    # the observation streams downstream models fit
make figures    # the figures, into data/build/figures/<release>/
make compare    # ours against the two other lineages (needs `make external`)
make doc        # render analysis/data.html and explore.html
make test       # the tests, each pinned to a named report
```

**Run `make check` first.** It's the only step that looks *outward*: every other
check asks whether the reports we hold are internally consistent, and none of
them can ask whether we hold the reports that *exist*. It exits 0 when we're
current, 1 when new reports are out (`make refresh`), 2 when the source has
changed under us (look before fetching), 3 when the site doesn't answer, and 4
when we're current but the source has gone quiet.

`data.html` is the document of record — what exists, what reconciles, every
number read from a build artefact at render time. `explore.html` is its
interactive companion. `make serve` serves both (port 8790 by default).

## Releases

Data ships as git tags, `data/<date>-r<n>`. The date is the data date — the date
the newest report the build read speaks for — and `<n>` is the revision. The
first release for a data date is `-r0`. If anything changes after that without a
new report arriving — a reader fix, a correction to a register — the release is
cut again as `-r1`, `-r2` and so on. So `data/2026-10-18-r1` would be the same
reports as `-r0`, read better. Published tags never move and are never deleted,
because downstream models pin one per fit; a later revision supersedes an
earlier one without withdrawing it. Every tag is recorded in
`registers/released_tags.tsv`, and what changed in each, including whether it
breaks anything, is in the [CHANGELOG](CHANGELOG.md).

A tag is cut only when every gate passes: the accounting identities hold, the
test suite passes, every quote behind the counts outside the DRC is on the page
it cites, and the committed figures rebuild byte-identically from a fresh clone
(`make release-check`).

**Releases are cut automatically.** A scheduled job (`make daily`, run at 14:00
and 22:00 on my machine) checks INSP for new reports, fetches and builds them,
and runs every gate. If they all pass, it tags the release, pushes it and logs
it on the pinned *Daily releases* issue; its CHANGELOG entry is a short
generated stub. If a gate fails, it files a `gate-failure` issue at once — the
badge above turns red — and starts a Claude Code agent on a branch, with
instructions in [`scripts/daily_fix_prompt.md`](scripts/daily_fix_prompt.md), to
find the page that broke the reader and propose a fix. The agent can't push or
tag; its fix arrives as a pull request that I review, and merging it is what
lets the next run cut a revision. Releases stop while a failure is open, so a
tag never skips past a report nobody has read correctly.

## Layout

| Path          | What                                                                                                                          |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `data/raw/`   | fetched and hand-recorded inputs: the PDF archive (pinned by manifest), the INSP index, geography, populations, export tables |
| `data/build/` | everything derived — gitignored, always safe to delete, rebuilt by `make`                                                     |
| `figures/`    | the only derived files committed, so documents outside the pipeline can link them; captions in `figures/README.md`            |
| `registers/`  | **hand-authored judgements** about specific pages, the only content no rule can regenerate; see `registers/README.md`         |
| `docs/`       | the extraction, validation and data-contract pages                                                                            |
| `notes/`      | dated lab notes: the design decisions, the measured dead ends, the findings                                                   |
| `scripts/`    | everything the Makefile calls; `scripts/lib/` is the geometry and vocabulary layer                                            |
| `analysis/`   | the rendered documents and their fail-closed guard                                                                            |

## Conventions

- **polars, not pandas; `uv` for packages.** No absolute paths in anything
  committed.
- **Every artefact has a rule.** A file under `data/build/` with no `make` rule
  that regenerates it is a bug.
- **A sum of nothing is null, not zero.** polars sums an all-null group to 0,
  which fabricates observations; every aggregation here guards against it.
- **Data dates come from each page's printed report date, never the filename.**
  Upload filenames carry the publication date, no date, or (once) a timestamp
  that parses as the year 2022.
- **Flows and stocks never share a column.** The same French word heads both, in
  different vintages.
