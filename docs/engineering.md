# How this was built

This dataset was written mostly by AI agents (Anthropic's Claude Code), with me
directing the engineering. I want to explain why I think that's a strength
rather than something to apologize for, and what we did to make the pipeline
trustworthy.

## Two months, one person, and a report every day

The outbreak's national public health institute (INSP) publishes a situation
report, or "sitrep", most days: a PDF of French tables giving cases and deaths
for every health zone (the DRC's district-level unit of health administration).
I started this pipeline on 16 August. If I'd worked alone, I could have done
one of two things in that time. I could have transcribed the tables by hand
(though realistically not all of them, since I was also building the models
these data feed, among other things), or written a quick scraper and
spot-checked it. Both are how most outbreak
datasets get made, and both fail quietly. A hand transcription has typos that
nobody checks for, and a scraper's errors look like perfectly good numbers.

What the agents changed is the cost of code. Writing a check, a test or a
second independent reader went from an afternoon to a few minutes. So I could
afford to do the things a careful data engineer would do with a team and a year:
check every number several ways, write a test for every bug, rebuild everything
from scratch on every release, and send independent reviewers after the
pipeline to try to break it. The agents also make mistakes, sometimes
confidently, so the whole design assumes that any single reading might be
wrong, and catches it before it ships.

My claim is narrow. With a few weeks and a deadline, a well-engineered
pipeline written by agents and driven by a human who's thinking hard about the
engineering beats what that same human could build alone. Not because the
agents are smarter, but because they make rigor cheap enough to afford.

## The reports check themselves

Situation reports are ledgers. Almost every table prints a total next to the
parts it sums: health-zone rows under a province row, province rows above a
national total. So a number is only accepted when the page's own arithmetic
balances around it. If the zones don't add up to the province total the same
page prints, the build fails, and someone has to look.

This catches the errors that matter most, the ones that look fine from the
outside. Early on, a table broken across two pages slid one column into its
neighbour, and the pipeline read the share of deaths found in the community as
1.00 where the page prints 0.55. That kind of error looks plausible, but it
doesn't balance.

Tables are also read from the cell borders Word draws in the PDF rather than
from a text dump of the page, so a long zone name stays on one row and a blank
cell stays blank instead of shifting its neighbours over. More in
[how the extraction works](https://github.com/vsbuffalo/ebola-bdbv-data/blob/main/docs/extraction.md).

## When in doubt, refuse

If a page can't be read cleanly, the pipeline says so and leaves a hole. It
doesn't guess. A missing number costs coverage, and downstream models can
handle a gap they know about. A wrong number costs correctness, and nobody
downstream can see it.

When a page genuinely disagrees with itself (and some do), I read the page and
record the judgment in a small register file, quoting what the page says. Each
entry is tied to the exact bytes of that PDF, so if INSP reissues the report,
the old judgment stops applying and it comes back for a fresh look.

## Everything is pinned and rebuilds exactly

Every PDF is pinned by its SHA-256 hash. Every output file is produced by a
named `make` step, never by hand. Rebuilding a release from its git tag gives
byte-identical files, and before each release is tagged, it's rebuilt from a
fresh clone to prove that. If a downstream model was fit to a release, you can
get exactly that data back.

## Checked against other people's readings, never built from them

Two other groups transcribe the same reports: INRB-UMIE, at the DRC's national
biomedical research institute, and the epiforecasts scan. I compare every
value against both and record every disagreement. Neither one is an input, so
an error in theirs can't flow into ours. When we disagree, I go back to the
page. Of the 23 health-zone days where INRB-UMIE's transcription and ours
differ, the page prints our number in all 23. One caveat: everyone is
reading the same PDFs, so agreement tells you the transcription is right, not
that the counts are.

## Trying to break it on purpose

Twice I sent teams of independent reviewer agents after the pipeline, each
with a different way it might fail and told to work from the PDFs rather than
our documentation. One reviewer re-implemented the whole time-series
construction from scratch and reproduced every stream file we had then, row
for row.
Another checked a random sample of 608 zone-table values against the printed
pages, and all 608 matched. Every bug these reviews found became a test pinned
to the report that exposed it. The suite now has over 400 tests.

## Every day, the same discipline

A scheduled job fetches each new report, rebuilds, and runs every check. If
everything passes, it tags a release on its own. If anything fails, it opens a
high-priority issue and stops. An agent then tries a fix, but in a sandbox
with no network access and no ability to push or release. It can only propose
a fix as a pull request, and a human decides whether to merge it.

## What this doesn't buy

None of this makes INSP's counts true. It makes reading errors loud. Cases go
unreported, reports get revised, and the source's own totals sometimes
disagree. Those problems are documented, not fixed, and the
[data contract](https://github.com/vsbuffalo/ebola-bdbv-data/blob/main/docs/data-contract.md)
and the [validation notes](https://github.com/vsbuffalo/ebola-bdbv-data/blob/main/docs/validation.md)
say what to watch out for before fitting anything.
