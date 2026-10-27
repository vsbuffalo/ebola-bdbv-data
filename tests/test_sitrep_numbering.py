"""Report numbers are INSP's claim about a report, checked against its date.

Pinned to 2026-10-25/26: INSP uploaded the 23 October report as
`SITREP_MVEBDB_163_23_10_2026.pdf` (its front page says SitRep 162), then the
real 163 for 24 October. Counting numbers, the upstream check said CURRENT for
two days, and the index fetch would have kept the later 163 and dropped the
23 October report without a word.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_sitrep_index import numbering_conflicts, numbering_shifts  # noqa: E402


def row(num, date, name=""):
    return {"sitrep": str(num), "data_date": date, "filename": name}


AS_UPLOADED = [row(161, "2026-10-22"), row(163, "2026-10-23"),
               row(163, "2026-10-24"), row(164, "2026-10-25")]


def test_one_number_with_two_dates_is_a_conflict():
    assert numbering_conflicts(AS_UPLOADED) == {"163": ["2026-10-23", "2026-10-24"]}


def test_versions_of_one_report_share_a_date_and_do_not_conflict():
    assert numbering_conflicts([row(160, "2026-10-21"), row(160, "2026-10-21")]) == {}


def test_a_skipped_number_is_a_shift():
    """The state on 25 October, before the real 163 was uploaded: 161 then a
    '163' one day later. This is the notice that would have fired first."""
    assert numbering_shifts([row(161, "2026-10-22"), row(163, "2026-10-23")]) == [
        "sitrep 161 (2026-10-22) is followed by 163 (2026-10-23): "
        "2 number(s) for 1 day(s)"]


def test_resolved_numbering_has_no_shift():
    resolved = [row(161, "2026-10-22"), row(162, "2026-10-23"),
                row(163, "2026-10-24"), row(164, "2026-10-25")]
    assert numbering_conflicts(resolved) == {} and numbering_shifts(resolved) == []


def test_the_committed_index_with_its_overrides_is_consistent():
    """Every report so far, as the fetch resolves it: no number under two
    dates, and number and date advance together throughout."""
    ov = {}
    for line in (ROOT / "registers/sitrep_number_overrides.tsv").read_text().splitlines():
        if line.strip() and not line.startswith(("#", "filename\t")):
            fn, num, date = line.split("\t")
            ov[fn] = (num, date)
    with (ROOT / "data/raw/insp_sitrep_index.tsv").open() as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    for r in rows:
        if r["filename"] in ov:
            r["sitrep"], r["data_date"] = ov[r["filename"]]
    assert numbering_conflicts(rows) == {}
    assert numbering_shifts(rows) == []
