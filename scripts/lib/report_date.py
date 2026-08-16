"""The date a situation report's figures describe, read from the page.

THE DATA DATE IS A FACT PRINTED ON THE FRONT PAGE, and it was being taken from
the PDF's filename instead. INSP names its uploads inconsistently -- for six
reports the filename carries the PUBLICATION date, and for one it carries
neither date the report prints. The consequences were not subtle:

  * six reports were dated one day wrong, among them sitreps 16, 17, 22 and 23,
    which sit in the outbreak's first three weeks -- the window the growth rate
    is estimated from;
  * three data dates appeared to carry TWO reports each, which they do not.
    Under the printed dates every one of the 72 reports has a distinct data
    date. The apparent duplicates were 19/20, 23/24 and 50/51, each of which is
    two CONSECUTIVE DAYS;
  * and because the panel resolved an apparent duplicate by keeping the higher
    report number, sitreps 19, 23 and 50 were deleted outright -- three whole
    days of the series, removed to fix a collision that did not exist.

`registers/sitrep_number_overrides.tsv` already states the rule in its own header
-- "the filename dates are misleading and must NOT be parsed as data dates" --
but it was applied only where the filename had no parseable date at all. Where
one was present it was trusted.

THE REPORT DATE AND THE PUBLICATION DATE ARE BOTH KEPT. They differ by one to
two days and each answers a different question: the first dates the OBSERVATION,
the second dates the availability of it. A reporting-delay analysis needs both,
and conflating them shifts a whole series.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

# The reports spell the month in French, with inconsistent capitalisation and
# accents ("31 mai 2026", "01 Juin 2026", "03 juillet 2026").
MONTHS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}

_DATE = r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\.?\s+(\d{4})"
RAPPORTAGE = re.compile(rf"date\s+de\s+rapportage\s*:?\s*{_DATE}", re.I)
PUBLICATION = re.compile(rf"date\s+de\s+publication\s*:?\s*{_DATE}", re.I)


def _parse(m: re.Match | None) -> dt.date | None:
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower().strip("."))
    if month is None:
        return None
    try:
        return dt.date(int(m.group(3)), month, int(m.group(1)))
    except ValueError:
        return None


def printed_dates(text: str) -> tuple[dt.date | None, dt.date | None]:
    """(date de rapportage, date de publication) as the front page prints them.

    The text is whitespace-collapsed first: the front page is a table, so
    `pdftotext -layout` separates the label from its value by a run of spaces
    and sometimes wraps between them.
    """
    flat = " ".join(text.split())
    return _parse(RAPPORTAGE.search(flat)), _parse(PUBLICATION.search(flat))


FILENAME = re.compile(r"sitrep_(\d+)_(\d{4}-\d{2}-\d{2})")


def report_key(pdf: Path, text: str | None = None) -> tuple[int, str]:
    """(report number, data date) for one PDF.

    The NUMBER comes from the filename, which is derived from the committed
    index and is checked against it by the fetch rule. The DATE comes from the
    page, because that is where the source states it.

    A report with no readable `Date de rapportage` is a hard failure rather than
    a fall back to the filename. Falling back is what produced the defect this
    module exists to fix: the filename is right most of the time, so a silent
    fallback is invisible exactly when it is wrong.
    """
    m = FILENAME.search(pdf.stem)
    if not m:
        raise ValueError(f"{pdf.name} does not carry a report number")
    if text is None:
        text = subprocess.run(["pdftotext", "-q", "-layout", str(pdf), "-"],
                              capture_output=True, text=True).stdout
    rapportage, _ = printed_dates(text)
    if rapportage is None:
        sys.exit(
            f"{pdf.name} prints no readable `Date de rapportage`. The data date "
            f"is a fact on the page; the filename is not a substitute for it "
            f"(it carries the PUBLICATION date on six reports). Read the front "
            f"page and extend `report_date.MONTHS` or the pattern.")
    return int(m.group(1)), rapportage.isoformat()
