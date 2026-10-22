# The daily update failed a gate: find out why, and fix the reader if it is ours

You are working unattended in a checkout of ebola-bdbv-data, on the branch
`{branch}`, which already holds today's fetch (new situation reports
{new_reports}). The daily runner stopped because a gate failed:

- failing step: `{step}`
- tracking issue: #{issue}

The step's output, last lines:

```
{log_tail}
```

The release verdict (`make verdict`), if it ran:

```
{verdict}
```

Read `README.md`, `docs/extraction.md` and `docs/validation.md` before you
change anything; they say how this pipeline reads a page and what each gate
means.

## What to do

1. **Find the page.** Every failure here traces to a specific report and usually
   a specific line on it. Open the PDF in `data/raw/sitrep_pdfs/` and quote,
   verbatim, the text the failure is about.
2. **Decide whose defect it is.** Either the reader misreads a page it should
   read (ours: fix the reader), or the page itself is inconsistent or worded in
   a way no rule should guess at (the source's: record it in the register the
   docs name for that case, quoting the page).
3. **Fix the smallest thing**, and add a test in `tests/` pinned to the sitrep
   that exposed it, in the style of the tests already there.
4. **Re-run the failing step**, then `make test` and `make verdict`, and confirm
   they pass.
5. **Commit** on this branch with a message in the repository's style
   (`area: what changed and why`), then write `{pr_body}`: what failed, the page
   quote, whose defect it is, what you changed, and the gate results. The runner
   pushes the branch and opens the pull request; you do not.

## What you must not do

- Do not add a row to `registers/reconciliation_exceptions.tsv`, or any other
  register that excuses a residual, without quoting the page text that shows the
  source itself prints the inconsistency.
- Do not loosen, skip or delete an existing test or check to make a gate pass. A
  failing pinned value means either the reader changed or the page did: find
  which.
- Do not edit `registers/released_tags.tsv`, create tags, push, or touch `main`.
- Do not guess a number the page does not print. Refusing a reading costs
  coverage; a wrong reading costs correctness, and the second is worse.

## If you cannot fix it

Stop, and still write `{pr_body}`: say what you found, quote the page, and say
what decision a person needs to make. An honest "this needs a human" is a
complete result.
