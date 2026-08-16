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
