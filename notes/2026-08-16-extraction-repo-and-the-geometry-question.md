# The extraction repo, and whether the parsing rules are forced

Date: 2026-08-16 Project: ebola-bdbv-data Status: trial run; the geometric
reading is measured, not proposed Tags: repo-split, pdf-extraction,
table-geometry

---

# Trial result — the geometric reading reproduces the reference exactly

Run: `scripts/trial_geometric_table2.py`, reading Table 2 from the drawn rules
via `scripts/lib/pdftable.py`, compared row by row against `sitrep_table2.csv`
from the `pdftotext` parser. Outputs under `data/trial/`.

Restricting to the **39 reports where the page's own arithmetic closes on the
geometric read** — the province rows sum to the report's printed `Total`, which
is the same identity the existing pipeline uses as its acceptance test:

|                                                     |       |
| --------------------------------------------------- | ----- |
| rows matched to the reference on (report, row name) | 1,702 |
| cumulative cases agree                              | 1,701 |
| cumulative deaths agree                             | 1,701 |
| **rows where a value disagrees**                    | **0** |
| rows present only in the reference                  | 0     |
| rows present only in the geometric read             | 34    |

The single non-agreeing row on each count is a null on both sides, not a
conflict. Where the geometric read is self-consistent it does not differ from
the regex parser anywhere, and it does not miss anything the regex parser found.

**Report coverage.** The reference reaches 63 reports; the geometric reader
reaches 71 with a single code path. Twelve of the extra are reports the
reference's Table 2 route does not produce: sitreps 005–015 are covered in the
existing pipeline by a _second_ parser (`parse_early_zone_table.py`, feeding
`sitrep_early_zones.csv`), so that comparison is not like-for-like — but the
fact that one geometric reader covers both the early and the main table layouts,
where the current pipeline needs two parsers with disjoint rule sets, is the
result. Sitreps 048, 084, 085 and 086 are genuine recoveries: the reference
produces no Table 2 rows at all for sitrep 048, while the geometric read returns
22 rows whose printed `Total` is 1,460 cases and 452 deaths.

Four reports go the other way (018, 026, 037, 090) and the geometric reader
should get them and does not.

## Where it fails, and what kind of failure it is

Every current failure is in **table selection**, not in reading cells. Of 82
reports: 71 return rows, 8 return none, 3 find no qualifying heading. Of those
returning rows, the identity closes on 39, is not checkable on 21 (no printed
total in the rows recovered), and fails on 11.

The failures concentrate by vintage. The 021–082 middle period is 36 of 50
closing. The 005–020 early period closes on none — those reports print a
different table whose totals my trial does not yet locate. The 083–092 vintage
closes on 3 of 10, which is the vintage the handoff already flags as churning
(renamed series, dropped caveat, dropped PPL table, `A ventiler` rows).

The one substantive selection bug I traced: on sitrep 083 the trial picks the
per-zone _outcomes_ table
(`Zone de santé | Cas confirmés | Guéris | En
hospitalisation | Décès`) instead
of Table 2, because that table's heading also names a health zone, a case count
and a death count. It then reads Bunia as 35 cases where Table 2 prints 967. The
heading vocabulary is too loose a key and needs the cumulative/daily distinction
to discriminate. That is a half-day of work on the selector, not a problem with
the grid.

This is the honest split: **cell reading is validated and exact; table selection
is unfinished.** The 400 lines of wrap-shape and column-ruler machinery in
`parse_zone_deaths.py` are the part the geometry replaces, and the trial says it
replaces them without changing a single value. The title-and-terminator span
search is the part that still needs domain knowledge — and it needed it before.

## What the trial deliberately does not do

No alias resolution, no province carry, no reconciliation exception register, no
rejected-values register, no `level` assignment beyond the province vocabulary
needed for the identity check. Those encode knowledge about the outbreak rather
than about PDF layout and a replacement would keep them unchanged. The
comparison is on raw printed values keyed by (report, row name), which is the
layer where the two approaches can actually disagree.

One correction worth recording, because it nearly became a false claim in this
note. The first comparison appeared to show the geometric reader recovering
`Boma Mangbetu` and `Makiso- Kisangani` on sitrep 074 where the reference missed
them. It had not: the reference holds those rows as `BomaMangbetu` and
`MakisoKisangani`, concatenated without a separator by the parser's fragment
join, and my join key collapsed whitespace instead of removing it. Both routes
read that report correctly and both agree with its printed total of 3,360. The
key now strips spacing entirely. The wrapped-row handling is still the clearest
illustration of what the geometry buys — it just is not a difference in the
extracted values on that report.

---

## Summary

Two recommendations, and the second is the load-bearing one.

**Move the extraction layer here as planned.** The seam is clean: the modelling
side reads exactly seven small TSV files and nothing else. `scripts/lib/` is
100% data-side with no model importer. All three test files are data-side. No
rule in `workflow/data.smk` touches a model, a posterior, or the `camdl` binary.
There is nothing to disentangle — only things to leave behind.

**Do not port the Table 2 parser as written.** The situation reports are
Microsoft Word exports that draw every table cell as a vector rectangle. The
current pipeline reads them through `pdftotext -layout`, which discards that
geometry and flattens the page into a character grid; the parser then spends
about 400 lines reconstructing, from character positions, the column and row
structure that was in the file to begin with. Most of the documented extraction
failures — the wrapped health-zone names, the drifting column ruler, the run-on
into the alerts table, sitrep 80's missing Ituri row — are artefacts of that
lossy projection rather than facts about the source. A 63-line geometric
extractor with no table-specific regular expressions recovers the rows that cost
the most effort. The measurement is below.

This does not eliminate the rules. It relocates the boundary between what is
forced by the documents and what is forced by the extraction technology, and the
boundary moves a long way.

## The question

The handoff frames the extraction as a pile of accumulated special cases, each
earned by a real failure and each documented with the cases it cost. Reading
`scripts/parse_zone_deaths.py` supports that reading: 1,130 lines, of which 368
are comments, and nearly every regular expression carries a war story naming the
report it broke on and the number of cases that went missing. The natural
conclusion is that the source is simply irregular and the rules are the price.

That conclusion is half right. The reports are irregular. But a large share of
the irregularity the parser handles is not in the reports — it is introduced
between the report and the parser.

## What the source documents actually are

Every one of the 82 archived PDFs is a Word export or a re-encoding of one. The
producers observed across the corpus: `Microsoft® Word LTSC`,
`Microsoft® Word
2016`, `Microsoft® Word for Microsoft 365`, `www.ilovepdf.com`
(a re-encode), and `macOS … Quartz PDFContext` (opened in Preview and re-saved).
None is a scan; 67 of 82 carry a structure tree (`Tagged: yes`).

Word draws table borders as thin filled rectangles. On page 4 of sitrep 080 —
the page whose Ituri row is the subject of one of the longest comments in the
parser — `pdfplumber` reports 248 horizontal rules, 91 vertical rules, and 80
cell-body rectangles. The horizontal rules sit at 31 distinct vertical
positions, and those positions _are_ the row boundaries, including the tall rows
that hold a name too wide for its column.

`pdftotext -layout` renders none of this. It emits a character grid in which a
tall cell becomes several text lines and a cell's column membership must be
inferred from where its characters happen to land.

## The measurement

Here is what `pdftotext -layout` gives for the Haut-Uélé block of sitrep 080,
page 4:

```
Haut-Uélé             61              34          33,3%              0        0        0        0
Boma                  13              4
                                                  33,3%              0        0        0        0
Mangbetu
Isiro                 19             11           50,0%              3        0        2        2
```

The health zone `Boma-Mangbetu` has become three text lines, the middle one
carrying no name and the outer two carrying no numbers. The parser handles this
with `SPLIT_HEAD`, `SPLIT_TAIL` and `FRAGMENT` — three regular expressions whose
combined comment block records that before they existed, `Boma-Mangbetu` (13
cases) and `Makiso-Kisangani` (3 cases) were dropped whole, which was exactly
the report's 16-case shortfall.

Here is the same block read from the drawn rules, by a function that contains no
pattern specific to this table:

```
y= 246.3 | Haut-Uélé         | 61 | 34 | 33,3%  | 0 | 0 | 0 | 0
y= 258.3 | Boma Mangbetu     | 13 |  4 | 33,3%  | 0 | 0 | 0 | 0
y= 281.6 | Isiro             | 19 | 11 | 50,0%  | 3 | 0 | 2 | 2
```

`Makiso- Kisangani | 3 | 3 | 100,0%` comes out the same way, as does the
terminating `Total | 3 802 | 1 707 | 44,2% | 58 | 40 | 32 | 72` with its
non-breaking-space thousands separators intact. The whole extractor is 63 lines:
snap the rectangle edges into an x-ordinate list and a y-ordinate list, then
assign each word to the cell whose interval pair contains its midpoint. There is
no ruler to learn, no column-gap threshold, no wrap shape to recognise, and no
row that can be dropped for failing to match a shape.

The same function reads the early reports, whose table has no letality column
and therefore a different row shape entirely. Sitrep 005, page 4:

```
Provinces | Zones de santé | Nbre de cas suspects | Nbre de décès suspects | Nbre de cas Confirmés | Nbre de contacts
Ituri     | Bunia          |  90 | 23 |  6 | 203
Nord-Kivu | Katwa          |   1 |  0 |  1 | ND
          | Total          | 575 | 148 | 51 | 847
```

Two things to note. The vertically merged province cell resolves correctly —
`Ituri` spans four zone rows in the source and lands on the row its rectangle
centres on, which is the behaviour `parse_early_zone_table.py` documents at
length as a hazard. And the header row extracts as clean column _names_, which
suggests that table identification could key on header cells rather than on a
title regular expression plus a lookahead window plus a terminator — the
mechanism whose failure twice sent the Table 2 span running into the alerts
table and returned 11,360 confirmed cases for a day that had 1,502.

I did not implement table selection, so treat that last point as a promising
direction rather than a demonstrated result.

## What this does and does not buy

It would be easy to overclaim here, so being explicit about scope.

**Addressed by geometry.** The five row shapes in `parse_zone_deaths` (`ROW`,
`ORPHAN`, `SPLIT_HEAD`/`SPLIT_TAIL`/`FRAGMENT`, `NO_LETALITY`, `AVENTILER`); the
learnt column ruler (`_cluster`, `_anchors`, `_fit`, `COL_GAP`, and the
two-candidate-ruler logic for the reports whose columns shift mid-page); the
blank-cell-versus-missing-cell problem that the module docstring identifies as
the reason the table must be read by character position at all; the positional
slicing in `parse_tables.py`; and the centred-province-label and three-line-wrap
rules in `parse_early_zone_table.py`. Call it 400 lines of code across three
files, plus the roughly 250 lines of comment that explain them.

**Partly addressed.** `parse_sitrep_national.py` reads dashboard tiles rather
than a table, matching a value to its label by column proximity. Real
coordinates are better than character columns here, but the genuine ambiguity —
the value sits _above_ its label in some vintages and _below_ in others —
remains.

**Not addressed at all.** `parse_laboratory.py`, `parse_provisional_caveat.py`
and `parse_sitrep_prose_zones.py` read narrative prose. There are no columns.
That is about 610 lines and it is irreducible vocabulary work.

**Not addressed, and not a parsing problem.** The French vocabulary — five
spellings of the unallocated-cases row, sixteen province spellings, the sentinel
set for "not reported" — is irreducible in content. It is currently declared six
separate times in six files with six different memberships, which is a real
defect, but the fix is one declarative table, not a different PDF library.

**Must be preserved exactly.** The semantic annotations are the project's actual
knowledge and none of this touches them: that a blank daily cell means zero but
an em-dash means not-reported; that the early table's suspected column is a
cumulative stock while the later one is a daily flow, so differencing one and
not the other silently mixes a stock with a flow; that the daily ascertainment
block is a stream with a start date rather than a series with holes; that `ND`
is never zero; that a negative cell is a declared downward revision and is
carried rather than clipped. These live in docstrings today. Whatever replaces
the parsers must let them be declared and enforced, not merely described.

## The three layers

The rules sort into three kinds, and conflating them is what makes the
proliferation look inevitable.

1. **Extraction-technology rules.** Wrap shapes, column rulers, span
   terminators, blank-cell alignment. Forced by `pdftotext -layout`, not by the
   documents. Largely removable.
2. **Source vocabulary.** French labels, spelling variants, sentinel spellings,
   province names. Forced by the documents, irreducible in content, but it is
   _data_ and belongs in a declarative table rather than in six sets of Python
   constants.
3. **Source semantics.** Stock versus flow, `ND` versus zero, start-date versus
   hole, which identity holds at which level, which residuals are verified
   exceptions. Forced by the documents, irreducible, and the part actually worth
   the 368 comment lines. This is what the repo exists to hold.

The current code expresses all three in the same medium — hand-tuned regular
expressions with prose commentary — which is why layer 1's accidents read as
layer 3's necessities.

## Incidental duplication, independent of the geometry question

Separately from the above, the eleven parsers share a skeleton that is currently
copied rather than shared. The `pdftotext -q -layout` invocation appears at
twelve call sites, ten byte-identical, plus one helper in `parse_zone_deaths.py`
that is defined and never called while the same call is inlined five lines
later. Four parsers run `pdftotext` twice per PDF because they call
`report_key(pdf)` without passing the text they are about to extract anyway.
`SPACES = "   "` is declared six times. The title-regex-to-terminator span
search has six near-identical implementations, one of which is a hand-copy of
`lib/indicator_table.span`. Nine parsers write a `_status.csv` sibling with the
same line. `parse_alerts_table.main` and `parse_care_table.main` are the same
function.

One consequence of this is a live correctness contradiction worth recording.
`lib/report_date.py` documents that the filename date is the _publication_ date
on six reports, that trusting it made three pairs of consecutive days look like
duplicates, and that the de-duplication which followed deleted sitreps 19, 23
and 50 outright. Three parsers still take the date from the filename, and
`parse_alerts_table.py` then re-implements that same de-duplication —
deliberately, with a fourteen-line comment — on the same three report pairs. Two
files in one directory hold opposite beliefs about the same three reports. It
has not caused harm because both parsers are unwired from the workflow. It is
the clearest available argument for a single entry point.

## An unrelated finding about the source

While validating the geometric extractor I checked whether the printed letality
column equals deaths divided by cases on its own row. Across the corpus it does,
essentially exactly: 34 of 34 rows on sitrep 081, 35 of 35 on sitrep 092, and
similar for every other report — with one exception.

**On sitrep 080 the letality column matches its own row in 7 of 31 rows.** I
rendered page 4 and read it: the page prints `Rimba 9 4 29,6%`,
`Goma 1 0
76,1%`, `Kalunguta 7 4 0,0%` and `Vuhovi 2 1 100,0%`, all
arithmetically impossible against their own cases and deaths. The cases and
deaths columns of that same page reconcile exactly — Nord-Kivu's twelve zone
rows sum to the 414 cases and 285 deaths its province row prints — so the two
columns the pipeline keeps are sound and only the derived column is wrong. The
likeliest reading is that the letality column was carried over from an earlier
vintage of the table while the counts were updated.

Three other reports (034, 049, 073) show a handful of mismatched rows rather
than a whole bad column.

The consequence: the decision to discard letality as "a redundant column is a
chance to disagree with ourselves" produced the right extraction, but the
inference behind it is worth inverting. A redundant column that the source
publishes is a free integrity check on the columns we keep — it is the only
per-row check available, since the reconciliation identity only constrains
column sums. Recomputing letality and comparing it to the printed value would
have flagged sitrep 080 immediately, and costs nothing. I would extract it as a
check and still refuse to use it as data.

## The port

The seam is narrower than the handoff states, in a way that matters.

**What the modelling layer reads: seven files, about 1.5 KB in total.**
`data/build/streams/{cases,deaths,community_deaths}_{ituri,nord_kivu}.tsv` and
`uganda_exports.tsv`. Two-column TSVs, `time` plus one count column, 2–13 rows
each. That is the entire interface, confirmed three ways: the rule inputs in
`workflow/model.smk`, the `[data.observations]` paths in `models/fit_2p_*.toml`,
and the `--data` arguments `scripts/camdl_fit.py` passes to `camdl pfilter`.

`zone_panel.csv` and the reconciliation CSVs, which the handoff names as part of
the release artefact, are **not** read by the modelling side. They should still
ship — they are the evidence the release is auditable — but nobody should
believe a fit breaks without them. It will not. It will fit happily against
unaudited streams, which is precisely the failure the release gate exists to
prevent, and the gate is therefore doing real work rather than ceremonial work.

**What comes here.** `workflow/data.smk` (21 rules, none model-touching), all
eight parsers, all four `build_*` stream scripts, `check_carried_forward.py`,
`check_upstream.py`, the two `fetch_sitrep_*.py` scripts, the three data figure
scripts, the whole of `scripts/lib/`, all of `tests/`, all of `data/raw/`,
`analysis/data.qmd` and `analysis/_guard.py`, and the six hand-authored
registers.

**What stays.** `workflow/model.smk`, `models/`, `scripts/camdl_fit.py`,
`compare_fits.py`, `plot_posterior_predictive.py`, `plot_latent_states.py`,
`project_scenarios.py`, `compare_to_epiforecasts.py`, `warm_start.py`, and the
three overnight driver shell scripts.

**What should be dropped rather than moved.** Eleven scripts have zero call
sites across `workflow/`, `Makefile`, `scripts/`, `analysis/`, `tests/` and
`models/`: `build_sitrep_typology.py`, `plot_sitrep_typology.py`,
`plot_epidemic_curve.py`, `plot_zone_deaths.py`, `parse_care_table.py`,
`parse_alerts_table.py`, `plot_observation_streams.py`, `publish_artifact.sh`,
and the old-trunk chain `parse_tables.py` → `build_series.py` →
`clean_zones.py`. The last three are superseded by the 2026-08-15 rebuild that
made our own parse the trunk instead of the INRB extraction. Note that dropping
`parse_care_table.py` takes `lib/indicator_table.py` with it — it is that
module's only importer, and `data/README.md`'s claim that row reading is shared
with `parse_indicator_tables.py` is stale.

`analysis/eda.qmd` is also dead and should not be ported: no rule renders it, it
reads two artefacts that no longer exist, it bypasses `_guard.py` entirely with
its own `load()`, and it is built on the INRB feed as trunk, which `data.qmd`
explicitly repudiates. Its statistical content — growth rates, doubling times,
the community-death-fraction analysis — has no home in the descriptive data
document and would need a new one.

**Four scripts are unwired but must come anyway**, because they produce
committed `data/raw/` inputs that the DAG depends on and that nothing else can
regenerate: `fetch_shapes.py` (the geojson, the alias table, and the province
list), `fetch_connectivity.py` (the population denominators), `fetch_inrb.py`,
`fetch_vintages.py`.

## Defects to fix during the move, not after

- `workflow/report.smk` does not declare
  `data/build/series/indicator_tables.csv` as an input, although
  `analysis/data.qmd:137` reads it. The guard passes because it _is_ a declared
  output of `data.smk`, so nothing fails — the document simply will not
  re-render when that artefact changes, which is the exact failure the explicit
  input list exists to prevent.
- `analysis/_guard.py`'s `source()` hardcodes a tab separator and is passed a
  `.csv` at `data.qmd:988`. It parses to a single column and the row count that
  depends on it is right by luck. `load()` infers the separator from the suffix;
  `source()` should too.
- `_guard.py` never checks snakemake's return code. If the DAG fails to build,
  the declared-outputs set comes back empty and every guarded call fails with
  "no rule declares it" rather than "snakemake could not build the DAG".
- `_guard.py`'s `WORKFLOWS` constant names `workflow/model.smk`, which is the
  only remaining data-to-model coupling. It degrades gracefully when the file is
  absent, so the split is safe, but the constant should become configuration
  rather than be silently truncated. This module is close to being worth
  extracting as a small standalone package; it knows about Snakemake and polars
  and nothing about Ebola, and the two failures it prevents occur in every
  analysis repository.
- Three files in `models/` point at `../data/build/streams-full/`, which no rule
  anywhere produces. Decide on them; do not port the breakage silently.
- `config/data.yaml` declares `data/raw/mirror` where the directory on disk is
  `data/raw/inrb_extraction`. It was renamed by hand and neither the config nor
  the 31 affected `PROVENANCE.tsv` rows were updated. Re-running `fetch_inrb.py`
  today would populate a second directory beside the first.

## Two open decisions

**The release artefact has no mechanism.** `data/build/` is gitignored, so the
thing the handoff proposes to tag does not exist in version control. Tagging a
data release needs a tracked release directory, git-lfs, or an out-of-band
artefact such as a GitHub release asset. This is the one genuinely unresolved
piece of the split plan and it should be settled before anything moves, because
it determines whether `data/build/` stays ignored.

**`archive/` is 2.1 GB on disk and 434 tracked files** — 48% of all tracked
files in the source repo and the dominant contributor to its 91 MB pack. It also
holds the only copy of `archive/data_old.smk`, which `data.smk` names as the
reference for the rebuild and which is the record of which rules deliberately
did _not_ come across. It should not be copied wholesale into a fresh repo.
Suggest keeping `data_old.smk` alone, in `docs/dev/`, and leaving the rest
behind in the modelling repo's history.

## Recommended sequence

1. Agree this proposal, and settle the release-artefact mechanism.
2. Port the layers that are not in question first: `data/raw/`, the registers,
   `scripts/lib/`, `tests/`, the fetch and check scripts, `workflow/data.smk`,
   `analysis/`. Get `make check` and `make build` green here against the
   existing parsers, unchanged. This is a move, and it should be provably a move
   — same inputs, byte-identical outputs.
3. Only then, with a green build and 41 passing tests as the reference, write
   the geometric reader for Table 2 and diff its output against
   `sitrep_table2.csv` row by row. The identity checks and the exception
   register are the acceptance criteria, and they already exist. If the
   geometric reader reproduces the current panel and empties some of the
   exception register, that is the result; if it does not, we have lost nothing
   and learned where the geometry is not enough.
4. Fold the incidental duplication into a shared substrate afterwards, when
   there is a second geometric parser to share it _with_ — not before, or the
   substrate will be shaped by the parsers we are trying to replace.

Step 3 before step 2 would be the mistake. The current parsers, whatever their
shape, encode 60 commits of hard-won knowledge about these documents, and the
only safe way to replace them is against a reference build that already passes.

## The structure tree, and a validation opportunity

I checked whether the tagged reports carry real table markup rather than merely
being tagged. They do. Sitrep 080's structure tree declares 13 `/Table`
elements, 163 `/TR` rows, 188 `/TH` header cells and 782 `/TD` data cells;
sitrep 060 declares 20 tables and 654 data cells. This is the document author's
own statement of which cell belongs to which row and column — stronger evidence
than either a character grid or an inference from border rectangles.

Two things stop it being the primary route.

It covers 67 of 82 reports. The other 15 have no structure tree at all — the
macOS Preview re-saves strip it, so sitrep 021 is untagged while its neighbours
are not. A route that fails on 15 reports needs the drawn-rule route as a
fallback anyway, and two routes are worse than one unless the second earns its
place.

And the text is not directly attached. A `/TD` node's `/K` entry points at a
marked-content identifier, not at a string; recovering the cell's text means
mapping those identifiers back through the page content stream's `BDC`/`EMC`
markers. No mainstream Python library does this out of the box. It is a day of
work, not twenty minutes.

So the recommendation stands: read the drawn rules, which work today, with
`pdfplumber`, on all 82 reports.

But the structure tree is worth building later for a different purpose. The
project's own provenance rule is that two extractions of one document are not
independent sources — agreement between them is evidence about transcription,
not about the measurement. That rule bites on the current cross-validation plan,
where our `pdftotext` extraction is compared against INRB's extraction of the
same PDFs. The structure tree is the rare case that escapes it: the author's
declared cell structure and an inference from drawn borders are genuinely
different claims about the document, and where they disagree, one of them is
wrong in a way neither can hide. That is a stronger check than anything
currently in the pipeline, and it would apply to 67 of 82 reports.

## What I have not checked

- Whether the drawn-rule grid yields a correct table on all 82 reports. The
  rules are _present_ on every report I sampled across all five producers,
  including the `ilovepdf` re-encodes and the macOS Preview re-saves, and I
  verified extraction against the rendered page on sitrep 080 and sitrep 005.
  That is four reports read closely, not a corpus run.
- Table _selection_ — finding Table 2 among the thirteen tables on a page — is
  the one part of the current parser the geometry does not obviously replace. I
  showed that header cells extract cleanly, which suggests keying on column
  names, but I did not build it.
- The eight reports that print no zone data in any form. I took the handoff's
  word that this is a source fact.
