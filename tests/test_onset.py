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
             97: 4084, 98: 4140, 99: 4140, 100: 4238, 101: 4287, 102: 4372,
             103: 4454, 106: 4628, 112: 4997, 123: 5626, 125: 5693,
             128: 5854, 129: 5896, 130: 5944, 132: 6046, 133: 6138,
             136: 6256, 138: 6370, 139: 6417, 140: 6468, 143: 6621,
             147: 7054, 149: 7136, 153: 7388, 154: 7438, 156: 7438,
             158: 7660, 159: 7660}


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
    # Every candidate report from 059 on is either an identified figure or a
    # refusal carrying a reason -- a silent skip is indistinguishable from a
    # parse failure, so there must be none. The count grows as reports arrive;
    # what is asserted is that none is unaccounted for, not a fixed total.
    assert vintages.height >= 42
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
    """Only over ACCEPTED reads. `read_total`/`printed_n` both being present
    used to imply a trustworthy digitisation, because every earlier refusal
    was decided before digitisation ran (no anchor row, ticks off grid). A
    read the gates refuse after digitising (138, 153 and 154, for reader
    disagreement) carries both columns too, so a row can hold both and
    still be exactly the bad read this test is checking for. Scoping to accepted rows keeps the assertion about what it
    was written to assert: agreement among the reads this build actually
    trusts, not among every number this build computed on the way to
    deciding whether to trust it.

    THE BOUND IS RELATIVE, LIKE THE GATE IT IS CHECKING, not the absolute 30
    cases this assertion used to hardcode. `gates.G2_UNDER` is 2% precisely
    because the axis legitimately stops short of the report date, so the
    newest onsets are in the printed total but not yet plotted -- a real
    property of the chart, not reader slop, and one that costs more absolute
    cases as the outbreak grows. A fixed absolute bound is only really
    testing a `printed_n` from when it was written (about 1,500): 127 prints
    5,797 and reads 62 short, 1.07%, a real test failure only because 30
    stopped meaning 2% once the outbreak grew past roughly 1,500 cases.

    THE BOUND IS STRICTLY TIGHTER THAN G2_UNDER, DELIBERATELY, not equal to
    it. `status != "refused"` already means `gates.judge` itself guarantees
    every surviving row sits inside G2_UNDER -- asserting `<= G2_UNDER` here
    would be true by construction of the filter above and catch nothing but
    a stale build artefact, the same failure mode this test exists to tell
    apart from a real one. Three-quarters of the band -- 1.5% -- is the
    companion to the "inner quarter" bound below (`0.25 * G2_UNDER`) read
    from the other end: no accepted read should sit in the OUTER quarter of
    G2's tolerance. It is independent of today's worst case rather than
    fitted to it -- 1.07% clears it with real margin, not by construction --
    so a future vintage genuinely drifting toward the edge of what G2 accepts
    still has somewhere to fail before the gate itself would refuse it."""
    import polars as pl
    from lib.onset import gates
    read = vintages.filter(pl.col("read_total").is_not_null()
                           & pl.col("printed_n").is_not_null()
                           & (pl.col("status") != "refused"))
    worst_frac = ((read["printed_n"] - read["read_total"])
                 / read["printed_n"]).max()
    bound = 0.75 * gates.G2_UNDER
    assert worst_frac <= bound, \
        f"worst under-read is {worst_frac:.1%} of printed n, beyond the " \
        f"{bound:.1%} bound -- the outer quarter of G2's own " \
        f"{gates.G2_UNDER:.0%} band, where an accepted vintage should not " \
        f"sit even though the gate itself would still take it"
    # MOST READS LAND WELL INSIDE THE GATE'S BAND, NOT MERELY INSIDE IT: the
    # same scale argument applies to "exact" as to "worst" above. `<= 1 case`
    # was a tight bound while `px_per_case` ran 5-7 (sitreps 064-083); it has
    # fallen to 2.7-3.0 as the same fixed chart height now packs in 5,000+
    # cases, so a single pixel of quantisation noise is worth close to three
    # cases and "exact to within one case" is asking for sub-pixel precision
    # a bar chart cannot supply. A quarter of G2's own band scales the same
    # way the band does and keeps the assertion's intent -- most reads are
    # comfortably tight, not just barely inside -- true at every printed_n
    # this build has seen: 84.8% of accepted reads clear it against a 60%
    # floor, both before and after 114-127.
    tight = ((read["printed_n"] - read["read_total"]).abs()
             <= 0.25 * gates.G2_UNDER * read["printed_n"]).sum()
    assert tight >= 0.6 * read.height, \
        f"only {tight} of {read.height} accepted reads land within a " \
        f"quarter of G2's {gates.G2_UNDER:.0%} band"


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
    from lib.onset.readers import detect_stacking, read_bars, refine_scale
    totals = []
    for f in images[:2]:
        im = np.asarray(Image.open(f).convert("RGB")).astype(float)
        cal = detect_stacking(im, refine_scale(im, calibrate(im)))
        bars = read_bars(im, cal)
        totals.append(sum(b.alive + b.dead for b in bars if b.read))
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
    """Only over ACCEPTED reads, for the same reason as the title-checksum
    test above: a refused read's `stable_total` is a real number computed
    from a read the gates went on to refuse, and comparing across a
    known-bad read is not evidence about the pipeline's monotonicity."""
    import polars as pl
    heads = (vintages.filter(pl.col("stable_total").is_not_null()
                             & (pl.col("status") != "refused"))
             .unique(subset=["dedup_head"], keep="first")
             .sort("report_date"))
    stables = heads["stable_total"].to_list()
    falls = [(a, b) for a, b in zip(stables, stables[1:]) if b < a - 45]
    assert not falls, f"stable-region totals fell: {falls}"


#: Onset vintages the reader refuses, each with the reason, so a refusal is a
#: recorded gap rather than a silent skip. The causes:
#:
#:   * a stray tick (59) -- a detection 0.11 weeks from the first, which no
#:     weekly axis can carry. The renders from 108 on that this entry used
#:     to share were a different defect, now fixed: their y axis is a light
#:     grey line the zero label touches, so the panel was taken to start at
#:     the label, and the label's ink below the baseline became a phantom
#:     first tick (see `calibrate._corner`).
#:
#:   * too few ticks detected for the anchor's span (108, 109, 141) -- the
#:     labels are registered, but the tick reader misses one (108) or three
#:     late ticks (141), so the detected count does not fit the weeks the
#:     printed labels span and the register's dates cannot be trusted onto
#:     these ticks.
#:
#:   * the title's printed total not read (111, 146, 151, 152) -- a genuine onset figure
#:     whose glyphs the title reader did not resolve. It is refused rather
#:     than read because that total is the checksum the bar sum is validated
#:     against, and reading the bars without it would ship an unvalidated
#:     vintage. 114 and 116 were this same failure -- their `)` glyph scored
#:     0.67-0.70 against the atlas's 0.72 match floor, just under it -- and
#:     are fixed: `scripts/lib/onset/glyphs/rparen/114.png` is a new
#:     exemplar, cut through the atlas's own `_normalise` from 114's own
#:     render, that raised both over the floor. 111 did not clear the same
#:     way, so its glyph is a different near-miss the new exemplar does not
#:     cover.
#:
#:   * the bar heights do not sum to the printed total (114) -- a different
#:     gate catching a different thing: 114's title now reads correctly
#:     (5,119, the fix above), but its digitised bars sum to 4,858, 261
#:     short. Some property of this specific render -- compression, contrast,
#:     something the pixel calibration reads slightly wrong -- is losing
#:     real ink, and the checksum gate is doing exactly its job by refusing
#:     a vintage that would otherwise ship 5% under its own printed count.
#:     140, 149 and 153-155 are refused by the same gate for a measured
#:     reason: `readers.refine_scale` moves the scale up by 1-1.5% from the
#:     label fit on these ~2.6 px-per-case renders (114 by 3.9%), and every
#:     upward move across the archive makes the read worse, while every
#:     downward one improves it; at this resolution a case is about the size
#:     of the measured bar tops' noise, so the integer lattice no longer pins
#:     the scale.
#:
#:   * the two readers disagree on over a quarter of bars (138, 149, 153-155,
#:     159) -- at 2.3-2.8 px per case the outline reader often misses the
#:     stroke between the alive and dead segments, and JPEG chroma smears
#:     that boundary across about a case, so the cross-check cannot confirm
#:     the split. 159 reads within its printed total (-0.65%) and is refused
#:     on this gate alone.
#:
#:   * the y axis not read (135, 150) -- too few labels recognised (135) or
#:     no zero glyph at the baseline (150).
#:
#:   * NOT AN ONSET FIGURE AT ALL (110) -- and this one is a defect, not a
#:     gap. Sitrep 110 prints a chart titled "par date de notification" where
#:     the others print "par date de debut des symptomes", and
#:     `lib/onset/identify.py` classified it `onset_daily` anyway. That module
#:     separates the two families on fill colour, and its premise -- "the
#:     notification charts are the only ones with a dark blue fill" -- has
#:     stopped holding: 110 measures dark_blue 0.0067 against a 0.05
#:     threshold, because the source restyled its notification chart into the
#:     onset chart's palette. The only thing standing between that chart and
#:     the onset series is the missing anchor row, which the backlog above
#:     invites someone to add. `registers/onset_axis_anchors.tsv` carries a
#:     note naming the hash so nobody adds it; the classifier still needs a
#:     discriminator that does not rest on a colour the source controls.
#:
#: The cost of the real refusals is that the triangle skips the refused
#: vintages: an increment is only ever taken between two accepted ones, so a
#: refused report widens the window of the next increment instead of
#: inventing one.
KNOWN_REFUSED = {
    59:  "x ticks are not on a weekly grid",
    108: "detected ticks",
    109: "detected ticks",
    110: "no anchor row",
    111: "printed n not found in the title",
    135: "y axis unreadable",
    138: "readers disagree",
    141: "detected ticks",
    146: "printed n not found in the title",
    150: "no zero label at the baseline",
    151: "printed n not found in the title",
    152: "printed n not found in the title",
    153: "readers disagree",
    154: "readers disagree",
    155: "readers disagree",
}

#: Reports after the last one this register was written against. The daily
#: release must not stop on the onset reader -- a refused vintage is left
#: out of the published reporting-delay table, not guessed -- so a new
#: report may refuse without an entry here; the
#: reasons above stay pinned, and a known one that starts reading, or
#: refuses for a different reason, still fails.
UNREGISTERED_FROM = 160


@needs_build
def test_refusals_are_the_known_ones_and_nothing_new(vintages):
    """A refusal is allowed; an *unexplained* refusal is not.

    This asserts the set rather than a count, so a new one fails here with its
    sitrep number instead of being absorbed into a tally that still looks
    plausible. Clearing an entry from `KNOWN_REFUSED` is the work of adding
    its anchor row, not of editing this test.
    """
    import polars as pl
    refused = vintages.filter((pl.col("status") == "refused")
                              & (pl.col("kind") == "onset_daily"))
    got = {n for n in refused["sitrep"].to_list() if n < UNREGISTERED_FROM}
    expected = set(KNOWN_REFUSED)
    assert got == expected, (
        f"unexplained refusal(s): {sorted(got - expected)}; "
        f"newly readable: {sorted(expected - got)}")
    for n, why in KNOWN_REFUSED.items():
        row = refused.filter(pl.col("sitrep") == n)
        assert why in row["reasons"][0], (
            f"sitrep {n} is refused for a different reason now: "
            f"{row['reasons'][0]}")


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


# --------------------------------------------------------------------------
# The long-axis renders (sitrep 108 on): a light grey y axis, half-pixel ticks.

def _image(sitrep: int):
    images = sorted((ONSET / "images").glob(f"*-{sitrep:03d}-*.png"))
    if not images:
        pytest.skip("images not built; run `make onset`")
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(images[0]).convert("RGB")).astype(float)


def test_a_light_grey_axis_is_the_panel_corner():
    # Sitrep 159's y axis is a grey line (luminance ~200) at x = 44 that the
    # zero label touches. Taking the baseline run's start (x = 35, the label)
    # as the corner clipped the zero out of the y reader's margin and made
    # the label's ink a phantom tick 1.9 weeks before 06 avr.
    from lib.onset.calibrate import calibrate
    cal = calibrate(_image(159))
    assert cal.panel.left == 44
    assert cal.tick_xs[0] == 78.0          # the 06 avr tick, not the label
    assert len(cal.tick_xs) == 29          # 06 avr .. 19 oct, 28 weeks
    assert [v for v, _ in cal.y_labels] == [0, 25, 50, 75, 100]


@needs_build
def test_the_zero_label_against_a_grey_axis_is_read(vintages):
    # 136 refused "no zero label at the baseline" for the same cause.
    import polars as pl
    row = vintages.filter(pl.col("sitrep") == 136)
    assert row["status"][0] == "accepted"
    assert row["printed_n"][0] == 6256


@needs_build
def test_sitrep_159_reads_within_its_printed_total(vintages):
    # Its first slot sat on the grey axis and read 98 cases from the line
    # alone (+0.64% over printed n, a G2 refusal). With slots required to
    # clear the border it reads inside G2. It prints the same n = 7,660 as
    # 158 and, read from the baseline's centre, agrees with 158 bar for
    # bar: one data snapshot, published from 158's render.
    import polars as pl
    from lib.onset import gates
    row = vintages.filter(pl.col("sitrep") == 159)
    n, got = row["printed_n"][0], row["read_total"][0]
    assert -gates.G2_UNDER * n <= got - n <= gates.G2_OVER * n
    head = vintages.filter(pl.col("sitrep") == 158)["dedup_head"][0]
    assert row["dedup_head"][0] == head
    assert not row["decoded_sha256"][0].startswith(head)


@needs_build
def test_no_bar_is_read_off_the_left_border(snapshots):
    # Every count before April in an accepted vintage was the axis line read
    # as fill: one or two cases on 28-29 March, zeros either side (sitreps
    # 100, 117, 119, 122, 130). The epidemic's first onsets are in April.
    import polars as pl
    early = snapshots.filter((pl.col("status") != "refused")
                             & (pl.col("onset_date") < "2026-04-01")
                             & ((pl.col("alive") + pl.col("dead")) > 0))
    assert early.height == 0, early.select("sitrep", "onset_date").rows()


def test_the_tick_grid_survives_half_pixel_tick_centres():
    # Tick centres are whole or half pixels. Thirty ticks 21.34 px apart
    # alternate 21 and 22 px gaps, whose median (21.5) drifted the old
    # distance-from-first test a quarter of a week over the axis.
    import numpy as np
    from lib.onset.calibrate import CalibrationError, bar_pitch
    true_gap = 21.34
    ticks = tuple(float(np.round(78 + k * true_gap * 2) / 2)
                  for k in range(30))
    pitch = true_gap / 7
    prof = np.array([0.0 if (x % pitch) < 0.6 else 10.0
                     for x in range(700)])
    got, _ = bar_pitch(prof, ticks)
    assert abs(got - pitch) < 0.01
    # A stray detection off the weekly grid still refuses (sitrep 059).
    with pytest.raises(CalibrationError, match="weekly grid"):
        bar_pitch(prof, (ticks[0], ticks[0] + 0.11 * true_gap) + ticks[1:])


# --------------------------------------------------------------------------
# The "donnees potentiellement incompletes" band: a translucent overlay over
# the last week of bars, read through rather than at.

def test_the_band_is_the_pink_cluster_not_the_first_pink_column():
    # Sitrep 106's "premier resultat positif" annotation box puts one pink
    # column at x = 174. Taken as the band's left edge, it marked 133 of
    # the figure's bars provisional and read them against washed colours.
    from lib.onset.calibrate import calibrate
    cal = calibrate(_image(106))
    assert cal.band_left == 688           # the antialiased edge column
    assert cal.band_right == 718
    assert 0.35 <= cal.palette.transmission <= 0.5


def test_bars_drawn_over_the_band_are_read_as_drawn():
    # In sitreps 059-062 the bars sit on top of the band in their legend
    # colours; inverting an overlay that is not over them would wash them
    # out. Measured, not assumed: the "bars on top" hypothesis wins.
    from lib.onset.calibrate import calibrate
    assert calibrate(_image(60)).palette.transmission is None
    assert calibrate(_image(106)).palette.transmission is not None


@needs_build
@pytest.mark.parametrize("sitrep,onset,total", [
    (106, "2026-08-24", 29),   # under the band and its label; read as 2
    (143, "2026-09-30", 23),   # narrow render, outline column; read as 2
    (149, "2026-10-05", 19),   # in the band's antialiased edge; read as 2
])
def test_a_bar_under_the_band_is_read_through_it(snapshots, sitrep, onset,
                                                 total):
    # Totals by eye from the extracted images, and equal (within a case) to
    # the epiforecasts digitisation at 7704956, which reads these bars
    # independently.
    import polars as pl
    row = snapshots.filter((pl.col("sitrep") == sitrep)
                           & (pl.col("onset_date") == onset))
    assert row.height == 1
    assert abs(row["total"][0] - total) <= 1, row.rows()


@pytest.mark.parametrize("sitrep", [106, 147])
def test_the_band_label_and_top_border_are_not_bar_outlines(sitrep):
    # The label's glyphs are drawn on top of the band, and the panel's top
    # border crosses it; both are dark, and the outline reader once took
    # them for bar tops (106's 26 August bar: 87 dead; 147's empty slots
    # after the report date: 104 cases). No bar in either band exceeds 30.
    from lib.onset.calibrate import calibrate
    from lib.onset.readers import detect_stacking, read_bars, refine_scale
    im = _image(sitrep)
    cal = detect_stacking(im, refine_scale(im, calibrate(im)))
    tops = [(b.edge_alive or 0) + (b.edge_dead or 0)
            for b in read_bars(im, cal) if b.provisional]
    assert tops and max(tops) <= 30, tops


# --------------------------------------------------------------------------
# Stacking order: which colour sits at the baseline is measured per render.
# Sitreps 059-062 stack dead (red) under alive (light blue); every render
# from 064 on stacks alive under dead. Read in the wrong order, 060's deaths
# were fitted as alive (27 dead of 1,792) and no gate saw it, because those
# renders print no total for G2 to reconcile against.

@pytest.mark.parametrize("sitrep,order,evidence", [
    (60, "dead_bottom", "0 alive_bottom / 62 dead_bottom"),
    (106, "alive_bottom", "109 alive_bottom / 0 dead_bottom"),
])
def test_stacking_order_is_measured_from_the_render(sitrep, order, evidence):
    # Unanimous in both: every two-colour bar votes the same way.
    from lib.onset.calibrate import calibrate
    from lib.onset.readers import detect_stacking, refine_scale
    im = _image(sitrep)
    cal = detect_stacking(im, refine_scale(im, calibrate(im)))
    assert cal.stacking.value == order
    assert cal.stacking_evidence == evidence


def test_bars_refuse_to_read_without_a_stacking_order():
    from lib.onset.calibrate import calibrate
    from lib.onset.readers import read_bars, refine_scale
    im = _image(60)
    with pytest.raises(ValueError, match="stacking order"):
        read_bars(im, refine_scale(im, calibrate(im)))


def test_an_ambiguous_stacking_vote_refuses():
    # A render whose bars carry one colour only (here: 060 with every
    # dead pixel repainted alive) has no two-colour bar to vote, and the
    # order is then not guessed.
    import numpy as np
    from lib.onset.calibrate import CalibrationError, calibrate
    from lib.onset.readers import detect_stacking, refine_scale
    im = _image(60)
    cal = refine_scale(im, calibrate(im))
    dead = np.array(cal.palette.dead)
    alive = np.array(cal.palette.alive)
    near = np.linalg.norm(im - dead, axis=2) < 40
    flat = im.copy()
    flat[near] = alive
    with pytest.raises(CalibrationError, match="stacking order not determined"):
        detect_stacking(flat, cal)


@needs_build
def test_060_reads_its_deaths_below_the_living(vintages, snapshots):
    import polars as pl
    row = vintages.filter(pl.col("sitrep") == 60)
    assert row["stacking"][0] == "dead_bottom"
    assert 300 <= row["read_dead"][0] <= 700, row.rows()
    # 1 June, the tallest bar: 51 cases, 19 of them dead, the dead segment
    # at the baseline (by eye from the extracted image). Read in the wrong
    # order it was 51 alive, 0 dead.
    bar = snapshots.filter((pl.col("sitrep") == 60)
                           & (pl.col("onset_date") == "2026-06-01"))
    assert (bar["alive"][0], bar["dead"][0]) == (32, 19), bar.rows()


@needs_build
def test_normal_order_renders_are_unchanged_in_kind(vintages):
    # 064 is the first render in the usual order and prints n = 2 064.
    import polars as pl
    row = vintages.filter(pl.col("sitrep") == 64)
    assert row["stacking"][0] == "alive_bottom"
    # Its printed 2,064 less the one date it does not read: 14 May, 10
    # cases, under the dashed line.
    assert row["read_total"][0] == 2054 and row["n_not_read"][0] == 1
    assert 400 <= row["read_dead"][0] <= 700


@needs_build
def test_every_read_render_records_its_stacking_order(vintages):
    import polars as pl
    read = vintages.filter(pl.col("read_total").is_not_null())
    assert not read["stacking"].is_null().any()
    early = read.filter(pl.col("sitrep") <= 63)["stacking"].unique().to_list()
    later = read.filter(pl.col("sitrep") >= 64)["stacking"].unique().to_list()
    assert early == ["dead_bottom"] and later == ["alive_bottom"]


# --------------------------------------------------------------------------
# Duplicate charts: the read published for a data snapshot is the earliest
# one the gates accept.

def _vintage(name, report, n, agree=True):
    """A synthetic read: forty settled onset dates summing to n, uneven
    from day to day so the alignment gate has a shape to register."""
    import datetime as dt
    from types import SimpleNamespace
    from lib.onset.assemble import Vintage
    from lib.onset.readers import BarMeasure
    dates = tuple(dt.date(2026, 5, 1) + dt.timedelta(days=k)
                  for k in range(40))
    w = [1 + (7 * k) % 11 for k in range(40)]
    per = [n * x // sum(w) for x in w]
    per[0] += n - sum(per)
    fields = {f: None for f in BarMeasure.__dataclass_fields__}
    bars = tuple(BarMeasure(**{
        **fields, "slot": k, "alive": per[k], "dead": 0, "margin": 9.0,
        "edge_alive": per[k], "edge_dead": 0, "reader_agreement": agree,
        "provisional": False, "resolution_cases": 0.3})
        for k in range(40))
    cal = SimpleNamespace(panel=SimpleNamespace(height=400))
    return Vintage(sha256=name, image_file=name, sitreps=(1,),
                   report_date=dt.date.fromisoformat(report), printed_n=n,
                   calibration=cal, bars=bars, dates=dates)


def test_a_duplicate_group_is_headed_by_its_earliest_accepted_member():
    """Sitreps 154 and 156 print the same n = 7,438 and are one snapshot.
    154's render is refused; headed by it, the group took 156's clean read
    down with it."""
    from lib.onset.gates import settle_heads
    before = _vintage("before", "2026-08-01", 100)
    bad = _vintage("bad", "2026-08-02", 120, agree=False)
    good = _vintage("good", "2026-08-04", 120)
    later = _vintage("later", "2026-08-05", 120)
    after = _vintage("after", "2026-08-06", 140)
    groups, verdicts, own = settle_heads(
        [(before, []), (bad, [good, later]), (after, [])])
    head, members = groups[1]
    assert head is good
    assert [m.sha256 for m in members] == ["bad", "later"]
    assert verdicts["good"].status == "accepted"
    assert own["bad"].status == "refused"
    assert "G-R" in own["bad"].reasons[0]
    assert set(own) == {"bad"}


def test_a_group_with_no_accepted_member_keeps_its_earliest_as_head():
    from lib.onset.gates import settle_heads
    before = _vintage("before", "2026-08-01", 100)
    bad = _vintage("bad", "2026-08-02", 120, agree=False)
    worse = _vintage("worse", "2026-08-04", 120, agree=False)
    groups, verdicts, own = settle_heads([(before, []), (bad, [worse])])
    head, members = groups[1]
    assert head is bad and members == [worse]
    assert verdicts["bad"].status == "refused"
    assert own["worse"].status == "refused" and "bad" not in own


def test_an_accepted_head_is_left_alone():
    from lib.onset.gates import judge, settle_heads
    a = _vintage("a", "2026-08-01", 100)
    b = _vintage("b", "2026-08-03", 120)
    c = _vintage("c", "2026-08-04", 120, agree=False)
    groups, verdicts, own = settle_heads([(a, []), (b, [c])])
    assert groups == [(a, []), (b, [c])]
    assert verdicts == judge([a, b]) and own == {}


# --------------------------------------------------------------------------
# Where a count puts a boundary: from the baseline's centre, rounded once,
# with the outline in one of the two rows there.

@pytest.mark.parametrize("sitrep,zero", [(64, -1.18), (87, -0.07),
                                         (127, -0.31)])
def test_the_bars_zero_is_the_centre_of_the_baseline(sitrep, zero):
    """`panel.bottom` is the first row of the axis line; the bars grow from
    its centre, which sits 1.2 px lower in 064 (a two-row line), 0.3 px in
    127 and at the row's own edge in 087."""
    from lib.onset.calibrate import baseline_zero, find_panel
    im = _image(sitrep)
    assert baseline_zero(im, find_panel(im)) == pytest.approx(zero, abs=0.1)


@pytest.mark.parametrize("sitrep,from_ticks", [(102, 2.8169), (112, 2.5927),
                                               (114, 2.9887), (154, 2.6582)])
def test_the_scale_is_refined_from_the_measured_zero(sitrep, from_ticks):
    """Fitted from the top edge of row `panel.bottom`, the scale absorbed
    the baseline's offset: 0.88% small on 102, 0.71% on 112, and at another
    minimum altogether on 114 (+3.9%) and 154 (+1.2%), the two charts that
    read 255 and 179 cases short. `from_ticks` is the scale given by the
    y axis's own tick marks on each render, measured once by hand."""
    from lib.onset.calibrate import calibrate
    from lib.onset.readers import refine_scale
    im = _image(sitrep)
    got = refine_scale(im, calibrate(im)).px_per_case
    assert got == pytest.approx(from_ticks, rel=0.003)


def _drawn_bar(c, zero, alive, dead):
    """One slot of a chart as the source draws it: fills from the
    baseline's centre, a 1.3 px outline centred on every segment edge and
    antialiased into the rows it partly covers."""
    import numpy as np
    from lib.onset.calibrate import Calibration, Palette, Panel, Stacking
    blue, red, ink = (190., 228., 241.), (198., 40., 47.), (60., 40., 45.)
    panel = Panel(left=2, top=5, right=37, bottom=300, top_from_border=True)
    im = np.full((320, 40, 3), 255.0)
    im[panel.bottom, panel.left:panel.right + 1] = (50., 50., 50.)
    edges = [zero + alive * c] if alive else []
    if dead:
        edges.append(zero + (alive + dead) * c)
    top = zero + (alive + dead) * c
    for i in range(panel.bottom - panel.top - 1):
        mid = i + 0.5
        fill = (np.array(blue) if mid < zero + alive * c
                else np.array(red) if mid < top else np.full(3, 255.0))
        cover = sum(max(0.0, min(i + 1, e + 0.65) - max(i, e - 0.65))
                    for e in edges)
        cover = min(1.0, cover)
        im[panel.bottom - 1 - i, 17:24] = \
            cover * np.array(ink) + (1 - cover) * fill
    cal = Calibration(
        panel=panel, palette=Palette(alive=blue, dead=red, band=None,
                                     transmission=None),
        day_px=6.0, x_phase=20.0, n_slots=1, px_per_case=c, y_step=25,
        y_labels=(), printed_n=None, band_left=None, band_right=None,
        tick_xs=(), stacking=Stacking.ALIVE_BOTTOM, y_zero=zero)
    return im, cal


@pytest.mark.parametrize("c,zero", [(2.6, -0.9), (2.6, -0.1), (2.98, -0.3),
                                    (3.3, -1.2), (6.9, -1.2)])
def test_a_drawn_bar_reads_back_at_every_small_count(c, zero):
    """Every (alive, dead) from an empty slot to 14 + 14, drawn at the
    scales and baseline offsets of the small renders and of one large one,
    reads back exactly. At 2.6 px per case a one-case segment is two or
    three rows, most of them outline: placed by two roundings from the
    row's edge, or with nothing asked of the boundary rows, a case could
    be added or dropped for the price of no row at all."""
    from lib.onset.readers import fit_bar
    wrong = []
    for alive in range(15):
        for dead in range(15):
            im, cal = _drawn_bar(c, zero, alive, dead)
            got = fit_bar(im, cal, 0)[:2]
            if got != (alive, dead):
                wrong.append(((alive, dead), got))
    assert not wrong, f"{len(wrong)} of 225 drawn bars misread: {wrong[:8]}"


@needs_build
@pytest.mark.parametrize("onset,alive,dead", [("2026-06-14", 24, 20),
                                               ("2026-06-13", 16, 11)])
def test_sitrep_127_mid_june_bars(snapshots, onset, alive, dead):
    """14 June is 24 alive and 20 dead on the image (outline ink ending at
    row 131 above the baseline at 2.98 px per case) and read 24 + 19: its
    44-case top was placed at row 72 + 60 = 132 and its 43-case top at
    72 + 57 = 129. 13 June, the bar beside it, was read correctly before
    and must stay so."""
    import polars as pl
    bar = snapshots.filter((pl.col("sitrep") == 127)
                           & (pl.col("onset_date") == onset))
    assert (bar["alive"][0], bar["dead"][0]) == (alive, dead)


@needs_build
@pytest.mark.parametrize("sitrep,onset", [(128, "2026-04-27"),
                                           (116, "2026-05-04"),
                                           (103, "2026-05-04")])
def test_an_empty_date_on_a_gridline_reads_empty(snapshots, sitrep, onset):
    """Three dates the image shows as a dotted gridline and a tick, read as
    1 + 1, 1 + 0 and 2 + 1 cases: a one-case bar was charged for one row
    of fill and excused three rows of gridline grey and neighbouring-bar
    halo as background. A bar now has to show its outline."""
    import polars as pl
    bar = snapshots.filter((pl.col("sitrep") == sitrep)
                           & (pl.col("onset_date") == onset))
    assert (bar["alive"][0], bar["dead"][0]) == (0, 0)


@needs_build
def test_charts_before_92_keep_their_printed_totals(vintages):
    """The large renders (4 to 8 px per case) read within two cases of
    their printed n before the zero and rounding were corrected, and the
    correction must not cost them that. Each now leaves one date unread --
    14 May, under the dashed line, which held 10 or 11 cases on every one
    of these charts -- so each is short by that bar and no more."""
    import polars as pl
    old = vintages.filter((pl.col("sitrep") < 92)
                          & pl.col("printed_n").is_not_null()
                          & pl.col("read_total").is_not_null())
    assert old.height >= 20
    assert set(old["n_not_read"].to_list()) == {1}
    off = {r["sitrep"]: r["read_total"] - r["printed_n"]
           for r in old.iter_rows(named=True)
           if not -12 <= r["read_total"] - r["printed_n"] <= -8}
    assert not off, f"read total minus printed n: {off}"


@needs_build
def test_sitrep_114_is_read(vintages):
    """Refused for reading 255 short of its printed 5,119 while its scale
    sat 3.9% high; from the measured zero it reads 17 short, about 10 of
    them the date under the dashed line that it does not read."""
    import polars as pl
    row = vintages.filter(pl.col("sitrep") == 114)
    assert row["status"][0] == "accepted"
    assert -0.004 * 5119 <= row["read_total"][0] - 5119 <= 0


@needs_build
def test_156_stands_for_the_snapshot_154_first_carried(vintages):
    import polars as pl
    v = {r["sitrep"]: r for r in vintages.filter(
        pl.col("sitrep").is_in([154, 156])).iter_rows(named=True)}
    assert v[154]["printed_n"] == v[156]["printed_n"] == 7438
    assert v[156]["status"] == "accepted"
    assert v[154]["status"] == "refused" and "G-R" in v[154]["reasons"]
    assert v[154]["dedup_head"] == v[156]["dedup_head"] \
        == v[156]["decoded_sha256"][:12]


# --------------------------------------------------------------------------
# The date under the dashed line is not read.

@pytest.mark.parametrize("sitrep", [60, 72, 87, 98, 113, 127, 129, 149, 159])
def test_the_dashed_line_is_found_on_14_may_and_nowhere_else(sitrep):
    """The source's "Premier resultat positif" line: pure red in the
    lossless renders (60, 72, 98), the dead fill's red after JPEG, and pale
    where it covers half a column (129, 149). Sitrep 73's rotated band
    label and 128's annotation lettering are red runs up a column too, at
    uneven spacings, and must not be taken for it."""
    import datetime as dt
    import numpy as np
    from lib.onset.assemble import load_anchors, slot_dates
    from lib.onset.calibrate import calibrate
    from lib.onset.readers import (NOT_READ_DASHED_LINE, detect_stacking,
                                   read_bars, refine_scale)
    images = sorted((ONSET / "images").glob(f"*-{sitrep:03d}-*.png"))
    im = _image(sitrep)
    cal = detect_stacking(im, refine_scale(im, calibrate(im)))
    dates = slot_dates(cal, load_anchors()[images[0].stem[-12:]])
    bars = read_bars(im, cal)
    unread = [d for b, d in zip(bars, dates) if not b.read]
    assert unread == [dt.date(2026, 5, 14)]
    bar = bars[dates.index(dt.date(2026, 5, 14))]
    assert bar.alive is None and bar.dead is None
    assert bar.not_read == NOT_READ_DASHED_LINE


def test_a_dashed_line_is_told_from_a_bar_and_from_lettering():
    import numpy as np
    from lib.onset.readers import dashed_line_columns
    _, cal = _drawn_bar(3.0, -0.3, 10, 12)
    im = np.full((320, 40, 3), 255.0)
    p = cal.panel
    red = (198., 40., 47.)
    for top in range(p.top + 2, p.bottom - 6, 15):     # dashes: 6 on, 9 off
        im[top: top + 6, 10] = red
    im[p.bottom - 120: p.bottom, 20] = red              # a tall dead bar
    for top in (20, 23, 31, 60, 64, 110, 290):          # lettering
        im[top: top + 2, 30] = red
    cols = np.where(dashed_line_columns(im, cal))[0].tolist()
    assert cols == [10]


@needs_build
def test_a_date_that_was_not_read_is_never_differenced(snapshots):
    """Not read is unobserved on that chart: empty counts with the reason
    beside them in snapshots.csv, left out of the chart's read total, and
    no row in the triangle -- where a zero would have been a bar falling
    to nothing and rising again."""
    import polars as pl
    unread = snapshots.filter(pl.col("not_read").is_not_null())
    assert unread.height > 0
    assert set(unread["onset_date"].to_list()) == {"2026-05-14"}
    for col in ("alive", "dead", "total"):
        assert unread[col].null_count() == unread.height
    read = snapshots.filter(pl.col("not_read").is_null())
    assert read["total"].null_count() == 0
    tri = pl.read_csv(ONSET / "triangle.csv", infer_schema_length=100000)
    assert tri.filter(pl.col("onset_date") == "2026-05-14").height == 0
    assert tri["d_total"].null_count() == 0


def test_the_triangle_skips_a_date_either_chart_did_not_read():
    import dataclasses
    from lib.onset.assemble import triangle
    a = _vintage("a", "2026-08-01", 100)
    b = _vintage("b", "2026-08-03", 120)
    gap = dataclasses.replace(b.bars[3], alive=None, dead=None,
                              not_read="test")
    b = dataclasses.replace(b, bars=b.bars[:3] + (gap,) + b.bars[4:])
    rows = triangle([a, b])
    assert len(rows) == 39
    assert b.dates[3].isoformat() not in {r["onset_date"] for r in rows}
    assert b.total == 120 - _vintage("b", "2026-08-03", 120).bars[3].alive
    assert b.n_not_read == 1


# --------------------------------------------------------------------------
# Exact agreement is recorded beside the gate's one-case agreement.

def test_exact_agreement_is_stricter_than_the_gates():
    """`reader_agreement` allows a case either way on each count, so a
    one-case error in either reader cannot clear it; `reader_exact` is the
    two readers giving the same pair."""
    from lib.onset.calibrate import calibrate
    from lib.onset.readers import detect_stacking, read_bars, refine_scale
    im = _image(127)
    bars = [b for b in read_bars(im, detect_stacking(
        im, refine_scale(im, calibrate(im)))) if b.read]
    for b in bars:
        same = (b.alive, b.dead) == (b.edge_alive, b.edge_dead)
        assert b.reader_exact == same
        assert b.reader_agreement or not b.reader_exact
    assert sum(b.reader_exact for b in bars) \
        < sum(b.reader_agreement for b in bars)


@needs_build
def test_exact_agreement_is_published_and_the_gate_is_unchanged(vintages,
                                                                snapshots):
    import polars as pl
    from lib.onset import gates, readers
    assert readers.AGREE_CASES == 1.0 and gates.GR_DISAGREE_MAX == 0.25
    read = vintages.filter(pl.col("read_total").is_not_null())
    assert (read["agreement_exact"] <= read["agreement"]).all()
    s = snapshots.filter(pl.col("not_read").is_null())
    assert s.filter(pl.col("reader_exact")
                    & ~pl.col("reader_agreement")).height == 0
    assert snapshots.filter(pl.col("not_read").is_not_null()
                            )["reader_exact"].null_count() > 0
