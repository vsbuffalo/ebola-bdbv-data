# The epiforecasts scan, pinned

`insp_sitrep_scanned.csv` is a committed copy of
`epiforecast-repro/raw/insp_sitrep_scanned.csv` — national headline values
read from the INSP situation-report PDFs by an LLM agent and re-scanned by a
second, with a notes column recording revisions and misprints.

It is a **check, never a trunk**: the comparison in `make compare` sets our
extraction against it, and this copy exists so that comparison is reproducible
from this repository alone. Before it was committed, the comparison read a
sibling checkout by relative path — a file a fresh clone could not obtain and
whose silent change would have moved our headline numbers.

- Source file: `../epiforecast-repro/raw/insp_sitrep_scanned.csv` (local
  checkout of the epiforecasts reproduction; not a git remote)
- Copied: 2026-08-17
- SHA-256 (first 16): `8082de3df68077e2`
- Rows: 72 + header (through sitrep 093)

To refresh against a newer sibling checkout: `make scan-refresh`, then commit
the diff — the diff **is** the record of what their scan changed.
