"""Tests on the lines that actually broke the extraction.

Every case here is a real report and a real failure, named by the sitrep it came
from. That is deliberate: each of these behaviours was arrived at empirically,
several of them after a fix in one place silently broke another, and a test that
does not pin a specific document is not much protection against that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_zone_table as E                                    # noqa: E402
from lib.tablespec import (Role, ZONE_TABLE, EARLY_ZONE_TABLE,    # noqa: E402
                           classify, norm)

PDFS = ROOT / "data" / "raw" / "sitrep_pdfs"
needs_pdfs = pytest.mark.skipif(
    not PDFS.is_dir() or not any(PDFS.glob("*.pdf")),
    reason="the PDF archive is not present; run `make fetch`")


def pdf(n: int) -> Path:
    hits = sorted(PDFS.glob(f"sitrep_{n:03d}_*.pdf"))
    if not hits:
        pytest.skip(f"sitrep {n} is not in the archive")
    return hits[0]


# --------------------------------------------------------------------------
# Cell values
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cell, want", [
    ("1 653", 1653),                 # ASCII thousands separator
    ("1 653", 1653),            # no-break space
    ("1 653", 1653),            # narrow no-break space
    ("42", 42),
    ("0", 0),
    ("-2", -2),                      # a declared downward revision is data
    ("-2*", -2),                     # sitrep 073: marker after the value
    ("* 59", 59),                    # sitrep 088: marker BEFORE the value
    ("59 *", 59),
    ("ND", None), ("N/D", None), ("NA", None),
    ("—", None), ("–", None), ("-", None),
    ("*", None),                     # a lone marker is not a value
    ("", None), ("   ", None),
    ("31,5%", None),                 # a letality cell is not a count
    ("Bunia", None),
])
def test_to_int(cell, want):
    assert E.to_int(cell) == want


def test_negative_cell_is_kept_not_clipped():
    """Sitrep 073 prints Katwa's daily deaths as `-2*`.

    The footnote reads "Harmonisation de nombre de deces ... (moins 2 deces)" --
    the source declaring that it removed two deaths from that zone. A declared
    downward revision is data, and clipping it to zero would put our series
    permanently two deaths above the source's own correction.
    """
    assert E.to_int("-2*") == -2


# --------------------------------------------------------------------------
# Row levels
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name, want", [
    ("Bunia", "zone"),
    ("Ituri", "province"),
    ("ITURI", "province"),
    ("Nord-Kivu*", "province"),           # a marker is typography, not a name
    ("Haut-Uélé", "province"),
    ("Bas Uélé", "province"),             # printed with a space, not a hyphen
    ("Sous-total Ituri", "province"),     # a subtotal IS the province total
    ("Sous total", "province"),
    ("Total", "national"),
    ("TOTAL", "national"),
    ("Total général", "national"),
    ("Autres ZS (données non ventilées)", "unassigned"),
    ("Autres zones non encore identifiées", "unassigned"),
    ("A ventiler", "unassigned"),
    ("Non identifiées", "unassigned"),
])
def test_level_of(name, want):
    assert E.level_of(name) == want


@pytest.mark.parametrize("printed, want", [
    ("1- Bunia", "Bunia"),
    ("2- Rwampara", "Rwampara"),
    ("10- Mambasa", "Mambasa"),
    ("3. Nizi", "Nizi"),
    ("4) Aru", "Aru"),
    ("- Autres ZS", "Autres ZS"),
    ("Bunia", "Bunia"),
    ("Makiso- Kisangani", "Makiso- Kisangani"),   # not an ordinal
])
def test_strip_ordinal(printed, want):
    """Some reports number their zone rows; the number is not part of the name.

    Requiring a row name to begin with a letter discarded EVERY numbered zone
    row: sitrep 020 kept five rows out of twenty-eight and Ituri came up 265
    cases short.
    """
    assert E.strip_ordinal(printed) == want


def test_subtotal_is_province_not_zone():
    """Counting `Sous-total Ituri` as a zone double-counts the province.

    It showed up as a residual of exactly twice the printed total on seven
    consecutive reports -- the signature of summing a level together with its
    own subtotals.
    """
    assert E.level_of("Sous-total Ituri") == E.level_of("Ituri")


# --------------------------------------------------------------------------
# Repeated names
# --------------------------------------------------------------------------

def _row(name, level, cases, deaths):
    return {"zone_reported": name, "level": level,
            "cum_cases": cases, "cum_deaths": deaths}


def test_namesake_zone_is_demoted():
    """Sitrep 092: Tshopo is a province AND a health zone inside it."""
    rows = [_row("Tshopo", "province", 11, 6),
            _row("Kabondo", "zone", 3, 2),
            _row("Tshopo", "province", 1, 0)]
    out = E.demote_repeats(rows)
    assert [r["level"] for r in out] == ["province", "zone", "zone"]
    assert len(out) == 3, "a real place must not be dropped"


def test_repeated_header_is_dropped():
    """Sitrep 048: Word repeats the province row atop the continuation page.

    Same name AND same counts, so it is typography. Demoting it to a zone
    instead added Ituri's own total to its parts and doubled them.
    """
    rows = [_row("ITURI", "province", 1333, 380),
            _row("Bunia", "zone", 416, 103),
            _row("ITURI", "province", 1333, 380)]
    out = E.demote_repeats(rows)
    assert len(out) == 2
    assert [r["level"] for r in out] == ["province", "zone"]


# --------------------------------------------------------------------------
# Column classification
# --------------------------------------------------------------------------

class FakeTable:
    """Enough of a pdftable.Table for the classifier."""

    def __init__(self, rows, header_rows=1):
        self._rows = rows
        self._h = header_rows
        self.ncols = max(len(r) for r in rows)
        self.nrows = len(rows)

    def row(self, i):
        r = list(self._rows[i])
        return r + [""] * (self.ncols - len(r))

    def header_rows(self):
        return self._h


def test_classify_splits_labels_from_values():
    t = FakeTable([["Zone", "Cas", "Décès"],
                   ["Bunia", "80", "8"],
                   ["Aru", "2", "1"],
                   ["Kilo", "2", "0"]])
    labels, values = classify(t, start=1)
    assert labels == [0]
    assert values == [1, 2]


def test_classify_handles_two_label_columns():
    """The early layout prints `Provinces` and `Zones de santé` side by side."""
    t = FakeTable([["Provinces", "Zones", "Suspects", "Confirmés"],
                   ["", "Bunia", "90", "6"],
                   ["Ituri", "Aru", "4", "1"],
                   ["", "Kilo", "3", "0"]])
    labels, values = classify(t, start=1)
    assert labels == [0, 1]
    assert values == [2, 3]


def test_classify_ignores_a_leading_spacer_column():
    """Sitrep 090's table carries an empty leading column."""
    t = FakeTable([["", "Zone", "Cas", "Décès"],
                   ["", "Bunia", "80", "8"],
                   ["", "Aru", "2", "1"],
                   ["", "Kilo", "2", "0"]])
    labels, values = classify(t, start=1)
    assert values == [2, 3], "the value sequence must not shift"


def test_sentinels_never_make_a_column_a_label():
    """`ND` and an em-dash are neither a number nor text, for classification.

    A column carrying them is still a value column, so long as it carries
    enough real numbers to qualify. What must never happen is a sentinel
    counting as TEXT, because that would make the column a label and push every
    later column one place along.
    """
    t = FakeTable([["Zone", "Cas", "Décès"],
                   ["Bunia", "80", "—"],
                   ["Aru", "2", "ND"],
                   ["Kilo", "2", "—"],
                   ["Nizi", "3", "1"],
                   ["Lita", "4", "2"],
                   ["Gety", "5", "3"]])
    labels, values = classify(t, start=1)
    assert labels == [0], "only the name column is a label"
    assert values == [1, 2], "the sentinel-bearing column is still a value column"


# --------------------------------------------------------------------------
# Table identification
# --------------------------------------------------------------------------

def test_outcomes_table_is_not_the_cumulative_table():
    """Sitrep 083 prints a per-zone OUTCOMES table with the same vocabulary.

    Reading it as the cumulative table gave Bunia 35 cases against a printed 967.
    Only `Guéris` and `En hospitalisation` tell them apart.
    """
    outcomes = ["Zone de santé", "Cas confirmés", "Guéris",
                "En hospitalisation", "Décès"]
    assert not ZONE_TABLE.identifies(outcomes)


def test_zone_table_survives_title_bleed():
    """From sitrep 083 the table's title is laid across the heading row."""
    bled = ["Province / Zone de santé", "Cas et décès Cas (n)",
            "confirmés Nombre cumulatif Décès (n)", "par province Létalité"]
    assert ZONE_TABLE.identifies(bled)


@pytest.mark.xfail(reason="known gap: sitrep 091's heading names no case column",
                   strict=True)
def test_zone_table_recognised_without_a_case_heading():
    """Sitrep 091's heading reads `Nombre cumulatif | Décès` and nothing else.

    The word `cas` appears nowhere, so the spec does not recognise the table
    even though its grid reads perfectly. Dropping the case requirement is NOT
    the fix: `Létalité` was dropped for the same reason and that immediately
    let this spec swallow the early layout, writing suspected cases out as
    confirmed ones. Each relaxation of the vocabulary has to be paid for with a
    discriminator, and this one does not have one yet.

    Marked strict so that it fails loudly if it ever starts passing by
    accident -- which would mean the vocabulary had been loosened without one.
    """
    sparse = ["Province / Zone de santé", "Nombre cumulatif", "Décès",
              "Situation du jour", "(24h)"]
    assert ZONE_TABLE.identifies(sparse)


def test_cumulative_spec_refuses_the_early_layout():
    """The regression that dropping `Létalité` introduced, pinned.

    Sitrep 005's early table heads a zone column, a case count and a death
    count, so it satisfies everything this spec requires. It must still be
    refused, because its case column counts SUSPECTED cases and reading it here
    put 309 suspected cases into the confirmed series.
    """
    early = ["Provinces", "Zones de santé", "Nbre de cas suspects",
             "Nbre de décès suspects", "Nbre de cas Confirmés",
             "Nbre de contacts"]
    assert not ZONE_TABLE.identifies(early)
    assert EARLY_ZONE_TABLE.identifies(early)


def test_early_spec_refuses_the_daily_sibling():
    """The early reports print a DAILY table beside the cumulative one.

    Same vocabulary under `Nouveaux`. It is a flow where the other is a stock,
    and reading one as the other mixes an increment into a cumulative series.
    """
    daily = ["Provinces touchées", "Zones de santé", "Nouveaux cas confirmés",
             "Nouveaux décès confirmés", "Nouveaux cas probables",
             "Nouveaux cas suspects", "Nouveaux contacts listés",
             "Guéris du jour"]
    assert not EARLY_ZONE_TABLE.identifies(daily)
    assert not ZONE_TABLE.identifies(daily)


def test_early_and_late_specs_do_not_both_claim_one_table():
    late = ["Province / Zone de santé", "Cas (n)", "Décès (n)", "Létalité"]
    assert ZONE_TABLE.identifies(late)
    assert not EARLY_ZONE_TABLE.identifies(late)


def test_norm_folds_accents_and_case():
    assert norm("DÉCÈS") == norm("deces") == "deces"
    assert norm("Haut-Uélé") == "haut-uele"


# --------------------------------------------------------------------------
# End to end, against real documents
# --------------------------------------------------------------------------

@needs_pdfs
def test_sitrep_080_recovers_wrapped_zone_names():
    """`Boma-Mangbetu` and `Makiso-Kisangani` wrap onto three text lines each.

    In a text rendering the name lands on one line and the numbers on another,
    so neither row looks like a row; both were dropped whole by the parser this
    replaces, which was exactly that report's 16-case shortfall.
    """
    rows, status = E.extract(pdf(80))
    assert status == "ok"
    by = {norm(r["zone_reported"]).replace(" ", ""): r for r in rows}
    assert by["bomamangbetu"]["cum_cases"] == 13
    assert by["bomamangbetu"]["cum_deaths"] == 4
    assert by["makiso-kisangani"]["cum_cases"] == 3


@needs_pdfs
def test_sitrep_080_identity_closes():
    rows, _ = E.extract(pdf(80))
    assert E.reconcile(rows)["identity"] == "ok"


@needs_pdfs
def test_sitrep_088_a_ventiler_deaths_are_read():
    """The count is printed as `*` with the figure wrapped onto the next line."""
    rows, _ = E.extract(pdf(88))
    av = [r for r in rows if norm(r["zone_reported"]).startswith("a ventiler")]
    assert av, "the unallocated-deaths row must be found"
    assert av[0]["cum_deaths"] == 59


@needs_pdfs
def test_sitrep_005_reads_the_early_layout():
    """A different table entirely: suspected cases, and no letality column."""
    rows, status = E.extract(pdf(5))
    assert status == "ok"
    assert {r["table"] for r in rows} == {"zone_early"}
    bunia = next(r for r in rows if r["zone_reported"] == "Bunia")
    assert bunia["suspected"] == 90
    assert bunia["cum_cases"] == 6


@needs_pdfs
def test_mixed_layout_suspected_is_a_flow_not_the_stock():
    """Sitrep 015 prints `Nouveaux cas suspects` -- the day's new suspected.

    Mapped to the same role as the early layout's cumulative, it ended a stock
    series with a one-day flow: the national suspected panel showed 1,077
    falling to 51 overnight. A flow and a stock never share a column.
    """
    rows, _ = E.extract(pdf(15))
    bunia = next(r for r in rows if r["zone_reported"] == "Bunia")
    assert bunia.get("suspected") is None
    assert bunia["new_suspected"] == 19


@needs_pdfs
def test_sitrep_092_tshopo_province_and_zone_are_distinguished():
    rows, _ = E.extract(pdf(92))
    tsh = [r for r in rows if norm(r["zone_reported"]).strip("*† ") == "tshopo"]
    assert len(tsh) == 2, "both the province and its namesake zone are printed"
    assert {r["level"] for r in tsh} == {"province", "zone"}


@needs_pdfs
@pytest.mark.parametrize("n", [60, 70, 80, 92])
def test_multi_page_tables_keep_their_province_rows(n):
    """The province rows are on the first page and the zones on the second.

    Choosing the larger page as the head dropped page one entirely; sitrep 060
    lost 1,808 of its 2,011 cases that way.
    """
    rows, _ = E.extract(pdf(n))
    levels = {r["level"] for r in rows}
    assert "province" in levels and "zone" in levels


# --------------------------------------------------------------------------
# The exception register
# --------------------------------------------------------------------------

import aggregate_provinces as A                                   # noqa: E402
import json
import polars as pl                                               # noqa: E402

REGISTER = ROOT / "registers" / "reconciliation_exceptions.tsv"


def _check_row(sitrep, province, rc, rd, verdict="fails"):
    return {"sitrep": sitrep, "date": "2026-01-01", "province": province,
            "residual_cases": rc, "residual_deaths": rd, "reconciled": verdict}


def _register(rows):
    return pl.DataFrame(rows, schema={c: pl.Utf8 for c in A.REGISTER_COLUMNS})


def _entry(sitrep, unit, column, gap, note="because the page says so"):
    return {"sitrep": str(sitrep), "date": "2026-01-01",
            "sha256_16": "0" * 16, "unit": unit, "column": column,
            "expected_gap": str(gap), "verified_by": "test", "note": note}


def test_exception_excuses_only_its_own_gap():
    """An entry licenses ONE residual, not a report.

    Recording the number rather than the report is what makes the register a
    claim about the page instead of a mute button: if our reading later changes
    the gap, the report goes straight back to the failing set.
    """
    ex = _register([_entry(53, "Nord-Kivu", "cum_cases", 5),
                    _entry(53, "Nord-Kivu", "cum_deaths", 7)])
    same = A.apply_exceptions(pl.DataFrame([_check_row(53, "Nord-Kivu", 5, 7)]), ex)
    assert same["reconciled"][0] == "verified_exception"

    # A gap that moved is not excused -- and since 2026-08-17 the entry it
    # strands is itself an error: an unused licence is a trap for the next
    # defect that happens to produce the same number, so the build stops.
    with pytest.raises(SystemExit, match="NO LONGER MATCH"):
        A.apply_exceptions(pl.DataFrame([_check_row(53, "Nord-Kivu", 6, 7)]), ex)


def test_exception_does_not_leak_to_another_province():
    ex = _register([_entry(53, "Nord-Kivu", "cum_cases", 5)])
    with pytest.raises(SystemExit, match="NO LONGER MATCH"):
        A.apply_exceptions(pl.DataFrame([_check_row(53, "Ituri", 5, 0)]), ex)


def test_a_reconciling_row_strands_its_entry():
    """A row that now reconciles leaves its licence unused -- an error, not a
    quiet success: the entry describes a state that no longer exists."""
    ex = _register([_entry(53, "Nord-Kivu", "cum_cases", 5)])
    with pytest.raises(SystemExit, match="NO LONGER MATCH"):
        A.apply_exceptions(
            pl.DataFrame([_check_row(53, "Nord-Kivu", 0, 0, verdict="ok")]), ex)


@needs_pdfs
def test_the_committed_register_is_not_stale():
    """Every entry's hash still matches the document it describes.

    A revised report must return to the failing set rather than inherit the
    exception its predecessor was granted, so this is the guarantee that makes
    the register safe to keep.
    """
    ex = A.load_exceptions(REGISTER, PDFS)
    assert ex.height > 0


@needs_pdfs
def test_a_stale_hash_stops_the_build(tmp_path):
    text = REGISTER.read_text().replace("d8d21e9c003d1ae7", "0" * 16)
    bad = tmp_path / "stale.tsv"
    bad.write_text(text)
    with pytest.raises(SystemExit, match="STALE"):
        A.load_exceptions(bad, PDFS)


def test_unverifiable_register_is_refused(tmp_path):
    """Without the archive the hashes cannot be checked, so nothing is excused."""
    bad = tmp_path / "reg.tsv"
    bad.write_text(REGISTER.read_text())
    with pytest.raises(SystemExit, match="suppression"):
        A.load_exceptions(bad, None)


@needs_pdfs
def test_every_registered_gap_is_the_gap_we_actually_measure():
    """The register describes THIS pipeline's residuals, not a remembered one.

    If the reader improves and a documented page starts closing, the entry is
    obsolete and should be deleted rather than left asserting a gap that no
    longer exists.
    """
    recon = ROOT / "data" / "build" / "series" / "province_series_reconciliation.csv"
    if not recon.exists():
        pytest.skip("run `make build` first")
    got = pl.read_csv(recon, infer_schema_length=None)
    ex = pl.read_csv(REGISTER, separator="\t", comment_prefix="#",
                     infer_schema_length=None)
    col = {"cum_cases": "residual_cases", "cum_deaths": "residual_deaths"}
    for e in ex.iter_rows(named=True):
        if e["column"] not in col:
            continue
        row = got.filter((pl.col("sitrep") == int(e["sitrep"]))
                         & (pl.col("province") == e["unit"]))
        assert row.height == 1, f"sitrep {e['sitrep']} {e['unit']} not in the build"
        assert row[col[e["column"]]][0] == int(e["expected_gap"]), (
            f"sitrep {e['sitrep']} {e['unit']} {e['column']}: register says "
            f"{e['expected_gap']}, build measures {row[col[e['column']]][0]}")


# --------------------------------------------------------------------------
# The provincial summary route
# --------------------------------------------------------------------------

from lib.tablespec import PROVINCIAL_SUMMARY                      # noqa: E402
from lib.pdftable import read as read_pdf                         # noqa: E402
from lib.tablespec import select as select_spec                   # noqa: E402


@needs_pdfs
@pytest.mark.parametrize("n, ituri_cases", [
    (84, 3563),   # no zone table exists; the summary is the only tabular case data
    (85, 3636),
    (86, 3704),
])
def test_summary_route_covers_the_tableless_vintage(n, ituri_cases):
    """Sitreps 084-086 dropped the per-zone table; the summary is what remains.

    The value asserted is Ituri's cumulative confirmed cases as printed. The
    first attempt at this route matched the ALERTS table instead -- it also has
    one row per province -- and read Ituri as 462 cumulative cases, its alert
    count for the day. The zones-touched cell (`53/140 (37,8 %)`) is the
    signature that separates them, and this test pins the corrected value.
    """
    got = select_spec(read_pdf(pdf(n)), PROVINCIAL_SUMMARY)
    assert got is not None
    m = got.pages[0]
    t = m.table
    rows = {m.label(t.row(i)): t.row(i) for i in range(t.header_rows(), t.nrows)}
    ituri = next(v for k, v in rows.items() if k and norm(k) == "ituri")
    assert E.to_int(m.get(ituri, Role.CUM_CASES)) == ituri_cases


# --------------------------------------------------------------------------
# The prose route
# --------------------------------------------------------------------------

import extract_prose_provinces as PR                              # noqa: E402


@needs_pdfs
def test_prose_route_reads_the_self_checking_sentence():
    """Sitrep 012's breakdown closes on its own arithmetic: 110+10+1 = 121."""
    rows, st = PR.extract(pdf(12))
    assert st == "ok"
    by = {r["province"]: r["cum_cases"] for r in rows}
    assert by == {"national": 121, "Ituri": 110, "Nord-Kivu": 10, "Sud-Kivu": 1}


@needs_pdfs
def test_prose_route_takes_only_what_the_page_states():
    """Sitrep 014 prints a national cumulative and no breakdown; so do we."""
    rows, st = PR.extract(pdf(14))
    assert st == "national_only"
    assert [r["level"] for r in rows] == ["national"]
    assert rows[0]["cum_cases"] == 210


def test_prose_route_refuses_a_breakdown_that_does_not_close(monkeypatch):
    """The sentence's own arithmetic is the licence; without it, nothing ships."""
    import subprocess as sp
    fake = "Cumul des cas confirmés : 100 cas dont 90 en Ituri et 5 au Nord-Kivu."
    class R: stdout = fake
    monkeypatch.setattr(PR.subprocess, "run", lambda *a, **k: R())
    rows, st = PR.extract(Path("/dev/null"))
    assert rows == []
    assert st.startswith("breakdown_does_not_close")


@pytest.mark.parametrize("name", [
    "Sans fiche", "ZS non identifiée", "Echantillons sans fiche",
])
def test_more_unassigned_spellings(name):
    """Sitrep 015 prints `Sans fiche` (14) and `ZS non identifiée` (6) once.

    Read as zones, they forward-filled to the end of the window as a constant
    +20 phantom in Ituri's cumulative -- invisible to the emitted==source-delta
    identity, caught only by comparing the grid against the printed province
    rows. They are pool spellings: counted, but not places.
    """
    assert E.level_of(name) == "unassigned"


# --------------------------------------------------------------------------
# The 2026-08-17 adversarial-review fixes, each pinned to the report that
# exposed it.
# --------------------------------------------------------------------------

def test_ordinal_strips_leading_footnote_marker():
    """Sitrep 090 prints its Haut-Uélé summary row as `* Haut Uélé`; the
    marker is typography, and requiring a letter first dropped 119 cases."""
    assert E.strip_ordinal("* Haut Uélé") == "Haut Uélé"
    assert E.strip_ordinal("1- Bunia") == "Bunia"
    assert E.strip_ordinal("– Nizi") == "Nizi"


@needs_pdfs
def test_087_daily_table_reads_as_daily_not_cumulative():
    """Sitrep 087 prints ONLY a daily table; the cumulative spec once claimed
    it and wrote the day's 57 new Ituri cases into `cum_cases`."""
    rows, st = E.extract(pdf(87))
    assert st == "ok"
    assert rows[0]["table"] == "zone_daily"
    assert all(r["cum_cases"] is None for r in rows)
    nat = [r for r in rows if r["level"] == "national"]
    assert len(nat) == 1 and nat[0]["new_cases"] == 87
    subs = [r for r in rows if r["level"] == "province"]
    assert sorted(s["new_cases"] for s in subs) == [15, 15, 57]
    chk = E.reconcile(rows, column="new_cases")
    assert chk["identity"] == "ok" and chk["residual"] == 0


@needs_pdfs
def test_013_split_subtotal_labels_are_provinces():
    """`Sous total` drawn as two cells read as the fragment `total` and all
    three provincial subtotals were levelled national."""
    rows, _ = E.extract(pdf(13))
    subs = [r for r in rows if r["level"] == "province"]
    assert [s["cum_cases"] for s in subs] == [110, 14, 1]
    nat = [r for r in rows if r["level"] == "national"]
    assert len(nat) == 1 and nat[0]["cum_cases"] == 125
    chk = E.reconcile(rows)
    assert chk["identity"] == "ok" and chk["basis"] == "provinces"


@needs_pdfs
@pytest.mark.parametrize("n, expect_total", [(9, 101), (13, 125)])
def test_wrapped_pool_row_is_recovered(n, expect_total):
    """`Echantillons sans fiche` wraps its name onto neighbouring grid rows;
    the value row had no label and was silently dropped, visible only as a
    -6 residual on sitreps 009 and 013."""
    rows, _ = E.extract(pdf(n))
    pool = [r for r in rows if "chantillons" in r["zone_reported"]]
    assert len(pool) == 1 and pool[0]["level"] == "unassigned"
    assert pool[0]["cum_cases"] == 6
    assert E.reconcile(rows)["identity"] == "ok"


@needs_pdfs
def test_093_intra_cte_column_survives_the_thin_head_page():
    """Pages 090-093 carry only the Ituri block on the head page; the intra-CTE
    column has one numeric cell there, the classifier dropped it, and the zip
    slid `Total décès` into `deaths_treatment_centre`. The printed row is
    89 / 30 / 17 / 47."""
    rows, _ = E.extract(pdf(93))
    itu = [r for r in rows if r["level"] == "province"
           and "ituri" in norm(r["zone_reported"])][0]
    assert (itu["new_cases"], itu["deaths_community"],
            itu["deaths_treatment_centre"], itu["deaths_total"]) == (89, 30, 17, 47)


@needs_pdfs
def test_058_headless_prose_contaminated_continuation_is_read():
    """Sitrep 058's page-5 continuation sits above three paragraphs of prose
    that outvote its seven data rows in the classifier; the page mapped to
    nothing and two provinces plus the national total vanished."""
    rows, _ = E.extract(pdf(58))
    nat = [r for r in rows if r["level"] == "national"]
    assert len(nat) == 1 and nat[0]["cum_cases"] == 1926
    assert E.reconcile(rows)["identity"] == "ok"
    names = {norm(r["zone_reported"]) for r in rows}
    assert {"wamba", "makiso-kisangani", "lubunga"} <= names


@needs_pdfs
def test_067_one_row_head_fragment_is_kept():
    """Sitrep 067's table opens with a heading plus ONE data row -- the Ituri
    province row -- at the foot of page 2. A single row cannot classify, the
    head was excluded, and all 29 zones beneath it lost their province."""
    rows, _ = E.extract(pdf(67))
    itu = [r for r in rows if r["level"] == "province"
           and norm(r["zone_reported"]) == "ituri"]
    assert len(itu) == 1 and itu[0]["cum_cases"] == 2202
    assert E.reconcile(rows)["identity"] == "ok"


@needs_pdfs
@pytest.mark.parametrize("n", [17, 33])
def test_summary_shaped_rows_refuse_the_zone_route(n):
    """Sitreps 017 and 033 print no per-zone table; the provincial summary was
    the only candidate left and was emitted as `zone_cumulative` -- provinces
    posing as zones. The row-shape guard refuses it structurally."""
    rows, st = E.extract(pdf(n))
    assert st == "no_matching_table" and not rows


@needs_pdfs
def test_092_split_province_labels_in_summary():
    """`Haut Uélé` and `Bas Uélé` drawn across two label cells came out as a
    zone named `Uélé` in provinces named `Haut` and `Bas` -- and both
    provinces collapsed onto one label in the same report."""
    from lib.tablespec import PROVINCIAL_SUMMARY
    rows, _ = E.extract(pdf(92), specs=(PROVINCIAL_SUMMARY,))
    names = [r["zone_reported"] for r in rows if r["level"] == "province"]
    assert "Haut Uélé" in names and "Bas Uélé" in names
    assert not any(r["zone_reported"] == "Uélé" for r in rows)


@needs_pdfs
def test_085_total_row_carried_onto_the_next_page_is_read():
    """Sitrep 085's page break leaves the summary's national `Total` row alone
    at the top of page 2, and the alerts table's title box is drawn over it --
    the row occupies y=72 to y=91, the title box y=87 to y=115. The two grids
    touch, so the rules formed ONE component whose outer edges are the union of
    both and which therefore matched no continuation, and the row was dropped:
    five province rows, status `ok`, nothing anywhere saying that a printed
    observation had been lost. The printed row is
    `Total 4 209 | 1 916 | 45,5 % | 53/140 (37,8 %) | 89`.

    The row count is asserted too, because the risk in reading a continuation
    out of a fused component is reading the OTHER table with it: the alerts
    grid beneath this row prints one line per province and a `Total Général`
    of 1 318.
    """
    from lib.tablespec import PROVINCIAL_SUMMARY
    rows, st = E.extract(pdf(85), specs=(PROVINCIAL_SUMMARY,))
    assert st == "ok"
    assert len(rows) == 6, "five provinces and the national total, and nothing "\
                           "from the alerts table drawn over it"
    nat = [r for r in rows if r["level"] == "national"]
    assert len(nat) == 1
    assert (nat[0]["cum_cases"], nat[0]["cum_deaths"],
            nat[0]["new_cases"]) == (4209, 1916, 89)
    assert nat[0]["page"] == 2, "the row is printed on page 2 and is filed there"
    assert E.reconcile(rows)["identity"] == "ok"


@needs_pdfs
def test_098_province_names_wrapped_at_their_hyphen_stay_provinces():
    """Sitrep 098 prints its province rows on a coloured band, and Word draws
    that band as one filled box per cell PER PRINTED LINE, inset inside the
    cell. `Nord-Kivu` and `Haut-Uélé` are the only names long enough to wrap,
    so in those two rows the label cell got two stacked boxes while the value
    cells kept one vertically-centred box -- whose edges (y=168.7 and y=178.1,
    inside a row running 164.2 to 182.6) ran the table's width and cut the row
    in two.

    `Nord-` kept the counts; `Kivu` was left alone in a row carrying no value,
    which is not a row, so the tail was dropped. `Nord-` matches no province,
    both rows were filed as health ZONES, and their totals left the province
    level and were double-counted at zone level. The national identity failed
    by exactly 680 + 165 = 845 cases.
    """
    rows, st = E.extract(pdf(98))
    assert st == "ok"
    by = {r["zone_reported"]: r for r in rows}
    assert "Nord-" not in by and "Haut-" not in by, "a wrapped tail was dropped"
    assert by["Nord-Kivu"]["level"] == "province"
    assert by["Haut-Uélé"]["level"] == "province"
    assert (by["Nord-Kivu"]["cum_cases"], by["Nord-Kivu"]["cum_deaths"]) == (680, 463)
    assert (by["Haut-Uélé"]["cum_cases"], by["Haut-Uélé"]["cum_deaths"]) == (165, 75)
    got = E.reconcile(rows)
    assert got["identity"] == "ok" and got["residual"] == 0


@needs_pdfs
@pytest.mark.parametrize("n, name", [
    (98, "Makiso-Kisangani"), (98, "Wanie-Rukula"), (98, "Miti-Murhesa"),
    (100, "Makiso-Kisangani"),
])
def test_a_zone_name_wrapped_at_its_hyphen_keeps_the_printed_spelling(n, name):
    """The same wrap in a zone name was never a level error, only a wrong
    name: these came out as `Makiso- Kisangani`, a spelling the page does not
    print. `pdftotext` reading the content stream returns `MakisoKisangani` --
    one word -- which is what says the break is typography, not content."""
    rows, _ = E.extract(pdf(n))
    names = {r["zone_reported"] for r in rows}
    assert name in names
    assert name.replace("-", "- ") not in names


@needs_pdfs
def test_099_continuation_page_is_read_and_the_table_completes():
    """Sitrep 099's zone table breaks across pages 2 and 3, and page 2's
    component came back as x=[16.9, 599.3] where the table is [77.1, 535.1]:
    the page footer is a coloured bar 35 pt below the last row, one of its
    internal boundaries sits at x=210-211 where the shading boxes put a rule at
    x=211.5, and `_coalesce` -- whose x-clustering is 6 pt and whose gap
    bridging is 36 pt -- joined footer to table into one vertical running to
    the foot of the page. The footer's page-wide horizontals then crossed it
    and the footer became part of the component.

    `select` chains a continuation by comparing its edges with the anchor's, so
    nothing on page 3 could match: the chain stopped at page 2. The report
    returned 25 rows ending at Nizi, its identity was `not_checkable`, and
    Nord-Kivu, Haut-Uélé, Tshopo, Sud-Kivu, Bas-Uélé and the national `Total`
    were never read.

    This is NOT sitrep 085's defect. There the CONTINUATION was fused and the
    anchor was sound; here the ANCHOR was fused, so the anchor's own edges were
    the wrong question to ask.
    """
    rows, st = E.extract(pdf(99))
    assert st == "ok"
    nat = [r for r in rows if r["level"] == "national"]
    assert len(nat) == 1, "the national Total row is printed on page 3"
    assert (nat[0]["cum_cases"], nat[0]["cum_deaths"]) == (5458, 2606)
    assert nat[0]["page"] == 3
    provinces = {r["zone_reported"] for r in rows if r["level"] == "province"}
    assert provinces == {"Ituri", "Nord-Kivu", "Haut-Uélé", "Tshopo",
                         "Sud-Kivu", "Bas Uélé"}
    got = E.reconcile(rows)
    assert got["identity"] == "ok" and got["residual"] == 0
    assert len(rows) == 65


@needs_pdfs
def test_102_continuation_page_is_read_and_the_table_completes():
    """Sitrep 102 failed with sitrep 099's SIGNATURE and not its cause, and the
    difference is why 099's guards did not cover it.

    On 099 the vertical that reached the footer was drawn by the coloured band
    Word paints on province rows, and `_nested` -- which reads a filled
    rectangle inside a larger one as paint rather than as a cell -- removed it.
    On 102 there is no such box to suppress: the vertical is the zone table's
    OWN column rule at x=401.45, and what it met is the page footer's own cell
    side at x=404.80. They sit 3.35 pt apart across the page, inside
    `_coalesce`'s 6 pt x-clustering, and 34.69 pt apart down it, inside its
    36 pt gap bridging -- so the two joined into one rule running to y=779.05,
    the footer's page-wide horizontals crossed it, and the footer unioned into
    the table's component.

    Page 2's component then came back as x=[16.95, 599.30] where the table is
    [83.79, 528.46]. `select` chains a continuation by comparing its edges with
    the anchor's, so nothing on page 3 matched and the chain stopped at page 2:
    25 rows ending at Nizi, identity `not_checkable`, and Ituri's own zones
    1,108 cases short of the 4,716 its province row prints.

    SITREP 101 IS THE SAME VINTAGE AND THE SAME LAYOUT and does not do this
    only because its page-2 table ends 6.9 pt higher, which puts the footer
    41.6 pt away and outside the bridging gap. Nothing can be keyed on where a
    table happens to stop, so the rule is about the two pieces: a gap is
    bridged only between pieces of one drawn line.
    """
    rows, st = E.extract(pdf(102))
    assert st == "ok"
    nat = [r for r in rows if r["level"] == "national"]
    assert len(nat) == 1, "the national Total row is printed on page 3"
    assert (nat[0]["cum_cases"], nat[0]["cum_deaths"]) == (5656, 2715)
    assert nat[0]["page"] == 3
    provinces = {r["zone_reported"]: r for r in rows if r["level"] == "province"}
    assert set(provinces) == {"Ituri", "Nord-Kivu", "Haut-Uélé", "Tshopo",
                              "Sud-Kivu", "Bas Uélé"}
    # Ituri's province row is on page 2 and every other province is on page 3 --
    # the rows the chain used to drop.
    assert (provinces["Ituri"]["cum_cases"],
            provinces["Ituri"]["cum_deaths"]) == (4716, 2119)
    assert provinces["Nord-Kivu"]["page"] == 3
    got = E.reconcile(rows)
    assert got["identity"] == "ok" and got["residual"] == 0
    assert len(rows) == 66


def test_a_rule_does_not_adopt_a_neighbour_it_merely_passes():
    """The geometric rule sitrep 102 needed, stated without the document.

    Pieces are grouped across the page at `SNAP_X` because a shared border
    arrives as its rule and the two cell faces beside it, a few points apart --
    and those lie SIDE BY SIDE over the same rows. Joining pieces END TO END
    says instead that a rule the page drew in pieces is one rule, and one drawn
    line has one coordinate. Allowing both at once let a column rule run 36 pt
    past its own end and adopt anything within 6 pt of it.

    The numbers are sitrep 102 page 2's: the table's column rule drawn per row
    down to y=740.86, and the page footer's 3.5 pt cell side at x=404.80
    starting 34.69 pt below it.
    """
    from lib.pdftable import Segment, _coalesce

    column = [Segment(401.45, y, y + 14.64, False)
              for y in (696.34, 710.98, 725.26)]
    footer = Segment(404.80, 775.55, 779.05, False)

    got = sorted(_coalesce(column + [footer]), key=lambda s: s.lo)
    assert len(got) == 2, "the footer was adopted by the table's column rule"
    assert got[0].hi == pytest.approx(739.90), "the column rule ends where drawn"
    assert got[1].lo == pytest.approx(775.55) and got[1].hi == pytest.approx(779.05)

    # AND THE BRIDGING THAT IS REAL STILL HAPPENS. A rule interrupted by a
    # double-height row -- the case COALESCE_GAP was measured on -- is drawn in
    # pieces at ONE coordinate, so it still joins across the same 34.69 pt.
    same_line = column + [Segment(401.45, 775.55, 779.05, False)]
    joined = _coalesce(same_line)
    assert len(joined) == 1
    assert joined[0].lo == pytest.approx(696.34)
    assert joined[0].hi == pytest.approx(779.05)


@needs_pdfs
@pytest.mark.parametrize("n", [99, 100])
def test_two_rows_with_no_rule_between_them_do_not_become_one_number(n):
    """Bas-Uélé's two health zones are separated by no horizontal rule at all;
    nine column rules stop and restart together at y=633.1 and nothing else
    marks the division. `_coalesce` joins each column's pieces into the single
    rule the reader sees, which dissolves exactly that evidence, and the two
    rows fused.

    The damage was not a missing row but a WRONG NUMBER. The fused cell reads
    `1 1`, and because a space is this source's thousands separator, `to_int`
    returned ELEVEN: Bas-Uélé's two cases were published as eleven and its
    deaths as ten, and the province missed its own printed total by nine on
    both reports. The page prints Buta 1/1 and Viadana 1/0 against a Bas-Uélé
    row of 2/1.
    """
    rows, _ = E.extract(pdf(n))
    by = {r["zone_reported"]: r for r in rows}
    assert "Buta Viadana" not in by, "two printed rows read as one"
    assert (by["Buta"]["cum_cases"], by["Buta"]["cum_deaths"]) == (1, 1)
    assert (by["Viadana"]["cum_cases"], by["Viadana"]["cum_deaths"]) == (1, 0)
    prov = by["Bas Uélé"]
    assert (prov["level"], prov["cum_cases"], prov["cum_deaths"]) == ("province", 2, 1)


@needs_pdfs
@pytest.mark.parametrize("n", [88, 89, 91, 95, 98])
def test_a_value_in_a_taller_cell_is_not_split_off_its_own_row(n):
    """The same shading boxes that cut sitrep 098's province rows in half were
    cutting ordinary zone rows too, wherever a column's cell is taller than the
    others because its heading wraps. Adja's `Total décès confirmés` is printed
    3.6 pt below the rest of its row, landed past the spurious edge, and was
    dropped as a row of its own with no other value in it -- a printed 0 read
    as "not reported", which is not the same thing."""
    rows, _ = E.extract(pdf(n))
    adja = [r for r in rows if r["zone_reported"] == "Adja"][0]
    assert (adja["cum_cases"], adja["cum_deaths"]) == (11, 1)
    assert adja["deaths_total"] == 0, "the page prints 0, not nothing"


@needs_pdfs
def test_087_province_beside_the_name_is_read_over_a_third_label_column():
    """Sitrep 087 prints three label columns -- a `Sous-total` prefix, the
    province, then the zone -- and `parent()` read the LEFTMOST, which is the
    prefix column and empty on an ordinary zone row. The province printed
    directly beside the name went unread."""
    rows, _ = E.extract(pdf(87))
    by = {r["zone_reported"]: r for r in rows}
    assert by["Mongbwalu"]["province_printed"] == "Ituri"
    assert by["Kalunguta"]["province_printed"] == "Nord-Kivu"
    assert by["Boma Mangbetu"]["province_printed"] == "Haut-Uélé"


@needs_pdfs
def test_005_merged_province_cell_survives_the_footnote_below_the_table():
    """Sitrep 005's component reaches past the table's data into the footnote
    (`*Ces données sont susceptibles de changer...`) and the section heading,
    whose prose falls in the two columns left of `Provinces`. The classifier
    calls those label columns, so the table has four; reading the leftmost
    asked a footnote for the province and got nothing, and the merged province
    cell one column to the right went unread."""
    rows, _ = E.extract(pdf(5))
    by = {r["zone_reported"]: r for r in rows}
    assert by["Bunia"]["province_printed"] == "Ituri"
    assert by["Katwa"]["province_printed"] == "Nord-Kivu"


@needs_pdfs
def test_summary_new_cases_column_is_read():
    """`IGNORED` placed for the zones-touched column (which never classifies
    as a value) swallowed `Nouveaux cas confirmés (24h)` instead: null on all
    348 summary rows. Sitrep 020 prints Ituri 18."""
    from lib.tablespec import PROVINCIAL_SUMMARY
    rows, _ = E.extract(pdf(20), specs=(PROVINCIAL_SUMMARY,))
    itu = [r for r in rows if norm(r["zone_reported"]) == "ituri"][0]
    assert itu["new_cases"] == 18


# --------------------------------------------------------------------------
# The laboratory prose route
# --------------------------------------------------------------------------

def test_lab_licensed_pair():
    """A (positives, samples) pair is licensed only by reproducing the
    printed positivity, uniquely -- ambiguity is refusal."""
    import extract_lab_prose as L
    assert L.licensed_pair([115, 45], [39.1]) == (45, 115, 39.1)
    assert L.licensed_pair([89, 59, 30, 288], [30.9]) == (89, 288, 30.9)
    assert L.licensed_pair([1, 6], [16.6]) == (1, 6, 16.6)   # truncation
    assert L.licensed_pair([199], [32.6]) is None            # no pair printed
    assert L.licensed_pair([10, 20, 40], [50.0]) is None     # ambiguous


@needs_pdfs
def test_lab_prose_sitrep_093():
    """Sitrep 093's chained lab sentence yields all three provinces, each
    licensed by its own printed rate; the fourth clause (Tshopo, spelled-out
    'un résultat positif') is correctly refused rather than guessed."""
    import extract_lab_prose as L
    got, _ = L.extract(pdf(93))
    by = {r["province"]: (r["samples"], r["positives"]) for r in got}
    assert by["Ituri"] == (288, 89)
    assert by["Nord-Kivu"] == (133, 8)
    assert by["Haut-Uélé"] == (9, 3)


@needs_pdfs
def test_lab_prose_death_split_is_not_a_positivity():
    """Sitrep 080's Ituri passage carries BOTH a death split and a real
    positivity, and the death split alone satisfies the licence: "23 décès
    dont 14 communautaires (60,9 %)" offers (14, 23) reproducing 60,9 %
    exactly. It was licensed, so the day read 14 positives out of 23 samples
    instead of the printed 53 out of 210. The guard is arithmetic and the
    ambiguity is semantic, so the clause has to leave the pool before the
    pair is chosen."""
    import extract_lab_prose as L
    got, _ = L.extract(pdf(80))
    itu = [r for r in got if r["province"] == "Ituri"]
    assert itu, "sitrep 080 licenses an Ituri lab row"
    assert (itu[0]["samples"], itu[0]["positives"]) == (210, 53)


def test_death_split_clause_leaves_the_pool():
    """The clause is removed whether or not it prints its own percentage,
    and a positivity sentence without a death split is untouched."""
    import extract_lab_prose as L
    assert "14" not in L.DEATH_SPLIT.sub(" ", "23 décès dont 14 communautaires (60,9 %)")
    assert "14" not in L.DEATH_SPLIT.sub(" ", "23 deces dont 14 communautaires")
    keep = "82 échantillons collectés et analysés (18 positifs)"
    assert L.DEATH_SPLIT.sub(" ", keep) == keep


@needs_pdfs
def test_lab_prose_flow_not_stock():
    """Sitrep 020's bullet vintage states no flow word; the laboratory
    section is daily by construction and the positives equal the day's
    printed new confirmed cases (18)."""
    import extract_lab_prose as L
    got, _ = L.extract(pdf(20))
    itu = [r for r in got if r["province"] == "Ituri"]
    assert itu and itu[0]["positives"] == 18 and itu[0]["samples"] == 82


@needs_pdfs
def test_lab_prose_fallback_admits_unprinted_rate_by_noun_adjacency():
    """Sitrep 092's Ituri passage prints '93 résultats positifs (336
    échantillons analysés), dont 85 nouveaux cas (54 vivants et 31 décès)'
    with no percentage anywhere in the sentence, so licensed_pair has
    nothing to check a pair against and this row used to refuse as
    'no_printed_rate'. The noun-adjacency fallback finds 336 beside
    'échantillons' and 93 beside the higher-priority 'résultats positifs' --
    NOT 85, which sits beside the lower-priority 'nouveaux cas' and names a
    different quantity (new cases among the positives, not all of them).
    printed_pct stays null: nothing is invented for the rate the source did
    not print."""
    import extract_lab_prose as L
    got, _ = L.extract(pdf(92))
    itu = [r for r in got if r["province"] == "Ituri"]
    assert itu, "sitrep 092 admits an Ituri lab row via the fallback"
    row = itu[0]
    assert (row["samples"], row["positives"]) == (336, 93)
    assert row["rate_printed"] is False
    assert row["printed_pct"] is None


@needs_pdfs
def test_lab_prose_fallback_refuses_when_the_positive_noun_is_not_adjacent():
    """Sitrep 082's Nord-Kivu passage prints '10 sont revenus positifs': the
    number and the word 'positifs' are separated by 'sont revenus', so the
    integer is not adjacent to the noun under this licence, and the sentence
    still refuses rather than guess which integer was meant."""
    import extract_lab_prose as L
    got, refused = L.extract(pdf(82))
    nk = [r for r in got if r["province"] == "Nord-Kivu"]
    assert not nk, "no Nord-Kivu row should be admitted for sitrep 082"
    assert any(r["why"] == "no_noun_anchor" and r["prov"] == "Nord-Kivu"
              for r in refused)


def test_lab_prose_fallback_rejects_positives_exceeding_samples():
    """Both nouns can be found and the sentence still not be readable: a
    positive count above the sample count is a sanity failure, not a
    licence, and must refuse rather than emit a row."""
    import extract_lab_prose as L
    pair, why = L.noun_adjacent_pair(
        "8 positifs parmi 5 échantillons analysés")
    assert pair is None
    assert why == "positives_exceed_samples"


def test_lab_prose_dedupe_prefers_a_validated_row_over_a_fallback_guess():
    """The real archive never states one province twice with one reading
    backed by a printed rate and the other not, so this policy is otherwise
    untested by any single report. A validated reading must win regardless
    of which one the document happened to state first -- and the ordinary
    case, two disagreeing validated (or two disagreeing unvalidated)
    readings, is still a conflict."""
    import extract_lab_prose as L

    def row(samples, positives, rate_printed):
        return {"province": "Ituri", "samples": samples, "positives": positives,
               "printed_pct": 10.0 if rate_printed else None,
               "rate_printed": rate_printed, "sentence": "s"}

    # validated seen first, fallback disagrees second -> fallback dropped.
    out, refused = L.dedupe_by_province([row(100, 10, True), row(90, 9, False)])
    assert [(r["samples"], r["positives"]) for r in out] == [(100, 10)]
    assert refused == []

    # fallback seen first, validated disagrees second -> validated wins.
    out, refused = L.dedupe_by_province([row(90, 9, False), row(100, 10, True)])
    assert [(r["samples"], r["positives"]) for r in out] == [(100, 10)]
    assert refused == []

    # two validated readings disagreeing is still a real conflict.
    out, refused = L.dedupe_by_province([row(100, 10, True), row(80, 8, True)])
    assert len(out) == 1 and len(refused) == 1
    assert refused[0]["why"] == "conflicting_sentences"


LAB_PROSE_BUILD = ROOT / "data" / "build" / "series" / "lab_prose.csv"
needs_lab_prose_build = pytest.mark.skipif(
    not LAB_PROSE_BUILD.exists(),
    reason="lab_prose.csv is not built; run `make build`")


@needs_lab_prose_build
def test_lab_prose_validated_rows_agree_with_their_own_printed_pct():
    """The invariant licensed_pair enforces at construction time, checked
    here against the file `make build` actually wrote: every row licensed by
    a printed percentage reproduces it, within the same tolerance the licence
    itself uses (one decimal place -> 0.15 points, integer percent -> 0.55,
    covering the source's habit of truncating rather than rounding).
    Fallback rows (rate_printed = False) are exempt by construction -- they
    have no printed_pct to agree with, which is exactly what distinguishes
    them."""
    import polars as pl
    df = pl.read_csv(LAB_PROSE_BUILD)
    rated = df.filter(pl.col("rate_printed"))
    assert rated.height > 0, "the build should carry percentage-licensed rows"
    bad = []
    for row in rated.iter_rows(named=True):
        p = row["printed_pct"]
        tol = 0.55 if float(p).is_integer() else 0.15
        computed = 100.0 * row["positives"] / row["samples"]
        if abs(computed - p) > tol:
            bad.append((row["sitrep"], row["province"], row["samples"],
                       row["positives"], p))
    assert not bad, bad


# --------------------------------------------------------------------------
# The letality check, and the register entry it produced
# --------------------------------------------------------------------------

REJECTED = ROOT / "registers" / "rejected_routes.tsv"


@pytest.mark.parametrize("cell, want", [
    ("41,3%", (41.3, "3")),
    ("41,6 %", (41.6, "6")),
    ("100,0%", (100.0, "0")),
    ("9,10%", (9.10, "10")),        # sitrep 074: one decimal padded to two
    ("26,9", (26.9, "9")),          # sitrep 052 prints no per-cell sign
    ("44", (44.0, "")),
    ("41.3%", (41.3, "3")),
    ("ND", None), ("—", None), ("", None), ("-", None),
    ("Bunia", None),
])
def test_to_pct(cell, want):
    assert E.to_pct(cell) == want


def _let_row(letality, cases, deaths, name="Bunia", level="zone"):
    return {"zone_reported": name, "level": level, "cum_cases": cases,
            "cum_deaths": deaths, "letality_printed": letality}


def test_letality_precision_is_the_column_not_the_cell():
    """Sitrep 074 prints two decimal digits and rounds to one.

    Every one of its 54 rows ends in a zero -- `9,10 %`, `41,40 %`, `35,30 %`
    -- because the column is rounded to a single decimal and then formatted to
    two. Held to the digits it prints, 29 of those 54 rows "fail" and a clean
    report is condemned as a displaced column, which is the most expensive
    mistake this check could make.
    """
    rows = [_let_row("9,10%", 11, 1), _let_row("41,40%", 2988, 1238),
            _let_row("35,30%", 17, 6), _let_row("100,00%", 5, 5)]
    assert E.letality_precision(rows) == 1
    assert all(E.letality_check(r, 1)["verdict"] == "ok" for r in rows)


def test_letality_precision_reads_a_column_that_does_resolve_hundredths():
    """Sitrep 064 really does print `36,83 %`, so its column resolves two."""
    assert E.letality_precision([_let_row("36,83%", 2267, 835),
                                 _let_row("33,30%", 3, 1)]) == 2


def test_a_cell_written_coarser_than_its_column_still_closes():
    """Sitrep 064 resolves the hundredths and still prints Sud-Kivu's 1/3 as
    `33,30 %`. That is one third written at one decimal, not a wrong number."""
    assert E.letality_check(_let_row("33,30%", 3, 1), 2)["verdict"] == "ok"


@pytest.mark.parametrize("cell, cases, deaths, want", [
    ("29,2%", 880, 257, "ok"),          # sitrep 077 Bunia, 29.2045 rounded
    ("27,2%", 114, 31, "ok"),           # 27.1930 rounded up
    ("0,0%", 1, 0, "ok"),
    ("100,0%", 5, 5, "ok"),
    ("30,9%", 1460, 452, "source_rounding"),   # sitrep 048: 30.9589 truncated
    ("44,2%", 3802, 1707, "inconsistent"),     # sitrep 080's Total: 44.90
    ("100,0%", 1, 0, "inconsistent"),          # sitrep 018's Logo
])
def test_letality_verdicts(cell, cases, deaths, want):
    assert E.letality_check(_let_row(cell, cases, deaths), 1)["verdict"] == want


def test_letality_is_not_checkable_without_both_counts():
    """A zone with no cases has no case fatality, and a missing count states
    nothing -- neither is a failure, and neither may be counted as a pass."""
    assert E.letality_check(_let_row("0,0%", 0, 0), 1) is None
    assert E.letality_check(_let_row("50,0%", None, 1), 1) is None
    assert E.letality_check(_let_row("50,0%", 4, None), 1) is None
    assert E.letality_check(_let_row("ND", 4, 2), 1) is None


def test_carried_forward_names_the_previous_report_not_a_failure():
    """Sitrep 073's Beni prints 69,8 %, which is 30/43 -- its own figure in the
    previous report -- against its current 34/44 = 77,3 %.

    The source assembles each report by editing the previous day's table, and a
    row whose counts were updated without its derived percentage keeps
    yesterday's. That is the source's behaviour, not our reading, and it has to
    be told apart from a displaced column or a dozen isolated rows across the
    corpus would look like the same defect as sitrep 080.
    """
    checks = [{**E.letality_check(_let_row("69,8%", 43, 30, "Beni"), 1), "sitrep": 72},
              {**E.letality_check(_let_row("69,8%", 44, 34, "Beni"), 1), "sitrep": 73}]
    assert checks[1]["verdict"] == "inconsistent"
    got = E.letality_carried_forward(checks)
    assert [c["verdict"] for c in got] == ["ok", "carried_forward"]
    assert got[1]["carried_from"] == "30/43"


def test_carried_forward_only_reaches_back_one_report():
    """Reaching further back explains almost any percentage by coincidence."""
    checks = [{**E.letality_check(_let_row("50,0%", 2, 1), 1), "sitrep": 70},
              {**E.letality_check(_let_row("60,0%", 5, 3), 1), "sitrep": 71},
              {**E.letality_check(_let_row("50,0%", 9, 2), 1), "sitrep": 72}]
    got = E.letality_carried_forward(checks)
    assert got[2]["verdict"] == "inconsistent"    # 50 % is report 70's, not 71's


@pytest.mark.parametrize("counts, want", [
    ({}, "not_printed"),
    ({"ok": 56}, "ok"),
    ({"ok": 36, "carried_forward": 1, "inconsistent": 3}, "rows_disagree"),
    ({"ok": 4, "carried_forward": 5, "inconsistent": 47}, "column_displaced"),
])
def test_letality_report_verdict(counts, want):
    """The boundary is a majority, and the two cases do not come close to
    touching: sitrep 080 fails 47 of 56 rows and the next worst 3 of 40."""
    assert E.letality_verdict(counts) == want


@needs_pdfs
def test_sitrep_080_daily_block_is_displaced_by_one_let_row():
    """The values on row i's line belong to row i-1, proved by the zone sums.

    This is the finding the letality check exists to catch, and the arithmetic
    is what establishes it -- `pdftotext -layout` misaligns wrapped labels, so
    visual adjacency proves nothing. The four daily figures printed on the
    `Adja` line are exactly the sum of the 27 Ituri zone lines BELOW it, on all
    four columns at once, so they are Ituri's own province totals printed one
    line low. `Adja` itself carries 11 cumulative cases and 1 cumulative death,
    which forbids the 49 new cases and 23 deaths on its line outright.
    """
    rows, _ = E.extract(pdf(80), specs=(ZONE_TABLE,))
    names = [r["zone_reported"] for r in rows]
    i = names.index("Adja")
    assert rows[i - 1]["zone_reported"] == "Ituri"
    assert (rows[i]["cum_cases"], rows[i]["cum_deaths"]) == (11, 1)
    below = rows[i + 1:i + 1 + 27]
    assert all(r["level"] == "zone" for r in below)
    for col, want in (("new_cases", 49), ("deaths_community", 13),
                      ("deaths_treatment_centre", 10), ("deaths_total", 23)):
        assert rows[i][col] == want, col
        assert sum(r[col] or 0 for r in below) == want, col


def _raw_letality(*ns):
    """The check as it runs before any register is consulted, over the reports
    given -- the carried-forward pass needs more than one to have anything to
    look back at."""
    out = []
    for n in ns:
        rows, _ = E.extract(pdf(n))
        d = E.letality_precision(rows)
        out += [{**c, "sitrep": n}
                for c in (E.letality_check(r, d) for r in rows) if c]
    return E.letality_carried_forward(out)


@needs_pdfs
def test_sitrep_080_letality_column_fails_far_harder_than_any_other():
    """52 of its 56 rows disagree with their own cases and deaths.

    Five of those 52 turn out to be the previous report's figure once the panel
    supplies one, leaving 47 unexplained -- but even taken alone the report is
    a majority failure and would gate the build, which is the property that
    matters. The next-worst report in the corpus has three.

    Measured on the RAW extraction: this is the evidence FOR the register
    entry, so it must not be produced BY it.
    """
    alone = _raw_letality(80)
    assert sum(1 for c in alone if c["verdict"] == "inconsistent") == 52
    assert sum(1 for c in alone if c["verdict"] == "ok") == 4

    with_history = [c for c in _raw_letality(79, 80) if c["sitrep"] == 80]
    assert sum(1 for c in with_history if c["verdict"] == "inconsistent") == 47
    assert sum(1 for c in with_history if c["verdict"] == "carried_forward") == 5


@needs_pdfs
#: (report, the report before it IN THE ARCHIVE, expected verdict). The
#: predecessor is named rather than computed: the archive has no sitreps 075 or
#: 076, so 077's previous appearance of a row is 074's, and `n - 1` would
#: silently skip the case instead of testing it.
@pytest.mark.parametrize("prev, n, want", [
    (79, 80, "column_displaced"),   # 47 of 56 -- the only report that gates
    (48, 49, "rows_disagree"),      # three isolated rows: recorded, not gating
    (64, 65, "rows_disagree"),      # one row: Haut-Uélé prints 62,2 % for 10/16
    (74, 77, "ok"),
    (82, 83, "ok"),                 # its Total is `source_rounding`, not a fail
])
def test_only_sitrep_080_reaches_the_gate(prev, n, want):
    """The gate is a majority, and nothing else in the corpus comes near it."""
    counts: dict[str, int] = {}
    for c in _raw_letality(prev, n):
        if c["sitrep"] == n:
            counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    assert E.letality_verdict(counts) == want


@needs_pdfs
def test_sitrep_080_summary_table_on_the_same_page_reads_clean():
    """The page adjudicates itself, which is what rules out our reader.

    The provincial summary is a second table over the same five provinces on
    the same document. Every one of its letality figures closes -- including a
    national 44,9 % against the zone table's 44,2 %, on one identical pair of
    3,802 cases and 1,707 deaths. The zone table's 44,2 % is 1657/3748, the
    PREVIOUS report's national pair.
    """
    rows, _ = E.extract(pdf(80), specs=(PROVINCIAL_SUMMARY,))
    d = E.letality_precision(rows)
    got = [c for c in (E.letality_check(r, d) for r in rows) if c]
    assert len(got) == 6 and all(c["verdict"] == "ok" for c in got)
    nat = next(c for c in got if c["level"] == "national")
    assert (nat["cum_cases"], nat["cum_deaths"]) == (3802, 1707)
    assert nat["letality_printed"] == 44.9


@needs_pdfs
def test_the_register_rejects_the_daily_block_and_keeps_the_cumulative():
    """Throwing sitrep 080 away to be rid of its daily block would take a
    cumulative series with it that closes exactly against the printed national
    total, at both levels and on both columns."""
    rej = E.load_rejected_routes(REJECTED, PDFS)[80]
    assert rej.route == "zone_cumulative"
    assert not rej.whole_route
    assert rej.columns == frozenset({
        "letality", "new_cases", "deaths_community",
        "deaths_treatment_centre", "deaths_total"})


@needs_pdfs
def test_the_rejected_columns_are_null_and_the_others_survive():
    panel = ROOT / "data" / "build" / "series" / "zone_table.csv"
    if not panel.exists():
        pytest.skip("run `make build` first")
    d = (pl.read_csv(panel, infer_schema_length=None)
         .filter(pl.col("sitrep") == 80))
    assert d.height > 0
    for col in ("new_cases", "deaths_community", "deaths_treatment_centre",
                "deaths_total"):
        assert d[col].null_count() == d.height, f"{col} must be null throughout"
    nat = d.filter(pl.col("level") == "national")
    assert (nat["cum_cases"][0], nat["cum_deaths"][0]) == (3802, 1707)
    prov = d.filter(pl.col("level") == "province")
    assert prov["cum_cases"].sum() == 3802
    assert prov["cum_deaths"].sum() == 1707


@needs_pdfs
def test_a_stale_rejected_route_hash_stops_the_build(tmp_path):
    """A revised document must return for a fresh judgement, not inherit one."""
    bad = tmp_path / "stale.tsv"
    bad.write_text(REJECTED.read_text().replace("fae9db4cc474db76", "0" * 16))
    with pytest.raises(SystemExit, match="STALE"):
        E.load_rejected_routes(bad, PDFS)


@needs_pdfs
def test_a_misspelled_rejected_column_stops_the_build(tmp_path):
    """The one failure a register must not have: an entry that reads as a
    judgement applied while the wrong values go on being published."""
    bad = tmp_path / "typo.tsv"
    bad.write_text(REJECTED.read_text().replace("deaths_total", "deaths_totl"))
    with pytest.raises(SystemExit, match="does not read"):
        E.load_rejected_routes(bad, PDFS)


@needs_pdfs
def test_a_blank_column_scope_stops_the_build(tmp_path):
    """Blank cannot mean `*`: the scope of a judgement is never a guess."""
    bad = tmp_path / "blank.tsv"
    bad.write_text(REJECTED.read_text().replace(
        "zone_cumulative\t*\tprovincial_summary",
        "zone_cumulative\t\tprovincial_summary"))
    with pytest.raises(SystemExit, match="`columns` blank"):
        E.load_rejected_routes(bad, PDFS)


@needs_pdfs
def test_the_committed_rejected_route_register_is_not_stale():
    got = E.load_rejected_routes(REJECTED, PDFS)
    assert set(got) == {33, 80}
    assert got[33].whole_route
# The front-page dashboard banner, in both layouts
# --------------------------------------------------------------------------

import extract_banner as B                                        # noqa: E402


@pytest.mark.parametrize("line, want", [
    # THE FUSION THAT REFUSED EVERY SINGLE-DIGIT TILE VALUE. A one-character
    # field used to swallow the rest of its line, so sitrep 008's recovery
    # count came out as one field, `'0                  16'`, matching no
    # number and refusing.
    ("     91               10          0                  16",
     [(5, "91"), (22, "10"), (34, "0"), (53, "16")]),
    ("      344*         60        6                  43,9%",
     [(6, "344*"), (19, "60"), (29, "6"), (48, "43,9%")]),
    # A single space inside a field is not a column break.
    ("Cumul cas confirmés       Cumul décès parmi",
     [(0, "Cumul cas confirmés"), (26, "Cumul décès parmi")]),
    ("  2", [(2, "2")]),
])
def test_fields_do_not_fuse(line, want):
    assert [(s, t) for s, _, t in B._fields(line)] == want


@pytest.mark.parametrize("field, want", [
    ("173", 173),
    ("1 333*", 1333),                 # thousands separator plus a marker
    ("1441", 1441),                   # the early vintage prints no separator
    ("202(23,1%)", 202),              # a count with a letality beside it
    ("609(92,7%)", 609),              # ... a bed-occupancy rate
    ("192(46 décès) **", 192),        # ... a worded sub-count
    ("1 309 · (44,0%)", 1309),        # ... introduced by a bullet
    ("719 · 36,6 %**", 719),          # sitrep 059 drops the brackets
    ("291(26,0%)1", 291),             # sitrep 040: a footnote digit trailing
    ("82 (17,6%)", 82),
    ("2911", 2911),                   # a real four-digit count still reads
    # NOT counts:
    ("47,5%", None),                  # a letality tile
    ("82,7", None),                   # sitrep 048 prints the rate unsuffixed
    ("ND", None), ("N/D", None), ("—", None),
    ("0                  16", None),  # a fused field must never read as one
    ("(60 décès)**", None),           # a stranded parenthetical
])
def test_tile_count_grammar(field, want):
    assert B._to_count(field) == want


@pytest.mark.parametrize("label, value, want", [
    ((0, 19), (15, 21), True),        # value centred inside a wider label
    ((100, 106), (102, 103), True),   # a lone digit under a short label
    ((99, 112), (106, 108), True),    # starts differ by 7, spans do not meet
    ((0, 19), (40, 50), False),       # the next tile along
    ((113, 119), (126, 139), False),  # adjacent tiles, 13 columns apart
])
def test_aligned(label, value, want):
    """A tile's value is CENTRED over its label block and the label wraps to a
    different width, so start-column proximity alone is not enough: sitrep 046
    prints `1 333*` at 15-21 above `Cumul cas confirmés` at 3-22."""
    assert B._aligned(value, label) is want


def test_equidistant_numbers_refuse_rather_than_guess():
    """Nearer-wins needs a tie-break, and there is no honest one: if the page
    puts an aligned count the same distance above and below a label, it has
    not said which is the tile's."""
    lines = ["   11        22",          # a dashboard row, one line above
             "   Guéris",
             "   33        44"]          # an aligned count, one line below
    pat = __import__("re").compile("Guéris")
    val, note = B._tile_value(lines, 1, (3, 9), pat, "Guéris")
    assert val is None
    assert "above (11)" in note and "as near beneath (33)" in note

    # Move the lower one further away and the upper one wins outright.
    val, note = B._tile_value(lines[:2] + ["", "   33        44"], 1, (3, 9),
                              pat, "Guéris")
    assert (val, note) == (11, "")


def test_dashboard_row_separates_the_banner_from_the_header():
    """The upward search accepts only a line of nothing but tile values.
    Above a label lies the report header, whose dates and zone counts are
    numbers belonging to no tile."""
    assert B._dashboard_row("    125     17    906   70,1%    1     ND")
    assert B._dashboard_row("   1 333*   399(29,7%)   609(92,7%)   189")
    assert not B._dashboard_row("Date de rapportage             29 mai 2026")
    assert not B._dashboard_row("Zones de Santé touchées (46)   Ituri (27/36)")
    assert not B._dashboard_row("       725")          # one field is not a row


@needs_pdfs
@pytest.mark.parametrize("n, isolated, recovered, deaths", [
    # VALUES ABOVE LABELS. Every one of these refused before the reader
    # searched upward.
    (8,  None, 0,   10),      # `Guéris` 0; `Cumul décès parmi les confirmés` 10
    (13, None, 1,   17),      # the report whose narrative announces the first recovery
    (15, None, 2,   42),      # the value row is split over two lines
    (18, 173,  6,   60),      # last report before the label says `cumul`
    (21, 258,  8,   82),      # `8` and `153` adjacent: the fused-field case
    (33, 379,  67,  202),
    (40, 408,  122, 291),     # `291(26,0%)1` -- a footnote digit on the value
    (46, 609,  189, 399),     # census discarded before, as a sibling table did not add up
    (48, 641,  213, 452),     # the row ends `82,7`, a rate with no percent sign
    (53, 680,  280, 580),
    (55, 764,  295, 625),     # the label stack puts the value seven lines up
    (58, 753,  318, 702),
    # LABELS ABOVE VALUES, unchanged by this reader.
    (62, 725,  390, 828),
    (70, 766,  540, 1309),
    (96, 730,  1115, 2476),
])
def test_banner_reads_both_layouts(n, isolated, recovered, deaths):
    got, _, _ = B.extract(pdf(n))
    assert got.get("patients_isolated") == isolated
    assert got.get("cumul_recovered") == recovered
    assert got.get("cumul_deaths") == deaths


@needs_pdfs
@pytest.mark.parametrize("n", [16, 17])
def test_suspects_in_isolation_is_not_the_ward_census(n):
    """Sitreps 016 and 017 print `Cas suspects en isolement` -- 101 and 104,
    suspects only -- beside a separate `Cas confirmés actifs` tile, and print
    no ward total at all. The all-patients wording arrives with sitrep 018.
    Reading either as the census would open the series with a sub-count."""
    got, why, labels = B.extract(pdf(n))
    assert got.get("patients_isolated") is None
    assert "Cas suspects en isolement" in labels["patients_isolated"]
    assert any("not the ward census" in w for w in why)


@needs_pdfs
def test_sitrep_007_recovery_tile_is_nd():
    """A missing marker is not a zero, in either layout."""
    got, why, _ = B.extract(pdf(7))
    assert got.get("cumul_recovered") is None
    assert got.get("cumul_deaths") == 6
    assert any("cumul_recovered" in w for w in why)


@needs_pdfs
def test_the_label_stack_is_reassembled_across_interleaved_lines():
    """Sitrep 055 prints `Nombre cumulé` two lines above `des guéris`, with a
    neighbouring tile's `jour` between them. The label decides whether a tile
    is the quantity wanted, so it has to be read whole."""
    _, _, labels = B.extract(pdf(55))
    assert labels["cumul_recovered"] == "Nombre cumulé des guéris"
    assert labels["patients_isolated"] == "Patients en isolement - hospitalisation"


@needs_pdfs
def test_sitrep_061_banner_and_occupancy_disagree_and_the_table_wins():
    """The page contradicts itself: the headline tile reads 737 while its own
    province split (544 + 188 + 4) and the occupancy table's `Fin J` row both
    read 736. The occupancy table keeps precedence -- it is the route that
    carries the confirmed/suspect split -- and the tile's figure is recorded
    rather than discarded."""
    got, why, _ = B.extract(pdf(61))
    assert got["patients_isolated"] == 736
    assert any("front-page tile says 737" in w for w in why)


def test_bare_gueris_label_is_gated_not_assumed():
    """`Guéris` without `cumul` could be a stock or the day's flow, and the
    page does not say. The gate publishes it only while the archive shows the
    two vintages are one series; a fabricated break must drop it."""
    good = pl.DataFrame({
        "sitrep": [17, 18, 19, 20],
        "cumul_recovered": [6, 6, 6, 7],
        "_recovery_label_is_bare": [True, True, False, False]})
    ok, why = B._bare_label_is_cumulative(good)
    assert ok and "both print 6" in why

    # The value jumps across the label change: the two vintages are no longer
    # shown to be the same series.
    broken = good.with_columns(pl.Series("cumul_recovered", [6, 6, 40, 41]))
    ok, why = B._bare_label_is_cumulative(broken)
    assert not ok and "not shown to be the same series" in why

    # The bare-label values fall: they cannot be a running total.
    falling = good.with_columns(pl.Series("cumul_recovered", [9, 6, 6, 7]))
    ok, why = B._bare_label_is_cumulative(falling)
    assert not ok and "non-decreasing" in why


@needs_pdfs
def test_the_two_stock_series_never_fall():
    """A cumulative that decreases is either a source revision -- which these
    two have never carried -- or a flow read as a stock. This is the standing
    check over the whole archive behind the bare-label gate."""
    pdfs = sorted(PDFS.glob("sitrep_*.pdf"))
    seen: dict[str, list] = {"cumul_recovered": [], "cumul_deaths": []}
    for p in pdfs:
        got, _, _ = B.extract(p)
        for k in seen:
            if got.get(k) is not None:
                seen[k].append((p.name, got[k]))
    for k, series in seen.items():
        falls = [(a, b) for a, b in zip(series, series[1:]) if b[1] < a[1]]
        assert not falls, f"{k} falls at {falls}"
    # EVERY report yields both, and the exceptions are named rather than
    # subtracted. This used to pin the two counts as literals, which meant a
    # green suite went red on the next `make fetch` for the sole reason that
    # the archive had grown -- and re-pinning a number that is SUPPOSED to
    # move trains the reader to bump it without asking whether a report
    # stopped yielding the field, which is the failure the check exists for.
    # Naming the exception keeps that failure detectable as the archive grows.
    # Each exception is a REPORT THAT DOES NOT PRINT THE FIGURE, and is named
    # here with the reason the page gives, so a tile that starts refusing for
    # some other reason cannot hide inside the set.
    NO_RECOVERIES = {
        "sitrep_001",   # prints `?` -- the first report did not yet know
        "sitrep_004",   # prints `Guéris du jour`, a daily flow, not the stock
        "sitrep_007",   # prints ND where the count goes
    }
    NO_DEATHS = {
        "sitrep_002",   # prints ND under `Décès confirmés`
    }
    missing = {k: sorted({p.name for p in pdfs} - {n for n, _ in v})
               for k, v in seen.items()}
    assert {n[:10] for n in missing["cumul_deaths"]} == NO_DEATHS, \
        missing["cumul_deaths"]
    assert {n[:10] for n in missing["cumul_recovered"]} == NO_RECOVERIES, \
        missing["cumul_recovered"]


@needs_pdfs
@pytest.mark.parametrize("n", [8, 18, 22])
def test_the_suspected_case_tile_is_not_published(n):
    """It is a running total, a stock and a daily flow across three vintages
    under near-identical wording; nothing observes any of them, and a geometry
    fix must not start emitting one as a side effect."""
    got, _, _ = B.extract(pdf(n))
    assert not any("suspect" in k for k in got), got

# Downward revisions: the carry-forward, its record, and the gates
#
# INSP revises its own cumulative downward -- Nord-Kivu goes 44 cases /
# 26 deaths on 10 June to 40 / 24 on 11 June -- and differencing turns that
# into a negative increment that no count likelihood can evaluate. The deficit
# is carried into later rows instead of being clipped away, and every case
# below is one of the two things that can go wrong with that: a total that
# moves, or a deficit that never discharges.
# --------------------------------------------------------------------------

import shutil                                                    # noqa: E402

import datetime as dt                                             # noqa: E402

import build_streams as BS                                        # noqa: E402

STREAMS = ROOT / "data" / "build" / "streams"
SERIES = ROOT / "data" / "build" / "series"
needs_streams = pytest.mark.skipif(
    not (STREAMS / "revisions.tsv").exists(),
    reason="the streams are not built; run `make build && make streams`")


def _released() -> list[BS.Written]:
    """Every stream file in the release, with how its rows relate to time.

    The resolution is read off the FILE rather than off a list here: a file
    carrying `days_covered` accumulates over a window and a file without one
    is a reading at an instant, which is the same distinction the build makes
    when it writes them. A hand-kept list would drift the first time a stream
    was added.
    """
    return [BS.Written(p, BS.STOCK if "days_covered"
                       not in BS.read_stream(p).columns else BS.DAILY)
            for p in sorted(STREAMS.glob("*.tsv"))
            if p.name != "revisions.tsv"]


def test_carry_forward_leaves_no_negative_and_moves_no_total():
    """The two properties the whole scheme rests on, on the real shape:
    Nord-Kivu's 11 June cumulative falls by 4, and 13 June's 22 pays it."""
    emitted, outstanding = BS.carry_forward([3, -4, 0, 22])
    assert emitted == [3, 0, 0, 18]
    assert sum(emitted) == sum([3, -4, 0, 22])
    assert min(emitted) == 0 and outstanding[-1] == 0


def test_carry_forward_is_not_clipping():
    """Clipping `[-4, 9]` gives 9 against a cumulative that moved 5, so the
    stream would permanently carry the four cases the source withdrew."""
    emitted, _ = BS.carry_forward([-4, 9])
    assert emitted == [0, 5] and sum(emitted) == 5


def test_a_deficit_larger_than_the_next_row_keeps_going():
    """Haut-Uélé's -6 of 18 July is not repaid until 22 July, across two days
    that report nothing and one that reports 5."""
    emitted, outstanding = BS.carry_forward([-6, 0, 0, 5, 6])
    assert emitted == [0, 0, 0, 0, 5]
    assert outstanding == [6, 6, 6, 1, 0]
    assert sum(emitted) == 5


def test_an_undischarged_deficit_is_reported_not_swallowed():
    """A withdrawal on the last report has nothing left to come out of. The
    function does not hide it: the outstanding balance is still 3 at the end,
    which is what the build's gate reads."""
    emitted, outstanding = BS.carry_forward([10, -5, 2])
    assert emitted == [10, 0, 0]
    assert outstanding[-1] == 3
    assert sum(emitted) == sum([10, -5, 2]) + 3      # short by exactly the carry


def test_negative_values_reads_the_published_file(tmp_path):
    """The non-negativity gate reads back off disk, so it covers a column that
    never passed through the carry -- a stock reading, or one added later."""
    good = tmp_path / "cases_x.tsv"
    good.write_text("time\tcases_x\n2026-06-01\t3\n")
    assert BS.negative_values([good]) == []
    bad = tmp_path / "cases_y.tsv"
    bad.write_text("time\tcases_y\n2026-06-01\t3\n2026-06-02\t-1\n")
    found = BS.negative_values([bad])
    assert len(found) == 1 and "cases_y = -1 at 2026-06-02" in found[0]


# -- the eight corrections in the corpus as it stands ----------------------

@needs_streams
def test_the_built_streams_publish_no_negative_count():
    every = [p for p in sorted(STREAMS.glob("*.tsv"))
             if p.name not in ("revisions.tsv", "uganda_exports.tsv")]
    assert every, "no streams found"
    assert BS.negative_values(every) == []


@needs_streams
def test_the_record_holds_every_revision_the_source_made():
    """Eight downward revisions exist in the corpus. Each opens a deficit on
    the row that differenced negative and closes it on a later row; none is
    left outstanding."""
    rev = pl.read_csv(STREAMS / "revisions.tsv", separator="\t",
                      infer_schema_length=None)
    opened = rev.filter(pl.col("raw") < 0)
    assert sorted(zip(opened["stream"], opened["time"], opened["raw"])) == [
        ("cases_daily_haut_uele", "2026-07-18", -6),
        ("cases_daily_ituri", "2026-07-12", -39),
        ("cases_daily_nord_kivu", "2026-06-11", -4),
        ("deaths_daily_haut_uele", "2026-07-18", -3),
        ("deaths_daily_ituri", "2026-07-12", -23),
        ("deaths_daily_nord_kivu", "2026-06-11", -2),
        ("deaths_daily_nord_kivu", "2026-07-12", -1),
        ("deaths_haut_uele", "2026-07-21", -1),
    ]
    # Every deficit discharges: the last row of each (stream, column) run
    # leaves nothing outstanding.
    last = (rev.group_by("stream", "column")
            .agg(pl.col("carry_after").last().alias("residual")))
    assert last.filter(pl.col("residual") != 0).is_empty()


#: Totals through sitrep 100. They move whenever the archive grows, and the
#: build itself already enforces the identity these assert -- `build_streams`
#: fails unless every stream's emitted total equals what the source's
#: cumulative moved. What these pin is the NUMBER, so that a change in it has
#: to be looked at and explained rather than absorbed.
#:
#: Ituri's two fell by 1,690 cases and 1,076 deaths when sitrep 098's wrapped
#: province rows were fixed. That is not the archive growing: 098 had been
#: reading Nord-Kivu's and Haut-Uélé's totals into Ituri, whose cumulative
#: then spiked to 6,200 and fell back to 3,487 on 099, and the carry that
#: absorbs a downward revision published the spike. 6 249 - 4 559 = 1 690 is
#: exactly the province residual that report was failing by.
#:
#: Ituri's cases then ROSE by 18, from 4 559 to 4 577, when sitrep 004 was
#: admitted to the archive. The stream is what the source's cumulative MOVED,
#: so it is measured from the earliest report that states a level: the base
#: was Ituri's 48 on sitrep 005 and is now its 30 on sitrep 004, and 48 - 30
#: = 18 is the movement that had no earlier reading to be measured against.
#: Nord-Kivu's 711 is unchanged, because 004 and 005 both print 3 there.
@needs_streams
@pytest.mark.parametrize("stream, column", [
    ("cases_daily_ituri", "cases_ituri"),
    ("deaths_daily_ituri", "deaths_ituri"),
    ("cases_daily_nord_kivu", "cases_nord_kivu"),
    ("deaths_daily_nord_kivu", "deaths_nord_kivu"),
    ("cases_daily_haut_uele", "cases_haut_uele"),
    ("deaths_daily_haut_uele", "deaths_haut_uele"),
    ("cases_haut_uele", "cases_haut_uele"),
    ("deaths_haut_uele", "deaths_haut_uele"),
])
def test_a_corrected_stream_still_totals_the_source_movement(stream, column):
    """The point of carrying rather than clipping: the corrected stream sums
    to exactly what the source's cumulative moved, unchanged by the fix.

    CHECKED AGAINST THE BUILD'S OWN ACCOUNTING, NOT A PINNED LITERAL. This was
    eight hardcoded totals, and every one went red on the next `make fetch`
    for the sole reason that the source had published another report -- which
    is the quantity the test is ABOUT. Re-pinning a number that is supposed to
    move trains the reader to bump it without asking whether the carry still
    discharges, which is the failure this exists to catch.

    What it can and cannot see, stated plainly: `source_delta` is computed by
    the build from the panel, and the sum here is read back off the EMITTED
    FILE, so this catches the two disagreeing -- a carry that did not
    discharge, a row dropped or written twice. It is not an independent
    recomputation of the movement, and it does not pretend to be; the panel
    aggregation it would have to duplicate is production code, and a test that
    re-runs the code it is testing proves nothing. The independent check on the
    movement itself is the extraction identity, which is gated in `make build`.
    """
    meta = json.loads((STREAMS / "meta.json").read_text())
    recon = meta["reconciliation"][stream]
    d = pl.read_csv(STREAMS / f"{stream}.tsv", separator="\t",
                    infer_schema_length=None, null_values="NA")
    emitted = int(d[column].sum())
    assert emitted == recon["source_delta"], (
        f"{stream} sums to {emitted} but the build recorded the source's "
        f"cumulative moving {recon['source_delta']}")
    assert recon["carry_residual"] == 0, (
        f"{stream} left {recon['carry_residual']} of a downward revision "
        f"undischarged at the end of the series")


# -- the synthetic province whose revision never discharges ----------------

PANEL_COLUMNS = ["sitrep", "date", "zone_reported", "province_printed", "level",
                 "table", "page", "cum_cases", "cum_deaths", "new_cases",
                 "deaths_community", "deaths_treatment_centre", "deaths_total",
                 "suspected", "new_suspected", "suspected_deaths", "contacts"]


def _synthetic_panel(path, ituri_cases, ituri_deaths):
    """A three-province panel with one zone each, over four report days.

    Enough of the real shape for the build to run end to end: a leading
    province row hands its name to the zone beneath it, and a national row
    carries the sum, which is what the national streams read.
    """
    rows = []
    dates = ["2026-05-20", "2026-05-21", "2026-05-22", "2026-05-23"]
    for i, (date, ic, idd) in enumerate(zip(dates, ituri_cases, ituri_deaths)):
        o = i + 1
        for prov, zone, c, dth in (("Ituri", "Bunia", ic, idd),
                                   ("Nord-Kivu", "Katwa", o, o),
                                   ("Haut-Uélé", "Wamba", o, o)):
            rows.append(dict(sitrep=5 + i, date=date, zone_reported=prov,
                             level="province", cum_cases=c, cum_deaths=dth))
            rows.append(dict(sitrep=5 + i, date=date, zone_reported=zone,
                             level="zone", cum_cases=c, cum_deaths=dth))
        rows.append(dict(sitrep=5 + i, date=date, zone_reported="TOTAL",
                         level="national", cum_cases=ic + 2 * o,
                         cum_deaths=idd + 2 * o))
    d = pl.DataFrame(rows)
    for c in PANEL_COLUMNS:
        if c not in d.columns:
            d = d.with_columns(pl.lit(None).alias(c))
    d.select(PANEL_COLUMNS).write_csv(path)


def _run_build(monkeypatch, panel, out_dir, *extra):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sys, "argv", [
        "build_streams.py", "--panel", str(panel),
        "--geojson", str(ROOT / "data/raw/health_zones.geojson"),
        "--population", str(ROOT / "data/raw/zone_population.csv"),
        "--out-dir", str(out_dir), *extra])
    BS.main()


needs_pdftotext = pytest.mark.skipif(
    shutil.which("pdftotext") is None,
    reason="pdftotext is not installed; the build records its version")


@needs_pdftotext
def test_the_build_stops_when_a_revision_never_discharges(monkeypatch, tmp_path):
    """A withdrawal on the LAST report has no later increment to come out of.

    Ituri's cumulative runs 10, 20, 30 and then the source revises it to 5,
    with nothing after it. The emitted total is then short of the cumulative's
    movement by exactly the outstanding deficit -- part of a revision silently
    dropped, which is the failure this gate exists for. It must stop the build
    and name the stream, not round the residue away.

    The two resolutions are short by different amounts, and both are right:
    the daily row for 23 May differences to -25 with nothing after it, while
    all four days fall in one week whose net movement is -5. Each file's
    residual is the shortfall in that file.
    """
    panel = tmp_path / "panel.csv"
    _synthetic_panel(panel, [10, 20, 30, 5], [2, 4, 6, 1])
    out = tmp_path / "streams"
    with pytest.raises(SystemExit) as e:
        _run_build(monkeypatch, panel, out)
    msg = str(e.value)
    assert "NEVER DISCHARGED" in msg
    assert "cases_daily_ituri:cases_ituri (25 outstanding)" in msg
    assert "cases_ituri:cases_ituri (5 outstanding)" in msg
    # It fails the reconciliation identity too, because those are the same
    # cases: what is emitted no longer sums to what the cumulative moved.
    assert "DO NOT RECONCILE" in msg
    # The record is written BEFORE the gate, so a failing build still leaves
    # the evidence of what it could not discharge.
    rev = pl.read_csv(out / "revisions.tsv", separator="\t",
                      infer_schema_length=None)
    itu = rev.filter((pl.col("stream") == "cases_daily_ituri")
                     & (pl.col("time") == "2026-05-23"))
    assert itu.height == 1 and itu["raw"][0] == -25 and itu["carry_after"][0] == 25


@needs_pdftotext
def test_the_same_build_passes_when_the_revision_discharges(monkeypatch,
                                                            tmp_path):
    """The control: move the withdrawal one report earlier, so the last
    report's increment pays it off. Nothing negative is published, the deficit
    is recorded and discharged, and the emitted total equals the movement."""
    panel = tmp_path / "panel.csv"
    _synthetic_panel(panel, [10, 20, 5, 40], [2, 4, 1, 8])
    out = tmp_path / "streams"
    _run_build(monkeypatch, panel, out)             # does not raise
    d = pl.read_csv(out / "cases_daily_ituri.tsv", separator="\t",
                    infer_schema_length=None)
    assert d["cases_ituri"].to_list() == [10, 0, 20]
    assert int(d["cases_ituri"].sum()) == 30        # 40 - 10, the movement
    rev = pl.read_csv(out / "revisions.tsv", separator="\t",
                      infer_schema_length=None)
    itu = rev.filter(pl.col("stream") == "cases_daily_ituri")
    assert itu["raw"].to_list() == [-15, 35]
    assert itu["carry_after"].to_list() == [15, 0]
    assert BS.negative_values([p for p in sorted(out.glob("*.tsv"))
                              if p.name != "revisions.tsv"]) == []


@needs_pdftotext
def test_an_untouched_build_still_writes_the_empty_record(monkeypatch, tmp_path):
    """A clean build and a missing artefact must not look the same, so the
    header is written even when there is nothing to record."""
    panel = tmp_path / "panel.csv"
    _synthetic_panel(panel, [10, 20, 30, 40], [2, 4, 6, 8])
    out = tmp_path / "streams"
    _run_build(monkeypatch, panel, out)
    rev = pl.read_csv(out / "revisions.tsv", separator="\t",
                      infer_schema_length=None)
    assert rev.height == 0
    assert rev.columns == ["stream", "column", "time", "raw", "emitted",
                           "carry_after", "flags"]


# --------------------------------------------------------------------------
# THE ACCUMULATION WINDOW: A SCORED ROW SITS WHERE ITS `days_covered` SAYS
#
# The engines these files are written for accumulate a modelled flow from the
# previous ROW of the stream to this one, and a row carrying no observation
# still resets that accumulator -- the reset is the row being present, not the
# row being scored. So the file's claim about its own window is checkable:
#
#     for every SCORED row:  time - (previous row's time) == days_covered
#
# It did not hold before this release. `care_admissions_nord_kivu` carried
# 1 June and 19 July in consecutive rows under a `days_covered` of 1, asking a
# model to explain 48 days of accumulated admissions with one day of them, and
# nothing caught it: the counts were right, the totals reconciled, every
# column was populated. The fix is a row on every report day the file spans,
# holding `NA` where the source said nothing.
# --------------------------------------------------------------------------

def _flow_file(path, rows, columns=("count",)):
    """A minimal published flow file, for testing the gates that read one.

    `rows` is `(time, days_covered, n_report_days, *values)`. Written through
    the same null token the build writes, so a test cannot pass against a file
    spelled differently from the ones that ship.
    """
    cols = {"time": [r[0] for r in rows],
            "days_covered": [r[1] for r in rows],
            "n_report_days": [r[2] for r in rows]}
    for i, c in enumerate(columns):
        cols[c] = [r[3 + i] for r in rows]
    (pl.DataFrame(cols)
     .select(["time", *columns, "days_covered", "n_report_days"])
     .write_csv(path, separator="\t", null_value=BS.NULL_TOKEN))
    return [BS.Written(path, BS.DAILY)]


def test_the_gate_catches_the_defect_that_shipped(tmp_path):
    """The exact shape `care_admissions_nord_kivu` shipped at r4: two scored
    rows 48 days apart, each claiming a one-day window. A model would score
    the second against 48 days of accumulated flow."""
    p = tmp_path / "care_admissions_nord_kivu.tsv"
    bad = BS.accumulation_windows(_flow_file(p, [
        ("2026-06-01", 1, 1, 3), ("2026-07-19", 1, 1, 5)],
        columns=("admissions_nord_kivu",)))
    assert len(bad) == 1
    assert "2026-07-19" in bad[0] and "48 day(s) after" in bad[0]


def test_the_gate_passes_once_the_hole_is_a_row(tmp_path):
    """The control: the same two observations with the report days between
    them present as `NA` rows. Nothing scored changed -- the counts are the
    same 3 and 5 at the same two times -- but every scored row now sits one
    day after the row before it."""
    p = tmp_path / "care_admissions_nord_kivu.tsv"
    written = _flow_file(p, [("2026-06-01", 1, 1, 3),
                             ("2026-06-02", 1, 0, None),
                             ("2026-06-03", 1, 0, None),
                             ("2026-06-04", 1, 1, 5)],
                         columns=("admissions_nord_kivu",))
    assert BS.accumulation_windows(written) == []
    assert BS.unscored_rows(written) == []


def test_an_unscored_row_is_not_read_as_an_observed_zero(tmp_path):
    """A 0 in a hole is a different datum from a hole: it says the source
    looked and counted none. The gate refuses a row marked unscored that
    carries a value at all."""
    p = tmp_path / "care_admissions_ituri.tsv"
    bad = BS.unscored_rows(_flow_file(p, [
        ("2026-06-01", 1, 1, 3), ("2026-06-02", 1, 0, 0)],
        columns=("admissions_ituri",)))
    assert len(bad) == 1 and "marked unscored" in bad[0]


def test_a_scored_row_may_not_have_a_hole_in_it(tmp_path):
    """The other half of present-together-or-hole: a row `n_report_days`
    calls scored must carry every one of its observations."""
    p = tmp_path / "care_admissions_ituri.tsv"
    bad = BS.unscored_rows(_flow_file(p, [
        ("2026-06-01", 1, 1, 3), ("2026-06-02", 1, 1, None)],
        columns=("admissions_ituri",)))
    assert len(bad) == 1 and "marked scored" in bad[0]


@pytest.mark.parametrize("placeholder, ok", [(1, True), (0, False),
                                             (None, False)])
def test_a_divisor_stays_positive_on_a_row_nobody_scores(tmp_path, placeholder,
                                                         ok):
    """`tests_*` is divided by, and a division is evaluated whether or not the
    row is scored -- so an empty or zero cell there is a division by zero in a
    term nobody meant to compute. 1 is the placeholder; 0 and empty are not."""
    p = tmp_path / "lab_daily_ituri.tsv"
    bad = BS.unscored_rows(_flow_file(p, [
        ("2026-06-01", 1, 1, 4, 40), ("2026-06-02", 1, 0, None, placeholder)],
        columns=("positives_ituri", "tests_ituri")))
    assert (bad == []) is ok
    if not ok:
        assert "divisor tests_ituri" in bad[0]


def test_a_binomial_size_goes_empty_with_its_numerator(tmp_path):
    """`deaths_split_*` is passed as a binomial `n`, never divided by, and
    `binomial(n = NA)` is unconstructible -- so an engine turns the row into a
    hole, which is what an unscored row should be. Both columns empty is
    therefore the accepted shape here, and a placeholder would be a fabricated
    trial count for no gain."""
    p = tmp_path / "community_deaths_daily_ituri.tsv"
    written = _flow_file(p, [("2026-06-01", 1, 1, 4, 9),
                             ("2026-06-02", 1, 0, None, None)],
                         columns=("community_deaths_ituri",
                                  "deaths_split_ituri"))
    assert BS.unscored_rows(written) == []
    assert BS.DENOMINATOR_OF["community_deaths"][1] == BS.BINOMIAL_SIZE


def test_a_two_column_stream_cannot_ship_without_naming_its_denominator(tmp_path):
    """The candidate set for a denominator is exactly the files with two
    observation columns, so a new one must not ship until someone has said
    which column is the total and what a model does with it."""
    p = tmp_path / "widgets_ituri.tsv"
    bad = BS.no_declared_denominator(_flow_file(p, [
        ("2026-06-01", 1, 1, 4, 40)], columns=("widgets_ituri", "gizmos_ituri")))
    assert len(bad) == 1 and "DENOMINATOR_OF" in bad[0]


def test_the_grid_is_calendar_days_so_every_row_covers_one_day():
    """A 24-hour figure covers one day however wide the silence behind it, and
    the accumulation window is set by the rows that exist. So every day between
    the first and last observation is a row, including days the archive holds
    no report for -- an NA row asserts only that the day existed and nobody
    reported this quantity, which the source does license.

    This REPLACED a report-day grid, which closed the gap only where the source
    published and left the days nobody published on widening the window.
    """
    got = BS.calendar_day_grid([dt.date(2026, 6, 1), dt.date(2026, 6, 5)])
    assert got == [dt.date(2026, 6, d) for d in (1, 2, 3, 4, 5)]


def test_the_grid_stops_at_the_streams_own_span():
    """A row before the first observation would claim the quantity was being
    reported and was empty; one after the last would claim the series is still
    running. Neither is something the file may assert."""
    got = BS.calendar_day_grid([dt.date(2026, 6, 2), dt.date(2026, 6, 4)])
    assert got == [dt.date(2026, 6, 2), dt.date(2026, 6, 3), dt.date(2026, 6, 4)]


def test_gridding_holes_a_row_and_fills_only_the_divisor():
    """One pass of the real function: the silent report day becomes a row with
    an empty numerator, `n_report_days` 0 and `n_report_days_silent` 1, and
    the divisor beside it carries the placeholder 1."""
    d = pl.DataFrame({"date": [dt.date(2026, 6, 1), dt.date(2026, 6, 3)],
                      "positives_ituri": [4, 6], "tests_ituri": [40, 60]})
    report = {dt.date(2026, 6, 1), dt.date(2026, 6, 2), dt.date(2026, 6, 3)}
    got = BS.on_calendar_day_grid(d, report, time_col="date",
                                  divisors=("tests_ituri",))
    assert got.height == 3
    assert got["n_report_days"].to_list() == [1, 0, 1]
    assert got["positives_ituri"].to_list() == [4, None, 6]
    assert got["tests_ituri"].to_list() == [40, 1, 60]
    assert got["days_covered"].to_list() == [1, 1, 1]
    assert got["n_report_days_silent"].to_list() == [0, 1, 0]


def test_the_two_kinds_of_hole_are_distinguishable_in_the_columns():
    """A day nobody published on and a day somebody published on without
    stating this quantity are different facts, and after the regrid the file
    separates them without a consumer needing the archive: both carry
    `n_report_days` 0, and only the second carries `n_report_days_silent` 1.
    """
    d = pl.DataFrame({"date": [dt.date(2026, 6, 1), dt.date(2026, 6, 4)],
                      "x": [1, 2]})
    # 2 June had a report that passed this quantity over; 3 June had none.
    report = {dt.date(2026, 6, 1), dt.date(2026, 6, 2), dt.date(2026, 6, 4)}
    got = BS.on_calendar_day_grid(d, report, time_col="date")
    assert got["n_report_days"].to_list() == [1, 0, 0, 1]
    assert got["n_report_days_silent"].to_list() == [0, 1, 0, 0]
    assert got["days_covered"].to_list() == [1, 1, 1, 1]


def test_an_observation_off_the_report_day_calendar_stops_the_build():
    """Every observation lands on a calendar grid by construction, so the
    check that still bites is an observation on a day the archive holds no
    report for: the calendar is wrong rather than the stream, and downstream
    it would surface as a negative silence count rather than as a message."""
    d = pl.DataFrame({"date": [dt.date(2026, 6, 1), dt.date(2026, 6, 2)],
                      "x": [1, 2]})
    with pytest.raises(SystemExit, match="the report-day calendar does not"):
        BS.on_calendar_day_grid(d, {dt.date(2026, 6, 1)}, time_col="date")


# -- the same three properties, on the files this build actually shipped ----

@needs_streams
def test_every_published_flow_stream_claims_the_window_it_sits_in():
    """The invariant, over the release. Read off the files, so it is a
    statement about what a consumer fits and not about the frames in memory."""
    assert BS.accumulation_windows(_released()) == []


@needs_streams
def test_no_published_unscored_row_is_malformed():
    assert BS.unscored_rows(_released()) == []


@needs_streams
def test_every_two_column_stream_names_its_denominator():
    assert BS.no_declared_denominator(_released()) == []


@needs_streams
def test_a_hole_carries_its_metadata_rather_than_being_a_bare_row():
    """A row that says WHY it is empty is strictly better than a hole, and
    nothing downstream reads these columns into a likelihood. Every NA row in
    the release carries its silence count, its source flags, and -- on the
    care ledger, which has one -- its `checks` verdict."""
    d = BS.read_stream(STREAMS / "care_admissions_nord_kivu.tsv")
    holes = d.filter(pl.col("n_report_days") == 0)
    assert holes.height > 0
    assert holes["admissions_nord_kivu"].null_count() == holes.height
    # Under the calendar grid a hole is one of TWO facts, and the column says
    # which: 1 where a report was published and passed this quantity over,
    # 0 where no report was published at all.
    assert set(holes["n_report_days_silent"].to_list()) <= {0, 1}
    assert holes["checks"].to_list() == ["unchecked"] * holes.height
    assert holes["flags"].null_count() == 0


@needs_streams
def test_a_hole_is_spelled_NA_on_disk_and_not_left_empty():
    """The token is load-bearing on both sides: an engine reads `NA` as a
    scheduled-but-unobserved time, and a consumer reading the file must
    declare it (`null_values="NA"`) or a hole comes back as a string."""
    text = (STREAMS / "care_admissions_nord_kivu.tsv").read_text()
    assert "\tNA\t" in text
    assert "\t\t" not in text


@needs_streams
@pytest.mark.parametrize("stream, column", [
    ("lab_daily_ituri", "tests_ituri"),
    ("lab_daily_nord_kivu", "tests_nord_kivu"),
    ("lab_daily_haut_uele", "tests_haut_uele"),
    ("lab_daily_national", "tests_national"),
])
def test_a_published_divisor_is_never_empty_or_zero(stream, column):
    d = BS.read_stream(STREAMS / f"{stream}.tsv")
    assert d[column].null_count() == 0
    assert d.filter(pl.col(column) == 0).height == 0


#: The stock files, and the reason each is one. A stock is a READING AT AN
#: INSTANT: it accumulates over no window, carries no `days_covered`, and a
#: 46-day gap in it is a reading taken 46 days later rather than a hole that
#: widens anything. Gridding one would add rows that assert a census was taken
#: and came back empty, which no report says. Derived from the build's own
#: declaration of which care families are stocks, so the list cannot drift
#: from the code that decides it.
STOCK_FILES = sorted(
    ["patients_isolated", "patients_isolated_confirmed", "cumul_recovered"]
    + [f"{f}_{p}" for f in sorted(BS.CARE_STOCK_FAMILIES)
       for p in ("ituri", "nord_kivu", "haut_uele", "national")])


@needs_streams
@pytest.mark.parametrize("stream", STOCK_FILES)
def test_a_stock_is_left_alone(stream):
    """No `days_covered`, no `n_report_days`, no hole, and the long gaps the
    source left are still there."""
    d = BS.read_stream(STREAMS / f"{stream}.tsv")
    assert "days_covered" not in d.columns
    assert "n_report_days" not in d.columns
    obs = [c for c in d.columns
           if c != "time" and c not in BS.METADATA_COLUMNS]
    for c in obs:
        assert d[c].null_count() == 0, f"{stream}:{c} has a hole in it"


@needs_streams
def test_the_care_census_keeps_the_gaps_the_source_left():
    """The sharpest case: Nord-Kivu's confirmed census has a 46-day gap. It is
    a reading 46 days later, not a widened window, and adding rows across it
    would invent readings the source never took."""
    d = BS.read_stream(STREAMS / "care_census_confirmed_nord_kivu.tsv")
    times = [dt.date.fromisoformat(t) for t in d["time"].to_list()]
    assert max(b - a for a, b in zip(times, times[1:])).days == 46


# --------------------------------------------------------------------------
# THE GENERATED DATA DICTIONARY
#
# `data/build/streams/README.md` ships with the vendored data and says, per
# published file, what it measures and what it covers. Two things can go wrong
# with a generated document, and both are silent: it can omit a file that
# shipped, and it can state a span that is not the span of the file it names.
# The third case is the one the register exists for -- a new stream arriving
# with no sentence describing it -- which must stop the build rather than
# ship an undocumented file.
# --------------------------------------------------------------------------

FAMILIES = ROOT / "registers" / "stream_families.tsv"
DICTIONARY = STREAMS / "README.md"
needs_dictionary = pytest.mark.skipif(
    not DICTIONARY.exists(),
    reason="the streams are not built; run `make build && make streams`")


def _dictionary_rows(path) -> dict[str, list[str]]:
    """The document's table rows, keyed on the filename each one describes.

    A row is a markdown table line whose first cell is a backticked filename,
    which is what separates it from the header, the rule beneath it and the
    prose around it.
    """
    rows = {}
    for line in path.read_text().splitlines():
        if line.startswith("| `"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows[cells[0].strip("`")] = cells
    return rows


@pytest.mark.parametrize("stem, family, place", [
    ("cases_ituri", "cases", "ituri"),
    ("cases_daily_ituri", "cases", "ituri"),
    ("community_deaths_daily_nord_kivu", "community_deaths", "nord_kivu"),
    ("deaths_national", "deaths", "national"),
    ("lab_daily_haut_uele", "lab", "haut_uele"),
    ("lab_national", "lab", "national"),
    # No place suffix at all: a front-page dashboard reading, national by
    # construction. `patients_isolated_confirmed` must not be split on the
    # shorter `patients_isolated` that is also a family here.
    ("patients_isolated", "patients_isolated", "national"),
    ("patients_isolated_confirmed", "patients_isolated_confirmed",
     "national"),
    ("cumul_recovered", "cumul_recovered", "national"),
])
def test_the_family_is_what_is_left_after_place_and_resolution(stem, family,
                                                               place):
    """Documentation is keyed on the family, so the split has to be exact:
    eight files publish the case family, and one wrong split would either
    silently invent a family or document a stream as the wrong quantity."""
    assert BS.stream_identity(stem) == (family, place)


def test_every_family_the_register_names_is_reachable():
    """A register row no filename can ever produce is a sentence that will
    never be printed, and would hide a typo in the key."""
    families = BS.load_families(FAMILIES)
    for family in families:
        assert BS.stream_identity(family) == (family, "national"), family


@needs_dictionary
def test_every_published_file_is_documented():
    """Nothing ships undescribed. Every TSV in the release appears either as
    a row of a family table or by name in one of the two sections for the
    files that are not observation streams."""
    rows = _dictionary_rows(DICTIONARY)
    text = DICTIONARY.read_text()
    for path in sorted(STREAMS.glob("*.tsv")):
        if path.name in ("revisions.tsv", "uganda_exports.tsv"):
            assert f"`{path.name}`" in text
            continue
        assert path.name in rows, f"{path.name} shipped but is not documented"
    assert len(rows) == len(list(STREAMS.glob("*.tsv"))) - 2


@needs_dictionary
def test_the_stated_range_is_the_range_of_the_file():
    """The spans are read off the files rather than out of `meta.json`, whose
    reconciliation block carries no dates for the community-death or
    laboratory streams. This asserts what the document claims against what
    the file it names actually holds.

    OBS AND ROWS ARE TWO NUMBERS, and the document states both. A flow file
    has a row on every report day it spans and holes the ones the source said
    nothing on, so counting rows as observations would report a stream printed
    on nine days out of thirty-one as having thirty-one. `Obs` is the scored
    count, `NA rows` the holes, and the stated span runs over the SCORED
    times -- the first and last day the source actually stated the quantity.
    """
    rows = _dictionary_rows(DICTIONARY)
    assert rows
    for name, cells in rows.items():
        _, _, _, n_obs, n_na, first, last, _ = cells
        d = BS.read_stream(STREAMS / name)
        scored = (d.filter(pl.col("n_report_days") > 0)
                  if "n_report_days" in d.columns else d)
        times = sorted(str(x) for x in scored["time"].to_list())
        assert int(n_obs) == scored.height, name
        assert (0 if n_na == "—" else int(n_na)) == d.height - scored.height, name
        assert (first, last) == (times[0], times[-1]), name


@needs_dictionary
def test_metadata_columns_are_never_listed_as_observations():
    """`days_covered` states how wide a row's window is and `n_report_days`
    how much of it the source reported on. A consumer that fitted either as a
    count would be fitting the calendar."""
    for name, cells in _dictionary_rows(DICTIONARY).items():
        listed = cells[-1]
        for meta in BS.METADATA_COLUMNS:
            assert f"`{meta}`" not in listed, f"{name} lists {meta}"


@needs_pdftotext
def test_an_unregistered_family_stops_the_build(monkeypatch, tmp_path):
    """A stream with no sentence describing it must not be able to ship.

    The register is doctored to drop `deaths` while the build still writes
    eight death files. The build stops, names every one of them, and says
    which family is missing -- and it does not leave a data dictionary behind
    that is silently missing a quarter of the release.
    """
    register = tmp_path / "families.tsv"
    register.write_text("\n".join(
        line for line in FAMILIES.read_text().splitlines()
        if not line.startswith("deaths\t")) + "\n")
    panel = tmp_path / "panel.csv"
    _synthetic_panel(panel, [10, 20, 30, 40], [2, 4, 6, 8])
    out = tmp_path / "streams"
    with pytest.raises(SystemExit) as e:
        _run_build(monkeypatch, panel, out, "--families", str(register))
    msg = str(e.value)
    assert "A PUBLISHED STREAM IS UNDOCUMENTED" in msg
    assert "deaths_ituri.tsv (family `deaths`)" in msg
    assert "deaths_daily_national.tsv (family `deaths`)" in msg
    # The cases family is registered, so it is not among the complaints.
    assert "cases_ituri.tsv" not in msg
    assert not (out / "README.md").exists()


@needs_pdftotext
def test_the_same_run_that_writes_the_streams_writes_the_dictionary(
        monkeypatch, tmp_path):
    """It travels with the data, so it is produced by the build rather than
    by a separate step that could be skipped or run against another vintage.

    This build has no laboratory or dashboard inputs, so those families are
    absent from the document entirely -- a section with no files is omitted,
    not printed empty.
    """
    panel = tmp_path / "panel.csv"
    _synthetic_panel(panel, [10, 20, 30, 40], [2, 4, 6, 8])
    out = tmp_path / "streams"
    _run_build(monkeypatch, panel, out)
    doc = out / "README.md"
    rows = _dictionary_rows(doc)
    assert set(rows) == {p.name for p in out.glob("*.tsv")
                         if p.name != "revisions.tsv"}
    text = doc.read_text()
    assert "Data date 2026-05-23" in text          # the panel's newest report
    assert "## Laboratory testing effort" not in text
    assert "## Cumulative recoveries" not in text
    # The carry record is written even when empty, and documented either way.
    assert "no rows yet, header only" in text
    # No uganda_exports was named, so no section claims one shipped.
    assert "uganda_exports" not in text


# --------------------------------------------------------------------------
# THE THREE REPORTS INSP DOES NOT SERVE
#
# SitReps 001, 002 and 004 are held from a secondary archive, their PDFs are
# committed, and `registers/external_sitreps.tsv` is the only thing that says
# so. Everything below pins a property that would otherwise fail silently:
# the register applying, the committed bytes being the ones it was written
# about, the archive reconciliation admitting them without going soft, and the
# date adjudication that keeps sitrep 004 off sitrep 005's day.
# --------------------------------------------------------------------------

import csv as _csv                                                # noqa: E402

import fetch_sitrep_pdfs as F                                     # noqa: E402
import lib.report_date as RD                                      # noqa: E402
from lib.report_date import (load_external_sitreps,               # noqa: E402
                             printed_dates, report_key,
                             verify_external)

EXTERNAL = ROOT / "registers" / "external_sitreps.tsv"
MANIFEST = ROOT / "data" / "raw" / "sitrep_pdfs.manifest.tsv"
INDEX = ROOT / "data" / "raw" / "insp_sitrep_index.tsv"


def test_the_external_register_parses():
    reg = load_external_sitreps(EXTERNAL)
    assert {r.sitrep for r in reg.values()} == {1, 2, 4}
    assert set(reg) == {"sitrep_001_2026-05-14.pdf",
                        "sitrep_002_2026-05-17.pdf",
                        "sitrep_004_2026-05-18.pdf"}
    for r in reg.values():
        assert len(r.sha256) == 64
        assert r.upstream_repo.startswith("https://")
        assert r.upstream_path and r.upstream_commit and r.retrieved
        # The note is what a future reader has instead of a fetch log.
        assert len(r.note) > 40


@needs_pdfs
def test_the_committed_pdfs_are_the_bytes_the_register_names():
    """These files have no upstream this project can re-fetch from, so the
    committed bytes ARE the source and the register is the only check on them.

    It also catches the one way the archive can now be assembled wrongly: if
    `data/raw/sitrep_pdfs` is symlinked in as a whole directory, these three
    resolve to a shared copy rather than to what git holds.
    """
    for name, r in load_external_sitreps(EXTERNAL).items():
        f = PDFS / name
        assert f.is_file(), f"{name} is not held"
        assert not f.is_symlink(), (
            f"{name} is a symlink; the three committed reports must be real "
            f"files, or a working copy can lose them without git noticing")
        verify_external(f, r)      # raises SystemExit on a mismatch


# --------------------------------------------------------------------------
# Reference tables are published, and are not streams
#
# A consumer asked for the burial-alert rows so it could pool them itself
# rather than take our pooled figure on trust. They were written to
# data/build/series/, which is the internal audit layer and which no consumer
# copies, so the rows were promised and never delivered. They are published
# now -- inside the directory consumers already take, and outside the stream
# dictionary, whose promises about time grids and coverage they cannot keep.
# --------------------------------------------------------------------------


@needs_pdfs
def test_the_reference_tables_are_published_beside_the_streams():
    import json
    d = ROOT / "data/build/streams/reference"
    meta = json.loads((ROOT / "data/build/streams/meta.json").read_text())
    assert set(meta["reference"]) == {f"reference/{n}"
                                      for n in BS.REFERENCE_TABLES}
    for name in BS.REFERENCE_TABLES:
        f = d / name
        assert f.is_file(), f"{name} is described in meta but not written"
        rows = len(f.read_text().splitlines()) - 1
        assert rows == meta["reference"][f"reference/{name}"]["rows"] > 0


@needs_pdfs
def test_reference_tables_are_not_in_the_stream_dictionary():
    """A stream is time-indexed and carries a coverage contract. These are a
    province-day ledger and a delay distribution, and listing them as streams
    would make the dictionary's promises false for two of its entries."""
    import json
    meta = json.loads((ROOT / "data/build/streams/meta.json").read_text())
    for name in BS.REFERENCE_TABLES:
        assert name not in meta["streams"]
        assert f"reference/{name}" not in meta["streams"]
    # and they must not be picked up as streams by a glob over the directory
    assert not list((ROOT / "data/build/streams").glob(
        "reference*.tsv")), "a reference table sits where a stream glob finds it"


@needs_pdfs
def test_the_published_rows_are_the_rows_we_pooled():
    """meta['swab_coverage'] is our pooling of burial_alerts.tsv. If the two
    ever disagree, the summary is a number with no rows behind it."""
    import json
    import polars as pl
    meta = json.loads((ROOT / "data/build/streams/meta.json").read_text())
    d = pl.read_csv(ROOT / "data/build/streams/reference/burial_alerts.tsv",
                    separator="\t", infer_schema_length=20000)
    u = d.drop_nulls(["alerts_total", "bodies_swabbed"]).filter(
        pl.col("alerts_total") > 0)
    for prov, v in meta["swab_coverage"]["by_province"].items():
        q = u.filter(pl.col("province") == prov)
        assert int(q["bodies_swabbed"].sum()) == v["bodies_swabbed"], prov
        assert int(q["alerts_raised"].sum() if "alerts_raised" in q.columns
                   else q["alerts_total"].sum()) == v["alerts_raised"], prov
        assert q.height == v["province_days"], prov


# --------------------------------------------------------------------------
# The onset-to-report delay
#
# `cases_*` is indexed by report date; a model's projected quantity is a
# confirmation event. The gap between the two instants is this distribution,
# and the one way to get it badly wrong is to pool it: the May and June
# cohorts are the epidemic's early history being reconstructed months later,
# not a reporting delay, and pooling them doubles the routine figure.
# --------------------------------------------------------------------------

import build_reporting_delay as BRD                               # noqa: E402


@needs_pdfs
def test_the_delay_is_reported_per_cohort_and_never_pooled():
    import json
    d = json.loads((ROOT / "data/build/series/reporting_delay.json").read_text())
    months = [c["onset_month"] for c in d["by_onset_month"]]
    assert months == sorted(months) and len(months) >= 4
    assert "mean_delay_days" not in d, "a pooled mean would describe no cohort"
    # The early cohorts must not be mistaken for a reporting delay: they are
    # far slower than the routine ones, which is the whole reason for the split.
    by = {c["onset_month"]: c for c in d["by_onset_month"]}
    assert by["2026-05"]["mean_delay_days"] > 3 * by["2026-07"]["mean_delay_days"]


@needs_pdfs
def test_the_usable_cohort_is_settled_and_recent():
    """The early cohorts are settled precisely because they are old. Picking on
    settledness alone would return retrospective reconstruction as the routine
    delay, which is how a fixed follow-up threshold first got this wrong."""
    import json
    d = json.loads((ROOT / "data/build/series/reporting_delay.json").read_text())
    by = {c["onset_month"]: c for c in d["by_onset_month"]}
    u = d["usable_cohort"]
    assert u and by[u]["settled"]
    assert u >= "2026-07", f"{u} is retrospective reconstruction, not a delay"
    newer = [m for m in by if m > u]
    assert all(not by[m]["settled"] for m in newer), \
        "a settled cohort newer than the usable one should have been chosen"


@needs_pdfs
def test_the_delay_distribution_is_a_distribution():
    import polars as pl
    d = pl.read_csv(ROOT / "data/build/series/reporting_delay.csv")
    for m in set(d["onset_month"].to_list()):
        s = d.filter(pl.col("onset_month") == m).sort("delay_days")
        assert abs(s["share"].sum() - 1.0) < 1e-3, m
        assert abs(s["cumulative_share"].to_list()[-1] - 1.0) < 1e-3, m
        assert s["cumulative_share"].is_sorted(), m


# --------------------------------------------------------------------------
# The safe-burial pillar's alert ledger
#
# A death never swabbed can never be confirmed, so bodies-swabbed over
# alerts-raised bounds what the confirmed-death series can see. Two things
# make this parse fragile and both are pinned here: the carried-over alert
# count appears in three constructions, two of which put it inside the total
# and one of which adds to it; and the laboratory section a page earlier uses
# the word "swab" for a specimen arriving at a bench rather than a body
# reached by a burial team.
# --------------------------------------------------------------------------

import extract_burial_alerts as BA                                # noqa: E402


def test_the_three_carried_over_constructions_are_read_correctly():
    add = BA.parse("Les équipes EDS ont enregistré 72 alertes de décès du jour "
                   "et 23 reports, pour 76 EDS réalisés (80 %) et 69 corps "
                   "prélevés par swab.")
    assert add["alerts_total"] == 95 and add["alert_construction"].startswith("et")
    assert add["bodies_swabbed"] == 69 and add["eds_done"] == 76
    # and the report's own 80% licenses it: 76/95 = 80.0
    assert BA.check(add)[0] == "ok"

    inside = BA.parse("Sur 93 alertes de décès reçues, dont 13 reports de la "
                      "veille, 60 corps ont été prélevés par swab sur 76 pris "
                      "en charge (78,9 %) et 72 EDS réalisés (77,4 %).")
    assert inside["alerts_total"] == 93, "dont must not be added"
    assert inside["bodies_reached"] == 76 and inside["bodies_swabbed"] == 60

    # The parenthetical reads as though it could be either. The source settles
    # it: 36 swabbed plus 1 failure is 37, the stated total, not 37 + 15.
    paren = BA.parse("le pilier EDS a reçu 37 alertes (15 reports) : 36 corps "
                     "swabés, un échec de swab et 34 EDS réalisés.")
    assert paren["alerts_total"] == 37, "the parenthetical is inside, not added"


def test_all_of_them_swabbed_is_not_lost():
    """A 100% day stated in words rather than digits. Dropping it would bias
    the pooled ratio downward."""
    r = BA.parse("Sur 6 alertes de décès reçues (3 à Isiro et 3 à Wamba), "
                 "toutes ont été prélevés par swab et 6 EDS réalisés.")
    assert r["alerts_total"] == 6 and r["bodies_swabbed"] == 6


def test_a_percentage_our_reading_cannot_reproduce_is_refused():
    r = BA.parse("Sur 80 alertes de décès, 12 corps ont été prélevés par swab "
                 "et 70 EDS réalisés (99 %).")
    status, why = BA.check(r)
    assert status == "refused", why


def test_the_laboratory_section_is_not_read_as_burial_rows():
    """`Bas-Uélé : 1 swab reçu et testé` is a specimen arriving at a bench, not
    a body a burial team reached. Scoped out by section, not by wording."""
    lab = ("1.3. Laboratoire • Bas-Uélé : 1 swab reçu et testé, le résultat "
           "est revenu positif. 1.4. Prévention et Contrôle de l'Infection "
           "(PCI/EDS) • Au Bas-Uélé, 3 corps swabés. "
           "1.5. Prise en charge holistique")
    got = {prov: BA.parse(sent) for sent, prov in BA.sentences(lab)
           if prov and BA.parse(sent)}
    assert "bas_uele" in got
    assert got["bas_uele"]["bodies_swabbed"] == 3, got["bas_uele"]["quote"]


@needs_pdfs
def test_swab_coverage_reaches_meta_per_province_and_is_never_pooled():
    import json
    meta = json.loads((ROOT / "data/build/streams/meta.json").read_text())
    sc = meta.get("swab_coverage")
    assert sc and sc["by_province"], "swab coverage is not published"
    for prov, v in sc["by_province"].items():
        assert 0 < v["value"] <= 1
        assert v["bodies_swabbed"] <= v["alerts_raised"]
        assert abs(v["value"] - v["bodies_swabbed"] / v["alerts_raised"]) < 1e-4
        assert v["province_days"] == len(v["sitreps"])
    # A single pooled number would invite exactly the case-weighting that
    # belongs on the consumer's side.
    assert "value" not in sc and "national" not in sc


# --------------------------------------------------------------------------
# The population table is geography, not a publication decision
#
# A consumer sums it to a national susceptible pool. It was derived by
# iterating the publication list, so publishing three provinces gave 18.3M and
# publishing six gave 31.9M for a population that had not changed by one
# person -- a reference constant moving under a downstream model because of a
# choice made here. These pin the decoupling and the arithmetic.
# --------------------------------------------------------------------------

import build_streams as BS                                        # noqa: E402

GEOJSON = ROOT / "data" / "raw" / "health_zones.geojson"
POPCSV = ROOT / "data" / "raw" / "zone_population.csv"


def test_the_population_table_covers_the_geography_not_the_published_set(
        monkeypatch):
    """Publishing fewer provinces must not shrink the denominator.

    The guard loop still runs over `STREAM_PROVINCES`, so narrowing it only
    removes checks; the table itself comes from the geojson and stays whole.
    """
    full = BS.populations(GEOJSON, POPCSV)
    monkeypatch.setattr(BS, "STREAM_PROVINCES", {"Ituri": "ituri"})
    narrowed = BS.populations(GEOJSON, POPCSV)
    assert narrowed == full, (
        "the population table tracked the publication list; a province we "
        "stop publishing would silently leave the susceptible pool")
    assert set(full) == {"bas_uele", "haut_uele", "ituri", "nord_kivu",
                         "sud_kivu", "tshopo"}


def test_the_population_parts_add_to_the_whole_exactly():
    """Rounding each province and reporting an unrounded total, or vice versa,
    leaves a consumer whose components disagree with the sum by a few people
    and no way to tell which is authoritative."""
    pops = BS.populations(GEOJSON, POPCSV)
    assert all(isinstance(v, int) and v > 0 for v in pops.values())
    assert sum(pops.values()) == 31_898_994


def test_a_zone_with_population_but_no_geography_stops_the_build(tmp_path):
    """Its people would belong to no province and vanish from the denominator
    silently, which is the one way this can be wrong without looking wrong."""
    import csv as _c
    bad = tmp_path / "pop.csv"
    with bad.open("w", newline="") as fh:
        w = _c.writer(fh)
        w.writerow(["zone", "population"])
        w.writerow(["Nowhere-At-All", 100000])
    with pytest.raises(SystemExit, match="no geography"):
        BS.populations(GEOJSON, bad)


# --------------------------------------------------------------------------
# Unreachable is not revised
#
# The held-file check makes one HEAD request per report and can fail in two
# ways that mean opposite things: a response carrying a different size says
# the document changed, and no response at all says only that we could not
# look. They were once counted the same, so a single transient 5xx out of 99
# requests aborted the pipeline and left a consumer pinned to a superseded
# release. These pin the distinction in both directions.
# --------------------------------------------------------------------------


class _Resp:
    def __init__(self, length): self.headers = {"Content-Length": str(length)}
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _one_row_index(tmp_path, name, url):
    """An index naming exactly one already-held report, so `main` reaches the
    HEAD check and nothing else. Nothing is downloaded and nothing written:
    the file exists, and no `--manifest` is passed."""
    sitrep, date = int(name.split("_")[1]), name.split("_")[2][:-4]
    idx = tmp_path / "index.tsv"
    with idx.open("w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["sitrep", "data_date", "url",
                                            "pick"], delimiter="\t")
        w.writeheader()
        w.writerow({"sitrep": str(sitrep), "data_date": date, "url": url,
                    "pick": "yes"})
    return idx


@needs_pdfs
def test_an_unreachable_pick_url_is_recorded_and_retried_not_fatal(
        tmp_path, monkeypatch, capsys):
    held = "sitrep_052_2026-07-05.pdf"
    calls = []

    def boom(req, timeout=None):
        calls.append(req.full_url)
        raise OSError("connection reset by peer")

    monkeypatch.setattr(F.urllib.request, "urlopen", boom, raising=False)
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    idx = _one_row_index(tmp_path, held, "https://insp.cd/x.pdf")
    monkeypatch.setattr(sys, "argv", ["f", "--index", str(idx),
                                      "--out", str(PDFS)])
    F.main()                                  # must not raise SystemExit

    assert len(calls) == 2, "an unreachable URL must be retried exactly once"
    err = capsys.readouterr().err
    assert "could not be checked against the pick URL" in err
    assert held in err, "the report that went unchecked must be named"


@needs_pdfs
def test_a_pick_url_serving_different_bytes_still_stops_the_build(
        tmp_path, monkeypatch):
    """The half that must stay fatal. A revision changes what every hash-keyed
    register judgement is about, so it is never resolved silently."""
    held = "sitrep_052_2026-07-05.pdf"
    size = (PDFS / held).stat().st_size
    monkeypatch.setattr(F.urllib.request, "urlopen",
                        lambda req, timeout=None: _Resp(size + 1),
                        raising=False)
    idx = _one_row_index(tmp_path, held, "https://insp.cd/x.pdf")
    monkeypatch.setattr(sys, "argv", ["f", "--index", str(idx),
                                      "--out", str(PDFS)])
    with pytest.raises(SystemExit, match="REVISED REPORTS WE HOLD"):
        F.main()


@needs_pdfs
def test_a_substituted_external_pdf_stops_the_build(tmp_path):
    text = EXTERNAL.read_text().replace(
        "821ea26be20720b8ead7ae39f5f3b1df38970ee29198c6851d491882f39ecb39",
        "0" * 64)
    bad = tmp_path / "external.tsv"
    bad.write_text(text)
    reg = load_external_sitreps(bad)["sitrep_001_2026-05-14.pdf"]
    with pytest.raises(SystemExit, match="DOES NOT MATCH ITS REGISTER"):
        verify_external(PDFS / "sitrep_001_2026-05-14.pdf", reg)


def test_a_row_whose_filename_contradicts_its_date_is_refused(tmp_path):
    """The archive name is DERIVED from the adjudicated date, so a row where
    one was edited and the other was not would name the file for one day while
    asserting another."""
    text = EXTERNAL.read_text().replace(
        "4\t2026-05-18\t2026-05-19", "4\t2026-05-16\t2026-05-19")
    bad = tmp_path / "external.tsv"
    bad.write_text(text)
    with pytest.raises(SystemExit, match="names the file"):
        load_external_sitreps(bad)


def test_a_row_missing_provenance_is_refused(tmp_path):
    out = []
    for ln in EXTERNAL.read_text().splitlines():
        if ln.startswith("1\t2026-05-14"):
            parts = ln.split("\t")
            parts[7] = ""                       # upstream_commit
            ln = "\t".join(parts)
        out.append(ln)
    bad = tmp_path / "external.tsv"
    bad.write_text("\n".join(out) + "\n")
    with pytest.raises(SystemExit, match="upstream_commit"):
        load_external_sitreps(bad)


# --- the date adjudication ------------------------------------------------

@needs_pdfs
@needs_pdftotext
def test_sitrep_004_prints_sitrep_005s_dates():
    """The source defect the register adjudicates, asserted on the pages
    themselves: two consecutive reports print the same reporting date AND the
    same publication date, while carrying different cumulative counts."""
    import subprocess

    def printed(n):
        t = subprocess.run(["pdftotext", "-q", "-layout", str(pdf(n)), "-"],
                           capture_output=True, text=True).stdout
        return printed_dates(t)

    assert printed(4) == printed(5)
    assert printed(4)[0].isoformat() == "2026-05-19"    # date de rapportage
    assert printed(4)[1].isoformat() == "2026-05-20"    # date de publication


@needs_pdfs
@needs_pdftotext
def test_the_register_files_sitrep_004_a_day_before_its_printed_date():
    assert report_key(pdf(1)) == (1, "2026-05-14")
    assert report_key(pdf(2)) == (2, "2026-05-17")
    assert report_key(pdf(4)) == (4, "2026-05-18")
    # ...and 005 keeps the day both pages claim, so nothing collides.
    assert report_key(pdf(5)) == (5, "2026-05-19")
    assert report_key(pdf(6)) == (6, "2026-05-20")


@needs_pdfs
@needs_pdftotext
def test_a_register_that_misquotes_the_page_stops_the_build(tmp_path,
                                                            monkeypatch):
    """The register licenses one substitution on one document, not a rule. If
    the page stops printing what the row says it prints, the judgement was made
    about a different document."""
    text = EXTERNAL.read_text().replace(
        "4\t2026-05-18\t2026-05-19", "4\t2026-05-18\t2026-05-21")
    bad = tmp_path / "external.tsv"
    bad.write_text(text)
    monkeypatch.setattr(RD, "_external", lambda: load_external_sitreps(bad))
    with pytest.raises(SystemExit, match="EXTERNAL REGISTER IS STALE"):
        RD.report_key(pdf(4))


# --- the archive reconciliation -------------------------------------------

def _index_nums() -> set[int]:
    with INDEX.open() as fh:
        return {int(r["sitrep"]) for r in _csv.DictReader(fh, delimiter="\t")
                if r["pick"] == "yes"}


@needs_pdfs
def test_the_manifest_lists_every_report_including_the_three():
    with MANIFEST.open() as fh:
        listed = {r["file"] for r in _csv.DictReader(fh, delimiter="\t")}
    assert listed == {p.name for p in PDFS.glob("*.pdf")}
    assert {"sitrep_001_2026-05-14.pdf", "sitrep_002_2026-05-17.pdf",
            "sitrep_004_2026-05-18.pdf"} <= listed


def test_the_three_are_declared_by_the_register_and_not_by_the_index():
    """The property that makes the union necessary: no index row will ever name
    them, so on the index alone they reconcile as strays."""
    assert _index_nums().isdisjoint({1, 2, 4})
    assert {r.sitrep for r in
            load_external_sitreps(EXTERNAL).values()} == {1, 2, 4}


def _stub_archive(tmp_path: Path) -> Path:
    """The archive's NAMES, with one-byte contents.

    `_write_manifest` reconciles on the report number parsed out of the
    filename and hashes whatever is there, so the bytes are irrelevant to what
    is under test and copying 141 MB per test is not.
    """
    archive = tmp_path / "pdfs"
    archive.mkdir()
    for p in PDFS.glob("*.pdf"):
        (archive / p.name).write_bytes(b"%PDF-stub")
    return archive


@needs_pdfs
def test_reconciliation_admits_the_register_but_not_an_undeclared_pdf(tmp_path):
    """Unioning the register's NUMBERS in must not soften the check: a PDF
    declared by neither the index nor the register is still a file globbed
    straight into the trunk with nothing accounting for it."""
    archive = _stub_archive(tmp_path)
    declared = _index_nums() | {1, 2, 4}
    F._write_manifest(archive, declared, tmp_path / "m.tsv")     # closes
    assert (tmp_path / "m.tsv").exists()

    (archive / "sitrep_777_2026-09-01.pdf").write_bytes(b"%PDF-stub")
    with pytest.raises(SystemExit, match="declared nowhere"):
        F._write_manifest(archive, declared, tmp_path / "m2.tsv")


@needs_pdfs
def test_the_index_alone_would_call_the_three_strays(tmp_path):
    """States the defect the union fixes, so a future edit that drops the
    register out of `want_nums` fails here rather than at someone's build."""
    with pytest.raises(SystemExit, match=r"declared nowhere: \[1, 2, 4\]"):
        F._write_manifest(_stub_archive(tmp_path), _index_nums(),
                          tmp_path / "m.tsv")


# --- what they extract to -------------------------------------------------

@needs_pdfs
def test_sitrep_001_matches_no_registered_table():
    """The outbreak's first report is narrative: it prints no table of any
    geometry this project reads, and the per-zone figures on its page 2 are
    inside an image the text layer does not carry. Recorded as
    `no_matching_table` rather than fitted to a spec invented for it."""
    rows, status = E.extract(pdf(1))
    assert status == "no_matching_table"
    assert rows == []


@needs_pdfs
def test_sitrep_002_zone_table_is_transposed_and_so_matches_nothing():
    """002 DOES break its counts down by health zone -- `Tableau 1`: Mongbwalu
    0, Rwampara 13, Bunia 0 -- but with indicators as ROWS and zones as
    COLUMNS, which is not the geometry of any registered spec."""
    rows, status = E.extract(pdf(2))
    assert status == "no_matching_table"
    assert rows == []


@needs_pdfs
def test_sitrep_004_reads_the_early_layout_and_closes():
    rows, status = E.extract(pdf(4))
    assert status == "ok"
    assert {r["table"] for r in rows} == {"zone_early"}
    assert {r["zone_reported"]: r["cum_cases"] for r in rows} == {
        "Mongbwalu": 1, "Rwampara": 19, "Bunia": 6, "Nyankunde": 4,
        "Goma": 1, "Katwa": 1, "Butembo": 1, "Total": 33}
    # The zone rows sum to the printed national total exactly.
    assert E.reconcile(rows, column="cum_cases") == {
        "identity": "ok", "residual": 0, "printed_total": 33,
        "parts_sum": 33, "basis": "zones"}


@needs_pdfs
def test_sitrep_004_is_the_first_report_to_place_cases_outside_ituri():
    """Three of its seven health zones are in Nord-Kivu, one case each. That is
    what the report adds beyond a national total: the date at which the
    outbreak is first recorded outside the province it began in."""
    rows, _ = E.extract(pdf(4))
    got = {r["zone_reported"] for r in rows} & {"Goma", "Katwa", "Butembo"}
    assert got == {"Goma", "Katwa", "Butembo"}


# --------------------------------------------------------------------------
# The care prose route
# --------------------------------------------------------------------------
#
# The reports state the treatment-centre ledger in words, and the wording moves
# under the reader every few weeks. Each case below is one report and one
# behaviour that was arrived at by reading the page it names.


def _care(n: int) -> dict[str, dict]:
    import extract_care_prose as C
    got, _ = C.extract(pdf(n))
    return {r["province"]: r for r in got}


def test_care_pct_tolerance_matches_the_sources_rounding():
    """Same rule as the laboratory route: one decimal gets 0.15, a bare
    integer percent gets 0.55, because the source both rounds and truncates.
    Sitrep 087 prints 61 % for 508/840, which is 60.48 %."""
    import extract_care_prose as C
    assert C.pct_ok(508, 840, 61)          # integer percent, 0.52 away
    assert C.pct_ok(548, 991, 55.3)        # 55.30
    assert not C.pct_ok(536, 965, 55.2)    # 55.54 -- sitrep 098 disagrees
    assert not C.pct_ok(53, 130, 44.6)     # 40.77 -- sitrep 097 disagrees
    assert not C.pct_ok(5, 0, 41.7)        # no beds is not a rate


def test_care_cumulative_clauses_leave_the_harvest_pool():
    """The reports mix outbreak-to-date figures into the same bullets. Read as
    the day's they are wrong by an order of magnitude -- sitrep 079's "155 cas
    confirmés admis en CTE/CT pour 55 décès, soit une mortalité intra-CTE de
    35 %" put 55 deaths on a day the same bullet reports four."""
    import extract_care_prose as C
    assert "374" not in C.pool("20 guéris, portant le cumul provincial à 374.")
    assert "22" not in C.pool("1 évadé à Masereka (cumul des évadés : 22) et 5 décès")
    assert "5" in C.pool("1 évadé à Masereka (cumul des évadés : 22) et 5 décès")
    assert "55" not in C.pool(
        "155 cas confirmés admis en CTE/CT pour 55 décès, soit une mortalité "
        "intra-CTE de 35 %. 44 admissions du jour")
    assert "392" not in C.pool("Au total de 392 décès sont enregistré.")


def test_care_number_words_and_aucun_are_read():
    """`aucun évadé` is a printed ZERO -- sitrep 100's Ituri absconder count --
    and dropping it would bias the absconder series upward."""
    import extract_care_prose as C
    assert "0" in C.pool("dont 14 guéris et aucun évadé")
    assert "4" in C.pool("Quatre patients occupent les 20 lits")
    assert "21" in C.pool("Vingt-et-un (21) décès enregistrés parmi les sorties")


def test_care_a_saturated_centre_count_is_not_a_bed_count():
    """"Trois CTE dépassent la saturation pour les confirmés -- Nizi (233 %),
    ISTM (147 %) et Bambu (140 %) -- et un pour les suspects (Logo, 150 %)"
    (sitrep 082) counts CENTRES. Read loosely, its "un pour les suspects" put
    one suspect bed in the Ituri row. The bed split is admitted only as the
    parenthetical that follows the word `lits`."""
    import extract_care_prose as C
    assert not C.BEDS_SPLIT_LITS.search("et un pour les suspects (Logo, 150 %)")
    m = C.BEDS_SPLIT_LITS.search(
        "pour 84 lits montés (46 pour les confirmés et 38 pour les suspects)")
    assert m and (m.group(1), m.group(2)) == ("46", "38")


@needs_pdfs
def test_care_sitrep_100_reads_every_province_bullet():
    """The last report in the archive, and the shape the modern vintage
    settles into: admissions, exits with their recovered and absconded
    components, the census, the beds, and the occupancy that checks them."""
    by = _care(100)
    itu = by["Ituri"]
    assert (itu["admissions"], itu["exits"]) == (94, 87)
    assert (itu["exits_recovered"], itu["exits_absconded"]) == (14, 0)
    assert (itu["census"], itu["beds"], itu["printed_occupancy_pct"]) == (528, 965, 54.7)
    assert "occupancy=pass" in itu["checks"]
    tsh = by["Tshopo"]
    assert (tsh["census"], tsh["census_confirmed"], tsh["census_suspect"]) == (4, 1, 3)
    assert (tsh["beds"], tsh["printed_occupancy_pct"]) == (14, 28.6)
    assert "census_split=pass" in tsh["checks"] and tsh["census_licensed"]
    hu = by["Haut-Uélé"]
    assert (hu["admissions"], hu["admissions_confirmed"],
            hu["admissions_suspect"]) == (11, 4, 7)
    assert by["Sud-Kivu"]["census_suspect"] == 29


@needs_pdfs
def test_care_sitrep_093_exit_decomposition_closes():
    """Sitrep 093's Ituri bullet is the fullest ledger in the archive: "116
    sorties dont 34 guéris, 51 non-cas, 8 évadés et 23 décès (dont 11
    confirmés)" sums to the exits exactly, and the census closes five more ways
    -- the split sums to the total, the bed split sums to the beds, and all
    three ratios reproduce their printed percentages."""
    itu = _care(93)["Ituri"]
    assert itu["exits"] == 116
    assert (itu["exits_recovered"], itu["exits_noncase"],
            itu["exits_absconded"], itu["exits_deaths"]) == (34, 51, 8, 23)
    assert itu["exits_deaths_confirmed"] == 11
    assert (itu["census"], itu["census_confirmed"],
            itu["census_suspect"]) == (548, 236, 312)
    assert (itu["beds"], itu["beds_confirmed"], itu["beds_suspect"]) == (991, 497, 494)
    for name in ("census_split", "beds_split", "occupancy", "occupancy_confirmed",
                 "occupancy_suspect", "exits_split"):
        assert f"{name}=pass" in itu["checks"], name
    assert itu["licensed"]


@needs_pdfs
def test_care_sitrep_097_occupancy_catches_a_carried_forward_census():
    """Sitrep 097 reprints sitrep 096's Haut-Uélé sentence verbatim -- "53
    patients ... (36 confirmés et 17 suspects) ... 130 lits" -- and changes
    only the occupancy, from 40,8 % to 44,6 %. 53/130 is 40,8 %, so the census
    is the stale half. Its Tshopo bullet does the reverse: the beds move from
    12 to 14 and the percentage stays at the one computed on 12. Neither is
    visible without the printed rate."""
    by = _care(97)
    hu = by["Haut-Uélé"]
    assert (hu["census"], hu["beds"], hu["printed_occupancy_pct"]) == (53, 130, 44.6)
    assert "occupancy=fail" in hu["checks"] and not hu["licensed"]
    tsh = by["Tshopo"]
    assert (tsh["census"], tsh["beds"], tsh["printed_occupancy_pct"]) == (5, 14, 41.7)
    assert "occupancy=fail" in tsh["checks"]
    # 096 prints the same Haut-Uélé numbers with the rate that fits them.
    assert "occupancy=pass" in _care(96)["Haut-Uélé"]["checks"]


@needs_pdfs
def test_care_sitrep_070_summary_sentence_is_the_national_ledger():
    """Sitreps 052-080 close the care section with one sentence covering the
    whole response. It is the only prose source of a national absconder count,
    and it closes three ways: the split sums to the census, the census over the
    beds reproduces the printed rate, and the exit categories sum to the exits.
    Its admissions figure is NOT taken -- the 893 here is the outbreak-to-date
    total while sitrep 077's is the day's, and nothing in the sentence says
    which."""
    ens = _care(70)["Ensemble"]
    assert (ens["census"], ens["census_confirmed"],
            ens["census_suspect"]) == (766, 278, 488)
    assert (ens["beds"], ens["printed_occupancy_pct"]) == (860, 89.1)
    assert ens["exits"] == 127
    assert (ens["exits_recovered"], ens["exits_deaths"],
            ens["exits_noncase"], ens["exits_absconded"]) == (21, 24, 78, 4)
    assert ens["admissions"] is None
    assert ens["licensed"]


@needs_pdfs
def test_care_national_summary_reproduces_the_front_page_tile():
    """The strongest evidence that this route reads what it claims to. On
    2026-07-23 the summary sentence gives 766 patients in isolation of whom 278
    confirmed; the front-page ISOLEMENT/CTE tile -- a different part of the
    same document, read by a different reader in this repository -- prints the
    same two numbers. Agreement here is evidence about transcription, not about
    the counts: both are the same organisation's figures on the same page."""
    import extract_banner as B
    ens = _care(70)["Ensemble"]
    banner, _, _ = B.extract(pdf(70))
    assert banner.get("patients_isolated") == ens["census"] == 766
    assert banner.get("patients_isolated_confirmed") == ens["census_confirmed"] == 278


@needs_pdfs
def test_care_sitrep_068_does_not_file_ituris_census_under_nord_kivu():
    """Sitrep 068 writes "→ Ituri : 24 nouveaux guéris dont 23 en Ituri et 1au
    Nord Kivu, 70 admissions, 556 patients en isolement, ...". The
    mid-sentence province name is not a passage opening, and taking it as one
    filed Ituri's census of 556 under Nord-Kivu, which held 175 that day."""
    by = _care(68)
    assert by["Ituri"]["census"] == 556
    assert by["Nord-Kivu"]["census"] == 175
    # and the report's own "16 décès parmi les sorties dont 68 confirmés" is
    # recorded and flagged rather than quietly kept.
    assert "deaths_conf_le_deaths=fail" in by["Ituri"]["checks"]


@needs_pdfs
def test_care_sitrep_079_refuses_a_passage_covering_two_provinces():
    """"→ Haut-Uélé et Tshopo : 2 confirmés ont été admis ... pour 37 malades
    hospitalisés en fin de journée (16 confirmés, 21 suspects)". There is no
    way to split 37 between the two, so both are refused rather than one being
    credited with the pair's figures."""
    import extract_care_prose as C
    _, refused = C.extract(pdf(79))
    assert any(r["why"] == "two_provinces_one_passage" for r in refused)
    by = _care(79)
    assert "Tshopo" not in by
    assert by["Ituri"]["census"] == 476


def test_care_a_flattened_table_row_is_recognised_as_one():
    """Sitreps 018-058 print the ledger as a TABLE inside the same section, and
    once the page is flattened a province name in it opens a segment whose
    every number belongs to a column this reader cannot see -- sitrep 021 read
    5 186 exits out of one, and sitreps 013-014 read thirteen recoveries and
    four transfers out of "10 39 6 2 101". Two signatures catch it: the table's
    own header words, and four or more bare integers in a row, which is not a
    French sentence. The table is a legitimate source and a richer one, but
    reading it with prose patterns is not reading it."""
    import extract_care_prose as C
    row = ("Sud-Kivu 6 0 Ensemble 233 62 Décédés (Suspects/Conf.) 6 0 0 6 "
           "Non-cas / Guéris 17 0 0 17 Évadés (Suspects/Conf.) 14 0 0 14 "
           "Total sorties 37 0 0 37 Patients en isolement (Fin J) 243 9 6 258")
    assert C.TABLE_ROW.search(row) and C.DIGIT_RUN.search(row)
    assert C.DIGIT_RUN.search("Nord-kivu) 19 lits TOTAL et Tx d'occup 10 39 6 2 101")
    prose = ("En Ituri, 94 nouvelles admissions ont été enregistrées pour 87 "
             "sorties, dont 14 guéris et aucun évadé. Ainsi, 528 patients sont "
             "hospitalisés pour 965 lits, soit un taux d'occupation de 54,7%.")
    assert not C.TABLE_ROW.search(prose) and not C.DIGIT_RUN.search(prose)


@needs_pdfs
def test_care_no_report_yields_an_absurd_exit_count():
    """The consequence of the guard above, over the whole archive: the largest
    daily exit count the source ever prints is in the low hundreds, and a
    reading in the thousands is a table row misread as a sentence."""
    import extract_care_prose as C
    for n in (13, 14, 21, 44, 49, 55):
        got, _ = C.extract(pdf(n))
        assert all(r["exits"] is None or r["exits"] < 500 for r in got), n


@needs_pdfs
def test_care_cumulative_admissions_never_enter_the_daily_column():
    """Sitreps 084-089 open the Nord-Kivu bullet with an outbreak-to-date
    admissions count and give the day's later in the same sentence. Sitrep 089
    prints both: "219 admissions cumulées ... ; 52 admissions du jour (4
    confirmés et 48 suspects)"."""
    nk = _care(89)["Nord-Kivu"]
    assert nk["admissions"] == 52
    assert (nk["admissions_confirmed"], nk["admissions_suspect"]) == (4, 48)
    assert "admissions_split=pass" in nk["checks"]
    # Sitrep 084's Nord-Kivu bullet is cumulative from end to end -- "235
    # admissions cumulées ... dont 187 cas confirmés, pour une mortalité
    # intra-CTE de 39 %" -- so it yields no row at all rather than a daily
    # admissions count of 235 on a day the province admitted a few dozen.
    assert "Nord-Kivu" not in _care(84)


@needs_pdfs
def test_care_a_subset_admissions_figure_is_refused_not_guessed():
    """THE NEGATIVE CASE. Sitrep 053 writes "Deux (2) nouvelles admissions
    concernaient des PPL et sont incluses dans les 67 admissions enregistrées
    au cours de la journée": two candidates, the subset printed first, and no
    closure to choose between them. Ambiguity is refusal -- the row must not
    report two admissions on a day with sixty-seven."""
    import extract_care_prose as C
    got, refused = C.extract(pdf(53))
    assert any(r["why"] == "ambiguous_admissions" for r in refused)
    itu = {r["province"]: r for r in got}.get("Ituri")
    assert itu is None or itu["admissions"] is None


# --------------------------------------------------------------------------
# What the care figure ASSERTS
# --------------------------------------------------------------------------
#
# `care_ledger.png` states numbers in words -- how often two independent
# readings of the isolation census agree, how far a sum of province bullets
# falls short of a national total, how thin the absconder series is. Those are
# claims about the source, so they are pinned here rather than left to be
# re-read off a figure. Nothing below tests pixels.

BUILD = ROOT / "data" / "build" / "series"
needs_build = pytest.mark.skipif(
    not (BUILD / "care_prose.csv").exists()
    or not (BUILD / "banner.csv").exists(),
    reason="the series are not built; run `make build`")


def _built():
    import polars as pl
    return (pl.read_csv(BUILD / "care_prose.csv", infer_schema_length=None),
            pl.read_csv(BUILD / "banner.csv", infer_schema_length=None))


def test_care_row_state_separates_a_contradiction_from_an_unchecked_row():
    """`licensed` is one boolean over two different situations. A row whose
    printed occupancy disagrees with its own census over its own beds is the
    SOURCE contradicting itself; a row that prints a census with nothing beside
    it to check against is unverified, not wrong. The figure draws them
    differently, so the classification is pinned."""
    import plot_figures as P
    assert P.care_row_state({"licensed": True, "checks": ""}) == "clean"
    assert P.care_row_state(
        {"licensed": False, "checks": "occupancy=fail"}) == "contradicted"
    assert P.care_row_state({"licensed": False, "checks": ""}) == "unchecked"
    # SCOPED TO THE QUANTITY. A row whose exit decomposition fails but whose
    # census closes twice over is not a contradicted census.
    row = {"licensed": False, "census_licensed": False,
           "checks": "exits_split=fail;contacts_rate=pass"}
    assert P.care_row_state(row, "licensed") == "contradicted"
    assert P.care_row_state(row, "census_licensed") == "unchecked"


@needs_build
def test_the_tile_and_the_prose_give_the_same_confirmed_census():
    """PANEL A'S ARGUMENT, as a number. Two readers -- `extract_banner` on the
    front-page ISOLEMENT/CTE tile and `extract_care_prose` on the care
    pillar's whole-response sentence -- read the same page. On every report day
    both print a confirmed isolation census, they agree exactly. Agreement is
    evidence about transcription rather than about the counts, but a misreading
    could not produce it, and that is the failure this route is exposed to."""
    import plot_figures as P
    care, banner = _built()
    a = P.census_agreement(care, banner)
    assert a["n_confirmed_both"] == 24
    assert a["n_confirmed_agree"] == a["n_confirmed_both"]
    assert (a["n_total_both"], a["n_total_agree"]) == (27, 25)


@needs_build
def test_both_census_disagreements_are_the_source_contradicting_itself():
    """And the check says WHICH HALF is wrong. On both days the sentence's
    stated total differs from its own confirmed + suspected split, and the tile
    agrees with the split -- so it is the stated total that is the bad number.
    2026-07-07 states 694 against its own 232 + 518 = 750, and the tile says
    750; 2026-07-14 states 753 against 270 + 466 = 736, and the tile says 736.
    Both were already flagged `census_split=fail` by the extraction."""
    import plot_figures as P
    care, banner = _built()
    dis = P.census_agreement(care, banner)["disagreements"]
    assert len(dis) == 2
    for d in dis:
        assert d["tile_matches_split"], d
        assert d["state"] == "contradicted", d
    assert {d["date"]: (d["prose_total"], d["prose_split_sum"], d["tile_total"])
            for d in dis} == {"2026-07-07": (694, 750, 750),
                              "2026-07-14": (753, 736, 736)}


@needs_build
def test_the_confirmed_tile_and_the_national_sentence_stop_on_the_same_day():
    """The reason the figure exists. The tile keeps printing a TOTAL isolation
    census to the end of the archive; it is the CONFIRMED half -- the only half
    that observes a confirmed-case compartment -- that stops, and the care
    section's whole-response sentence stops on the very same report. What
    carries the confirmed census onward is the per-province bullets alone."""
    import plot_figures as P
    care, banner = _built()
    a = P.census_agreement(care, banner)
    assert a["tile_confirmed_last"] == a["prose_national_last"] == "2026-08-02"
    assert a["tile_total_last"] > a["tile_confirmed_last"]
    assert a["prose_province_last"] > a["tile_confirmed_last"]


@needs_build
def test_province_bullets_do_not_sum_to_a_national_census():
    """The obvious move once the whole-response sentence stops is to add the
    province bullets up, and it does not work: on most report days only one to
    three of the six affected provinces print a bullet at all. Where the
    sentence is also printed the sum falls short of it on all but two days, by
    as much as 279 patients -- which would read as a collapse in the census
    rather than as missing bullets."""
    import plot_figures as P
    care, _ = _built()
    p = P.province_census_is_not_national(care)
    assert p["max_provinces_per_day"] == 3
    assert p["median_provinces_per_day"] == 1
    assert (p["n_short"], p["n_compared"]) == (15, 17)
    assert p["worst_shortfall"] == -279


@needs_build
def test_province_occupancy_cannot_see_a_saturated_centre():
    """PANEL B'S CAVEAT, as numbers. Occupancy at province grain is a ratio of
    sums and stays below capacity on the great majority of province-days. The
    reports meanwhile name individual treatment centres above capacity in a
    prose subsection the care extraction does not read, so the slack this panel
    shows is not evidence of free beds where the patients are.

    WHAT CHANGED ON 2026-08-29, and it is a finding rather than a drift. Until
    sitrep 103 exactly one province-day exceeded capacity -- Nord-Kivu at 139%
    on 3 August, readable as an outlier. Sitreps 104-106 add three CONSECUTIVE
    Nord-Kivu days over capacity (26-28 August: 214/206, 232/220, 236/220), so
    the province ends the archive saturated rather than spiking once. The
    caveat this test guards is unchanged and the panel's caption is generated
    from the data, but a reader who took "one outlier" from an earlier vintage
    would now be wrong.
    """
    import plot_figures as P
    care, _ = _built()
    o = P.occupancy_at_province_grain(care)
    # The province-day COUNT grows on every fetch and is not the finding;
    # assert that it is a real sample, then assert the finding itself.
    assert o["n"] > 50
    # Over-capacity days remain a small minority, and every one of them is the
    # same province -- that is the claim the panel rests on.
    assert 0 < o["n_over_100"] <= 0.1 * o["n"]
    assert {r["province"] for r in o["over_100"]} == {"Nord-Kivu"}
    assert round(max(r["occ"] for r in o["over_100"])) == 139
    # The tail is sustained, not a single spike: at least three of them are
    # consecutive report days.
    days = sorted(d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))
                  for d in (r["date"] for r in o["over_100"]))
    longest = run = 1
    for a, b in zip(days, days[1:]):
        run = run + 1 if (b - a).days == 1 else 1
        longest = max(longest, run)
    assert longest >= 3
    assert o["min"] < 20 and 50 < o["median"] < 70


@needs_build
def test_the_absconder_series_is_thin_and_the_figure_must_not_join_it():
    """An absconder is a confirmed patient who leaves care still infectious --
    the complement of the isolation census, and the two are halves of one
    transition. The count is printed on 24 province-days in the whole archive,
    only 5 of them after the tile's confirmed half stops, and 14 of the 24 are
    the whole-response figure rather than a province's. One is a printed zero,
    which is an observation and not an absence."""
    import plot_figures as P
    care, banner = _built()
    last = P.census_agreement(care, banner)["tile_confirmed_last"]
    a = P.absconder_coverage(care, last)
    assert a["n"] == 24
    assert a["n_after"] == 5
    assert a["n_national"] == 14
    assert a["n_zero"] == 1


@needs_build
def test_the_two_care_grains_overlap_so_the_ledger_is_faceted_not_stacked():
    """Panel C facets the whole-response sentence apart from the province
    bullets because on eleven report days both print an exit count, covering
    the same discharges. Stacking them would double count those days."""
    import plot_figures as P
    care, _ = _built()
    assert P.exits_double_counted_if_summed(care) == 11


# --------------------------------------------------------------------------
# THE OUTCOME LEDGER -- WHERE THE RECORD OF A CONFIRMED CASE IS
#
# `outcomes` claims, in words on a slide, that better than a quarter of
# everyone ever confirmed appears in none of the four counts INSP publishes.
# That is arithmetic over printed numbers, so the arithmetic is pinned here:
# the decomposition must close against the published case total, and the
# headline figures must be what the built series say. Nothing below tests
# pixels.

OUT_BUILD = ROOT / "data" / "build" / "series"
needs_outcome_build = pytest.mark.skipif(
    not (OUT_BUILD / "zone_table.csv").exists()
    or not (OUT_BUILD / "banner.csv").exists(),
    reason="the series are not built; run `make build`")


def _outcome_inputs():
    import polars as pl
    return (pl.read_csv(OUT_BUILD / "zone_table.csv", infer_schema_length=None),
            pl.read_csv(OUT_BUILD / "banner.csv", infer_schema_length=None))


@needs_outcome_build
def test_the_outcome_decomposition_closes_against_the_published_case_total():
    """THE PROPERTY THE WHOLE FIGURE RESTS ON. The four bands are not four
    estimates that happen to be near each other; they partition the published
    cumulative confirmed total exactly, which is why the top one can be read as
    a count of people. On every row that carries a ward census the four sum to
    `cum_cases`, and on every row without one the three that remain sum to it
    with the undivided residual, with no slack anywhere."""
    import polars as pl
    import plot_figures as P
    led = P.outcome_ledger(*_outcome_inputs())
    assert led.height > 60
    closes = led.select(
        (pl.col("cum_deaths") + pl.col("cumul_recovered") + pl.col("residual")
         == pl.col("cum_cases")).all()).item()
    assert closes, "dead + recovered + residual does not equal cum_cases"
    full = led.drop_nulls("unaccounted")
    four = full.select(
        (pl.col("cum_deaths") + pl.col("cumul_recovered") + pl.col("in_ward")
         + pl.col("unaccounted") == pl.col("cum_cases")).all()).item()
    assert four, "the four bands do not sum to cum_cases"
    # And the residual is an upper bound on the unaccounted count, which is
    # what licenses carrying it past the day the census stops.
    assert full.filter(pl.col("residual") < pl.col("unaccounted")).height == 0


@needs_outcome_build
def test_the_headline_numbers_are_what_the_published_series_say():
    """The four counts the figure states, on the last report day all four
    exist. 2 August (sitrep 080) prints 3,802 confirmed cases and 1,707
    confirmed deaths in the health-zone table's national row; the front-page
    tiles print 727 cumulative recoveries and 335 confirmed patients in
    isolation. The remainder is 1,033 people, 27% of everyone ever confirmed,
    and it is 1,033 because those four numbers are those four numbers."""
    import plot_figures as P
    h = P.outcome_headline(P.outcome_ledger(*_outcome_inputs()))
    assert h["census_date"] == "2026-08-02"
    assert (h["cum_cases"], h["cum_deaths"]) == (3802, 1707)
    assert (h["cumul_recovered"], h["in_ward"]) == (727, 335)
    assert h["unaccounted"] == 1033
    assert h["unaccounted"] == (h["cum_cases"] - h["cum_deaths"]
                                - h["cumul_recovered"] - h["in_ward"])
    assert round(h["share"], 4) == 0.2717
    # The count grows across the window over which the share is flat, so the
    # steadiness of the share is not the steadiness of the problem.
    assert h["run_start"] == "2026-07-18"
    assert (h["run_days"], h["run_start_unaccounted"]) == (14, 676)
    assert 0.27 <= h["run_share_min"] <= h["run_share_max"] <= 0.29


@needs_outcome_build
def test_the_ward_census_stops_and_only_the_undivided_residual_continues():
    """WHY THE COMPOSITION CHANGES SHAPE. The confirmed half of the isolation
    census is published for the last time on 2 August, while the case, death
    and recovery counts run to the end of the archive. Past that day the ward
    band and the unaccounted band cannot be told apart -- so the figure draws
    them as one, and what it may still assert is the sum, which is larger on
    the last report day than the whole residual was when the census stopped."""
    import polars as pl
    import plot_figures as P
    led = P.outcome_ledger(*_outcome_inputs())
    h = P.outcome_headline(led)
    after = led.filter(pl.col("date") > pl.lit(h["census_date"]))
    assert after.height > 10
    assert after["in_ward"].null_count() == after.height
    assert after["unaccounted"].null_count() == after.height
    assert after["residual"].null_count() == 0
    # `last_date` is the newest report the archive holds and moves on every
    # fetch, so it is DERIVED rather than pinned -- what matters is that the
    # headline reports the end of the series it drew, and that the residual
    # has grown since the census stopped.
    assert h["last_date"] == led["date"].max()
    assert h["last_date"] > h["census_date"]
    assert h["last_residual"] > h["census_residual"]
    assert h["census_residual"] == 1368


@needs_outcome_build
def test_every_hole_in_the_outcome_composition_carries_a_reason():
    """A break in the composition is a report day with no national cumulative,
    and there are three different causes: INSP published nothing that day, the
    report printed no health-zone table, or the table printed only its 24-hour
    columns. Every break must carry which -- none may fall through to an
    unlabelled default -- because the caption in `figures/README.md`
    states that there are three and names them, and a fourth cause appearing
    silently would make that caption wrong."""
    import plot_figures as P
    import polars as pl
    zone, banner = _outcome_inputs()
    status = pl.read_csv(OUT_BUILD / "zone_table_status.csv",
                         infer_schema_length=None)
    gaps = P.outcome_gaps(P.outcome_ledger(zone, banner), status)
    assert len(gaps) == 8
    assert all(g["why"].strip() for g in gaps)
    assert {(g["lo"].isoformat(), g["why"].replace("\n", " ")) for g in gaps} >= {
        ("2026-07-28", "no report published"),
        ("2026-08-06", "no health-zone table printed"),
        # sitrep 087 DOES print a health-zone table; it prints only the
        # 24-hour columns, so blaming the missing table would be wrong.
        ("2026-08-09", "no cumulative columns printed")}


@needs_build
def test_the_figure_registry_declares_every_input_each_figure_reads():
    """The declared inputs ARE the dependency set -- the data document's guard
    and the Makefile both read them -- so a figure that opens a file it did not
    declare would be rebuilt from an undeclared input. Splitting one figure in
    two is exactly when that goes wrong, because the inputs move with the
    panels."""
    import plot_figures as P
    for name in ("streams_detail", "national_detail", "care_ledger",
                 "outcomes"):
        _, inputs = P.FIGURES[name]
        for rel in inputs.values():
            assert (ROOT / rel).exists(), f"{name} declares missing {rel}"
    assert "banner" not in P.FIGURES["streams_detail"][1], \
        "the banner moved to national_detail with the panels that read it"
    assert "banner" in P.FIGURES["national_detail"][1]


# --------------------------------------------------------------------------
# THE CAPTION DOCUMENT
#
# `figures/` holds the committed copies of the published figures, and
# `figures/README.md` holds the caption each one travels with: what it
# shows, and the limits on what it licenses a reader to conclude. Several of
# these figures are drawn at slide proportions and carry almost no text, which
# is only defensible while the caption exists -- so this pair of tests is the
# same shape as the stream register's: a figure with no caption must stop the
# suite, and a caption naming no figure must too, because it is either a typo
# or a figure that was dropped without its caption going with it.
# --------------------------------------------------------------------------

FIGURE_DIR = ROOT / "figures"
CAPTIONS = FIGURE_DIR / "README.md"


def _caption_sections(path: Path) -> list[str]:
    """The filenames the document captions, in document order.

    A section opens with a level-two heading holding nothing but a backticked
    filename, which is what separates it from the prose headings around it and
    keeps the parse from drifting as the prose is edited.
    """
    names = []
    for line in path.read_text().splitlines():
        if line.startswith("## `") and line.rstrip().endswith("`"):
            names.append(line[4:].rstrip()[:-1])
    return names


def test_every_committed_figure_has_a_caption():
    """No figure ships uncaptioned. These are published artefacts -- the
    README embeds them and the cross-repo channel links them -- and a figure
    that reaches a slide without the sentence saying what its top band does
    NOT mean is the failure this document exists to prevent."""
    captioned = set(_caption_sections(CAPTIONS))
    shipped = sorted(p.name for p in FIGURE_DIR.glob("*.png"))
    assert shipped, "no committed figures found; has figures/ moved?"
    for name in shipped:
        assert name in captioned, \
            f"{name} is committed but has no section in {CAPTIONS.name}"


def test_every_caption_names_a_figure_that_exists():
    """The other direction, which catches the two ways this document rots: a
    misspelt filename in a heading, and a figure retired without its caption
    going with it. Either leaves a caption nothing can ever be read against."""
    sections = _caption_sections(CAPTIONS)
    assert len(sections) == len(set(sections)), \
        f"{CAPTIONS.name} captions the same figure twice"
    for name in sections:
        assert (FIGURE_DIR / name).exists(), \
            f"{CAPTIONS.name} captions {name}, which is not in {FIGURE_DIR}"


# --------------------------------------------------------------------------
# THE CARE LEDGER AS PUBLISHED STREAMS
#
# `care_prose.csv` was extracted and drawn without anything being published
# from it. These pin what is published now: that the streams carry the
# extraction's numbers unaltered, that the confirmed census -- the quantity the
# release exists for -- holds the observations it should, that a flow row
# covers one day and not the calendar gap, and that a stock carries no
# accumulation window at all.
# --------------------------------------------------------------------------

CARE_PROSE = BUILD / "care_prose.csv"
needs_care_streams = pytest.mark.skipif(
    not CARE_PROSE.exists() or not any(STREAMS.glob("care_*.tsv")),
    reason="the care streams are not built; run `make build && make streams`")

#: The reports' word for the all-provinces column -> the slug the build files
#: it under. Read off the build rather than retyped, so a change there fails
#: here rather than passing against a stale copy.
CARE_PLACES = dict(BS.STREAM_PROVINCES) | {BS.CARE_NATIONAL: "national"}


def _care_files():
    return sorted(STREAMS.glob("care_*.tsv"))


def _care_stream(path):
    """`(province, source column, the SCORED rows)` for one care file.

    The holes are dropped here because every caller is asking what the source
    stated; a flow file's other rows exist to close the accumulation interval,
    not to carry a value.
    """
    t = BS.read_stream(path)
    if "n_report_days" in t.columns:
        t = t.filter(pl.col("n_report_days") > 0)
    obs = [c for c in t.columns if c not in BS.METADATA_COLUMNS and c != "time"]
    assert len(obs) == 1, f"{path.name} publishes {obs}, expected one column"
    for prov, slug in CARE_PLACES.items():
        if path.stem.endswith("_" + slug):
            return prov, obs[0][: -(len(slug) + 1)], t
    raise AssertionError(f"{path.name} names no place this build streams")


def _synthetic_care(path):
    """A minimal care ledger over the synthetic panel's report days: one
    province stating a census with its confirmed half, on two of the four.

    Every column the build harvests is present, empty where the passage says
    nothing -- the shape `extract_care_prose.py` writes. The column list comes
    off `CARE_STREAMS` so it cannot drift from what the build reads.
    """
    quantities = [col for _, col, _ in BS.CARE_STREAMS]
    rows = []
    for date, census, conf, adm in (("2026-05-20", 10, 4, 3),
                                    ("2026-05-22", 12, 5, 2)):
        row = {"sitrep": 5, "date": date, "province": "Ituri"}
        row |= {q: None for q in quantities}
        # A stock AND a flow, two report days apart with a silent day between
        # them: the census exercises the family that must not be gridded, and
        # the admissions the family that must be.
        row |= {"census": census, "census_confirmed": conf,
                "census_suspect": census - conf, "admissions": adm,
                "checks": "census_split=pass", "licensed": True,
                "census_licensed": True, "sentence": "-"}
        rows.append(row)
    pl.DataFrame(rows).write_csv(path)


@needs_care_streams
def test_the_care_streams_carry_exactly_what_the_extraction_read():
    """No filtering, no re-derivation, no rounding. Every row the extraction
    holds for that province and that column is published, at the same date and
    with the same value -- including the rows whose own arithmetic did not
    close, which are kept and flagged rather than dropped, because a report
    contradicting itself is a finding about the source."""
    care = pl.read_csv(CARE_PROSE, infer_schema_length=None)
    assert _care_files(), "no care streams were written"
    for path in _care_files():
        prov, col, got = _care_stream(path)
        want = (care.filter((pl.col("province") == prov)
                            & pl.col(col).is_not_null())
                .sort("date"))
        assert got["time"].to_list() == want["date"].to_list(), path.name
        assert got[got.columns[1]].to_list() == want[col].to_list(), path.name


@needs_care_streams
def test_the_confirmed_census_holds_the_observations_the_release_rests_on():
    """THE PRIORITY QUANTITY. It reads a state rather than a thinned flow, so
    it constrains the isolation rate with no reporting fraction in front of it
    -- and it is thin, which is the thing a consumer must see before fitting
    it. Ituri and Nord-Kivu are the two provinces the models pin; the split at
    2 August is where the front-page tile stopped and these files became the
    only route to the quantity."""
    counts = {}
    for slug in ("ituri", "nord_kivu"):
        t = pl.read_csv(STREAMS / f"care_census_confirmed_{slug}.tsv",
                        separator="\t", infer_schema_length=None)
        counts[slug] = (t.height,
                        t.filter(pl.col("time") > "2026-08-02").height)
    assert counts == {"ituri": (23, 9), "nord_kivu": (17, 10)}
    # The national file is the whole-response summary sentence, which stopped
    # on the same report as the tile -- so nothing national survives the split.
    nat = pl.read_csv(STREAMS / "care_census_confirmed_national.tsv",
                      separator="\t", infer_schema_length=None)
    assert nat["time"].max() == "2026-08-02"


@needs_care_streams
def test_a_care_flow_row_covers_the_window_it_claims():
    """The single most dangerous thing a consumer could do with these files.

    The report states one 24-hour figure for the report day, so a row holds
    ONE day of admissions. Making `days_covered` say 1 was not enough on its
    own, because an engine accumulates between the ROWS that are present and
    reads no column to decide the window: a file holding only the days the
    source spoke made each next row's window as wide as the silence behind it.

    THE INVARIANT, and it is now exact: every calendar day the file spans is a
    row, so `days_covered` is 1 EVERYWHERE and a row's value covers precisely
    the interval since the row before it. A report-day grid got this right
    only where the source published on consecutive days; the days nobody
    published on stayed absent and kept widening the window.
    """
    seen_no_report = seen_silent = False
    for path in _care_files():
        t = BS.read_stream(path)
        if "days_covered" not in t.columns:
            continue                       # a stock; the test below covers it
        times = [dt.date.fromisoformat(x) for x in t["time"].to_list()]
        gaps = [(b - a).days for a, b in zip(times, times[1:])]
        assert set(gaps) <= {1}, f"{path.name} skips a calendar day"
        assert set(t["days_covered"].to_list()) == {1}, path.name
        assert set(t["n_report_days"].to_list()) <= {0, 1}, path.name
        # A hole is one of two facts and the column says which: 1 where a
        # report was published and passed this quantity over, 0 where no
        # report was published at all.
        holes = t.filter(pl.col("n_report_days") == 0)
        silent = holes["n_report_days_silent"].to_list()
        assert set(silent) <= {0, 1}, path.name
        seen_silent |= 1 in silent
        seen_no_report |= 0 in silent
    assert seen_silent, "no care flow stream holds a silent-report-day hole"
    assert seen_no_report, "no care flow stream holds a no-report-day hole"


@needs_care_streams
def test_the_census_streams_carry_no_accumulation_window():
    """A stock is a reading at an instant, so a span column would assert an
    interval that does not exist -- the rule `uganda_exports` follows. It must
    still state its coverage, which for a single-place stream is how many
    report days went by saying nothing."""
    for path in STREAMS.glob("care_census*.tsv"):
        t = pl.read_csv(path, separator="\t", infer_schema_length=None)
        assert "days_covered" not in t.columns, path.name
        assert "n_report_days" not in t.columns, path.name
        assert "n_report_days_silent" in t.columns, path.name


@needs_care_streams
def test_the_absconder_streams_are_published_thin_and_say_how_thin():
    """Published because nothing else observes a route back into the community
    while still infectious, and published WITH its scarcity visible rather than
    left to be discovered: one file holds a single scored row, and a report
    that does not mention absconders is SILENT rather than reporting none, so
    the rows standing for those reports hold `NA` and never 0."""
    # The PROPERTY, not the enumeration. Which places have an absconder stream
    # is a function of which provinces reported one, and that grows: Tshopo
    # gained one the day the six-province scope landed. A test listing the
    # files fails on the release that adds a province, which is the wrong
    # moment to be arguing with a test about something it was never guarding.
    files = sorted(STREAMS.glob("care_exits_absconded_*.tsv"))
    assert len(files) >= 3
    assert any(p.stem.endswith("_national") for p in files)
    obs = {}
    for p in files:
        t = BS.read_stream(p)
        scored = t.filter(pl.col("n_report_days") > 0)
        obs[p.stem] = scored.height
        assert (scored[t.columns[1]] >= 0).all()
        assert t["n_report_days_silent"].min() >= 0
        # The silence is a hole, not a zero: every unscored row is empty in
        # the observation column.
        holes = t.filter(pl.col("n_report_days") == 0)
        assert holes[t.columns[1]].null_count() == holes.height, p.name
    assert obs["care_exits_absconded_nord_kivu"] == 1
    assert obs["care_exits_absconded_ituri"] == 8
    assert obs["care_exits_absconded_national"] == 14


def test_care_state_scopes_the_verdict_to_the_quantity_it_describes():
    """Three states, not two, and each scoped to the closures that bear on the
    published column. A row whose exit decomposition disagrees with itself can
    still carry a census that closes twice over, so the census stream must not
    inherit the exits' failure -- and a passage with nothing to check against
    is unverified, which is a different claim from wrong."""
    census = ("census_split", "occupancy_confirmed")
    assert BS.care_state("census_split=pass;occupancy_confirmed=pass",
                         census) == "closes"
    assert BS.care_state("census_split=fail;confirmed_le_census=pass",
                         census) == "contradicts"
    assert BS.care_state("confirmed_le_census=pass", census) == "unchecked"
    assert BS.care_state("", census) == "unchecked"
    # The exits failing says nothing about the census.
    row = "exits_split=fail;census_split=pass"
    assert BS.care_state(row, census) == "closes"
    assert BS.care_state(row, ("exits_split",)) == "contradicts"


# --------------------------------------------------------------------------
# THE COVERAGE CONTRACT
#
# A stream that aggregates over a population must publish how much of that
# population it saw. The rule is pinned here because breaking it cost real
# time downstream: without `n_provinces` the national laboratory stream's
# coverage deficit reads exactly like an under-reporting one, and was very
# nearly fitted as a probability of publication.
# --------------------------------------------------------------------------

#: Every published stream read out of PROSE rather than off a drawn table.
#: A table prints every province or does not exist; a paragraph writes out
#: whichever provinces its author wrote out, which is the whole difference.
PROSE_PREFIXES = ("lab_", "care_")


def _prose_streams():
    return sorted(p for p in STREAMS.glob("*.tsv")
                  if p.name.startswith(PROSE_PREFIXES))


@needs_dictionary
def test_every_prose_derived_stream_states_its_coverage_in_a_column():
    """The contract, asserted over the release rather than over a list: any
    file built from prose carries `n_report_days_silent`, and any file whose
    row is a total over provinces carries `n_provinces` beside it. A docstring
    saying so would not have stopped the failure this exists for."""
    assert _prose_streams()
    for path in _prose_streams():
        t = pl.read_csv(path, separator="\t", infer_schema_length=None)
        assert "n_report_days_silent" in t.columns, \
            f"{path.name} is prose-derived and states no coverage"
        assert t["n_report_days_silent"].min() >= 0, path.name
        if path.stem.startswith("lab") and path.stem.endswith("national"):
            assert "n_provinces" in t.columns, \
                f"{path.name} totals over provinces and does not say how many"


@needs_dictionary
def test_the_weekly_laboratory_file_states_both_axes_of_its_coverage():
    """A weekly bin sums over report days AND over provinces, and only one of
    those was ever stated -- and not on this file, which is the one a consumer
    reaches for first. `n_provinces` is how many distinct provinces the bin saw
    at all, `n_province_days` how many province-days were summed, so the ratio
    of the second to `n_report_days` is the mean breadth the bin's total rests
    on: the number that decides whether a shortfall against the case series is
    reporting or composition."""
    t = pl.read_csv(STREAMS / "lab_national.tsv", separator="\t",
                    infer_schema_length=None)
    for col in ("n_report_days", "n_report_days_silent", "n_provinces",
                "n_province_days"):
        assert col in t.columns, col
    assert (t["n_province_days"] >= t["n_provinces"]).all()
    assert (t["n_province_days"] >= t["n_report_days"]).all()
    assert t["n_provinces"].min() >= 1


def test_silent_report_days_counts_the_calendar_the_row_did_not_use():
    """Pure, and the whole definition: report days in `(previous time, this
    time]` that did not feed the row. Zero on a contiguous series, the count of
    skipped reports otherwise -- and it refuses rather than clamps when the
    calendar is missing a day a row rests on, because a negative coverage would
    be a defect in the calendar and not a small number."""
    import datetime as _dt

    def d(day):
        return _dt.date(2026, 8, day)

    cal = [d(1), d(2), d(3), d(4), d(5)]
    assert BS.silent_report_days([d(2), d(3)], [1, 1], cal, d(1)) == [0, 0]
    assert BS.silent_report_days([d(2), d(5)], [1, 1], cal, d(1)) == [0, 2]
    # a weekly bin: four report days in the window, three of them fed it
    assert BS.silent_report_days([d(5)], [3], cal, d(1)) == [1]
    with pytest.raises(SystemExit, match="report-day calendar"):
        BS.silent_report_days([d(2)], [3], cal, d(1))


@needs_dictionary
def test_the_dictionary_states_the_coverage_contract_as_a_contract():
    """Not a convention and not left in a docstring: the reading section of the
    shipped dictionary states it, and names every column that carries it."""
    text = DICTIONARY.read_text()
    assert "HOW MUCH OF ITS POPULATION IT SAW" in text
    for col in ("n_provinces", "n_province_days", "n_report_days_silent",
                "checks"):
        assert f"`{col}`" in text, col


# --------------------------------------------------------------------------
# THE DICTIONARY SAYS HOW TO READ A STREAM, AND FAILS CLOSED ON IT
# --------------------------------------------------------------------------

@needs_dictionary
def test_every_family_in_the_dictionary_says_how_to_read_it():
    """Saying what a quantity is is not saying how to read it, and the traps
    are not visible in a span or a column name. Every section the document
    prints for a family carries the reading beneath its table."""
    text = DICTIONARY.read_text()
    families = BS.load_families(FAMILIES)
    printed = [f for f in families if f"## {families[f]['title']}" in text]
    assert len(printed) >= 10, printed
    assert text.count("**How to read it.**") == len(printed)
    # Compared on collapsed whitespace, because `make fmt` rewraps the
    # dictionary's prose at 80 columns and the register holds each reading on
    # one line. What this test is for is that the dictionary says what the
    # register says; where the line breaks fall is the formatter's business,
    # and asserting them would make tidying the document a test failure.
    flat = " ".join(text.split())
    for family in printed:
        reading = families[family]["interpretation"]
        assert reading.strip(), family
        assert " ".join(reading.split()) in flat, family


def test_the_register_carries_a_reading_for_every_family_it_names():
    """Both sentences are required of every row, including the two files that
    are not observation streams, which are rendered in their own sections and
    could otherwise lose one quietly."""
    for family, entry in BS.load_families(FAMILIES).items():
        assert entry["measures"].strip(), family
        assert entry["interpretation"].strip(), family


@needs_pdftotext
def test_a_family_with_no_reading_stops_the_build(monkeypatch, tmp_path):
    """The same fail-closed rule the `measures` sentence has had, extended to
    the reading: blanking one stops the build and names the family, rather than
    shipping a stream whose limits nobody wrote down."""
    header = FAMILIES.read_text().splitlines()
    col = None
    out_lines = []
    for line in header:
        if line.startswith("family\t"):
            col = line.split("\t").index("interpretation")
        if col is not None and line.startswith("cases\t"):
            cells = line.split("\t")
            cells[col] = ""
            line = "\t".join(cells)
        out_lines.append(line)
    assert col is not None, "the register has no interpretation column"
    register = tmp_path / "families.tsv"
    register.write_text("\n".join(out_lines) + "\n")
    panel = tmp_path / "panel.csv"
    _synthetic_panel(panel, [10, 20, 30, 40], [2, 4, 6, 8])
    out = tmp_path / "streams"
    with pytest.raises(SystemExit) as e:
        _run_build(monkeypatch, panel, out, "--families", str(register))
    msg = str(e.value)
    assert "no `interpretation` for ['cases']" in msg
    assert not (out / "README.md").exists()


@needs_pdftotext
def test_an_unregistered_care_family_still_stops_the_build(monkeypatch,
                                                          tmp_path):
    """The register is fail-closed over whatever a run wrote, so adding a whole
    group of streams must not have opened a hole in it: with the confirmed
    census dropped from the register and a care input supplied, the build stops
    and names the files rather than documenting the release short."""
    register = tmp_path / "families.tsv"
    register.write_text("\n".join(
        line for line in FAMILIES.read_text().splitlines()
        if not line.startswith("care_census_confirmed\t")) + "\n")
    panel = tmp_path / "panel.csv"
    _synthetic_panel(panel, [10, 20, 30, 40], [2, 4, 6, 8])
    care = tmp_path / "care.csv"
    _synthetic_care(care)
    out = tmp_path / "streams"
    with pytest.raises(SystemExit) as e:
        _run_build(monkeypatch, panel, out, "--families", str(register),
                   "--care", str(care))
    msg = str(e.value)
    assert "A PUBLISHED STREAM IS UNDOCUMENTED" in msg
    assert ("care_census_confirmed_ituri.tsv "
            "(family `care_census_confirmed`)") in msg
    assert "care_census_ituri.tsv" not in msg      # that family is registered


@needs_pdftotext
def test_the_build_stops_if_a_flow_stream_loses_its_report_day_rows(monkeypatch,
                                                                   tmp_path):
    """THE GATE IS WIRED IN, not merely written. Both halves of the r4 shape
    are restored here -- rows only on the days the source spoke, and a
    `days_covered` of 1 regardless -- and the build must refuse to ship it.

    Two report days apart with one silent day between them is the smallest
    version of what `care_admissions_nord_kivu` shipped at 48.
    """
    panel = tmp_path / "panel.csv"
    _synthetic_panel(panel, [10, 20, 30, 40], [2, 4, 6, 8])
    care = tmp_path / "care.csv"
    _synthetic_care(care)
    monkeypatch.setattr(BS, "calendar_day_grid", lambda times: sorted(times))
    monkeypatch.setattr(BS, "spans", lambda times, left: [1] * len(list(times)))
    out = tmp_path / "streams"
    with pytest.raises(SystemExit) as e:
        _run_build(monkeypatch, panel, out, "--care", str(care))
    msg = str(e.value)
    assert "A SCORED ROW DOES NOT SIT WHERE ITS `days_covered` SAYS" in msg
    assert "care_admissions_ituri.tsv" in msg
    assert "2026-05-22 claims days_covered = 1 but sits 2 day(s) after" in msg
    # The stock beside it is not implicated: it carries no `days_covered` and
    # accumulates over no window, so the gate has nothing to say about it.
    assert "care_census_ituri.tsv" not in msg


@needs_pdftotext
def test_the_same_build_passes_with_the_report_day_rows_present(monkeypatch,
                                                               tmp_path):
    """The control: the same two observations, unchanged, with the silent
    report day between them present as a row. Nothing scored moves."""
    panel = tmp_path / "panel.csv"
    _synthetic_panel(panel, [10, 20, 30, 40], [2, 4, 6, 8])
    care = tmp_path / "care.csv"
    _synthetic_care(care)
    out = tmp_path / "streams"
    _run_build(monkeypatch, panel, out, "--care", str(care))   # does not raise
    d = BS.read_stream(out / "care_admissions_ituri.tsv")
    assert d["time"].to_list() == ["2026-05-20", "2026-05-21", "2026-05-22"]
    assert d["admissions_ituri"].to_list() == [3, None, 2]
    assert d["n_report_days"].to_list() == [1, 0, 1]
    assert d["days_covered"].to_list() == [1, 1, 1]
    assert d["checks"].to_list() == ["unchecked", "unchecked", "unchecked"]
    # The stock is untouched: two rows, the two the source stated.
    c = BS.read_stream(out / "care_census_ituri.tsv")
    assert c["time"].to_list() == ["2026-05-20", "2026-05-22"]


@needs_pdfs
def test_the_care_census_worked_example_is_still_true():
    """The `care_census` interpretation cites a specific pair of report days to
    show that the TOTAL census moves on suspect churn while the confirmed half
    moves the other way. A worked example in a document nothing checks is a
    number waiting to rot, so it is pinned here: if the extraction changes,
    this fails and the register is corrected rather than quietly disagreeing
    with the data it describes.
    """
    cp = pl.read_csv(ROOT / "data/build/series/care_prose.csv",
                     infer_schema_length=20000)
    d = {r["date"]: r for r in cp.filter(
        (pl.col("province") == "Ituri")
        & pl.col("date").is_in(["2026-07-25", "2026-07-26"])).iter_rows(named=True)}
    a, b = d["2026-07-25"], d["2026-07-26"]
    assert (a["census"], a["census_confirmed"], a["census_suspect"]) == (602, 287, 315)
    assert (b["census"], b["census_confirmed"], b["census_suspect"]) == (531, 304, 227)
    # the point of the example: total DOWN, confirmed UP, and the split closes
    assert b["census"] - a["census"] == -71
    assert b["census_confirmed"] - a["census_confirmed"] == +17
    assert b["census_suspect"] - a["census_suspect"] == -88
    assert ((b["census_confirmed"] - a["census_confirmed"])
            + (b["census_suspect"] - a["census_suspect"])
            == b["census"] - a["census"])
    # and the register must still carry it
    reg = FAMILIES.read_text()
    for frag in ("602 to 531", "287 to 304", "315 to 227"):
        assert frag in reg, f"the worked example lost {frag!r} from the register"


# --------------------------------------------------------------------------
# The day's own notification count, read from the banner tile
# --------------------------------------------------------------------------

import extract_daily_notified as N                                 # noqa: E402


def test_a_tile_is_read_by_column_not_by_flattening():
    """Sitrep 069's deaths tile closes its parenthesis two lines down, and the
    suspected-case tile occupies those same lines further right. Flattening
    the page splices "318 Ituri 188 · N-Kivu 119" into the deaths tile, whose
    breakdown then cannot sum to 62 and whose licence would refuse a page that
    is in fact perfectly well formed.
    """
    page = (
        "          +97 nouveaux cas (Ituri 73 · N-Kivu 18-\n"
        "          Haut-Uele 6)\n"
        "                                                        "
        "+62 décès (Ituri 45 · Nord-Kivu 14 –   318 Ituri 188 · N-Kivu 119\n"
        "                                                        "
        "Haut-Uele 3)                           Uélé 7 · Tshopo 4\n")
    got = {N._quantity(N.TILE.search(t).group(2)): t for t in N.tiles(page)}
    assert "318" not in got["deaths"], "a neighbouring tile leaked in"
    assert N.PROVINCE.findall(got["deaths"]) == [
        ("Ituri", "45"), ("Nord-Kivu", "14"), ("Haut-Uele", "3")]


def test_a_province_name_may_wrap_mid_word():
    """Sitrep 071 breaks the line after "Haut-" and closes "Uele 4)" below."""
    page = ("     +45 décès (Ituri 35 · Nord-Kivu 6 – Haut-\n"
            "     Uele 4)\n")
    tile, = N.tiles(page)
    assert sum(int(v) for _, v in N.PROVINCE.findall(tile)) == 45


def test_a_footnote_marker_may_stand_between_a_province_and_its_count():
    """Sitrep 073 prints "Nord-Kivu* 8". Dropping the province silently would
    leave the tile short of its own total rather than refusing."""
    tile = "+32 décès (Ituri 23 · Nord-Kivu* 8 - Haut-Uele 1)"
    assert sum(int(v) for _, v in N.PROVINCE.findall(tile)) == 32


def test_a_declared_harmonisation_is_followed_past_its_parenthesis():
    """Sitrep 077 ends the line on "+ 7" and opens the next with
    "harmonisés". The tile's own parentheses balance before that, so a
    parenthesis-only continuation rule stops early and loses the one number
    the source went out of its way to state separately."""
    page = ("     +24 décès (Ituri 20 · Nord-Kivu 4) + 7\n"
            "     harmonisés (Haut-Uélé)\n")
    tile, = N.tiles(page)
    assert N.HARMONISED.search(tile).group(1) == "7"


def test_an_uncorroborated_total_is_refused_rather_than_published():
    """The licence is the point: a banner number that neither its own
    breakdown nor the report's 24-hour sentence agrees with is a misread digit
    away from shipping silently, so it does not ship at all."""
    assert N.read_prose("au cours des dernières 24 heures, 58 nouveaux cas "
                        "confirmés, 37 décès confirmés et 19 guérisons") == {
        "cases": 58, "deaths": 37, "recovered": 19}
    # the per-province sentences state the same nouns and never sign them, so
    # they cannot be mistaken for the country's total
    assert N.read_prose("Ituri : 73 nouveaux cas confirmés et 45 décès") == {}


@needs_pdfs
def test_the_22_july_backlog_is_still_272_cases_and_174_deaths():
    """The whole reason this stream exists, pinned against both files.

    On 2026-07-22 the national confirmed cumulative moved 369 while the report
    says 97 were notified that day; its own footnote attributes the rest to
    integrating the harmonised Ituri and Nord-Kivu provincial databases. A
    consumer differencing the cumulative reads 369 as one day's incidence.
    """
    for stem, moved, notified in (("cases", 369, 97), ("deaths", 236, 62)):
        d = BS.read_stream(STREAMS / f"{stem}_daily_national.tsv")
        n = BS.read_stream(STREAMS / f"{stem}_notified_national.tsv")
        row = d.filter(pl.col("time") == "2026-07-22")
        assert int(row[f"{stem}_national"][0]) == moved
        assert int(row["days_covered"][0]) == 1, "not a one-day window"
        assert int(n.filter(pl.col("time") == "2026-07-22")
                   [f"{stem}_notified_national"][0]) == notified


@needs_pdfs
def test_the_one_day_the_source_declares_the_split_closes_exactly():
    """2026-08-02 is the single day the reports print both halves: "+40 décès
    du jour (...) · +10 par harmonisation". The differenced stream moved 50.
    That 40 + 10 = 50 is the strongest evidence in the archive that these two
    readings differ by retrospective attribution and by nothing else -- so if
    it ever stops holding, one of the two extractions has drifted.
    """
    d = BS.read_stream(STREAMS / "deaths_daily_national.tsv")
    n = BS.read_stream(STREAMS / "deaths_notified_national.tsv")
    moved = int(d.filter(pl.col("time") == "2026-08-02")["deaths_national"][0])
    row = n.filter(pl.col("time") == "2026-08-02")
    stated = int(row["deaths_notified_national"][0])
    assert "harmonisation_declared=10" in row["flags"][0]
    assert stated == 40 and moved == 50
    assert stated + 10 == moved


@needs_pdfs
def test_the_notified_series_spans_only_the_window_the_source_printed_one():
    """It exists for sitreps 059-083 and nowhere else, which is the same
    stretch the reports flag as consolidating. The register says so, and a
    span claimed in prose that the file does not have is the kind of drift
    these pins exist to catch."""
    n = BS.read_stream(STREAMS / "cases_notified_national.tsv")
    assert n["time"].min() == "2026-07-12"
    assert n["time"].max() == "2026-08-05"
    scored = n.filter(pl.col("n_report_days") > 0)
    assert scored.height == 23, "every report day in the window carries one"
    reg = FAMILIES.read_text()
    assert "2026-07-12 to 2026-08-05" in reg


def test_a_province_the_tile_omits_is_a_zero_not_a_hole():
    """The tile states a total over five provinces and a breakdown that closes
    on it, so a province missing from the breakdown contributed nothing. That
    is arithmetic, not a judgement about coverage — and it is the opposite of
    the laboratory and care families, where an unmentioned province is silence
    with no total to close against. `printed` keeps the two apart on the row.
    """
    page = "     +50 nouveaux cas (Ituri 42 · N-Kivu 8)\n"
    tile, = N.tiles(page)
    named = dict((N.PROVINCES[N._key(p)], int(v))
                 for p, v in N.PROVINCE.findall(tile))
    assert named == {"Ituri": 42, "Nord-Kivu": 8}
    assert sum(named.values()) == 50, "the breakdown must close to license this"
    assert [p for p in N.PLACES if p not in named] == [
        "Haut-Uélé", "Sud-Kivu", "Tshopo"]


@needs_pdfs
def test_the_province_split_closes_to_the_national_total_everywhere():
    """The split is the same reading that licensed the national figure, so if
    it ever stops summing to it one of the two is being read wrong."""
    d = pl.read_csv(ROOT / "data/build/series/daily_notified.csv")
    nat = d.filter(pl.col("place") == "national").select(
        "date", "quantity", pl.col("notified").alias("nat"))
    prov = (d.filter(pl.col("place") != "national")
            .group_by("date", "quantity")
            .agg(pl.col("notified").sum().alias("prov")))
    j = nat.join(prov, on=["date", "quantity"], how="inner")
    assert j.height == 63, "every day with a breakdown carries a full split"
    assert j.filter(pl.col("nat") != pl.col("prov")).height == 0


@needs_pdfs
def test_the_22_july_backlog_splits_the_way_the_source_prints_it():
    """The two-province substitution the modelling side needs, pinned. Ituri
    carries essentially all of the batch; Nord-Kivu's notified CASES exceed
    its cumulative movement, so the correction there is upward — a reminder
    that this is not uniformly "remove a backlog".
    """
    want = {("cases", "ituri"): (347, 73), ("cases", "nord_kivu"): (16, 18),
            ("deaths", "ituri"): (213, 45), ("deaths", "nord_kivu"): (20, 14)}
    for (stem, slug), (moved, notified) in want.items():
        d = BS.read_stream(STREAMS / f"{stem}_daily_{slug}.tsv")
        n = BS.read_stream(STREAMS / f"{stem}_notified_{slug}.tsv")
        row = d.filter(pl.col("time") == "2026-07-22")
        assert int(row[f"{stem}_{slug}"][0]) == moved
        assert int(row["days_covered"][0]) == 1
        assert int(n.filter(pl.col("time") == "2026-07-22")
                   [f"{stem}_notified_{slug}"][0]) == notified


@needs_pdfs
def test_the_excluding_backlog_family_differs_only_where_the_source_says_so():
    """The variant is the differenced family with the register's rows replaced
    and nothing else touched. If it ever differs on a day
    `retrospective_batches.tsv` does not name, the substitution has escaped its
    scope — which is the failure that would matter, because this family is
    meant to be bound without being read.
    """
    reg = pl.read_csv(ROOT / "registers/retrospective_batches.tsv",
                      separator="\t", comment_prefix="#",
                      infer_schema_length=None)
    licensed = {(r["date"], q, p)
                for r in reg.iter_rows(named=True)
                for q in (("cases", "deaths") if r["quantity"] == "both"
                          else (r["quantity"],))
                for p in str(r["places"]).split(",")}
    for stem in ("cases", "deaths"):
        for slug in ("national", "ituri", "nord_kivu", "haut_uele"):
            a = BS.read_stream(STREAMS / f"{stem}_daily_{slug}.tsv")
            b = BS.read_stream(STREAMS / f"{stem}_excluding_backlog_{slug}.tsv")
            assert a["time"].to_list() == b["time"].to_list()
            j = a.select("time", pl.col(f"{stem}_{slug}").alias("base")).join(
                b.select("time", pl.col(f"{stem}_{slug}").alias("var")),
                on="time")
            for r in j.filter(pl.col("base") != pl.col("var")).iter_rows(named=True):
                assert (r["time"], stem, slug) in licensed, (
                    f"{stem}_{slug} changed on {r['time']}, which the register "
                    "does not license")


@needs_pdfs
def test_the_22_july_footnote_scope_excludes_haut_uele():
    """The footnote names Ituri and Nord-Kivu. Haut-Uélé's two readings also
    differ that day, by one case and one death, and the source does not say
    those belong to earlier days — so they keep the differenced value. The
    place column is what holds that line, and dropping it silently widened the
    substitution when this was first built.
    """
    for stem, value in (("cases", 5), ("deaths", 2)):
        a = BS.read_stream(STREAMS / f"{stem}_daily_haut_uele.tsv")
        b = BS.read_stream(STREAMS / f"{stem}_excluding_backlog_haut_uele.tsv")
        row = lambda d: int(d.filter(pl.col("time") == "2026-07-22")
                            [f"{stem}_haut_uele"][0])
        assert row(a) == value and row(b) == value
    # and the notified reading, which is what would have been substituted
    n = BS.read_stream(STREAMS / "cases_notified_haut_uele.tsv")
    assert int(n.filter(pl.col("time") == "2026-07-22")
               ["cases_notified_haut_uele"][0]) == 6


@needs_pdfs
def test_the_totals_the_register_and_release_notes_claim_are_real():
    """Both documents state how many records the variant leaves unscored. A
    number quoted in prose that no build checks is one that rots."""
    got = {}
    for stem in ("cases", "deaths"):
        a = BS.read_stream(STREAMS / f"{stem}_daily_national.tsv")
        b = BS.read_stream(STREAMS / f"{stem}_excluding_backlog_national.tsv")
        got[stem] = (int(a[f"{stem}_national"].sum()),
                     int(b[f"{stem}_national"].sum()))
    # Pin the exclusion, not the totals. The archive total grows on every
    # fetch -- it went 5,912 to 6,067 the day two reports landed -- so a test
    # asserting it fails for the right reason at the worst time, on a release.
    # What must not move is how many records the substitution takes out: that
    # is two fixed historical batches and a change in it is a real defect.
    assert got["cases"][0] - got["cases"][1] == 272
    assert got["deaths"][0] - got["deaths"][1] == 184
    reg = FAMILIES.read_text()
    assert "272 national cases excluded" in reg
    assert "184 national deaths" in reg


# --------------------------------------------------------------------------
# Release tags are part of the data contract
# --------------------------------------------------------------------------

import re                                                       # noqa: E402

RELEASED = ROOT / "registers" / "released_tags.tsv"


def _git(*args: str) -> str:
    import subprocess
    return subprocess.run(("git", "-C", str(ROOT), *args),
                          capture_output=True, text=True).stdout.strip()


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="not a git checkout")
def test_every_published_release_tag_is_still_where_it_was():
    """A consumer pins a tag per fit, so a tag that moves or disappears takes a
    fit's data with it. The modelling side had two vintages vendored, fitted
    against and overwritten before any commit of theirs captured them; for that
    period the reproducibility of twelve fits rested on a tag here continuing to
    exist. That makes immutability a property of the contract, and this is the
    check that makes it one rather than a promise.

    If this fails, restore the tag. Do not edit the register to match.
    """
    reg = pl.read_csv(RELEASED, separator="\t", comment_prefix="#",
                      infer_schema_length=None)
    assert reg.height >= 30, "the register lost rows; it is append-only"
    live = set(_git("tag", "-l", "data/*").split())
    missing = [r["tag"] for r in reg.iter_rows(named=True)
               if r["tag"] not in live]
    assert not missing, f"published release tags have been deleted: {missing}"
    moved = [(r["tag"], r["commit"], got)
             for r in reg.iter_rows(named=True)
             if (got := _git("rev-list", "-n", "1", r["tag"])) != r["commit"]]
    assert not moved, f"published release tags now name a different commit: {moved}"


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="not a git checkout")
def test_new_release_tags_are_added_to_the_register():
    """The register is only a guarantee if it is complete. A tag published and
    not recorded is one nothing would notice the loss of."""
    reg = pl.read_csv(RELEASED, separator="\t", comment_prefix="#",
                      infer_schema_length=None)
    known = set(reg["tag"].to_list())
    live = set(_git("tag", "-l", "data/*").split())
    assert not (live - known), (
        f"release tags exist that the register does not record: "
        f"{sorted(live - known)}. Append them to {RELEASED.name}.")


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="not a git checkout")
def test_releases_from_september_carry_an_explicit_revision_number():
    """From 2026-09-01 the first release of a day is `-r0`, so every tag has one
    shape and a consumer's parser needs no special case. The bare form was read
    inconsistently even here: 2026-08-15 runs bare, r2, r3 ... with no r1, so
    that day's bare tag stood for revision one, while every other day's stood
    for revision zero. Historical tags are not renamed — published fits point
    at them."""
    bare = [t for t in _git("tag", "-l", "data/*").split()
            if re.fullmatch(r"data/\d{4}-\d\d-\d\d", t)]
    late = [t for t in bare if t.removeprefix("data/") >= "2026-09-01"]
    assert not late, (
        f"these tags are missing an explicit revision: {sorted(late)}. "
        "The first release of a day is `-r0`.")


@pytest.mark.skipif(not (ROOT / "data/build/figures/latest").exists(),
                    reason="no build in this checkout")
def test_every_committed_figure_came_from_the_release_directory():
    """`figures/` is the captioned subset of the current release, and nothing
    else. That sentence is only true if every committed PNG is byte-identical
    to the one in `data/build/figures/<release>/` it was copied from.

    It went untrue once, quietly. `make compare` drew its two comparison
    figures straight into `data/build/compare/` and copied them to the
    committed directory from there, so they never passed through the release
    directory at all — which made `latest/` not a superset of what shipped, and
    made "which release is this figure from" unanswerable for three of the
    sixteen. Both targets now draw into the release directory and copy out of
    it, and this is the check that keeps it that way.
    """
    latest = ROOT / "data/build/figures/latest"
    missing, differ = [], []
    for png in sorted(FIGURE_DIR.glob("*.png")):
        built = latest / png.name
        if not built.exists():
            missing.append(png.name)
        elif built.read_bytes() != png.read_bytes():
            differ.append(png.name)
    assert not missing, (
        f"committed figures with no counterpart in {latest.name}/: {missing}. "
        "Every figure must be drawn into the release directory and copied "
        "from there, so the release it belongs to is answerable.")
    assert not differ, (
        f"committed figures that differ from the current build: {differ}. "
        "Run `make figures && make compare`.")


@needs_pdfs
def test_care_sitrep_062_summary_does_not_credit_ituri_with_tshopos_census():
    """Sitrep 062: "L'Ituri concentre l'essentiel des patients (549), avec une
    saturation persistante au CT de Bambu (316 %) ... tandis que le Nord-Kivu
    et la Tshopo comptaient respectivement 171 et 5 patients en isolement."

    The summary sentence runs from its subject into other provinces with no
    full stop between. The only phrase in it shaped like a census is Tshopo's
    "5 patients en isolement", so `census_ituri` published 5 on a day the ward
    held 541 the morning after. Nothing caught it: the segment carries no bed
    count, so the row's `checks` were `unchecked`, and a wrong stock in a
    stream of ~500s is invisible in a table.

    It was found by drawing the census beside the flows in `streams_detail`,
    where it is a vertical line to the axis.
    """
    by = _care(62)
    assert by["Ituri"]["census"] == 549
    # Nord-Kivu's 171 and Tshopo's 5 are *not* recovered from this sentence, and
    # that is the right outcome rather than a gap to close: "respectivement 171
    # et 5" ties two numbers to two provinces by order alone, and reading it
    # would be guessing at a construction the licence has not established. They
    # are absent, not wrong.
    assert "Nord-Kivu" not in by or by["Nord-Kivu"]["census"] is None


def test_care_the_summary_cut_keeps_the_subjects_own_figure():
    """Cutting the summary sentence at the next province must not throw away
    the subject's census with it. `pool` strips parentheticals to keep
    cumulative clauses out of the number pool, which also removes "(549)", so
    this phrasing is read off the raw segment."""
    import extract_care_prose as C
    seg = ("l'essentiel des patients (549), avec une saturation persistante "
           "au CT de Bambu (316 %), tandis que le Nord-Kivu")
    m = C.ESSENTIEL.search(seg)
    assert m and C._int(m.group(1)) == 549


@needs_pdfs
def test_every_province_the_source_reports_is_published():
    """The guard against the mistake that prompted it. Tshopo, Sud-Kivu and
    Bas-Uélé were extracted in full and published nowhere for weeks; their
    absence from the streams was read as the source not reporting them.

    `build_streams.py` now stops if a place carries confirmed cases and is
    neither published nor listed in `registers/excluded_places.tsv` with a
    reason. This checks the outcome rather than the mechanism: every province
    the series carry cases for has a published daily case stream.
    """
    ps = pl.read_csv(ROOT / "data/build/series/province_series.csv",
                     try_parse_dates=True).drop_nulls("province")
    reported = {p for p, n in ps.group_by("province")
                .agg(pl.col("cum_cases").max()).iter_rows() if n and n > 0}
    assert len(reported) >= 6, reported
    excluded = set()
    reg = ROOT / "registers/excluded_places.tsv"
    if reg.exists():
        d = pl.read_csv(reg, separator="\t", comment_prefix="#",
                        infer_schema_length=None)
        if d.height:
            excluded = set(d["place"].to_list())
    missing = []
    for prov in sorted(reported - excluded):
        slug = BS.STREAM_PROVINCES.get(prov)
        if slug is None or not (STREAMS / f"cases_daily_{slug}.tsv").exists():
            missing.append(prov)
    assert not missing, (
        f"the source reports confirmed cases for {missing} and no daily case "
        "stream is published for them. Add to STREAM_PROVINCES, or record a "
        "reason in registers/excluded_places.tsv.")


@needs_pdfs
def test_the_excluding_backlog_family_covers_every_published_place():
    """It is the family we tell consumers to fit, so a consumer binding it
    across provinces must not find some absent. Bas-Uélé and Sud-Kivu have no
    notified stream — the banner printed its breakdown only for sitreps 059-083
    — and requiring one silently skipped writing their file."""
    for slug in BS.STREAM_PROVINCES.values():
        for stem in ("cases", "deaths"):
            f = STREAMS / f"{stem}_excluding_backlog_{slug}.tsv"
            assert f.exists(), f"{f.name} is not published"
