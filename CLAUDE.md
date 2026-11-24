# Working in ebola-bdbv-data

Read `README.md`, `docs/extraction.md` and `docs/validation.md` first: they
say how the pipeline reads a page and what each gate means.

## A break in extraction is ours to repair, and repairing it is part of the pipeline

The INSP situation reports change their wording, layout and file names without
notice, and every change can turn a reader that worked yesterday into one that
reads nothing, or reads the wrong number, while every gate still passes. So:

- **Treat lost coverage as a break, not as data the source stopped
  publishing.** When a series thins out (refusals rise in a `*_status.csv`, a
  province or a day stops appearing, a weekly total falls far below its usual
  level), open the newest PDFs before concluding anything. Usually the numbers
  are still printed and the wording changed.
- **Repair it with a better extractor, and backfill.** The raw PDFs are all in
  `data/raw/sitrep_pdfs/`, so every released value can be re-read. Fix the
  reader or write a new one, rebuild, and let the daily release revise the
  affected rows. Do not leave a gap in the data because the old reader refused.
- **Look for a second printing of the same number.** The reports often state
  one quantity twice: a front-page sentence and a section paragraph, a total
  and its breakdown, a count and its printed percentage. A sentence whose shape
  stays fixed is the better extractor, and the two printings check each other.
  Make that check a test or a gate, so that the next change in wording fails
  loudly instead of silently thinning the data.
- **Never guess a number the page does not print.** A repair widens what is
  read correctly; it does not fill holes with estimates. A refusal costs
  coverage, and a wrong reading costs correctness, which is worse.
- **Say what changed for anyone using the data.** A repair that revises
  released rows goes in `CHANGELOG.md` with the reports and the size of the
  change. If the source itself changed what a number means (for example, a
  sample count that starts including repeat samples), record that as a
  finding: in the stream's `interpretation` in `registers/stream_families.tsv`
  and in the release notes.

## Standing workflow

Fix pull requests that build cleanly (`make streams` passes and `make verdict`
reports GO) are merged without waiting, then `main` is checked out and the
daily update is run so the released data catches up. Force-pushes, history
rewrites and deleting release tags always need explicit approval.
