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
def test_lab_prose_flow_not_stock():
    """Sitrep 020's bullet vintage states no flow word; the laboratory
    section is daily by construction and the positives equal the day's
    printed new confirmed cases (18)."""
    import extract_lab_prose as L
    got, _ = L.extract(pdf(20))
    itu = [r for r in got if r["province"] == "Ituri"]
    assert itu and itu[0]["positives"] == 18 and itu[0]["samples"] == 82


# --------------------------------------------------------------------------
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

import build_streams as B                                        # noqa: E402

STREAMS = ROOT / "data" / "build" / "streams"
needs_streams = pytest.mark.skipif(
    not (STREAMS / "revisions.tsv").exists(),
    reason="the streams are not built; run `make build && make streams`")


def test_carry_forward_leaves_no_negative_and_moves_no_total():
    """The two properties the whole scheme rests on, on the real shape:
    Nord-Kivu's 11 June cumulative falls by 4, and 13 June's 22 pays it."""
    emitted, outstanding = B.carry_forward([3, -4, 0, 22])
    assert emitted == [3, 0, 0, 18]
    assert sum(emitted) == sum([3, -4, 0, 22])
    assert min(emitted) == 0 and outstanding[-1] == 0


def test_carry_forward_is_not_clipping():
    """Clipping `[-4, 9]` gives 9 against a cumulative that moved 5, so the
    stream would permanently carry the four cases the source withdrew."""
    emitted, _ = B.carry_forward([-4, 9])
    assert emitted == [0, 5] and sum(emitted) == 5


def test_a_deficit_larger_than_the_next_row_keeps_going():
    """Haut-Uélé's -6 of 18 July is not repaid until 22 July, across two days
    that report nothing and one that reports 5."""
    emitted, outstanding = B.carry_forward([-6, 0, 0, 5, 6])
    assert emitted == [0, 0, 0, 0, 5]
    assert outstanding == [6, 6, 6, 1, 0]
    assert sum(emitted) == 5


def test_an_undischarged_deficit_is_reported_not_swallowed():
    """A withdrawal on the last report has nothing left to come out of. The
    function does not hide it: the outstanding balance is still 3 at the end,
    which is what the build's gate reads."""
    emitted, outstanding = B.carry_forward([10, -5, 2])
    assert emitted == [10, 0, 0]
    assert outstanding[-1] == 3
    assert sum(emitted) == sum([10, -5, 2]) + 3      # short by exactly the carry


def test_negative_values_reads_the_published_file(tmp_path):
    """The non-negativity gate reads back off disk, so it covers a column that
    never passed through the carry -- a stock reading, or one added later."""
    good = tmp_path / "cases_x.tsv"
    good.write_text("time\tcases_x\n2026-06-01\t3\n")
    assert B.negative_values([good]) == []
    bad = tmp_path / "cases_y.tsv"
    bad.write_text("time\tcases_y\n2026-06-01\t3\n2026-06-02\t-1\n")
    found = B.negative_values([bad])
    assert len(found) == 1 and "cases_y = -1 at 2026-06-02" in found[0]


# -- the eight corrections in the corpus as it stands ----------------------

@needs_streams
def test_the_built_streams_publish_no_negative_count():
    every = [p for p in sorted(STREAMS.glob("*.tsv"))
             if p.name not in ("revisions.tsv", "uganda_exports.tsv")]
    assert every, "no streams found"
    assert B.negative_values(every) == []


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


@needs_streams
@pytest.mark.parametrize("stream, column, total", [
    ("cases_daily_ituri", "cases_ituri", 4343),
    ("deaths_daily_ituri", "deaths_ituri", 1923),
    ("cases_daily_nord_kivu", "cases_nord_kivu", 642),
    ("deaths_daily_nord_kivu", "deaths_nord_kivu", 434),
    ("cases_daily_haut_uele", "cases_haut_uele", 152),
    ("deaths_daily_haut_uele", "deaths_haut_uele", 68),
    ("cases_haut_uele", "cases_haut_uele", 152),
    ("deaths_haut_uele", "deaths_haut_uele", 68),
])
def test_a_corrected_stream_still_totals_the_source_movement(stream, column,
                                                             total):
    """The point of carrying rather than clipping: the corrected stream sums
    to exactly what the source's cumulative moved, unchanged by the fix."""
    d = pl.read_csv(STREAMS / f"{stream}.tsv", separator="\t",
                    infer_schema_length=None)
    assert int(d[column].sum()) == total


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


def _run_build(monkeypatch, panel, out_dir):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sys, "argv", [
        "build_streams.py", "--panel", str(panel),
        "--geojson", str(ROOT / "data/raw/health_zones.geojson"),
        "--population", str(ROOT / "data/raw/zone_population.csv"),
        "--out-dir", str(out_dir)])
    B.main()


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
    assert B.negative_values([p for p in sorted(out.glob("*.tsv"))
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
