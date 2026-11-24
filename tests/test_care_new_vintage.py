"""The care ledger in the "Province : ..." vintage (sitrep 178 onward).

From report 176 the care pillar's bullets became full paragraphs, and the
reader's yield fell from about 2.2 licensed censuses per report to 0.6. The
numbers were all still printed. Each test below quotes the page it is pinned
to; the last is the tripwire that keeps the next change of wording from
thinning the ledger silently again.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_care_prose as C  # noqa: E402

PDFS = ROOT / "data" / "raw" / "sitrep_pdfs"
SERIES = ROOT / "data" / "build" / "series"
needs_pdfs = pytest.mark.skipif(
    not PDFS.is_dir() or not any(PDFS.glob("*.pdf")),
    reason="the PDF archive is not present; run `make fetch`")
needs_series = pytest.mark.skipif(
    not (SERIES / "care_prose_status.csv").exists(),
    reason="the series are not built; run `make build`")


def care(n: int) -> dict[str, dict]:
    hits = sorted(PDFS.glob(f"sitrep_{n:03d}_*.pdf"))
    if not hits:
        pytest.skip(f"sitrep {n} is not in the archive")
    rows, _ = C.extract(hits[0])
    return {r["province"]: r for r in rows}


@needs_pdfs
def test_190_reads_past_the_word_logistique():
    """"Nord-Kivu : ... Sur le plan logistique, 19 ambulances sont
    disponibles ... Ituri : 611 patients hospitalisés au total (372 confirmés
    et 239 suspects)". The section used to end at "logistique", inside the
    first bullet, and the report yielded no care row."""
    by = care(190)
    nk, itu = by["Nord-Kivu"], by["Ituri"]
    assert (nk["census"], nk["census_confirmed"], nk["census_suspect"]) == \
        (599, 152, 447)
    assert (itu["census"], itu["census_confirmed"], itu["census_suspect"]) == \
        (611, 372, 239)
    assert itu["census_licensed"] and nk["census_licensed"]


@needs_pdfs
def test_the_first_province_after_the_title_opens_a_passage():
    """"3.3.1. Principales actions Nord-Kivu : La journée compte 604 patients
    hospitalisés (139 cas confirmés et 465 suspects ...)" (sitrep 189)."""
    nk = care(189)["Nord-Kivu"]
    assert (nk["census"], nk["census_confirmed"], nk["census_suspect"]) == \
        (604, 139, 465)


@needs_pdfs
def test_the_start_of_day_census_is_not_the_census():
    """"La journée a débuté avec 37 patients hospitalisés (34 suspects et 3
    confirmés) ... 29 patients restent hospitalisés à l'issue de la journée"
    (Nord-Ubangi, sitrep 186): the census is the 29."""
    assert care(186)["Nord-Ubangi"]["census"] == 29


@needs_pdfs
def test_the_day_balances_where_the_start_is_printed():
    """"Sur un report de 482 patients ..., 116 nouvelles admissions ... et 84
    sorties ... 514 patients hospitalisés" (Nord-Kivu, sitrep 185):
    482 + 116 - 84 = 514."""
    nk = care(185)["Nord-Kivu"]
    assert (nk["census_start"], nk["admissions"], nk["exits"], nk["census"]) == \
        (482, 116, 84, 514)
    assert "balance=pass" in nk["checks"]


@needs_pdfs
def test_a_stale_admissions_clause_fails_the_balance():
    """Sitrep 181 prints Nord-Kivu's "604 nouvelles admissions (132 confirmés
    et 472 suspects)" -- the previous report's census, word for word -- beside
    "14 patients en report", "200 sorties" and "540 patients hospitalisés".
    Its own split sums, so only the day's balance can refuse it."""
    nk = care(181)["Nord-Kivu"]
    assert nk["admissions"] == 604
    assert "balance=fail" in nk["checks"] and not nk["licensed"]


@needs_pdfs
def test_patients_outside_the_treatment_centres_are_not_the_census():
    """"535 patients aux lits (184 confirmés, 351 suspects ...) ... 155
    patients sont hospitalisés hors CTE/CT" (Nord-Kivu, sitrep 178)."""
    nk = care(178)["Nord-Kivu"]
    assert (nk["census"], nk["census_confirmed"]) == (535, 184)


@needs_pdfs
def test_a_run_on_province_is_not_filed_under_the_one_before():
    """"Cumul des guéris : 48 Ituri : 383 patients sont hospitalisés"
    (sitrep 185) and "au CTE d'Isiro Bas-Uélé Aucun nouveau cas confirmé"
    (sitrep 188): no full stop before either province, and both were read
    into the province before them."""
    by = care(185)
    assert by["Ituri"]["census"] == 383
    assert by["Tshopo"]["exits"] is None
    by = care(188)
    assert by["Bas-Uélé"]["admissions"] == 13
    assert "Haut-Uélé" not in by or by["Haut-Uélé"]["admissions"] is None


@needs_pdfs
def test_a_meals_share_is_not_a_bed_count():
    """"97 % (359/372) des patients ont reçu des repas chauds" (Ituri,
    sitrep 186) read as 372 beds."""
    assert care(186)["Ituri"]["beds"] is None


@needs_pdfs
def test_the_long_parenthetical_census_of_nord_kivu():
    """"Au total, 595 patients (197 confirmés et 398 suspects, dont 67
    enfants de moins de 5 ans et 27 malades critiques) restent en isolement"
    (sitrep 174): Nord-Kivu's, not a national summary."""
    by = care(174)
    assert (by["Nord-Kivu"]["census"], by["Nord-Kivu"]["census_confirmed"]) \
        == (595, 197)
    assert "Ensemble" not in by


@needs_pdfs
def test_continuity_of_services_is_not_the_care_pillar():
    """"En Ituri, 18 guéris (12 au premier suivi et 6 au second) ont
    bénéficié d'un suivi médical" sits under "Continuité des Soins" in
    sitrep 161, a section about ordinary health services: survivors in
    follow-up, not the day's recoveries (the care bullet prints 8)."""
    assert care(161)["Ituri"]["exits_recovered"] in (None, 8)


@needs_series
def test_the_province_censuses_sum_to_the_front_page_tile():
    """The second printing. The front-page ISOLEMENT/CTE tile states the
    national census; the province paragraphs sum to it exactly on 33 reports
    between 109 and 165. From 181 the tile prints about 1,700 against about
    1,000 in the paragraphs and no longer measures the same thing, so the
    check stops at 165 rather than excusing that gap."""
    c = (pl.read_csv(SERIES / "care_prose.csv", infer_schema_length=None)
         .filter(pl.col("province") != "Ensemble")
         .group_by("sitrep").agg(pl.col("census").sum().alias("sum")))
    b = pl.read_csv(SERIES / "banner.csv")
    j = b.join(c, on="sitrep").filter(pl.col("sitrep").is_between(100, 165))
    assert j.filter(pl.col("sum") == pl.col("patients_isolated")).height >= 33


@needs_series
def test_the_care_reader_has_not_gone_quiet():
    """The tripwire. Over reports 150-175 the reader licensed a census for
    about 2.5 provinces per report; if the last seven reports average less
    than one, the wording has changed again."""
    st = pl.read_csv(SERIES / "care_prose_status.csv").sort("sitrep")
    last = st.tail(7)
    assert last["n_census_licensed"].mean() >= 1.0, last
