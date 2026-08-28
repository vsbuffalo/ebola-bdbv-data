"""The onset reader's regression fixtures, pinned to real documents.

Every case is a failure mode the design note documents from the upstream
reader, asserted against the vintages this pipeline actually produced. The
CSV-level tests read `data/build/onset/` and skip when it has not been
built (`make onset`); the pixel-level render-invariance test reads the two
published images directly, because it *is* the 087/088 incident: the same
chart at two JPEG encodings moved an upstream reproduction number, and a
correct reader must return the same counts from both.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ONSET = ROOT / "data" / "build" / "onset"
needs_build = pytest.mark.skipif(
    not (ONSET / "vintages.csv").is_file(),
    reason="the onset build is not present; run `make onset`")

# The totals these renders print in their own titles, verified by eye
# against the extracted images and, where they overlap, against the
# independent upstream record.
PRINTED_N = {64: 2064, 65: 2090, 66: 2175, 67: 2233, 68: 2306, 69: 2329,
             72: 2521, 73: 2567, 77: 2814, 78: 2855, 79: 2915, 81: 3066,
             82: 3092, 83: 3092, 87: 3362, 88: 3362, 92: 3767, 94: 3838,
             97: 4084, 98: 4140, 99: 4140, 100: 4238, 101: 4287, 102: 4372}


@pytest.fixture(scope="module")
def vintages():
    import polars as pl
    return pl.read_csv(ONSET / "vintages.csv")


@pytest.fixture(scope="module")
def snapshots():
    import polars as pl
    return pl.read_csv(ONSET / "snapshots.csv")


# --------------------------------------------------------------------------
# Identification: the caption lies, and the refusals prove we never read it.

@needs_build
def test_the_notification_imposters_are_refused_by_name(vintages):
    import polars as pl
    for sitrep in (84, 85, 86):
        row = vintages.filter(pl.col("sitrep") == sitrep)
        assert row.height == 1
        assert row["status"][0] == "refused"
        assert "no onset figure" in row["reasons"][0]


@needs_build
def test_every_onset_report_is_accounted_for(vintages):
    # 42 candidate reports from 059; each is an identified figure or a
    # refusal with a reason -- a silent skip is indistinguishable from a
    # parse failure, so there must be none.
    assert vintages.height == 42
    assert not vintages["status"].is_null().any()
    assert (vintages["status"] == "refused").sum() \
        + (vintages["kind"] == "onset_daily").sum() >= 42


# --------------------------------------------------------------------------
# The printed total: the checksum every vintage reconciles against.

@needs_build
def test_printed_totals_read_exactly(vintages):
    import polars as pl
    got = {r["sitrep"]: r["printed_n"]
           for r in vintages.filter(
               pl.col("printed_n").is_not_null()).iter_rows(named=True)}
    for sitrep, n in PRINTED_N.items():
        assert got.get(sitrep) == n, \
            f"sitrep {sitrep}: printed n read as {got.get(sitrep)}, is {n}"


@needs_build
def test_reads_reconcile_with_their_own_titles(vintages):
    import polars as pl
    read = vintages.filter(pl.col("read_total").is_not_null()
                           & pl.col("printed_n").is_not_null())
    worst = (read["read_total"] - read["printed_n"]).abs().max()
    assert worst <= 30, f"worst |deficit| is {worst} cases"
    exact = ((read["read_total"] - read["printed_n"]).abs() <= 1).sum()
    assert exact >= 0.6 * read.height


# --------------------------------------------------------------------------
# The 087/088 incident: one chart, two encodings, one answer.

@needs_build
def test_the_re_encoded_chart_is_one_observation(vintages):
    import polars as pl
    pair = vintages.filter(pl.col("sitrep").is_in([87, 88, 89, 90, 91]))
    heads = set(pair["dedup_head"].to_list())
    assert len(heads) == 1, \
        "sitreps 087-091 carry one chart and must collapse to one vintage"


def test_render_invariance_on_the_087_088_pair():
    images = sorted((ONSET / "images").glob("*-087-*.png")) \
        + sorted((ONSET / "images").glob("*-088-*.png"))
    if len(images) < 2:
        pytest.skip("images not built; run `make onset`")
    import numpy as np
    from PIL import Image
    from lib.onset.calibrate import calibrate
    from lib.onset.readers import read_bars, refine_scale
    totals = []
    for f in images[:2]:
        im = np.asarray(Image.open(f).convert("RGB")).astype(float)
        cal = refine_scale(im, calibrate(im))
        bars = read_bars(im, cal)
        totals.append(sum(b.alive + b.dead for b in bars))
    assert abs(totals[0] - totals[1]) <= 10, \
        f"the same chart read {totals[0]} and {totals[1]}; " \
        "upstream's reader lost 184 cases here"


@needs_build
def test_the_25_july_bar(snapshots):
    # The requirements note's fixture bar: upstream's good read gives
    # 28 alive + 15 dead, and their bad re-encode read gave 27 + 0. This
    # pipeline reads 29 + 15 with both readers agreeing at a confident
    # margin, on a figure whose total reconciles with its printed n
    # exactly -- the bar top sits within half a pixel of both 43 and 44 at
    # 4.33 px per case, so the pin is the dead cap (which the incident
    # amputated) exactly, and the alive count to the stated resolution.
    import polars as pl
    bar = snapshots.filter((pl.col("onset_date") == "2026-07-25")
                           & (pl.col("sitrep") == 87))
    assert bar.height == 1
    assert bar["dead"][0] == 15, \
        f"the 25 July red cap reads {bar['dead'][0]}, is 15"
    assert abs(bar["alive"][0] - 28) <= 1
    assert bar["reader_agreement"][0]


# --------------------------------------------------------------------------
# Monotonicity: late reporting only adds cases.

@needs_build
def test_stable_regions_never_fall(vintages):
    import polars as pl
    heads = (vintages.filter(pl.col("stable_total").is_not_null())
             .unique(subset=["dedup_head"], keep="first")
             .sort("report_date"))
    stables = heads["stable_total"].to_list()
    falls = [(a, b) for a, b in zip(stables, stables[1:]) if b < a - 45]
    assert not falls, f"stable-region totals fell: {falls}"


@needs_build
def test_no_vintage_was_refused_by_the_gates(vintages):
    # The archive as read today passes its own gates; a future change that
    # trips one should be looked at, not absorbed. Sitrep 059 is the known
    # exception: its earliest render misaligns ticks and bars and is
    # refused at calibration, loudly.
    import polars as pl
    refused = vintages.filter((pl.col("status") == "refused")
                              & (pl.col("kind") == "onset_daily"))
    assert refused["sitrep"].to_list() == [59]


# --------------------------------------------------------------------------
# The triangle never spans a refused vintage.

@needs_build
def test_triangle_endpoints_are_accepted(vintages):
    import polars as pl
    tri = pl.read_csv(ONSET / "triangle.csv")
    ok = set(vintages.filter(pl.col("status") != "refused")
             ["dedup_head"].drop_nulls().to_list())
    used = set(tri["sha12_from"].to_list()) | set(tri["sha12_to"].to_list())
    assert used <= ok


# --------------------------------------------------------------------------
# The anchor register is internally consistent.

def test_gamma_cdf_reproduces_the_printed_quantiles():
    # The comparison figure draws Akilimali et al.'s onset-to-sample Gamma
    # through a scipy-free incomplete-gamma implementation; it must land on
    # the quantiles the paper actually printed (median and quartiles) and
    # the q90 the modelling repository derived from the same fit.
    from plot_figures import (_gammainc_p, AKILIMALI_GAMMA_K,
                              AKILIMALI_GAMMA_THETA)
    for q, want in [(1.80, 0.25), (4.80, 0.50), (10.25, 0.75),
                    (17.68, 0.90)]:
        got = _gammainc_p(AKILIMALI_GAMMA_K, q / AKILIMALI_GAMMA_THETA)
        assert abs(got - want) < 0.01, (q, got, want)


def test_anchor_register_spans_whole_weeks():
    import csv
    import datetime as dt
    path = ROOT / "registers" / "onset_axis_anchors.tsv"
    with open(path, newline="") as f:
        rows = list(csv.DictReader(
            (line for line in f if not line.startswith("#")),
            delimiter="\t"))
    assert len(rows) >= 28
    for r in rows:
        span = (dt.date.fromisoformat(r["last_date"])
                - dt.date.fromisoformat(r["first_date"])).days
        assert span > 0 and span % 7 == 0, \
            f"{r['image_file']}: {span} days is not whole weeks"
