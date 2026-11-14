"""The text of a PDF as `pdftotext` renders it, or a stopped build.

Every prose route reads a report through `pdftotext`, and each used to run it
at its own call site and take `stdout` without looking at the exit status. A
run that fails -- a file poppler cannot open, a crash, a kill -- prints nothing
to stdout, and nothing is exactly what a report with no laboratory paragraph,
no care pillar or no burial sentence looks like. The extractors record that as
a report that said nothing, which is a legitimate status with its own row, so
a run that failed once would have been published as silence from the source.
(A file that fails every time was stopped, but by `report_date.report_key`,
whose message blames the page for printing no readable date.)

Reading through here turns that into an error naming the file. The flags are
the caller's, because the routes differ on purpose: the front page and the
sentences read on one line want `-layout`, and the two-column pillars want the
content-stream order `-layout` destroys.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class PdfTextError(RuntimeError):
    """`pdftotext` did not exit cleanly, so there is no text to read."""


def pdftotext(pdf: Path, *flags: str) -> str:
    """Stdout of `pdftotext -q <flags> <pdf> -`.

    Raises `PdfTextError` on a non-zero exit. An empty string is returned only
    when poppler ran cleanly and the document has no text layer.
    """
    r = subprocess.run(["pdftotext", "-q", *flags, str(pdf), "-"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        detail = r.stderr.strip() or "no message (it runs with -q)"
        raise PdfTextError(
            f"pdftotext exited {r.returncode} on {pdf}: {detail}. A failed "
            "run prints no text, and an extractor reading that would record "
            "the report as silent rather than unread.")
    return r.stdout
