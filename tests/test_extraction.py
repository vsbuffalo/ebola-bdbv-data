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
    seen: dict[str, list] = {"cumul_recovered": [], "cumul_deaths": []}
    for p in sorted(PDFS.glob("sitrep_*.pdf")):
        got, _, _ = B.extract(p)
        for k in seen:
            if got.get(k) is not None:
                seen[k].append((p.name, got[k]))
    for k, series in seen.items():
        falls = [(a, b) for a, b in zip(series, series[1:]) if b[1] < a[1]]
        assert not falls, f"{k} falls at {falls}"
    # One per report in the archive, which is 90; sitrep 007 prints ND for
    # recoveries. These counts move whenever the archive grows, so a failure
    # here means "reports were fetched", not "the reader broke" -- check the
    # falls assertion above first, which is the one that is about the data.
    assert len(seen["cumul_recovered"]) == 89
    assert len(seen["cumul_deaths"]) == 90


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

import build_streams as BS                                        # noqa: E402

STREAMS = ROOT / "data" / "build" / "streams"
needs_streams = pytest.mark.skipif(
    not (STREAMS / "revisions.tsv").exists(),
    reason="the streams are not built; run `make build && make streams`")


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
@needs_streams
@pytest.mark.parametrize("stream, column, total", [
    ("cases_daily_ituri", "cases_ituri", 4559),
    ("deaths_daily_ituri", "deaths_ituri", 2030),
    ("cases_daily_nord_kivu", "cases_nord_kivu", 711),
    ("deaths_daily_nord_kivu", "deaths_nord_kivu", 484),
    ("cases_daily_haut_uele", "cases_haut_uele", 172),
    ("deaths_daily_haut_uele", "deaths_haut_uele", 76),
    ("cases_haut_uele", "cases_haut_uele", 172),
    ("deaths_haut_uele", "deaths_haut_uele", 76),
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
