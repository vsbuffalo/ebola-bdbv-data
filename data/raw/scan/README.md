# The epiforecasts scan, pinned

`insp_sitrep_scanned.csv` is a committed copy of `data/insp_sitrep_scanned.csv`
from [epiforecasts/BVDOutbreakSize](https://github.com/epiforecasts/BVDOutbreakSize)
— national headline values read from the INSP situation-report PDFs, with a
notes column recording revisions, misprints and which of two printed numbers
the scan chose.

It is a **check, never an input**: `make compare` sets our extraction against
it, and nothing in `make build` or `make streams` reads it. The copy is
committed so the comparison is reproducible from this repository alone.

- Pinned commit: the `BVDOutbreakSize` row of `external.lock`
- SHA-256 (first 16): `fb9cc78ae1882770`
- Rows: 135 + header (through sitrep 149)

`make scan-refresh` downloads the file at exactly the pinned commit, and
`make scan-update` moves the pin to their current head first. Commit the diff:
it is the record of what their scan changed.
