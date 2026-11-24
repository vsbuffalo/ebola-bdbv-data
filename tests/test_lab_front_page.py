"""The front page's national laboratory total (scripts/extract_lab_front_page.py).

Each pinned reading quotes the report it comes from. The archive-wide tests
are the two-printings check the reader exists for, and the tripwire that keeps
this reader from thinning silently the way the section reader did.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_lab_front_page as F  # noqa: E402

PDFS = ROOT / "data" / "raw" / "sitrep_pdfs"
SERIES = ROOT / "data" / "build" / "series"
STREAMS = ROOT / "data" / "build" / "streams"
needs_pdfs = pytest.mark.skipif(
    not PDFS.is_dir() or not any(PDFS.glob("*.pdf")),
    reason="the PDF archive is not present; run `make fetch`")
needs_series = pytest.mark.skipif(
    not (SERIES / "lab_front_page.csv").exists(),
    reason="the series are not built; run `make build`")


def pdf(n: int) -> Path:
    hits = sorted(PDFS.glob(f"sitrep_{n:03d}_*.pdf"))
    if not hits:
        pytest.skip(f"sitrep {n} is not in the archive")
    return hits[0]


@needs_pdfs
@pytest.mark.parametrize("n, samples, positives, pct", [
    # "Un total de 435 nouveaux échantillons a été analysé dans les
    # laboratoires ayant transmis leurs données ; 56 de ces échantillons se
    # sont révélés positifs au virus Bundibugyo, soit 12,9 % de positivité."
    (185, 435, 56, 12.9),
    # "Pour la journée du 22 septembre 2026, 328 nouveaux échantillons ont été
    # analysés, 47 se sont révélés positifs, soit 14,0 % de positivité." --
    # the date's own integers (22, 2026) sit before the sample count.
    (131, 328, 47, 14.0),
    # "Des 446 nouveaux échantillons analysés, 56 se sont révélés positifs"
    (133, 446, 56, 12.6),
    # "323 nouveaux échantillons a été analysé ; 66 de ces échantillons ..."
    (141, 323, 66, 20.4),
    (190, 625, 39, 6.2),
])
def test_front_page_total(n, samples, positives, pct):
    got, why = F.extract(pdf(n))
    assert why is None
    assert (got["samples"], got["positives"], got["printed_pct"]) == \
        (samples, positives, pct)


@needs_pdfs
@pytest.mark.parametrize("n", [
    # "383 nouveaux échantillons a été analysé ; 81 de ces échantillons se
    # sont révélés positifs ..., soit 21,4 %": 81/383 is 21.1 %, so the page's
    # own arithmetic does not close and neither count can be checked.
    165,
    # "439 nouveaux échantillons a été analysé, avec une positivité de 14,4 %":
    # no positive count printed, and none is derived from the rate.
    169,
])
def test_a_sentence_that_does_not_check_is_refused(n):
    got, why = F.extract(pdf(n))
    assert got is None and why == "no_unique_licensed_count"


def test_licence_refuses_ambiguity_and_accepts_truncation():
    assert F.licensed_positives(6, [1], 16.6) == 1      # 16.67 truncated
    assert F.licensed_positives(100, [10, 11], 10.5) is None
    assert F.licensed_positives(100, [120], 12.0) is None


@needs_series
def test_the_two_printings_agree_where_the_section_was_fully_read():
    """The front page's total is the sum of the section's province
    paragraphs. On reports before the denominator widened, every report whose
    province sum reaches the front page's samples must match its positives
    too, and no province sum may exceed the front page by more than report
    174's 5 samples (531 against 526, with every paragraph read)."""
    fp = pl.read_csv(SERIES / "lab_front_page.csv")
    lp = (pl.read_csv(SERIES / "lab_prose.csv").group_by("sitrep")
          .agg(pl.col("samples").sum().alias("ps"),
               pl.col("positives").sum().alias("pp")))
    j = fp.join(lp, on="sitrep").filter(pl.col("sitrep") < F.WIDENED_FROM)
    exact = j.filter(pl.col("ps") == pl.col("samples"))
    assert exact.height >= 13
    assert (exact["pp"] == exact["positives"]).all()
    assert (j["ps"] - j["samples"]).max() <= 5


@needs_series
def test_the_front_page_reader_has_not_gone_quiet():
    """The tripwire for the next change of wording. The sentence has been on
    every report but two since 130, so if it is not read on at least five of
    the last seven reports, the reader has stopped matching the page."""
    st = pl.read_csv(SERIES / "lab_front_page_status.csv").sort("sitrep")
    last = st.tail(7)
    assert last["parsed"].sum() >= 5, last


@needs_series
def test_published_divisor_is_never_empty_or_zero():
    d = pl.read_csv(STREAMS / "lab_front_page_daily_national.tsv",
                    separator="\t", comment_prefix="#", null_values=["NA"])
    assert d["tests_national"].null_count() == 0
    assert d.filter(pl.col("tests_national") == 0).height == 0
    assert set(d["vintage"]) == {"province_sum", "widened"}
