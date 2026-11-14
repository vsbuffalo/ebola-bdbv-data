"""The release verdict: what it must refuse, on builds made up for the purpose.

`build_verdict.py` reads files other steps wrote and computes nothing, so the
ways it can be wrong are the ways it can read nothing: a file that is not
there, or a column under another name. Each test is one of those.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_verdict as V                                          # noqa: E402


@pytest.fixture
def build(tmp_path, monkeypatch):
    """A minimal build that passes every gate, under a scratch root."""
    series = tmp_path / "data/build/series"
    streams = tmp_path / "data/build/streams"
    series.mkdir(parents=True)
    streams.mkdir(parents=True)
    (series / "zone_table_status.csv").write_text(
        "sitrep,date,status,identity\n5,2026-05-19,ok,ok\n")
    (series / "zone_table.csv").write_text(
        "sitrep,date,level,cum_cases\n5,2026-05-19,zone,51\n")
    (series / "province_series_reconciliation.csv").write_text(
        "sitrep,date,province,reconciled\n5,2026-05-19,Ituri,ok\n")
    (streams / "cases_daily_national.tsv").write_text(
        "window_start\twindow_stop\tcases_national\n"
        "2026-05-19\t2026-05-20\t18\n")
    (streams / "meta.json").write_text('{"reconciliation": {}}')
    monkeypatch.setattr(V, "ROOT", tmp_path)
    monkeypatch.setattr(V, "SERIES", series)
    monkeypatch.setattr(V, "STREAMS", streams)
    repo = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(V, "REQUIRED", tuple(
        (tmp_path / p.relative_to(repo), target) for p, target in V.REQUIRED))
    return series, streams


def test_a_complete_consistent_build_is_go(build):
    blocking, _, _, facts = V.collect()
    assert blocking == []
    assert facts["province reconciliations"] == "1"


def test_an_empty_build_directory_is_not_go(build):
    """Every check skips a file it cannot find, so a build directory holding
    nothing used to sort nothing into BLOCKING and print GO."""
    series, streams = build
    for f in [*series.iterdir(), *streams.iterdir()]:
        f.unlink()
    blocking, _, _, _ = V.collect()
    assert len(blocking) == len(V.REQUIRED)
    assert all("has not been built" in b for b in blocking)


def test_a_missing_reconciliation_file_blocks(build):
    """The file `aggregate_provinces.py` writes last. A run of that step that
    stops before writing leaves the rest of the build looking complete."""
    series, _ = build
    (series / "province_series_reconciliation.csv").unlink()
    blocking, _, _, _ = V.collect()
    assert len(blocking) == 1
    assert "province_series_reconciliation.csv" in blocking[0]


def test_a_province_total_that_fails_blocks(build):
    """The verdict read a `status` column for the value `disagrees`; the file
    has a `reconciled` column whose value is `fails`, so the check could not
    fire on any input."""
    series, _ = build
    (series / "province_series_reconciliation.csv").write_text(
        "sitrep,date,province,reconciled\n"
        "5,2026-05-19,Ituri,ok\n"
        "5,2026-05-19,Nord-Kivu,fails\n"
        "5,2026-05-19,Tshopo,verified_exception\n"
        "5,2026-05-19,Sud-Kivu,not_checkable\n")
    blocking, _, _, _ = V.collect()
    assert len(blocking) == 1
    assert blocking[0].startswith("1 province total(s) disagree")


def test_a_reconciliation_file_without_its_column_blocks(build):
    """A renamed column must not turn the check back into one that reads
    nothing and passes."""
    series, _ = build
    (series / "province_series_reconciliation.csv").write_text(
        "sitrep,date,province,status\n5,2026-05-19,Ituri,ok\n")
    blocking, _, _, _ = V.collect()
    assert len(blocking) == 1
    assert "no `reconciled` column" in blocking[0]


def test_the_values_the_verdict_reads_are_the_ones_the_aggregation_writes():
    """The two scripts share the column name and the failing value only by
    spelling them the same; this is the pin between them."""
    import aggregate_provinces as A
    import polars as pl
    panel = pl.DataFrame({
        "sitrep": [5, 5], "date": ["2026-05-19", "2026-05-19"],
        "zone_reported": ["Ituri", "Bunia"], "level": ["province", "zone"],
        "province": ["Ituri", "Ituri"],
        "cum_cases": [10, 7], "cum_deaths": [2, 2]})
    _, check = A.aggregate(panel)
    assert check["reconciled"].to_list() == ["fails"]
