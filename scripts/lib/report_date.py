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

ONE REPORT IS FILED AGAINST ITS PRINTED DATE, and only because two reports
print the same one. SitRep 004 and SitRep 005 both print `Date de rapportage:
19 mai 2026` and both print `Date de publication: 20 mai 2026`, while carrying
different cumulative counts (33 and 51). Under the rule above they land on one
day and the panel carries two national cumulatives for it. The adjudication --
which day each of the first four reports occupies, and why no other assignment
closes -- is written out in `registers/external_sitreps.tsv`, and this module
applies it from there. It is not a fallback to the filename and not a rule: it
is one document, named, hash-verified, with its printed date recorded beside
the filed one so a later reader can overturn the judgement on the same
evidence.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: scripts/lib/report_date.py -> parents[2] is the repo root. Derived from this
#: file's own location, never from the working directory: a register found only
#: when the script runs from the repo root is a register that silently stops
#: applying, which is the failure mode `load_rejected_routes` documents.
REGISTERS = Path(__file__).resolve().parents[2] / "registers"

# The reports spell the month in French, with inconsistent capitalisation and
# accents ("31 mai 2026", "01 Juin 2026", "03 juillet 2026") -- and the
# standard abbreviations, against the day the source starts using them:
# sitrep 048 already prints the bare "1 juillet 2026", so "1er" and "sept."
# are one typesetting decision away, and either would have stopped the whole
# build (a failure here is total, deliberately).
MONTHS = {
    "janvier": 1, "janv": 1, "fevrier": 2, "février": 2, "fevr": 2, "févr": 2,
    "mars": 3, "avril": 4, "avr": 4, "mai": 5, "juin": 6, "juillet": 7,
    "juil": 7, "aout": 8, "août": 8, "septembre": 9, "sept": 9,
    "octobre": 10, "oct": 10, "novembre": 11, "nov": 11,
    "decembre": 12, "décembre": 12, "dec": 12, "déc": 12,
}

# `1er juin` is standard French for the first of the month.
_DATE = r"(\d{1,2})(?:er)?\s+([A-Za-zÀ-ÿ]+)\.?\s+(\d{4})"
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


@dataclass(frozen=True)
class ExternalReport:
    """One row of `registers/external_sitreps.tsv`.

    A report INSP does not serve, held from a secondary archive, whose PDF is
    committed because nothing can fetch it again. `data_date` is the day this
    project files it under and `printed_data_date` is what its front page
    prints; they differ on exactly one report and the register says why.
    """

    sitrep: int
    data_date: str
    printed_data_date: str
    filename: str
    sha256: str
    upstream_repo: str
    upstream_path: str
    upstream_commit: str
    retrieved: str
    note: str


REQUIRED_FIELDS = ("sitrep", "data_date", "printed_data_date", "filename",
                   "sha256", "upstream_repo", "upstream_path",
                   "upstream_commit", "retrieved", "note")


def load_external_sitreps(
        path: Path | None = None) -> dict[str, ExternalReport]:
    """The register, keyed on ARCHIVE FILENAME.

    Keyed on the name rather than the hash so the lookup costs nothing on the
    ninety-one reports this register says nothing about; the hash is the
    identity and is checked in `verify_external`, on the three it names.

    A register that cannot be read stops the caller. Reading nothing quietly
    would file sitrep 004 under its printed date, collide it with 005, and
    publish two national cumulatives for 19 May with no message anywhere.
    """
    path = path or (REGISTERS / "external_sitreps.tsv")
    if not path.exists():
        sys.exit(f"register not found: {path} -- three reports' data dates and "
                 "the provenance of their committed PDFs live there, and "
                 "applying nothing silently re-dates sitrep 004 onto 005")
    out: dict[str, ExternalReport] = {}
    with path.open() as fh:
        rows = [ln for ln in fh if not ln.startswith("#")]
    for e in csv.DictReader(rows, delimiter="\t"):
        missing = [f for f in REQUIRED_FIELDS if not (e.get(f) or "").strip()]
        if missing:
            sys.exit(f"{path}: row for sitrep {e.get('sitrep')!r} leaves "
                     f"{', '.join(missing)} blank. Every column of this "
                     "register is load-bearing: without provenance the row "
                     "cannot be re-examined, and these files have no upstream "
                     "we control.")
        r = ExternalReport(
            sitrep=int(e["sitrep"]), data_date=e["data_date"],
            printed_data_date=e["printed_data_date"], filename=e["filename"],
            sha256=e["sha256"], upstream_repo=e["upstream_repo"],
            upstream_path=e["upstream_path"],
            upstream_commit=e["upstream_commit"], retrieved=e["retrieved"],
            note=e["note"])
        expect = f"sitrep_{r.sitrep:03d}_{r.data_date}.pdf"
        # THE FILENAME IS DERIVED FROM THE ADJUDICATION, so a row whose name
        # does not follow from its own number and date is a row where one of
        # the three was edited and the others were not -- and the archive
        # would then be named for one date while the register asserted
        # another.
        if r.filename != expect:
            sys.exit(f"{path}: sitrep {r.sitrep} is filed as {r.data_date} but "
                     f"names the file {r.filename}; expected {expect}")
        out[r.filename] = r
    return out


@lru_cache(maxsize=1)
def _external() -> dict[str, ExternalReport]:
    return load_external_sitreps()


def verify_external(pdf: Path, reg: ExternalReport) -> None:
    """The committed bytes are the ones the register was written about.

    Hash-verified like every register, and for a sharper reason than the
    others: these three PDFs have no upstream this project can re-fetch from,
    so the committed bytes ARE the source. A mismatch is not a stale judgement
    to refresh, it is the only copy having changed.
    """
    got = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if got != reg.sha256:
        sys.exit(
            f"EXTERNAL REPORT DOES NOT MATCH ITS REGISTER: {pdf.name}\n"
            f"  register: {reg.sha256}\n"
            f"  file:     {got}\n"
            f"INSP does not serve this report and `make fetch` cannot replace "
            f"it. The committed PDF is the source. Restore it from git "
            f"(`git checkout -- {pdf.as_posix()}`) rather than refreshing the "
            f"hash -- and if the working copy is a symlink into a shared "
            f"archive, that is the cause: these three must be real files.")


def report_key(pdf: Path, text: str | None = None) -> tuple[int, str]:
    """(report number, data date) for one PDF.

    The NUMBER comes from the filename, which is derived from the committed
    index and is checked against it by the fetch rule. The DATE comes from the
    page, because that is where the source states it.

    A report with no readable `Date de rapportage` is a hard failure rather than
    a fall back to the filename. Falling back is what produced the defect this
    module exists to fix: the filename is right most of the time, so a silent
    fallback is invisible exactly when it is wrong.

    THE ONE EXCEPTION IS DECLARED, HASH-VERIFIED AND EXACT. A report named in
    `registers/external_sitreps.tsv` is filed under the date that register
    states -- but only after the page is read as usual and found to print what
    the register says it prints. The register does not license "ignore this
    page"; it licenses one specific substitution, and stops the build the day
    the page stops supporting it.
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

    reg = _external().get(pdf.name)
    if reg is None:
        return int(m.group(1)), rapportage.isoformat()
    verify_external(pdf, reg)
    if rapportage.isoformat() != reg.printed_data_date:
        sys.exit(
            f"EXTERNAL REGISTER IS STALE for {pdf.name}: it records the front "
            f"page as printing `{reg.printed_data_date}`, and the page prints "
            f"`{rapportage.isoformat()}`. The judgement in "
            f"registers/external_sitreps.tsv was made about a different "
            f"document. Re-read the page and rewrite the row; do not refresh "
            f"the date.")
    if int(m.group(1)) != reg.sitrep:
        sys.exit(f"{pdf.name} carries report number {int(m.group(1))}, and "
                 f"registers/external_sitreps.tsv records {reg.sitrep}")
    return reg.sitrep, reg.data_date
