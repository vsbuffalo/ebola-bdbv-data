"""The export tables: cases counted outside the DRC.

Each test pins a property a consumer's likelihood depends on and that a
plausible-looking edit could break without any total moving.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_export_streams as X  # noqa: E402

EXPORTS = ROOT / "data" / "raw" / "exports"
STREAMS = ROOT / "data" / "build" / "streams"


def _tables():
    return (X.read_tsv(EXPORTS / "sources.tsv"), X.read_tsv(EXPORTS / "counts.tsv"),
            X.read_tsv(EXPORTS / "cases.tsv"))


def test_the_committed_tables_validate():
    X.validate(*_tables())


def test_imported_and_infected_in_the_drc_are_kept_apart():
    """Nigeria's case is imported into Nigeria by WHO's headline while its
    source of infection is under investigation. Collapsing the two would make
    it observe DRC prevalence, which no source says it does."""
    _, counts, cases = _tables()
    ng = next(c for c in cases if c["case_id"] == "NG-01")
    assert ng["class"] == "imported"
    assert ng["infection_country"] == "under_investigation"
    afro = next(c for c in counts if c["country"] == "Nigeria"
                and c["source_id"] == "afro_nigeria")
    assert afro["imported"] == "1" and afro["imported_from_drc"] == ""
    assert afro["under_investigation"] == "1"


def test_medical_evacuations_are_tallied_in_the_drc_and_get_no_stream(tmp_path):
    """WHO: «will not be reported as a local case of BVD in the Netherlands»."""
    _, _, cases = _tables()
    evac = [c for c in cases if c["mechanism"] == "medical_evacuation"]
    assert {c["case_id"] for c in evac} == {"DE-01", "DE-02", "NL-01"}
    assert {c["tally_country"] for c in evac} == {"DRC"}
    sys.argv = ["x", "--exports", str(EXPORTS), "--series-dir", str(tmp_path / "s"),
                "--streams-dir", str(tmp_path / "t")]
    X.main()
    names = {p.name for p in (tmp_path / "t").glob("exports_*.tsv")}
    assert names == {"exports_france.tsv", "exports_kenya.tsv",
                     "exports_nigeria.tsv", "exports_uganda.tsv"}


def test_a_printed_total_the_cases_do_not_reach_is_a_gap_not_an_error():
    """Kenya counts 8 on 18 October and the primary sources describe 3."""
    _, counts, cases = _tables()
    gaps = {(r["country"], r["as_of"], r["quantity"]): r["gap"]
            for r in X.reconcile(counts, cases)}
    assert gaps[("Kenya", "2026-10-18", "confirmed")] == 5
    assert gaps[("Kenya", "2026-10-16", "confirmed")] == 0


def test_a_total_from_a_check_source_is_refused():
    sources, counts, cases = _tables()
    bad = [dict(c) for c in counts]
    bad[0]["source_id"] = "ng_von_20oct"     # a secondary report
    with pytest.raises(SystemExit, match="is a check"):
        X.validate(sources, bad, cases)


def test_uganda_pins_only_what_the_sources_print():
    """No row on 28 May or 21 June, the two moments uganda_exports pins and no
    primary source prints (vsbuffalo/ebola-bdbv-data#1)."""
    _, counts, _ = _tables()
    ug = {c["as_of"]: c["imported"] for c in counts if c["country"] == "Uganda"}
    assert "2026-05-28" not in ug and "2026-06-21" not in ug
    assert ug["2026-05-20"] == "2" and ug["2026-06-06"] == "14"
    assert ug["2026-07-02"] == "15"


@pytest.mark.skipif(not (EXPORTS / "snapshots").exists(),
                    reason="needs `make fetch-exports`")
def test_every_checkable_quote_is_on_its_page():
    import check_export_quotes as Q
    sys.argv = ["x", "--exports", str(EXPORTS)]
    Q.main()
