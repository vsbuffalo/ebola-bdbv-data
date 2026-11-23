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


# --- the series renamed at report 179 (`MVE` dropped from the filename) ---

def _entry(name: str, date: str = "2026-11-22T09:31:35") -> dict:
    return {"source_url": f"https://insp.cd/wp-content/uploads/2026/11/{name}",
            "date": date}


def test_the_n179_shape_is_admitted_with_its_number_and_date():
    from fetch_sitrep_index import parse_row
    r = parse_row(_entry("SitRep_N190_20-11-2026_corrige_VF-1.pdf"))
    assert r is not None
    assert (r["sitrep"], r["data_date"], r["status"]) == ("190", "2026-11-20", "final")


def test_another_disease_in_the_n179_shape_is_refused():
    from fetch_sitrep_index import parse_row
    assert parse_row(_entry("SitRep_N012_20-11-2026_cholera.pdf")) is None


def test_a_pdf_no_rule_explains_is_an_alarm_whatever_its_name():
    """The 179 rename hid behind a name the predicate refused and nothing
    flagged. Any refused PDF without a stated reason is now CHANGED."""
    from check_upstream import load_exclusions, unexplained_pdfs
    ex = load_exclusions()
    entries = [_entry("SitRep_Ebola_191_21-11-2026.pdf"),        # a rename
               _entry("Rapport_MVE-BDBV_191.pdf".replace("MVE", "Ebola")),
               _entry("Sitrep_MVE-Ituri_N°004-au-20-mai-2026.pdf"),  # `_EXCLUDE`
               _entry("Repartition_hebdomadaire_des_cas_deces_letalite_SE46_2026.pdf"),
               _entry("SitRep_N190_20-11-2026_corrige_VF-1.pdf")]   # accepted
    assert unexplained_pdfs(entries, ex) == ["SitRep_Ebola_191_21-11-2026.pdf",
                                             "Rapport_Ebola-BDBV_191.pdf"]


def test_every_exclusion_row_matches_its_own_example_and_accepts_no_report():
    """A row that matches no example explains nothing, and one that matched a
    report we fetch would be the silent refusal this register exists to end."""
    from check_upstream import load_exclusions
    rows = list(csv.DictReader(
        (ln for ln in (ROOT / "data/raw/insp_sitrep_index.tsv").open()
         if not ln.startswith("#")), delimiter="\t"))
    for x in load_exclusions():
        assert x.pattern.search(x.example)
        hits = [r["filename"] for r in rows if x.pattern.search(r["filename"])]
        assert not hits, (x.series, hits)


def test_a_comparison_source_two_days_ahead_is_a_lead_and_one_day_is_not():
    """Replays 12 November: INRB-UMIE through the 11th, we through the 8th."""
    from check_upstream import comparison_leads
    leads = comparison_leads("2026-11-08", {"INRB": "2026-11-11",
                                            "scan": "2026-11-09",
                                            "down": None})
    assert leads == [("INRB", "2026-11-11", 3)]
