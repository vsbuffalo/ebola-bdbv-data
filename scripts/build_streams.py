"""The weekly observation streams the models fit, from the health-zone panel.

Turns the zone-level cumulative extraction into per-province weekly INCIDENCE
TSVs plus a constants file. Nothing here is specific to any fitting engine
except the output shape -- one file per stream, `time` plus a single named
count column -- which is what a camdl `observations { }` block reads and any
other engine would want too.

HOW A CUMULATIVE PANEL BECOMES WEEKLY INCIDENCE
Each zone's cumulative value is forward-filled onto a daily grid, the zones of
a province are summed, and the summed series is differenced. A province's
series therefore steps whenever any of its zones reports, and a multi-day gap
attributes its cases to the day the report landed -- a small distortion at
province level, where many zones report on any given day. The daily increments
are then binned into 7-day totals anchored at day 0.

CUMULATIVE DECREASES ARE CARRIED FORWARD, NEITHER CLIPPED NOR PUBLISHED AS
NEGATIVE INCIDENCE. A fall in a cumulative column is the source's own downward
revision -- Nord-Kivu's printed cumulative goes 44 cases / 26 deaths on 10 June
to 40 / 24 on 11 June, and sitrep 073 prints Katwa's daily deaths as `-2` under
a note declaring two deaths removed. Differencing turns each into a negative
increment, and a negative increment is not an observation any count likelihood
can evaluate: Poisson and negative binomial are both defined on the
non-negative integers, so a stream carrying one is unusable for the single
thing these files exist for. Clipping it to zero is worse than useless -- it
keeps the cases the source deleted, and it breaks the identity below, because
the emitted total would then exceed the cumulative's movement by exactly the
size of the revision. So the deficit is CARRIED instead: the row emits 0 and
the remainder is subtracted from subsequent rows until it discharges. Every
emitted value is a non-negative integer, every stream's total still equals the
source's own movement exactly, and the correction is not silent -- every row it
touched is written to `revisions.tsv` beside the streams, with the raw
increment, the value emitted, the carry still outstanding and the source's flag
for that report day, so a consumer can see the revision rather than infer it
from a hole. The carry is applied to the rows a consumer actually fits, which
means a week whose net movement is already non-negative is left alone even when
one of its days was a revision: `cases_haut_uele`'s week to 21 July nets +7 and
is untouched, while `cases_daily_haut_uele` shows the -6 of 18 July carried
across the days that follow. The two resolutions therefore attribute a revision
to different rows, and both still total the source's movement. A carry that has
NOT discharged by the end of a series would mean part of a revision was
silently dropped and the emitted total no longer equals that movement; like a
broken identity, it stops the build rather than being rounded away.

THE TRAILING PARTIAL BIN IS KEPT, AND EVERY BIN'S OBSERVATION TIME IS ITS
LAST REPORT DAY. An engine that accumulates between consecutive observation
times scores the window (previous time, this time], so a four-day trailing
bin under a seven-day nominal label reads as a 43% fall in daily rate that
did not happen -- which is exactly what the streams showed before the times
were fixed. With last-report-day times, every window's length equals the
span its count covers, partial bins included. (Dropping the partial bin
instead was measured by the reference pipeline to cost 298 Ituri cases, the
most recent days of the outbreak.)

THE IDENTITY THAT GATES THE OUTPUT
What is emitted must sum to what the source's cumulative moved:
    sum(weekly increments) == last cumulative - cumulative at the window start
per province and stream, exactly. A build in which they differ does not write
partial streams quietly; it stops.

WHY TWO PROVINCES (AND ONE ON PROBATION)
Ituri and Nord-Kivu carry ~96% of confirmed cases and are the streams the
models pin. Haut-Uele has grown to ~140 cases -- no longer the quarter of a
percent it was when the two-province decision was made -- so its streams are
now BUILT as well, and taking them into a likelihood is a modelling decision
recorded there, not here. Tshopo, Sud-Kivu and Bas-Uele remain dropped, and
the count each carried is written into the meta file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

import polars as pl

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate_provinces import carry_province
from lib.tablespec import norm as _norm

#: observed spelling -> canonical zone name, folded on both sides. Two files:
#: the INRB-derived table (fetched, data/raw) and the hand-authored local one
#: (registers/), later entries winning, exactly as the reference pipeline
#: loads them. Aliases are applied HERE, at stream construction, not in the
#: extraction: the panel keeps what each page printed, verbatim.
def load_aliases(*paths: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        d = pl.read_csv(path, comment_prefix="#", infer_schema_length=0)
        for row in d.iter_rows(named=True):
            out[zone_key(row["observed_name"])] = row["canonical_nom"]
    return out

ALIASES: dict[str, str] = {}   # populated in main(), after zone_key exists


def zone_key(name: str) -> str:
    """One forward-fill series per zone, not per spelling.

    Forward-filling keys on the zone name, and a name variant -- `Makiso-
    Kisangani` against `MakisoKisangani`, `ITURI`'s casing, an accent -- would
    otherwise open a SECOND series that carries its last value to the end of
    the window beside the first. The duplication is invisible to the emitted ==
    source-delta identity, because both sides inflate together: Ituri emitted
    4,591 cases against a printed final cumulative of about 4,105, and the
    identity closed. Only the comparison against the printed province totals
    showed it. TRUE aliases (`Kilo Mission` for `Kilo`) are a register concern
    and are not resolved here; folding handles spelling only.
    """
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "", _norm(name))


def canonical_zone(name: str, level: str) -> str:
    """One series per PLACE (or per pool), not per printing.

    Spelling variants fold together; a registered alias -- `Gethy` for `Gety`,
    `Kilo Mission` for `Kilo`, `Nai-Nia` for `Nia-Nia` -- maps to its canonical
    zone; and EVERY unassigned row maps to the single pool `unassigned`,
    because `Autres ZS (donnees non ventilees)`, `Non identifiees`, `Sans
    fiche` and `A ventiler` are one evolving quantity spelled by vintage, and
    forward-filling each spelling as its own series kept all of them alive at
    once -- 94 + 94 + 17 + 17 + 17 + 14 + 6 + 6 phantom Ituri cases at the end
    of the window.
    """
    if level == "unassigned":
        return "unassigned"
    k = zone_key(name)
    return zone_key(ALIASES[k]) if k in ALIASES else k

DAY0 = dt.date(2026, 5, 19)
BIN_DAYS = 7

#: Streams are built for these; the rest are dropped and counted in the meta.
#: Every province the source has ever reported a confirmed case in. All six,
#: and it was three until 2026-09-01.
#:
#: The three added carry 26 cases between them against a national 6,100, and
#: the case for publishing them anyway is that a province's importance to a
#: consumer is not its share of the national total. Bas-Uélé is nineteen days
#: old, has three of its eleven health zones affected, three deaths on four
#: cases, and the reports say it has no treatment centre meeting standards and
#: no partner supporting case management. Tshopo has 19 cases spread across
#: seven of twenty-three zones, which is a wide footprint for a small count and
#: reads as scattered introductions rather than one chain. Neither is visible
#: to anyone reading only the published streams, and a reader who noticed their
#: absence would reasonably conclude the source was not reporting them.
#:
#: Sud-Kivu is included on the same rule though it is quiet -- last confirmed
#: case 2026-05-29 -- because a stream that exists and is flat says something a
#: missing stream does not.
STREAM_PROVINCES = {"Ituri": "ituri", "Nord-Kivu": "nord_kivu",
                    "Haut-Uélé": "haut_uele", "Tshopo": "tshopo",
                    "Sud-Kivu": "sud_kivu", "Bas-Uélé": "bas_uele"}


def daily_cumulative(panel: pl.DataFrame, province: str, col: str) -> pl.DataFrame:
    """The province's summed cumulative, forward-filled onto a daily grid."""
    parts = panel.filter(
        (pl.col("province") == province)
        & pl.col("level").is_in(["zone", "unassigned"])
        & pl.col(col).is_not_null())
    if parts.is_empty():
        return pl.DataFrame({"date": [], "cum": []},
                            schema={"date": pl.Date, "cum": pl.Int64})
    parts = parts.with_columns(pl.col("date").str.to_date())
    lo, hi = parts["date"].min(), parts["date"].max()
    grid = pl.DataFrame({"date": pl.date_range(lo, hi, "1d", eager=True)})
    wide = grid
    parts = parts.with_columns(
        pl.struct(["zone_reported", "level"])
        .map_elements(lambda r: canonical_zone(r["zone_reported"], r["level"]),
                      return_dtype=pl.Utf8).alias("zkey"))
    for key in parts["zkey"].unique().to_list():
        if key == "unassigned":
            continue
        z = (parts.filter(pl.col("zkey") == key)
             .group_by("date").agg(pl.col(col).last())
             .rename({col: f"v_{key}"}))
        wide = wide.join(z, on="date", how="left")

    # THE UNASSIGNED POOL IS NOT A ZONE, AND IT NEEDS TWO DIFFERENT RULES.
    # Within a report it is a SUM: one report can print two pool rows at once
    # (sitrep 015: `ZS non identifiée` 6 beside `Sans fiche` 14), and
    # last-value-wins silently dropped one. Across reports its absence is
    # ZERO, not the previous value: a zone missing from a report is a zone
    # whose count did not change, but a pool row the source stops printing is
    # a pool the source has stopped counting -- Ituri's `Non identifiées = 17`
    # last printed on 21 July forward-filled for 23 days while every printed
    # province total already excluded it, then retired as a -17 revision
    # inside the newest week when the source finally printed `A ventiler = 0`.
    # So on any report day that carries this province's rows, the pool is
    # what the report printed, and nothing when it printed nothing.
    rep_dates = parts.select("date").unique()
    pool = (parts.filter(pl.col("zkey") == "unassigned")
            .group_by("date").agg(pl.col(col).sum().alias("v_unassigned")))
    pool = (rep_dates.join(pool, on="date", how="left")
            .with_columns(pl.col("v_unassigned").fill_null(0)))
    wide = wide.join(pool, on="date", how="left")

    value_cols = [c for c in wide.columns if c.startswith("v_")]
    wide = wide.with_columns([pl.col(c).fill_null(strategy="forward")
                              for c in value_cols])
    return wide.select(
        "date", pl.sum_horizontal([pl.col(c).fill_null(0)
                                   for c in value_cols]).alias("cum"))


def weekly_increments(cum: pl.DataFrame,
                      report_dates: pl.Series | None = None) -> pl.DataFrame:
    """Daily differences of the cumulative, binned into 7-day totals from day 0.

    THE OBSERVATION TIME IS THE BIN'S LAST REPORT DAY, not the bin's nominal
    calendar end. An engine that accumulates between consecutive observation
    times scores the window (previous time, this time], and the bin's counts
    all fall on its report days -- so last-report-day times make every
    window's length equal the span its count actually covers. Labelling with
    the nominal end instead stretched the trailing window: the last bin held
    four days of data under a seven-day label, every stream's newest point
    read 43% low in daily rate, and all six streams showed a fall where five
    had risen. (The same arithmetic understates a late-starting stream's
    FIRST bin, and any interior bin whose last days went unreported.)

    AN EMPTY WEEK IS NOT A ZERO WEEK. The daily grid is forward-filled, so a
    week containing no report at all would difference to a sum of exactly 0 --
    a fabricated observation of no transmission, when the truth is no
    observation. Each bin therefore records how many REPORT days fed it, and a
    bin fed by none is dropped rather than emitted as 0. The widest gap so
    far is five days (5-10 August); the guard exists for the corpus this
    becomes when the source pauses longer.
    """
    d = cum.with_columns(
        (pl.col("cum") - pl.col("cum").shift(1)).alias("inc")).drop_nulls("inc")
    d = d.with_columns(
        (((pl.col("date") - pl.lit(DAY0)).dt.total_days() - 1)
         // BIN_DAYS).alias("bin"))
    if report_dates is not None:
        d = d.with_columns(pl.col("date").is_in(report_dates.to_list())
                           .alias("_isrep"))
    else:
        d = d.with_columns(pl.lit(True).alias("_isrep"))
    out = (d.group_by("bin")
           .agg(pl.col("inc").sum().alias("count"),
                pl.col("date").filter(pl.col("_isrep")).max().alias("time"),
                pl.col("_isrep").sum().alias("n_report_days"))
           .sort("bin"))
    empty = out.filter(pl.col("n_report_days") == 0)
    if empty.height:
        print(f"  NOTE: {empty.height} week(s) contained no report at all "
              "and are omitted rather than emitted as zero")
    return out.filter(pl.col("n_report_days") > 0)


def spans(times, left) -> list[int]:
    """How many days each row's window covers: `(previous time, this time]`,
    with `left` standing in as the boundary before the first row.

    EVERY EMITTED FILE CARRIES THIS, weekly ones included. The row spacing of
    a "weekly" stream is 4 to 8 days (the lab stream's is 2 to 9), because
    observation times are the last REPORT day in each bin and the source does
    not publish on a fixed cadence -- so a consumer inferring the interval
    from the filename, or from the gap to the next row, infers it wrong
    exactly where it matters. Stating it per row makes the accumulation
    window a property of the data rather than of a naming convention.
    """
    out, prev = [], left
    for t in times:
        out.append(int((t - prev).days))
        prev = t
    return out


def calendar_day_grid(times) -> list:
    """Every calendar day the stream spans, so a single-day-figure file has a
    ROW on each and every row's window is exactly one day.

    THE GRID IS CALENDAR DAYS, AND THIS REPLACED A REPORT-DAY GRID. These
    streams carry a figure the report states for one 24-hour period, so the
    value covers one day however wide the silence behind it. An engine that
    accumulates a modelled flow between consecutive rows integrates over the
    whole gap, so a row must exist on every day the value does not cover, or
    the observation is compared against a model quantity that spans days it
    never described. A report-day grid closes that gap only where the source
    published; the days nobody published on stayed absent and kept widening
    the window.

    The earlier rule read "a bin on a day the archive holds no report for
    would be an assertion the source never licensed". That is true of a row
    carrying a ZERO and false of a row carrying NA, which asserts only that
    the day existed and nobody reported this quantity. The same note worried
    that a row would "manufacture a reset point"; manufacturing exactly that
    reset is what a 24-hour figure requires, and not manufacturing it is what
    made the observation mean something the source never said.

    STREAMS BUILT BY DIFFERENCING A CUMULATIVE DO NOT COME HERE, and must not:
    there the value genuinely covers the interval since the previous row, so
    the accumulation window and the value already agree and inserting a row
    would break a correct arm. The invariant this function exists to enforce
    -- a row's value covers exactly the interval since the previous row --
    holds for those streams by construction and for these by gridding.

    Bounded by the stream's own first and last observation. A row before the
    first would claim the quantity was being reported and was empty; a row
    after the last would claim the series is still running.
    """
    lo, hi = min(times), max(times)
    return [lo + dt.timedelta(days=i) for i in range((hi - lo).days + 1)]


def silent_report_days(times, contributed: list[int], report_days, left) -> list[int]:
    """Per row, how many report days in its window said NOTHING of this
    quantity for this place.

    THE COVERAGE STATEMENT FOR A PROSE-DERIVED STREAM. A table prints every
    province every day or does not exist; a paragraph writes out whichever
    provinces its author wrote out, and a stream built from one therefore has
    two different kinds of hole in it -- days on which nobody reported, and
    days on which somebody reported and did not mention this. A file holding
    only the rows that exist cannot tell the two apart, so nine observations
    in three weeks reads the same whether the source published nine times or
    twenty. Stating the silence per row makes the difference legible without
    the reader needing the archive: 0 means the previous observation was the
    previous report day, and anything larger counts the report days in between
    that passed this quantity over.

    The window is the one `spans` uses -- `(previous time, this time]`, with
    `left` standing in before the first row -- so the two columns describe the
    same interval and a consumer can read them together. `contributed` is how
    many report days fed the row: 1 for a daily or stock row, the bin's
    `n_report_days` for a weekly one.

    A negative would mean the row rests on report days the calendar does not
    hold, which is a defect in the calendar rather than a small number, so it
    raises instead of being clamped.
    """
    held = sorted(report_days)
    out, prev = [], left
    for t, n in zip(times, contributed):
        seen = sum(1 for d in held if prev < d <= t)
        if seen < n:
            raise SystemExit(
                f"the report-day calendar holds {seen} day(s) in "
                f"({prev}, {t}] but a stream row rests on {n}: the calendar "
                "is missing report days this build read.")
        out.append(seen - int(n))
        prev = t
    return out


def on_calendar_day_grid(d: pl.DataFrame, report_days, *, time_col: str,
                         divisors=()) -> pl.DataFrame:
    """A single-day-figure stream with a row on every calendar day it spans:
    the days the source stated the quantity carry it, every other day NA.

    WHY A HOLE MUST BE A ROW. These streams hold a figure the report states
    for the report day itself -- one 24-hour count -- so a row is one day of
    flow whatever the gap behind it. An engine that accumulates a modelled
    flow between consecutive OBSERVATION ROWS therefore integrates over the
    whole gap and compares the result against a single day's count: a stream
    whose rows sat 48 days apart asked the model to explain 48 days of
    admissions with one day of them. Writing the gap into `days_covered`
    instead does not help, because the accumulation window is set by the rows
    that exist and not by any column. The row is what resets the accumulator,
    so the hole has to be a row.

    AFTER GRIDDING, `days_covered` IS 1 ON EVERY ROW by construction, and the
    two kinds of hole separate in the columns rather than needing the archive:
    a day nobody published on is `n_report_days` 0 with `n_report_days_silent`
    0, and a day somebody published on without stating this quantity is
    `n_report_days` 0 with `n_report_days_silent` 1.

    WHAT AN NA ROW SAYS AND WHAT IT DOES NOT. The observation cell is empty:
    no likelihood term, and in particular NOT an observed zero -- a report
    that does not mention absconders is silent about them, not reporting none.
    Everything describing the row stays populated (`n_report_days_silent`,
    `checks`, `flags` are the caller's; `days_covered` and `n_report_days` are
    set here), because a row that says why it is empty is strictly better than
    a bare hole and no engine reads those columns into a likelihood.

    `n_report_days` IS THE SCORED MARKER: 1 where a report day fed the row and
    0 where none did. It is already published on every flow file, it is already
    documented as "how many report days fed the row", and 0 is the truthful
    value for a row no report day fed -- so the file states which of its rows
    can be scored without any new column and without a consumer having to
    guess from a null.

    A DIVISOR NEVER GOES EMPTY OR ZERO. Where a second observation column is
    one the model DIVIDES BY -- `tests_*` beneath `positives_*` -- the division
    can be evaluated on a row that contributes no likelihood term, and an empty
    or zero cell there is a division by zero in an expression nobody meant to
    compute. So an inserted row carries the placeholder 1: never read, because
    the numerator beside it is empty and the row is unscored, and positive so
    that it cannot reach a division as a zero. A denominator the model passes
    as a binomial `n` rather than dividing by is NOT filled -- see
    `DENOMINATOR_OF` for why the two roles part company here.

    Pure, and the observation columns are whatever `d` carries besides
    `time_col`: the caller has already reduced its frame to the columns it
    intends to publish, so nothing here needs to know what a stream measures.
    """
    have = d[time_col].to_list()
    grid = calendar_day_grid(have)
    # Every observation lands on the calendar grid by construction, so the
    # check that remains is the one that still bites: an observation on a day
    # the archive holds no report for means the report-day calendar is wrong,
    # and `n_report_days_silent` would go negative downstream rather than say
    # so. Raise here, where the message can name the day.
    if off := sorted(set(have) - set(report_days)):
        raise SystemExit(
            f"a stream has an observation on {off}, which the report-day "
            "calendar does not hold: the calendar is wrong rather than the "
            "stream.")
    out = (pl.DataFrame({time_col: grid}, schema={time_col: pl.Date})
           .join(d.with_columns(pl.lit(1, pl.Int64).alias("n_report_days")),
                 on=time_col, how="left")
           .sort(time_col)
           .with_columns(pl.col("n_report_days").fill_null(0)))
    times = out[time_col].to_list()
    left = times[0] - dt.timedelta(days=1)
    return out.with_columns(
        pl.Series("days_covered", spans(times, left), dtype=pl.Int64),
        pl.Series("n_report_days_silent",
                  silent_report_days(times, out["n_report_days"].to_list(),
                                     report_days, left), dtype=pl.Int64),
        *[pl.col(c).fill_null(1) for c in divisors])


# ---- THE VOCABULARY THE PUBLISHED FILES ARE DOCUMENTED IN ----------------
# `data/build/streams/README.md` travels with the vendored data and answers
# the question `meta.json` cannot: what is `community_deaths_daily_ituri`, and
# what dates does it cover? Everything in it is read back off the files this
# run wrote; the one thing no build can generate -- the sentence saying what a
# quantity MEASURES -- comes from `registers/stream_families.tsv`.

#: `time` aside, these columns describe the ROW rather than observing
#: anything: how wide its window is, how much of that window the source
#: reported on, what the page said about that day, how many provinces fed it,
#: and whether the passage it came from closed its own arithmetic. Every other
#: column in a stream file is an observation.
#:
#: THE COVERAGE COLUMNS ARE `n_provinces`, `n_province_days` AND
#: `n_report_days_silent`, and they exist because a stream that aggregates
#: over a population must say how much of that population it saw. Reading a
#: prose-derived total without them turns a coverage deficit into an apparent
#: reporting deficit -- which is exactly what happened downstream to the
#: laboratory stream, where a fitted "probability of publication" of ~0.77 was
#: measuring how much of the country the paragraph had been written out for.
METADATA_COLUMNS = ("days_covered", "n_report_days", "flags", "n_provinces",
                    "n_province_days", "n_report_days_silent", "checks",
                    "consolidating")

#: HOW A HOLE IS SPELLED ON DISK, in one place because both sides of it have
#: to agree. The engines these files are written for read the literal token
#: `NA` in an observation cell as "scheduled, unobserved": no likelihood term,
#: but the row still closes the interval. An EMPTY cell is not that token, so
#: the writer states it explicitly rather than taking polars' default.
#:
#: The same token is a trap on the reading side, and this repository reads its
#: own output in four places -- the gates, the generated dictionary, the
#: figures and the tests. In polars `NA` does not parse as null by default, so
#: one hole turns an integer column into a STRING column: the non-negativity
#: gate then skips it as non-numeric, and a plotting library draws the strings
#: at the axis baseline, which renders a hole as an observed zero in a figure
#: that looks entirely plausible. Everything here reads through `read_stream`
#: for that reason.
NULL_TOKEN = "NA"


def read_stream(path: Path) -> pl.DataFrame:
    """A published stream file, with holes read as nulls rather than as the
    string `NA`. The only way this repository reads its own output."""
    return pl.read_csv(path, separator="\t", infer_schema_length=None,
                       null_values=NULL_TOKEN)


#: What a model does with a denominator, which decides what an UNSCORED row
#: must carry in it. Two roles, and the difference is the whole reason the
#: distinction is written down rather than assumed:
#:
#:   DIVISOR        the model divides by it. A division can be evaluated on a
#:                  row that is never scored, so the column must hold a
#:                  positive value on every row -- an empty or zero cell is a
#:                  division by zero in a term nobody meant to compute. An
#:                  unscored row therefore carries the placeholder 1.
#:   BINOMIAL_SIZE  the model passes it as the `n` of a binomial or
#:                  beta-binomial. `binomial(n = NA)` cannot be constructed at
#:                  all, so an engine reading it turns the whole row into a
#:                  hole, which is exactly what an unscored row should be. A
#:                  placeholder would be a fabricated trial count for no gain,
#:                  so the column goes empty beside its numerator.
DIVISOR, BINOMIAL_SIZE = "divisor", "binomial size"

#: family -> (the observation column that is a DENOMINATOR, what a model does
#: with it). A denominator is the total that the other observation column
#: beside it is a count OUT OF, rather than a count in its own right.
#:
#: IDENTIFIED STRUCTURALLY, NOT BY NAME. A denominator can only exist where a
#: file publishes more than one observation column, so the candidate set is
#: exactly the files with two, and `no_declared_denominator` below fails the
#: build if one of those has no entry here -- a future two-column stream
#: cannot ship until someone has decided which of its columns is the total and
#: what is done with it.
#:
#: The roles are read off the consuming models rather than guessed.
#: `tests_national` appears as `beta_binomial(n = tests_national, mean =
#: projected / tests_national, ...)`, so it is a divisor as well as a size and
#: takes the stricter rule; the per-province `tests_*` are summed into that
#: same divisor upstream, so the family takes one rule throughout.
#: `deaths_split_*` appears only as `beta_binomial(n = deaths_split_*, mean =
#: projected, ...)`, where `projected` is a ratio of modelled intensities and
#: no data column enters the division -- it is a size and never a divisor.
DENOMINATOR_OF = {"lab": ("tests", DIVISOR),
                  "community_deaths": ("deaths_split", BINOMIAL_SIZE)}


def denominators_in(stem: str, columns, *, role: str | None = None
                    ) -> tuple[str, ...]:
    """A published file's denominator columns, from its stem; `role` narrows
    to the ones a model uses that way."""
    family, slug = stream_identity(stem)
    entry = DENOMINATOR_OF.get(family)
    if entry is None or (role is not None and entry[1] != role):
        return ()
    col = f"{entry[0]}_{slug}"
    return (col,) if col in columns else ()


#: How a row's `time` relates to the count beside it. Passed at every write
#: site rather than inferred from the filename, because it is a property of
#: how the rows were MADE -- differenced into 7-day bins, differenced per
#: report day, or read off the front-page dashboard at an instant.
WEEKLY, DAILY, STOCK = "weekly", "daily", "stock"

RESOLUTION_PROSE = {
    WEEKLY: "weekly, 7-day bins",
    DAILY: "one row per report day",
    STOCK: "a reading at an instant",
}


class Written(NamedTuple):
    """A file this run published, and how its rows relate to time."""
    path: Path
    resolution: str


def stream_places() -> dict[str, str]:
    """Place slug -> the place it names, for the generated documentation.

    Derived from the provinces streams are built for, so adding one adds its
    place here too. `national` is every province the source reports, which is
    NOT the sum of the province streams: three small provinces and the rows
    the source has not attributed are deliberately outside them.
    """
    return {slug: prov for prov, slug in STREAM_PROVINCES.items()} | {
        "national": "DRC, all provinces"}


def stream_identity(stem: str) -> tuple[str, str]:
    """`(family, place slug)` for a published stream, from its file stem.

    The family is what is left once the place and the `daily` marker come off
    -- `community_deaths_daily_ituri` is the community-death family in Ituri,
    `lab_national` the laboratory family nationally, `patients_isolated`
    itself, nationally. Longest slug first, so a family name that happened to
    end in a shorter slug could not be mis-split.

    Documentation is keyed on the family, never on the file: eight files
    publish the case family in two resolutions for four places, and one
    sentence describing all eight cannot drift between them.
    """
    for slug in sorted(stream_places(), key=len, reverse=True):
        if stem.endswith("_" + slug):
            rest = stem[: -(len(slug) + 1)]
            return (rest[:-len("_daily")] if rest.endswith("_daily")
                    else rest), slug
    return stem, "national"


def _with_declared(flags: str, n: int | None) -> str:
    """`flags` with the source's own harmonisation count appended.

    The reports print it twice, both times for deaths: "+24 décès (...) + 7
    harmonisés (Haut-Uélé)" on 2026-07-30 and "+40 décès du jour (...) · +10
    par harmonisation" on 2026-08-02. On the second the arithmetic closes
    exactly against the differenced stream -- 40 notified plus 10 harmonised
    is the 50 the cumulative moved -- which is the clearest evidence in the
    archive that the two readings differ by retrospective attribution and by
    nothing else.
    """
    if n is None:
        return flags
    tag = f"harmonisation_declared={int(n)}"
    return tag if flags in ("-", "", None) else f"{flags};{tag}"


def daily_increments(cum: pl.DataFrame, report_dates: pl.Series) -> pl.DataFrame:
    """One row per REPORT DAY: the cumulative's movement since the previous
    report day, and the length of the interval that movement covers.

    THE INTERVAL IS THE POINT. Report days are irregular -- the source has
    skipped one to four days nine times, once five -- so a daily row is not
    "a day's cases": it is everything the cumulative moved over
    `(previous report day, this report day]`, which `days_covered` states.
    An engine that accumulates between consecutive observation times reads
    that correctly with no rescaling; anything that divides must divide by
    `days_covered` and not by one. Nothing here is spread across the
    interval, because the source does not say how it was distributed.

    Report days with no report are absent, never zero -- the same rule the
    weekly bins follow, and for the same reason.
    """
    d = (cum.filter(pl.col("date").is_in(report_dates.to_list())).sort("date")
         .with_columns((pl.col("cum") - pl.col("cum").shift(1)).alias("count"),
                       (pl.col("date") - pl.col("date").shift(1))
                       .dt.total_days().alias("days_covered"))
         .drop_nulls("count"))
    return d.select("date", "count", "days_covered")


def carry_forward(counts: list[int]) -> tuple[list[int], list[int]]:
    """The same series with the same total, but no negative value in it.

    Walks the series once holding an outstanding DEFICIT. A row whose value
    would be negative emits 0 and opens a deficit of that size; every later row
    pays the deficit down before emitting what is left. Returns the emitted
    values beside the deficit still outstanding AFTER each row, which is what
    makes the correction auditable: the row where a deficit opens and the rows
    where it is paid off are exactly the rows on which `emitted` differs from
    `counts`, and the last element of the second list is the part of a revision
    that never found later cases to take it out of.

    WHY THIS AND NOT CLIPPING. Both remove the negative; only this one leaves
    the total alone. Clipping `[-4, 9]` gives `[0, 9]`, total 9 against a
    cumulative that moved 5, so the stream would permanently carry the four
    cases the source withdrew. Carrying gives `[0, 5]`, total 5. A deficit
    larger than the next row simply keeps going: `[-9, 4, 6]` -> `[0, 0, 1]`.

    Pure, and the only place the rule is written down; every emitted count
    column in this build goes through it, weekly and daily alike.
    """
    emitted: list[int] = []
    outstanding: list[int] = []
    deficit = 0
    for x in counts:
        v = int(x) - deficit
        deficit = -v if v < 0 else 0
        emitted.append(v if v > 0 else 0)
        outstanding.append(deficit)
    return emitted, outstanding


def negative_values(paths: list[Path]) -> list[str]:
    """Every negative number in the files this build published, as findings.

    Fail-closed, and deliberately read back off DISK rather than from the
    frames in memory: what a consumer fits is the file, and a column that never
    passed through `carry_forward` -- a stock reading, a column added later --
    is still covered by this. Nothing here is expected to fire; a hit means a
    count that no likelihood can evaluate reached an output file, which stops
    the build.
    """
    out: list[str] = []
    for path in sorted(paths):
        t = read_stream(path)
        for col in t.columns:
            if not t[col].dtype.is_numeric():
                continue
            for r in t.filter(pl.col(col) < 0).iter_rows(named=True):
                out.append(f"{path.name}: {col} = {r[col]} at {r['time']}")
    return out


def observation_columns(columns) -> list[str]:
    """A published file's observation columns: `time` and the row-describing
    columns removed, everything else is something the source measured."""
    return [c for c in columns if c != "time" and c not in METADATA_COLUMNS]


def accumulation_windows(written: list[Written]) -> list[str]:
    """Every scored row on a flow file whose `days_covered` is not the gap to
    the row before it, as findings.

    THE INVARIANT, AND WHY IT IS A GATE RATHER THAN A CONVENTION:

        for every SCORED row on a flow file
            time - (time of the previous ROW, NA or scored) == days_covered

    The engines these files are written for accumulate a modelled flow from
    the previous ROW OF THE SAME STREAM to this one, and a row that carries no
    observation still resets the accumulator, because the reset is the row
    existing rather than the row being scored. `days_covered` is what the file
    claims that window to be. Where the two differ the model integrates over
    one interval and compares the result against a count covering another, and
    nothing in the file says so: the numerator silently widens while the
    denominator stays where it was. Four published streams had gaps of 11 to
    48 days under a `days_covered` of 1 before this gate existed, and one
    assertion would have named every one of them.

    Read back off DISK, like `negative_values` and for the same reason: what a
    consumer fits is the file. Flow files only -- a stock is a reading at an
    instant, accumulates over no window and carries no `days_covered`, so
    there is nothing here for it to violate. The FIRST row of a file is
    exempt: it has no previous row, so the gap it would be measured against
    does not exist.
    """
    out: list[str] = []
    for w in sorted(written, key=lambda w: w.path):
        if w.resolution == STOCK:
            continue
        t = read_stream(w.path)
        rows = t.iter_rows(named=True)
        prev = next(rows, None)
        if prev is None:
            continue
        for r in rows:
            gap = (dt.date.fromisoformat(r["time"])
                   - dt.date.fromisoformat(prev["time"])).days
            prev = r
            if r["n_report_days"] and gap != r["days_covered"]:
                out.append(
                    f"{w.path.name}: the row at {r['time']} claims "
                    f"days_covered = {r['days_covered']} but sits {gap} day(s) "
                    "after the row before it, so a model accumulating between "
                    f"rows would score {gap} day(s) of flow against it")
    return out


def unscored_rows(written: list[Written]) -> list[str]:
    """Every way an NA row could be malformed, as findings.

    Three properties, all of which a consumer relies on and none of which is
    visible in a column name:

      * a row marked unscored (`n_report_days` 0) really is empty of
        observations, so nothing is half-scored -- a row with a count in one
        cell and a hole in another has semantics no engine here has been
        tested against;
      * a row marked scored has no hole in it, for the same reason;
      * a DIVISOR is present and non-zero on an unscored row, because the
        division can be evaluated on a row that contributes no likelihood
        term.

    A divisor is exempt from the first property, and that is the point of
    naming it: the placeholder is not an observation, it is what keeps an
    unscored row from being arithmetically dangerous.
    """
    out: list[str] = []
    for w in sorted(written, key=lambda w: w.path):
        if w.resolution == STOCK:
            continue
        t = read_stream(w.path)
        obs = observation_columns(t.columns)
        div = denominators_in(w.path.stem, t.columns, role=DIVISOR)
        for r in t.iter_rows(named=True):
            scored = bool(r["n_report_days"])
            for c in obs:
                if scored and r[c] is None:
                    out.append(f"{w.path.name}: {c} is empty at {r['time']} on "
                               "a row marked scored (n_report_days > 0)")
                elif not scored and c not in div and r[c] is not None:
                    out.append(f"{w.path.name}: {c} = {r[c]} at {r['time']} on "
                               "a row marked unscored (n_report_days = 0)")
            for c in div:
                if not scored and not r[c]:
                    out.append(
                        f"{w.path.name}: the divisor {c} is "
                        f"{'empty' if r[c] is None else r[c]} at {r['time']} "
                        "on an unscored row, where it can still be divided by")
    return out


def no_declared_denominator(written: list[Written]) -> list[str]:
    """Files publishing two observation columns whose family has not said
    which of them is the total the other is drawn out of.

    The candidate set for a denominator is exactly the files with more than
    one observation column, so this is the whole of the question `DENOMINATOR_OF`
    answers. Fail-closed so that adding a two-column stream forces the
    decision, rather than leaving a divisor to be discovered by a model
    dividing by a hole.
    """
    out: list[str] = []
    for w in sorted(written, key=lambda w: w.path):
        t = read_stream(w.path)
        obs = observation_columns(t.columns)
        if len(obs) > 1 and not denominators_in(w.path.stem, t.columns):
            out.append(f"{w.path.name}: publishes {obs} and its family "
                       f"`{stream_identity(w.path.stem)[0]}` has no entry in "
                       "DENOMINATOR_OF saying which is the denominator")
    return out


#: Where the sentences live, and how the generated file names it to a reader.
#: Repository-relative on both counts: nothing committed or generated here
#: carries a path that is true on one filesystem only.
FAMILY_REGISTER = "registers/stream_families.tsv"
DICTIONARY = "README.md"


def load_families(path: Path) -> dict[str, dict[str, str]]:
    """The register of what each observation family measures, keyed on family.

    Hand-authored and unregenerable, like every other register: a sentence
    saying what a quantity is has no identity a pipeline could check it
    against, which is exactly why it cannot be derived and must be written
    down once per quantity rather than once per file.
    """
    d = pl.read_csv(path, separator="\t", comment_prefix="#",
                    infer_schema_length=0)
    return {r["family"]: r for r in d.iter_rows(named=True)}


def stream_facts(path: Path) -> dict:
    """What a published file says about itself: how many rows, how many of
    them carry an observation, which `time` values it spans, and which of its
    columns are observations.

    ROWS AND OBSERVATIONS ARE TWO NUMBERS, and conflating them is exactly the
    thing this release exists to stop. A flow file has a row on every report
    day it spans, and the rows the source said nothing on hold `NA`; counting
    those as observations would report a stream printed on nine days out of
    thirty-one as having thirty-one. `n_obs` is the scored count -- what a
    likelihood actually sees -- and `n_rows` is the file's height.

    SPANS AND GAPS ARE MEASURED OVER SCORED TIMES for the same reason. The
    interior gaps of a gridded file are one day by construction; the gap that
    tells a reader how intermittent the quantity is, is the gap between the
    days the source stated it.

    READ OFF THE FILE, not off `meta.json`. The reconciliation block carries a
    date range for the streams built by differencing a cumulative, but not for
    the community-death or laboratory streams, so keying documentation off it
    would leave thirteen of the published files with no stated span. A
    document that states the range of the file it documents, measured from
    that file, is also simply the more honest construction.
    """
    t = read_stream(path)
    scored = (t.filter(pl.col("n_report_days") > 0)
              if "n_report_days" in t.columns else t)
    times = sorted(str(x) for x in scored["time"].to_list())
    return {"n_obs": scored.height,
            "n_rows": t.height,
            "n_holes": t.height - scored.height,
            "first": times[0] if times else "-",
            "last": times[-1] if times else "-",
            "times": times,
            "all_columns": list(t.columns),
            "columns": [c for c in t.columns
                        if c != "time" and c not in METADATA_COLUMNS]}


def _table(rows: list[list[str]], header: list[str],
           align: list[str]) -> list[str]:
    return ["| " + " | ".join(header) + " |",
            "| " + " | ".join(align) + " |"] + \
           ["| " + " | ".join(r) + " |" for r in rows]


def _aside(path: Path, entry: dict[str, str], shape: str) -> list[str]:
    """One of the two files that are NOT observation streams, in its own
    section. Forcing either into the streams table would state a resolution,
    a place and an accumulation window that it does not have."""
    f = stream_facts(path)
    span = (f"{f['n_obs']} rows, {f['first']} to {f['last']}"
            if f["n_obs"] else "no rows yet, header only")
    return [f"## {entry['title']}", "",
            f"`{path.name}` — {entry['measures']}", "",
            shape, "",
            "Columns: " + ", ".join(f"`{c}`" for c in f["all_columns"])
            + f". {span}.", "",
            "**How to read it.** " + entry["interpretation"], ""]


def data_dictionary(written: list[Written], register: Path, *,
                    data_date: str, revisions: Path,
                    uganda: Path | None) -> str:
    """The per-release reference card for the files this run published.

    FAIL-CLOSED, over the files THIS RUN WROTE. The set comes from the write
    log rather than from a glob of the output directory, which can still hold
    a stream from an older vintage of this script that no rule produces any
    more -- documenting one of those would describe the release as containing
    a file it does not ship. A written stream whose family has no sentence
    stops the build and names the file, so a new stream cannot ship
    undocumented; adding one means adding a row to the register, once per
    quantity rather than once per place.
    """
    families = load_families(register)
    orphans = [(w.path.name, stream_identity(w.path.stem)[0]) for w in written
               if stream_identity(w.path.stem)[0] not in families]
    if orphans:
        sys.exit(
            "A PUBLISHED STREAM IS UNDOCUMENTED. This run wrote these files, "
            f"but their observation family has no row in {FAMILY_REGISTER}, "
            f"so {DICTIONARY} cannot say what they measure:\n  "
            + "\n  ".join(f"{name} (family `{fam}`)"
                          for name, fam in sorted(orphans))
            + "\nAdd one row per FAMILY, not per file: the place and the "
              "resolution are filled in from the files themselves.")

    # The two files that are not observation streams are documented from the
    # same register, in their own sections, so their sentences cannot go
    # missing quietly either.
    asides = ["revisions"] + (["uganda_exports"] if uganda is not None else [])
    if absent := [f for f in asides if f not in families]:
        sys.exit(f"{FAMILY_REGISTER} has no row for {absent}, and these files "
                 "are published: every section of the data dictionary is "
                 "written from the register or not at all.")

    # SAYING WHAT A STREAM MEASURES IS NOT SAYING HOW TO READ IT. The second
    # sentence is the one that stops a consumer misusing the file -- which
    # `days_covered` means here, what the coverage column changes, what the
    # quantity is NOT -- so it is required exactly as the first is, and a
    # family whose reading is blank stops the build rather than shipping a
    # stream whose limits nobody wrote down.
    for key in ("measures", "interpretation"):
        blank = sorted(f for f, e in families.items()
                       if not (e.get(key) or "").strip())
        if blank:
            sys.exit(
                f"{FAMILY_REGISTER} has no `{key}` for {blank}. Every family "
                "needs both: `measures` says what the quantity is, "
                "`interpretation` says how to read it and where it misleads. "
                "A stream must not ship with either one missing.")

    # A FAMILY WITHOUT A DECLARED SPAN CANNOT SHIP, for the same reason it
    # cannot ship without a sentence: a consumer accumulating between rows
    # needs to know whether the value covers the interval or one day, and
    # guessing it from the numbers is what the modelling side had to do.
    if undeclared := sorted(set(families) - set(VALUE_SPAN)):
        sys.exit(
            f"{FAMILY_REGISTER} has families with no entry in `VALUE_SPAN`: "
            f"{undeclared}. Declare what one row's value covers -- `interval` "
            "for a family differenced from a cumulative, `report_day` for a "
            "printed 24-hour figure, `stock` for a reading at an instant -- "
            "before publishing it.")

    places = stream_places()
    order = {slug: i for i, slug in enumerate(places)}
    rank = {WEEKLY: 0, DAILY: 1, STOCK: 2}
    by_family: dict[str, list[Written]] = {}
    for w in written:
        by_family.setdefault(stream_identity(w.path.stem)[0], []).append(w)

    out = [
        "# The published observation streams", "",
        f"**Data date {data_date}** — the newest situation report this build "
        "read.",
        "",
        "**Generated** by `scripts/build_streams.py` during `make streams`, "
        f"from `{FAMILY_REGISTER}`. Do not edit it by hand; the next build "
        "overwrites it. Every count and date below is read back off the file "
        "it describes.", "",
        "## Reading any row", "",
        "- **`time` is the observation time, and what it spans depends on the "
        "resolution.** A weekly row is scored over its 7-day bin. A daily row "
        "covers `(previous report day, this report day]` — report days are "
        "irregular, so `days_covered` states the length of that interval, and "
        "nothing is spread across it. A stock row is a reading at that "
        "instant and accumulates over no window at all.",
        "- **A day with no report is absent, never zero.** A gap is a missing "
        "observation, not an observed absence of transmission.",
        "- **EVERY FLOW FILE SATISFIES THIS, AND THE BUILD FAILS IF IT DOES "
        "NOT:**",
        "",
        "  ```",
        "  for every SCORED row:  time - (time of the previous ROW, NA or "
        "scored) == days_covered",
        "  ```",
        "",
        "  An engine accumulates a modelled flow from the previous ROW OF THE "
        "SAME STREAM to this one, and a row carrying no observation still "
        "resets that accumulator, because what resets it is the row being "
        "present and not the row being scored. `days_covered` is what the file "
        "claims the window to be. A scored row whose `days_covered` understates "
        "its gap therefore makes the model accumulate over a window the row "
        "does not claim — it is scored against more flow than it represents, "
        "and nothing in the file says so. Where the source published no report "
        "at all, the gap widens and `days_covered` widens with it: an honest "
        "wide bin rather than a silent one.",
        "- **A HOLE IS A ROW WITH `NA` IN IT, and `n_report_days` says which "
        "rows those are.** On the flow families the source states as a single "
        "24-hour figure per report, every report day the file spans is a row: "
        "the days the source stated the quantity carry it, and the days it did "
        "not carry `NA` in every observation column with `n_report_days` 0. An "
        "`NA` contributes no likelihood term and is **not an observed zero** — "
        "a report that does not mention absconders is silent about them, not "
        "reporting none. Read these files with `NA` declared as the null "
        "token (in polars, `null_values=\"NA\"`): it is not a null token by "
        "default, and one hole otherwise turns an integer column into a string "
        "column that a plotting library will draw at the axis baseline, "
        "rendering a hole as an observed zero. The one column that stays "
        "populated on an unscored row is a **divisor** — `tests_*`, which a "
        "model divides by — where a placeholder of 1 is written, because a "
        "division can be evaluated on a row that is never scored and a null or "
        "zero there would divide by zero.",
        "- **No published count is negative.** Where the source revised its "
        "own cumulative downward, the deficit is carried into later rows "
        "rather than clipped, so a stream still totals exactly what the "
        "source's cumulative moved. `revisions.tsv` below is the row-by-row "
        "record of every row that touched.",
        "- **Observation columns and metadata columns.** The first column is "
        "always `time`. "
        + ", ".join(f"`{c}`" for c in METADATA_COLUMNS)
        + " describe the row rather than the epidemic; every other column is "
        "an observation, and each is named below.",
        "- **A STREAM STATES HOW MUCH OF ITS POPULATION IT SAW, and that is "
        "part of the contract, not a convention.** Any file whose rows "
        "aggregate over something — provinces, report days — publishes the "
        "coverage in a column beside the count, because without it a coverage "
        "deficit is indistinguishable from an under-reporting one and gets "
        "fitted as the second. `n_provinces` is how many provinces a row's "
        "total is the sum over, and `n_province_days` how many "
        "province-report-days; `n_report_days` is how many report days fed "
        "the row — 0 on a hole, which is what marks a row as unscored — and "
        "`n_report_days_silent` how many report days fell in the same window "
        "and said nothing of this quantity for this place. A row read without "
        "them is a total over an unstated denominator. Every stream carries "
        "`n_report_days`; the ones whose window can contain a report day that "
        "passed the quantity over carry `n_report_days_silent` beside it, and "
        "the ones summing over provinces carry `n_provinces` and "
        "`n_province_days`.",
        "- **`checks` is the source's own arithmetic on the passage a value "
        "came from**, on the streams read out of prose: `closes` where every "
        "check bearing on that quantity passed, `contradicts` where one "
        "failed — the report's numbers disagreeing with each other, kept and "
        "flagged rather than dropped — and `unchecked` where the passage "
        "offered nothing to check that quantity against. Unchecked is not "
        "wrong; it is unverified.", "",
    ]

    # A STREAM THAT STOPS EARLY LOOKS EXACTLY LIKE ONE THAT IS UP TO DATE
    # unless the reader compares two dates in a table, which is precisely the
    # comparison a consumer skips. `patients_isolated_confirmed` ends 20 days
    # before the rest of this release because the source stopped printing its
    # tile after sitrep 080; nothing in a per-file row says so. Derived rather
    # than written into the register, because it must stop being true the day
    # the source resumes -- and a hand-kept note would not.
    #
    # SPARSE IS NOT STOPPED, and the difference is measurable rather than a
    # matter of opinion. A stream the source prints intermittently already
    # shows long gaps INSIDE it; a trailing gap no larger than those is the
    # same intermittency continuing, and reporting it as though the series had
    # ended would raise an alarm about the normal behaviour of the quantity.
    # A trailing gap wider than any interior one is the thing worth a second
    # look. Both are listed, and the column says which is which, because the
    # prose-derived care streams made the distinction load-bearing: several of
    # them print on a third of report days by nature.
    behind = []
    for w in written:
        if w.path.name == DICTIONARY:
            continue
        f = stream_facts(w.path)
        last = f["last"]
        if last >= data_date:
            continue
        gap = (dt.date.fromisoformat(data_date)
               - dt.date.fromisoformat(last)).days
        days = [dt.date.fromisoformat(t) for t in f["times"]]
        # None, not 0, where there IS no interior gap: a file with a single
        # observation has nothing to be compared against, and calling its
        # trailing gap "wider than any gap inside the stream" would report the
        # absence of a comparison as a finding.
        inner = [int((b - a).days) for a, b in zip(days, days[1:])]
        behind.append((w.path.name, last, gap, max(inner) if inner else None))
    if behind:
        out += [
            "## Streams with no observation at the data date", "",
            "These stop before the rest of the release, and the last column "
            "says whether that is unusual FOR THIS STREAM. A quantity the "
            "source prints only now and then already has gaps this wide "
            "inside it, and its trailing gap is that same intermittency "
            "continuing — not a series that ended. A trailing gap wider than "
            "any gap inside the stream is the one to look at: it is normally "
            "the SOURCE having stopped publishing the quantity rather than "
            "this pipeline having failed to read it, and the `written_from` "
            "note in `registers/stream_families.tsv` says which, but either "
            "way the tail should not be fitted as though observation "
            "continued.", "",
        ]
        def _days(n: int) -> str:
            return f"{n} day" if n == 1 else f"{n} days"

        out += _table(
            [[f"`{n}`", last, _days(gap),
              "—" if widest is None else _days(widest),
              "cannot say — the file holds one observation"
              if widest is None else
              "no — the stream is this intermittent throughout"
              if gap <= widest else
              "yes — wider than any gap inside the stream"]
             for n, last, gap, widest in sorted(behind)],
            ["File", "Last `time`", "Behind the data date",
             "Widest gap inside the stream", "Unusual for this stream?"],
            ["---", "---", "---:", "---:", "---"])
        out += [""]

    for family, entry in families.items():
        group = by_family.get(family)
        if not group:                    # a vintage this build has no rows for
            continue
        rows = []
        for w in sorted(group, key=lambda w: (rank[w.resolution],
                                              order[stream_identity(
                                                  w.path.stem)[1]])):
            f = stream_facts(w.path)
            rows.append([f"`{w.path.name}`",
                         places[stream_identity(w.path.stem)[1]],
                         RESOLUTION_PROSE[w.resolution],
                         str(f["n_obs"]),
                         str(f["n_holes"]) if f["n_holes"] else "—",
                         f["first"], f["last"],
                         ", ".join(f"`{c}`" for c in f["columns"])])
        out += [f"## {entry['title']}", "", entry["measures"], ""]
        # OBS AND HOLES ARE SEPARATE COLUMNS. `Obs` is what a likelihood sees;
        # `NA rows` is how many report days the file spans on which the source
        # said nothing, present so the accumulation window each observation is
        # scored over is exactly the window its row claims.
        out += _table(rows,
                      ["File", "Place", "Resolution", "Obs", "`NA` rows",
                       "First `time`", "Last `time`", "Observation column(s)"],
                      ["---", "---", "---", "---:", "---:", "---", "---",
                       "---"])
        # HOW TO READ IT, beneath the table that says what is in it. Every
        # trap listed here has already cost someone in this project real time,
        # and none of them is visible in a span and a column name.
        out += ["", "**How to read it.** " + entry["interpretation"], ""]

    out += _aside(
        revisions, families["revisions"],
        "Not an observation stream, and keyed differently: one row per "
        "published row a deficit was open at, keyed `stream, column, time` so "
        "it joins straight onto the stream file it names. `raw` is what "
        "differencing the source gave, `emitted` is what the stream carries, "
        "and `carry_after` is the deficit still outstanding after that row. "
        "An empty file with its header is the normal, healthy state.")
    if uganda is not None:
        out += _aside(
            uganda, families["uganda_exports"],
            "Not an incidence stream, and deliberately unlike the ones beside "
            "it: these are CUMULATIVE counts read at the moments WHO "
            "bulletins pin, so there is no `days_covered` and no "
            "`n_report_days` — the rows accumulate over no window, and a span "
            "column would assert one that does not exist.")

    out += ["The contract these files ship under, and what a consumer must do "
            "when it changes, is in the repository's `README.md` and "
            "`CHANGELOG.md`. `meta.json` beside them carries the build's "
            "global fields — `day0`, `bin_days`, `population`, the dropped "
            "provinces and the reconciliation record.", ""]
    return "\n".join(out)


def daily_flags(dates: pl.Series, caveat: pl.DataFrame | None,
                exceptions: pl.DataFrame | None, province: str) -> pl.Series:
    """What the SOURCE says about each report day, for a consumer that wants
    to down-weight consolidation rather than absorb it in dispersion.

      consolidating      the report carries the "recent fluctuations ...
                         notification delays and progressive consolidation"
                         caveat -- the custodians declining to read their own
                         newest points as epidemiology.
      harmonisation      the early footnote declaring the cumulative still
                         under harmonisation; `_undercount` where the source
                         states outright that it omits community cases and
                         escapees.
      stale_distribution this province's zone rows are a distribution from an
                         earlier date, by the page's own note (sitrep 059) --
                         registered, so the flag follows the register rather
                         than a guess.

    Empty means the page said nothing of the kind. A downward revision is NOT
    flagged here: it is not something the page said about the day, and it is
    already recorded row by row in `revisions.tsv`, which carries this column's
    value for the same day beside it.
    """
    cav: dict[str, list[str]] = {}
    if caveat is not None:
        for r in caveat.iter_rows(named=True):
            k = r["kind"]
            if k in ("none", None):
                continue
            tag = ("consolidating" if k == "recent_data_provisional"
                   else "harmonisation_undercount"
                   if k == "harmonisation_undercount"
                   else "harmonisation" if k == "harmonisation_pending"
                   else k)
            cav.setdefault(r["date"], []).append(tag)
    stale: set[str] = set()
    if exceptions is not None and not exceptions.is_empty():
        for r in exceptions.iter_rows(named=True):
            if r["unit"] == province and "distribution" in (r["note"] or ""):
                stale.add(r["date"])
    out = []
    for d in dates.to_list():
        s = str(d)
        tags = list(dict.fromkeys(cav.get(s, [])))
        if s in stale:
            tags.append("stale_distribution")
        # "-" rather than "": polars writes an empty string as a quoted ""
        # in TSV, which a naive reader takes as a two-character value.
        out.append("|".join(tags) if tags else "-")
    return pl.Series("flags", out, dtype=pl.Utf8)


def ascertainment(panel: pl.DataFrame,
                  province: str) -> tuple[pl.DataFrame, dict]:
    """Weekly community-death count beside the week's total split deaths,
    and the check of both against the printed province rows.

    From the daily ascertainment block, which begins 13 July:
    `deaths_community` are confirmed deaths that occurred in the community
    (post-mortem swab; the person was never isolated) and `deaths_total` is
    the day's confirmed deaths however ascertained. Weeks are the same bins as
    the incidence streams, with the same last-report-day observation times.

    THE INPUT IS THE PRINTED PROVINCE ROW, AND THE ZONE SUM IS THE CHECK --
    the reverse of the cumulative streams, for a reason the cumulative
    streams do not have. A zone-summed daily figure exists only over the rows
    that print BOTH columns, and that row filter is a SELECTION: a day whose
    rows print totals without community figures (sitrep 088's `A ventiler`
    row carries 59 deaths and no split) is not "a missing report" that
    undercounts both columns together -- it is a denominator truncated on a
    criterion correlated with the quantity being estimated. A column shift
    did exactly that on the last four reports (every surviving row had
    community == total by construction) and the emitted final-week fraction
    read 1.000 against a printed 0.55. The printed province row states both
    columns whole; its agreement with the zone rows, where they print a full
    breakdown, is checked at the aggregation step and again here, and the
    dates where the two disagree go into the meta file.
    """
    printed = (panel.filter((pl.col("province") == province)
                            & (pl.col("level") == "province")
                            & pl.col("deaths_community").is_not_null()
                            & pl.col("deaths_total").is_not_null())
               .with_columns(pl.col("date").str.to_date())
               .group_by("date")
               .agg(pl.col("deaths_community").last(),
                    pl.col("deaths_total").last()))
    if printed.is_empty():
        return pl.DataFrame(), {}
    zoned = (panel.filter((pl.col("province") == province)
                          & pl.col("level").is_in(["zone", "unassigned"])
                          & pl.col("deaths_community").is_not_null()
                          & pl.col("deaths_total").is_not_null())
             .with_columns(pl.col("date").str.to_date())
             .group_by("date")
             .agg(pl.col("deaths_community").sum().alias("comm_zones"),
                  pl.col("deaths_total").sum().alias("total_zones")))
    chk = printed.join(zoned, on="date", how="inner").sort("date")
    bad = chk.filter((pl.col("deaths_community") != pl.col("comm_zones"))
                     | (pl.col("deaths_total") != pl.col("total_zones")))
    vs = {"n_compared": chk.height,
          "n_equal": chk.height - bad.height,
          "dates_disagree": [str(x) for x in bad["date"].to_list()]}
    # `n_report_days` is the coverage number that matters for a flow SUM: the
    # row's calendar span says how wide its window is, this says how much of
    # that window the source actually reported on.
    weekly = (printed.with_columns(
                  (((pl.col("date") - pl.lit(DAY0)).dt.total_days() - 1)
                   // BIN_DAYS).alias("bin"))
              .group_by("bin")
              .agg(pl.col("deaths_community").sum(),
                   pl.col("deaths_total").sum(),
                   pl.col("date").max().alias("time"),
                   pl.len().alias("n_report_days"),
                   pl.col("date").min().alias("first_day"))
              .sort("bin"))
    return weekly, vs


#: The provinces whose streams are NOT emitted; their per-bin movement is the
#: named remainder in the national-vs-provinces reconciliation below.
DROPPED_PROVINCES = ("Tshopo", "Sud-Kivu", "Bas-Uélé")


#: The front-page dashboard tile as a LAST-RESORT source for a national
#: cumulative, keyed by the column it can supply.
#:
#: DEATHS ONLY, and the asymmetry is deliberate. The zone and province tables
#: gained their cumulative-death column on sitrep 015 (29 May) but have
#: printed a cumulative-case column since the first held report, so the tile
#: can only ever add dates to the death series -- for cases it would add
#: nothing and could only introduce a disagreement. It is placed last so that
#: wherever a table prints the figure the table's value stands unchanged.
#:
#: THE TILE IS THE SAME QUANTITY AS THE TABLE, established before wiring and
#: re-established on every build (`banner_vs_table` in meta.json): on the 76
#: dates where both print a national cumulative confirmed-death count they
#: agree on 75. The one exception is sitrep 059, whose printed national
#: `Total` row (718) sits one below its own province rows (608+100+1+7+3 =
#: 719) and one below this tile; the register already licenses that report's
#: internal gaps. The reverse case is sitrep 083, where the tile and the
#: `Total` row agree at 1850 and the province rows sum to 1851.
BANNER_NATIONAL = {"cum_deaths": "cumul_deaths"}


def national_printed(panel: pl.DataFrame, summary: pl.DataFrame | None,
                     prose: pl.DataFrame | None, col: str,
                     banner: pl.DataFrame | None = None) -> pl.DataFrame:
    """The printed national cumulative, one value per report date, coalesced
    zone route -> provincial summary -> prose -> front-page tile -- the same
    precedence the national comparison uses. BUILT FROM THE PRINTED ROWS, not
    by summing the emitted province streams: those deliberately exclude three
    small provinces and whatever the source has not attributed, and a national
    series must not inherit that exclusion.
    """
    sources: list[pl.DataFrame | None] = [panel, summary, prose]
    tile = BANNER_NATIONAL.get(col)
    if banner is not None and tile and tile in banner.columns:
        sources.append(banner.select(
            "date", pl.col(tile).alias(col),
            pl.lit("national").alias("level")))
    frames = []
    for prio, d in enumerate(x for x in sources
                             if x is not None and col in x.columns):
        n = (d.filter((pl.col("level") == "national")
                      & pl.col(col).is_not_null())
             .group_by("date").agg(pl.col(col).last().alias("v"))
             .with_columns(pl.lit(prio).alias("prio")))
        frames.append(n)
    allv = pl.concat(frames)
    if allv.is_empty():
        return pl.DataFrame({"date": [], "cum": []},
                            schema={"date": pl.Date, "cum": pl.Int64})
    return (allv.sort("prio").group_by("date").agg(pl.col("v").first())
            .with_columns(pl.col("date").str.to_date())
            .sort("date").rename({"v": "cum"}))


def national_cumulative_grid(printed: pl.DataFrame) -> pl.DataFrame:
    """The printed national values forward-filled onto a daily grid."""
    if printed.is_empty():
        return printed
    lo, hi = printed["date"].min(), printed["date"].max()
    grid = pl.DataFrame({"date": pl.date_range(lo, hi, "1d", eager=True)})
    return (grid.join(printed, on="date", how="left")
            .with_columns(pl.col("cum").fill_null(strategy="forward")))


def orphan_pool_increments(panel: pl.DataFrame, col: str) -> pl.DataFrame:
    """Per-bin movement of rows the source counts nationally but assigns to
    no province -- the early `Echantillons sans fiche` pool, judged `none` in
    the override register. Inside the printed national total, outside every
    province stream; when sitrep 013 folds the pool into Ituri's subtotal its
    exit here (-6) mirrors its entry in the Ituri stream, so the remainder
    accounting stays closed across the hand-off. Absence on a report day is
    zero: the pool exists only while printed.
    """
    dates = (panel.filter(pl.col(col).is_not_null())
             .select(pl.col("date").str.to_date()).unique().sort("date"))
    if dates.is_empty():
        return pl.DataFrame({"bin": [], "count": []},
                            schema={"bin": pl.Int64, "count": pl.Int64})
    pool = (panel.filter((pl.col("level") == "unassigned")
                         & pl.col("province").is_null()
                         & pl.col(col).is_not_null())
            .group_by("date").agg(pl.col(col).sum().alias("v"))
            .with_columns(pl.col("date").str.to_date()))
    d = (dates.join(pool, on="date", how="left")
         .with_columns(pl.col("v").fill_null(0))
         .with_columns((pl.col("v") - pl.col("v").shift(1)).alias("inc"))
         .drop_nulls("inc")
         .with_columns((((pl.col("date") - pl.lit(DAY0)).dt.total_days() - 1)
                        // BIN_DAYS).alias("bin")))
    return d.group_by("bin").agg(pl.col("inc").sum().alias("count")).sort("bin")


# ---- THE CARE LEDGER, PUBLISHED -------------------------------------------
# The situation reports state a daily care ledger IN WORDS, province by
# province, under the care pillar: who was admitted, who left and how, and how
# many people were in the treatment and transit centres at the end of the day.
# `scripts/extract_care_prose.py` reads it; this is where the parts of it that
# stand as observations become streams.
#
# WHY THE CONFIRMED CENSUS IS THE ONE THAT MATTERS. Every other stream here
# observes a THINNED FLOW -- a count of events that reached a page, so a model
# must carry a reporting fraction in front of it and cannot separate that
# fraction from the rate that produced the events. The census is a STATE: the
# number of confirmed people in care at an instant. A compartment model reads
# it directly, `tau*I = dC/dt + delta*C`, with nothing free in front of it, so
# it is the strongest instrument this archive offers for the isolation rate.
# It is also the quantity the front-page tile stopped printing on 2 August;
# the province bullets carry it to the end of the archive.

#: The word the reports' own tables use for the all-provinces column, which is
#: how the whole-response summary sentence is filed. Mapped onto the same
#: place slug the rest of the build uses for a national stream.
CARE_NATIONAL = "Ensemble"

#: family stem -> (the column in care_prose.csv, the checks that bear on it).
#: ONE ROW PER QUANTITY, and the place is substituted mechanically, exactly as
#: the documentation register is keyed. A quantity is here only if it stands
#: on its own as an observation for at least one streamed province; the
#: cumulative care figures, the bed capacity, the contact-tracing proportion
#: and the readmission count are extracted but not published, because they are
#: either not observations of the epidemic or too thin to be one.
CARE_STREAMS = (
    ("care_census", "census",
     ("census_split", "occupancy")),
    ("care_census_confirmed", "census_confirmed",
     ("census_split", "occupancy_confirmed", "confirmed_le_census")),
    ("care_census_suspect", "census_suspect",
     ("census_split", "occupancy_suspect")),
    ("care_admissions", "admissions",
     ("admissions_split",)),
    ("care_exits", "exits",
     ("exits_split", "exits_over_total")),
    ("care_exits_recovered", "exits_recovered",
     ("exits_split", "recovered_le_exits")),
    ("care_exits_noncase", "exits_noncase",
     ("exits_split",)),
    ("care_exits_absconded", "exits_absconded",
     ("exits_split",)),
    ("care_exits_deaths", "exits_deaths",
     ("exits_split", "deaths_conf_le_deaths")),
)

#: Which of the families above are STOCKS -- a reading of how many people were
#: in care at the end of the report day. The rest are FLOWS the report states
#: for that day, which is why they carry `days_covered` of exactly 1: the
#: source prints one 24-hour figure and this build never spreads it.
CARE_STOCK_FAMILIES = frozenset(
    {"care_census", "care_census_confirmed", "care_census_suspect"})


#: WHAT A ROW'S VALUE COVERS, per family, published in `meta.json` so a
#: consumer never has to infer it from the numbers.
#:
#: THE TWO FLOW KINDS LOOK IDENTICAL IN A FILE AND ARE NOT THE SAME STATEMENT.
#: A family built by DIFFERENCING the source's cumulative has a value covering
#: the whole interval since the previous row -- when the source skips two days,
#: the next row's count is three days of cases. A family built from a PRINTED
#: 24-HOUR FIGURE has a value covering one day whatever the silence behind it.
#: An engine that accumulates a modelled flow between consecutive rows is
#: correct on the first without help and wrong on the second unless every day
#: is a row, which is why only the second kind is gridded onto calendar days.
#:
#: The modelling repository asked for this after losing most of a day to the
#: ambiguity; deriving it from the data means comparing gap rows against
#: one-day rows and hoping the epidemic held still, which is not a contract.
VALUE_SPAN = {
    # differenced from the source's own cumulative
    "cases": "interval", "deaths": "interval",
    #: the same, with the source's declared backlogs taken out. Still an
    #: interval family: both substituted rows cover exactly one day in the
    #: differenced stream, so replacing their value does not change what a
    #: row spans.
    "cases_excluding_backlog": "interval",
    "deaths_excluding_backlog": "interval",
    # a printed 24-hour figure, gridded onto calendar days
    "community_deaths": "report_day", "lab": "report_day",
    "cases_notified": "report_day", "deaths_notified": "report_day",

    "care_admissions": "report_day", "care_exits": "report_day",
    "care_exits_recovered": "report_day", "care_exits_noncase": "report_day",
    "care_exits_absconded": "report_day", "care_exits_deaths": "report_day",
    # a reading at an instant: accumulates over no window at all
    "care_census": "stock", "care_census_confirmed": "stock",
    "care_census_suspect": "stock", "patients_isolated": "stock",
    "patients_isolated_confirmed": "stock", "cumul_recovered": "stock",
    "uganda_exports": "stock",
    # not an observation stream
    "revisions": "none",
}


def care_state(checks: str, scope: tuple[str, ...]) -> str:
    """`closes`, `contradicts` or `unchecked` for one care row and quantity.

    The care extraction runs every arithmetic check a passage makes available
    and records the verdict, pass or fail, in a `checks` string. Collapsing
    that to one boolean would put two unlike rows on the same side of it: a
    row whose printed occupancy disagrees with its own census over its own
    beds is THE SOURCE CONTRADICTING ITSELF and its value is suspect, while a
    row that prints a census with nothing beside it to check against is
    unverified rather than wrong. A consumer that wants only rows the source
    proved consistent filters on `closes`; one that wants everything the
    source said keeps all three and weighs them.

    SCOPED TO THE QUANTITY, because a row whose exit decomposition disagrees
    with itself can still carry a census that closes twice over -- so only the
    checks in `scope` count. (`scripts/plot_figures.py` states the same three
    states for the care figure, over a row dict and a precomputed licence
    boolean; the shapes differ enough that one function would take both a row
    and a scope and use one or the other.)
    """
    got = [c.partition("=") for c in (checks or "").split(";") if c]
    rel = [(name, verdict) for name, _, verdict in got if name in scope]
    if not rel:
        return "unchecked"
    return "closes" if all(v == "pass" for _, v in rel) else "contradicts"


def _slug(name: str) -> str:
    """`Haut-Uélé` -> `haut_uele`. Accent-folded, so the geojson's spelling and
    the reports' spelling of a province reach the same key."""
    import unicodedata
    t = unicodedata.normalize("NFKD", name or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def populations(geojson: Path, pop_csv: Path) -> dict[str, int]:
    """Full-province denominators for the response frame: every zone in the
    geography, whether or not the province is affected or published.

    The frame is the source's own, not ours. Sitrep 108: «60 des 151 (39,7%)
    zones de santé *des six provinces* restent affectées depuis le début de
    l'épidémie en RDC» -- six provinces, 151 health zones, and the geojson
    holds exactly those 151. So this is the population the reports' own
    affected-zone fraction is a fraction of.

    Derived from the geojson rather than from `STREAM_PROVINCES`, which is the
    publication list and a different thing entirely. Iterating the publication
    list made a *reference constant* move whenever a publication decision
    changed: three provinces published gave a national denominator of 18.3M
    and six gave 31.9M, for a population that had not changed by one person.
    A consumer summing this to a susceptible pool would have been silently
    re-scaled by an extraction decision. Geography and publication are now
    independent, which is what they always were.

    Integers, and the national total is the sum of the *rounded* provinces, so
    the parts add to the whole exactly. The underlying figures are WorldPop
    raster counts aggregated to health zone (see PROVENANCE.tsv), which come
    out fractional; a population reported to ten decimal places is false
    precision, and one that does not sum to its own total is a trap.
    """
    geo = json.loads(geojson.read_text())
    zone_prov = {f["properties"]["nom"]: f["properties"]["province"]
                 for f in geo["features"]}
    pop = dict(pl.read_csv(pop_csv).iter_rows())

    missing = sorted(set(pop) - set(zone_prov))
    if missing:
        sys.exit(f"{len(missing)} zone(s) carry a population but no geography, "
                 f"so their people belong to no province and would vanish from "
                 f"the denominator: {', '.join(missing[:5])}")

    out: dict[str, float] = {}
    for zone, people in pop.items():
        out[_slug(zone_prov[zone])] = out.get(_slug(zone_prov[zone]), 0.0) + people
    rounded = {k: int(round(v)) for k, v in sorted(out.items())}

    # Every province we publish must have a denominator. The old failure was a
    # spelling drift between the geojson and the reports producing a zero, and
    # a denominator of zero is never a population.
    for prov, slug in STREAM_PROVINCES.items():
        if not rounded.get(slug, 0) > 0:
            sys.exit(f"population for {prov} (slug {slug}) came out "
                     f"{rounded.get(slug, 0)}: the geojson province spellings "
                     f"no longer fold onto STREAM_PROVINCES, and zero is not a "
                     f"population")
    return rounded


def swab_coverage(burial_csv: Path) -> dict:
    """Per-province swab coverage, pooled from the burial pillar's own rows.

    A death that is never swabbed can never become a confirmed case, so this
    bounds what the confirmed-death series can see. A model that declares an
    ascertainment constant is declaring this quantity.

    Published per province and never pooled across them. A case-weighted
    average would use a consumer's own case counts, which belong on the
    consumer's side; the per-province measurement is the part only this
    repository can verify against the page, and a consumer weighting it can
    then test its weighting against what is published here.

    The denominator is *alerts raised*, not bodies the team reached. The
    reports print the inner step once in 102 -- sitrep 099, "60 corps ont été
    prélevés par swab sur 76 pris en charge (78,9 %)" against 93 alerts -- so
    the alert-to-reached loss cannot be measured systematically and is inside
    this figure rather than beside it. The field name says which, because the
    two differ by that step and only the name would distinguish them.
    """
    if not burial_csv.exists():
        return {}
    d = pl.read_csv(burial_csv, infer_schema_length=20000)
    d = d.drop_nulls(["alerts_total", "bodies_swabbed"]).filter(
        pl.col("alerts_total") > 0)
    out: dict[str, dict] = {}
    for prov in sorted(set(d["province"].to_list())):
        q = d.filter(pl.col("province") == prov)
        sw, al = int(q["bodies_swabbed"].sum()), int(q["alerts_total"].sum())
        out[prov] = {
            "value": round(sw / al, 4),
            "bodies_swabbed": sw,
            "alerts_raised": al,
            "province_days": q.height,
            "sitreps": sorted(int(x) for x in q["sitrep"].to_list()),
            "first": q["date"].min(), "last": q["date"].max(),
        }
    return {
        "by_province": out,
        "definition":
            "bodies swabbed / death alerts raised, pooled over the province-"
            "days on which the safe-burial pillar prints both. The denominator "
            "is alerts raised, so this spans the whole path from alert to swab "
            "and includes the alert-to-reached loss; it is not the inner "
            "swabbed-over-reached step, which the reports print once in 102.",
        "not_pooled_across_provinces":
            "deliberate. A case-weighted average would use a consumer's case "
            "counts, which are the consumer's to supply.",
        "caution":
            "not a constant. Sitrep 108 records 9 bodies left unswabbed for "
            "community resistance in Ituri, and the reports began quantifying "
            "refusals only on 30 August, so coverage moves with community "
            "acceptance -- plausibly correlated with transmission itself.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", required=True, type=Path)
    ap.add_argument("--geojson", required=True, type=Path)
    ap.add_argument("--population", required=True, type=Path)
    ap.add_argument("--burial-alerts", type=Path, default=None,
                    help="burial_alerts.csv; its per-province pooled coverage "
                         "goes into meta so a consumer pins it by tag rather "
                         "than copying a number out of prose")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--summary", type=Path, default=None,
                    help="province_summary.csv, so the national series covers "
                         "the reports whose vintage dropped the zone table")
    ap.add_argument("--prose", type=Path, default=None,
                    help="prose_provinces.csv, for the three prose-only reports")
    ap.add_argument("--lab", type=Path, default=None,
                    help="lab_prose.csv: licensed daily testing volume and "
                         "positives, for the national testing stream")
    ap.add_argument("--banner", type=Path, default=None,
                    help="banner.csv: the front-page census of people in "
                         "isolation and the cumulative recoveries")
    ap.add_argument("--care", type=Path, default=None,
                    help="care_prose.csv: the daily care ledger the reports "
                         "state in words, per province -- the isolation "
                         "census with its confirmed half, the admissions and "
                         "the exit decomposition")
    ap.add_argument("--caveat", type=Path, default=None,
                    help="provisional_caveat.csv, so daily rows carry the "
                         "source's own consolidation flags")
    ap.add_argument("--excluded-places", type=Path,
                    default=ROOT / "registers/excluded_places.tsv",
                    help="places the source reports that this build "
                         "deliberately does not publish, each with a reason; "
                         "anything reported and neither published nor listed "
                         "here stops the build")
    ap.add_argument("--batches", type=Path,
                    default=ROOT / "registers/retrospective_batches.tsv",
                    help="the register of days the source says a cumulative's "
                         "movement holds records belonging to earlier days; "
                         "drives the excluding-backlog families")
    ap.add_argument("--notified", type=Path, default=None,
                    help="daily_notified.csv: the count the banner states "
                         "for the report day itself, so the day's own "
                         "notifications can be told from the cumulative's "
                         "movement on the days the two differ")
    ap.add_argument("--exceptions", type=Path,
                    default=ROOT / "registers/reconciliation_exceptions.tsv",
                    help="the exception register, for the stale-distribution "
                         "flag on daily rows")
    ap.add_argument("--families", type=Path, default=ROOT / FAMILY_REGISTER,
                    help="the register of what each observation family "
                         "measures; a stream this run writes whose family is "
                         "not in it stops the build")
    ap.add_argument("--uganda-stream", type=Path, default=None,
                    help="uganda_exports.tsv, so the data dictionary can "
                         "state its span; written by build_uganda_stream.py, "
                         "which the Makefile runs first for that reason")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    ALIASES.update(load_aliases(Path("data/raw/zone_aliases.csv"),
                                Path("registers/zone_aliases_local.csv")))
    panel = carry_province(pl.read_csv(args.panel, infer_schema_length=None))

    # The province total, not its largest single zone. `max` over zone rows
    # reported Tshopo as 9 when the province had 19 -- it was the biggest zone,
    # not the province -- so the one number telling a reader what publication
    # leaves out understated it by half.
    dropped = (panel.filter(pl.col("level").is_in(["zone", "unassigned"])
                            & ~pl.col("province").is_in(list(STREAM_PROVINCES))
                            & pl.col("cum_cases").is_not_null())
               .group_by("province", "date")
               .agg(pl.col("cum_cases").sum().alias("cum_cases"))
               .group_by("province").agg(pl.col("cum_cases").max()))

    # A place the source reports and this build does not publish stops the
    # build. Tshopo, Sud-Kivu and Bas-Uélé were extracted in full and published
    # nowhere for weeks: the series carried them, `STREAM_PROVINCES` did not,
    # and the only trace was a `dropped_provinces` field in `meta.json` that
    # nobody reads and that understated the drop by half. Their absence from
    # the published streams was read, reasonably, as the source not reporting
    # them.
    #
    # So it is a gate rather than a note. A province appearing for the first
    # time is a real event -- Bas-Uélé arrived on 2026-08-13 -- and it deserves
    # a decision, not a default. Publish it by adding it to STREAM_PROVINCES,
    # or record why not in the exclusion register; either way somebody chose.
    excluded = {}
    if args.excluded_places and args.excluded_places.exists():
        reg = pl.read_csv(args.excluded_places, separator="\t",
                          comment_prefix="#", infer_schema_length=None)
        excluded = {r["place"]: r["reason"] for r in reg.iter_rows(named=True)}
    unpublished = sorted(set(dropped["province"].to_list()) - set(excluded))
    if unpublished:
        counts = dict(zip(dropped["province"].to_list(),
                          dropped["cum_cases"].to_list()))
        sys.exit(
            "The source reports a place this build does not publish:\n  "
            + "\n  ".join(f"{q} — {counts.get(q)} confirmed cases"
                           for q in unpublished)
            + "\nEvery place the reports carry confirmed cases for is published,"
              " or is recorded with a reason in "
              f"{args.excluded_places.name if args.excluded_places else 'the exclusion register'}."
              " Add it to STREAM_PROVINCES in this file, or add a row saying"
              " why it stays out. Do not leave it silently extracted and"
              " unpublished: that is how three provinces went missing.")

    summary = (pl.read_csv(args.summary, infer_schema_length=None)
               if args.summary and args.summary.exists() else None)
    prose = (pl.read_csv(args.prose, infer_schema_length=None)
             if args.prose and args.prose.exists() else None)
    banner = (pl.read_csv(args.banner, infer_schema_length=None)
              if args.banner and args.banner.exists() else None)
    care = (pl.read_csv(args.care, infer_schema_length=None)
            if args.care and args.care.exists() else None)
    notified = (pl.read_csv(args.notified, infer_schema_length=None)
                if args.notified and args.notified.exists() else None)
    #: (date, quantity, place slugs) per declared retrospective batch. The
    #: place scope is the SOURCE's scope, not wherever the numbers differ: the
    #: 22 July footnote names Ituri and Nord-Kivu, and Haut-Uélé's readings
    #: differ that day too without the source saying why.
    batches: list[tuple[str, str, set[str]]] = []
    if args.batches and args.batches.exists():
        reg = pl.read_csv(args.batches, separator="\t", comment_prefix="#",
                          infer_schema_length=None)
        known = {"national", *STREAM_PROVINCES.values()}
        for r in reg.iter_rows(named=True):
            places = {p.strip() for p in str(r["places"]).split(",")}
            if unknown := places - known:
                sys.exit(f"{args.batches}: row {r['date']} names places that "
                         f"no stream covers: {sorted(unknown)}")
            batches.append((str(r["date"]), r["quantity"], places))

    # THE REPORT-DAY CALENDAR: every date the archive holds a report for, which
    # is the denominator the coverage columns are counted against. Taken from
    # the front-page reader, which reads every report including the ones whose
    # vintage prints no zone table, and unioned with the panel so it is still
    # right if the banner is not built. Derived, never listed: a hand-kept
    # calendar would drift from the archive the first time a report landed.
    report_days = {dt.date.fromisoformat(d)
                   for d in panel["date"].unique().to_list()}
    if banner is not None:
        report_days |= {dt.date.fromisoformat(d)
                        for d in banner["date"].unique().to_list()}

    # The source's own words about each report day, read here rather than at
    # the daily block below because the carry-forward record wants them too:
    # a revision that lands on a day the page already called provisional is a
    # different thing from one that lands on a day it did not.
    caveat = (pl.read_csv(args.caveat, infer_schema_length=None)
              if args.caveat and args.caveat.exists() else None)
    exceptions = (pl.read_csv(args.exceptions, separator="\t",
                              comment_prefix="#", infer_schema_length=None)
                  if args.exceptions and args.exceptions.exists() else None)

    recon: dict[str, dict] = {}
    #: Not a stream reconciliation but a SOURCE-AGREEMENT check, so it lives
    #: beside `reconciliation` rather than inside it: every entry there is
    #: keyed by a stream and read as one by the data document.
    banner_vs_table: dict[str, dict] = {}
    failures: list[str] = []
    weekly_by_name: dict[str, pl.DataFrame] = {}
    revisions: list[dict] = []
    carry_failures: list[str] = []
    written: list[Written] = []

    def write_stream(d: pl.DataFrame, path: Path, resolution: str) -> None:
        """Write a published stream, and remember that we published it.

        Two read-backs work off this log rather than off the output directory,
        which can still hold a file from an older vintage of this script that
        no rule produces any more: the non-negativity gate, and the generated
        data dictionary. `resolution` is stated here because how a row relates
        to time is a property of how these rows were made, not of the name
        they are written under.
        """
        assert resolution in RESOLUTION_PROSE, resolution
        # THE ONE FLAG A CONSUMER ACTS ON, AS A COLUMN RATHER THAN A SUBSTRING.
        # `flags` is prose the page said about the day and it carries several
        # values; a consumer wanting to drop batch-consolidation days had to
        # string-match it, and a string match is a silent failure waiting for
        # the day the vocabulary grows. `consolidating` is 1 or 0 and needs no
        # parsing. It is derived from `flags` here rather than plumbed through
        # every builder, so it cannot disagree with the prose beside it.
        if "flags" in d.columns:
            d = d.with_columns(
                pl.col("flags").fill_null("")
                .str.contains("consolidating").cast(pl.Int64)
                .alias("consolidating"))
        # `NA` AND NOT AN EMPTY CELL, on every file whether or not it has a
        # hole in it: the token is a property of the format, so a consumer
        # reading the release with `null_values="NA"` reads all of it the same
        # way and a file that gains its first hole does not change format.
        d.write_csv(path, separator="\t", null_value=NULL_TOKEN)
        written.append(Written(path, resolution))

    def carried(d: pl.DataFrame, stream: str, column: str, *,
                count_col: str = "count", time_col: str = "time",
                flags: list[str] | None = None,
                province: str = "national") -> pl.DataFrame:
        """Replace `count_col` with its carried-forward values, recording every
        row the correction touched and any deficit left outstanding at the end.

        `stream` names the FILE and `column` the observation inside it, because
        two files here publish two count columns each (community deaths beside
        total split deaths; positives beside tests) and a record keyed on the
        filename alone could not say which of them was corrected.
        """
        raw = [int(x) for x in d[count_col].to_list()]
        if flags is None:
            flags = daily_flags(d[time_col], caveat, exceptions,
                                province).to_list()
        emitted, outstanding = carry_forward(raw)
        # A ROW GOES IN THE RECORD IF THE DEFICIT WAS OPEN AT IT -- not only if
        # its value changed. A row that would have emitted 0 anyway while a
        # deficit is outstanding is still a row whose future was mortgaged, and
        # leaving it out would print `carry_after` as a column with holes in
        # it, which no longer reads as a running balance.
        for t, r, e, o, f in zip(d[time_col].to_list(), raw, emitted,
                                 outstanding, flags):
            if e != r or o:
                revisions.append({"stream": stream, "column": column,
                                  "time": str(t), "raw": r, "emitted": e,
                                  "carry_after": o, "flags": f})
        if outstanding and outstanding[-1]:
            carry_failures.append(f"{stream}:{column} "
                                  f"({outstanding[-1]} outstanding)")
        return d.with_columns(pl.Series(count_col, emitted, dtype=pl.Int64))

    def carry_note(stream: str, column: str) -> dict:
        """What the carry did to one column, for the meta file: how many rows
        it touched, and what (if anything) it failed to discharge."""
        rows = [r for r in revisions
                if r["stream"] == stream and r["column"] == column]
        return {"n_carried": len(rows),
                "carry_residual": rows[-1]["carry_after"] if rows else 0}

    for prov, slug in STREAM_PROVINCES.items():
        for col, stem in (("cum_cases", "cases"), ("cum_deaths", "deaths")):
            cum = daily_cumulative(panel, prov, col)
            if cum.is_empty():
                continue
            rep = (panel.filter(
                (pl.col("province") == prov)
                & pl.col("level").is_in(["zone", "unassigned"])
                & pl.col(col).is_not_null())
                .select(pl.col("date").str.to_date()).unique()["date"])
            weekly = weekly_increments(cum, rep)
            name = f"{stem}_{slug}"
            # THE RAW BINS, KEPT DELIBERATELY. The per-bin national identity
            # below -- national = provinces + dropped + orphan pool -- is a
            # statement about the source's own arithmetic, so it is checked on
            # what the cumulatives moved. Feeding it carried values instead
            # would make a deficit crossing a bin boundary in one province
            # surface as unattributed movement, which is what that check
            # reports as a defect.
            weekly_by_name[name] = weekly
            pub = carried(weekly, name, name, province=prov)
            emitted = int(pub["count"].sum())
            source_delta = int(cum["cum"][-1] - cum["cum"][0])
            recon[name] = {
                "emitted": emitted, "source_delta": source_delta,
                "difference": emitted - source_delta,
                "first_date": str(cum["date"][0]),
                "last_date": str(cum["date"][-1]),
                "n_obs": weekly.height,
                **carry_note(name, name),
            }
            if emitted != source_delta:
                failures.append(name)

            # THE CHECK THE INTERNAL IDENTITY CANNOT DO. emitted == source
            # delta closes even when the grid itself is inflated, because both
            # sides inflate together -- duplicate zone spellings did exactly
            # that. The printed province rows are the independent statement:
            # at every report date that prints one, the forward-filled grid is
            # compared against it, and the worst and final gaps go into the
            # meta file where a reader will meet them.
            printed = (panel.filter((pl.col("level") == "province")
                                    & (pl.col("province") == prov)
                                    & pl.col(col).is_not_null())
                       .group_by("date").agg(pl.col(col).last())
                       .with_columns(pl.col("date").str.to_date()))
            chk = (cum.join(printed, on="date", how="inner").sort("date")
                   .with_columns((pl.col("cum") - pl.col(col)).alias("gap")))
            if chk.height:
                # STABLE TIE-BREAK, FOR BYTE-DETERMINISM. polars' default
                # sort is unstable under ties, and a stream whose gaps are
                # all zero (cases_haut_uele: a 30-way tie) picked an
                # arbitrary worst_gap_date per run -- the one nondeterminism
                # in an otherwise byte-identical build, and the modelling
                # repo verifies its vendored copy by hash. Earliest date
                # wins among equals.
                worst = chk.sort([pl.col("gap").abs(), pl.col("date")],
                                 descending=[True, False]).row(0)
                recon[name]["vs_printed"] = {
                    "n_compared": chk.height,
                    "n_equal": chk.filter(pl.col("gap") == 0).height,
                    "worst_gap": int(worst[chk.columns.index("gap")]),
                    "worst_gap_date": str(worst[0]),
                    "final_gap": int(chk["gap"][-1]),
                }
            write_stream(
                pub.with_columns(
                    pl.Series("days_covered",
                              spans(pub["time"].to_list(), cum["date"][0])))
                .select(pl.col("time").dt.to_string("%Y-%m-%d"),
                        pl.col("count").alias(name),
                        "days_covered", "n_report_days"),
                args.out_dir / f"{name}.tsv", WEEKLY)

        asc, asc_vs = ascertainment(panel, prov)
        if not asc.is_empty():
            cname, tname = f"community_deaths_{slug}", f"deaths_split_{slug}"
            asc = carried(asc, cname, cname, count_col="deaths_community",
                          province=prov)
            asc = carried(asc, cname, tname, count_col="deaths_total",
                          province=prov)
            write_stream(
                asc.with_columns(
                    pl.Series("days_covered",
                              spans(asc["time"].to_list(),
                                    asc["first_day"][0] - dt.timedelta(days=1))))
                .select(pl.col("time").dt.to_string("%Y-%m-%d"),
                        pl.col("deaths_community").alias(cname),
                        pl.col("deaths_total").alias(tname),
                        "days_covered", "n_report_days"),
                args.out_dir / f"{cname}.tsv", WEEKLY)
            recon[cname] = {
                "n_obs": asc.height,
                "emitted": int(asc["deaths_community"].sum()),
                "emitted_total": int(asc["deaths_total"].sum()),
                "vs_printed_daily": asc_vs,
                **carry_note(cname, cname),
            }
            if asc_vs.get("dates_disagree"):
                print(f"  community_deaths_{slug}: zone-summed daily split "
                      f"deaths disagree with the printed province row on "
                      f"{len(asc_vs['dates_disagree'])} of "
                      f"{asc_vs['n_compared']} dates: "
                      f"{', '.join(asc_vs['dates_disagree'])}",
                      file=sys.stderr)

    # The PDF text layer these streams ultimately came through; recorded so a
    # future byte-reproducibility question can start from the tool version
    # instead of archaeology. pdftotext prints its version to stderr.
    import subprocess
    pv = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True)
    pdftotext_version = (pv.stderr or pv.stdout).splitlines()[0].strip() \
        if (pv.stderr or pv.stdout) else "unknown"

    # ------------------------------------------------------------------
    # NATIONAL STREAMS, from the printed national rows -- never from summing
    # the emitted province streams, which deliberately exclude the three
    # small provinces and the unattributed pool. Same gates: emitted must
    # equal the printed cumulative's movement exactly. And the relationship
    # to the province streams is CHECKED, not assumed: per bin,
    #   national = emitted provinces + dropped provinces + orphan pool
    # is recorded in the meta file with any unattributed residue, which is
    # the signature of an attribution or double-count defect.
    for col, stem in (("cum_cases", "cases"), ("cum_deaths", "deaths")):
        # THE TILE IS NOT ASSUMED TO BE THE TABLE'S QUANTITY; it is checked,
        # every build, on the dates where both print one. See BANNER_NATIONAL.
        tile = BANNER_NATIONAL.get(col)
        if banner is not None and tile and tile in banner.columns:
            tab = national_printed(panel, summary, prose, col)
            cmp = (banner.select(pl.col("date").str.to_date(),
                                 pl.col(tile).alias("tile"))
                   .join(tab, on="date", how="inner")
                   .filter(pl.col("tile").is_not_null()
                           & pl.col("cum").is_not_null()))
            bad = cmp.filter(pl.col("tile") != pl.col("cum")).sort("date")
            banner_vs_table[f"{stem}_national"] = {
                "column": tile,
                "both_print": cmp.height,
                "agree": cmp.height - bad.height,
                "disagree": [{"date": str(r["date"]), "tile": r["tile"],
                              "table": r["cum"]}
                             for r in bad.iter_rows(named=True)],
                "tile_only_dates": int(
                    banner.filter(pl.col(tile).is_not_null()).height
                    - cmp.height),
            }
            print(f"  {stem}_national: the front-page tile and the printed "
                  f"table both print a national cumulative on {cmp.height} "
                  f"date(s) and agree on {cmp.height - bad.height}; the tile "
                  f"fills "
                  f"{banner_vs_table[f'{stem}_national']['tile_only_dates']} "
                  f"date(s) no table prints")
            if bad.height:
                print(f"  {stem}_national: the front-page tile and the "
                      f"printed table disagree on {bad.height} of "
                      f"{cmp.height} shared date(s) -- "
                      + ", ".join(f"{r['date']} tile {r['tile']} vs table "
                                  f"{r['cum']}"
                                  for r in bad.iter_rows(named=True)))

        printed = national_printed(panel, summary, prose, col, banner)
        cum = national_cumulative_grid(printed)
        if cum.is_empty():
            continue
        weekly = weekly_increments(cum, printed["date"])
        name = f"{stem}_national"
        weekly_by_name[name] = weekly          # raw, for the per-bin identity
        pub = carried(weekly, name, name, province="national")
        emitted = int(pub["count"].sum())
        source_delta = int(cum["cum"][-1] - cum["cum"][0])
        recon[name] = {
            "emitted": emitted, "source_delta": source_delta,
            "difference": emitted - source_delta,
            "first_date": str(cum["date"][0]),
            "last_date": str(cum["date"][-1]),
            "n_obs": weekly.height,
            **carry_note(name, name),
        }
        if emitted != source_delta:
            failures.append(name)

        # The per-bin identity against the province streams, on the raw bins
        # of both sides -- see the note where the province bins are stored.
        # A configured province may not have reported yet, and the identity has
        # to survive that. Bas-Uélé was in this list for nineteen days before
        # its first case; a province with no rows writes no weekly stream, and
        # summing over the configured list rather than the written one raised a
        # KeyError that stopped the build. It contributes nothing to the
        # identity either way, so it is skipped rather than special-cased.
        prov_names = [f"{stem}_{s}" for s in STREAM_PROVINCES.values()
                      if f"{stem}_{s}" in weekly_by_name]
        psum = None
        for pn in prov_names:
            w = weekly_by_name[pn].select("bin", pl.col("count").alias(pn))
            psum = w if psum is None else psum.join(w, on="bin", how="full",
                                                   coalesce=True)
        psum = psum.with_columns(
            pl.sum_horizontal([pl.col(c).fill_null(0) for c in prov_names])
            .alias("provinces"))
        dropped_w = None
        for dprov in DROPPED_PROVINCES:
            dcum = daily_cumulative(panel, dprov, col)
            if dcum.is_empty():
                continue
            drep = (panel.filter((pl.col("province") == dprov)
                                 & pl.col("level").is_in(["zone", "unassigned"])
                                 & pl.col(col).is_not_null())
                    .select(pl.col("date").str.to_date()).unique()["date"])
            dw = (weekly_increments(dcum, drep)
                  .select("bin", pl.col("count").alias(dprov)))
            dropped_w = dw if dropped_w is None else dropped_w.join(
                dw, on="bin", how="full", coalesce=True)
        dcols = [c for c in (dropped_w.columns if dropped_w is not None else [])
                 if c != "bin"]
        orphan = orphan_pool_increments(panel, col).rename({"count": "orphan"})

        chk = (weekly.select("bin", "time", pl.col("count").alias("national"))
               .join(psum.select("bin", "provinces"), on="bin", how="left")
               .join(dropped_w.select(["bin"] + dcols) if dropped_w is not None
                     else pl.DataFrame({"bin": []}, schema={"bin": pl.Int64}),
                     on="bin", how="left")
               .join(orphan, on="bin", how="left")
               .with_columns([pl.col(c).fill_null(0)
                              for c in ["provinces", "orphan"] + dcols])
               .with_columns(
                   (pl.col("national") - pl.col("provinces")
                    - pl.sum_horizontal([pl.col(c) for c in dcols] or [pl.lit(0)])
                    - pl.col("orphan")).alias("unattributed"))
               .sort("bin"))
        recon[name]["vs_province_sum"] = [
            {"bin": int(r["bin"]), "time": str(r["time"]),
             "national": int(r["national"]),
             "emitted_provinces": int(r["provinces"]),
             "dropped_provinces": int(sum(r[c] for c in dcols)),
             "orphan_pool": int(r["orphan"]),
             "unattributed": int(r["unattributed"])}
            for r in chk.iter_rows(named=True)]
        bad = chk.filter(pl.col("unattributed") != 0)
        if bad.height:
            print(f"  {name}: {bad.height} bin(s) where national != provinces "
                  f"+ named remainder -- unattributed movement:", file=sys.stderr)
            for r in bad.iter_rows(named=True):
                print(f"    bin {r['bin']} ({r['time']}): "
                      f"unattributed {r['unattributed']:+d}", file=sys.stderr)

        write_stream(
            pub.with_columns(
                pl.Series("days_covered",
                          spans(pub["time"].to_list(), cum["date"][0])))
            .select(pl.col("time").dt.to_string("%Y-%m-%d"),
                    pl.col("count").alias(name),
                    "days_covered", "n_report_days"),
            args.out_dir / f"{name}.tsv", WEEKLY)

    # National ascertainment, from the printed national row's daily split --
    # checked per date against the sum of the printed PROVINCE rows, the
    # national-level identity the aggregation step does not run.
    nat_daily = (panel.filter((pl.col("level") == "national")
                              & pl.col("deaths_community").is_not_null()
                              & pl.col("deaths_total").is_not_null())
                 .with_columns(pl.col("date").str.to_date())
                 .group_by("date")
                 .agg(pl.col("deaths_community").last(),
                      pl.col("deaths_total").last()))
    if not nat_daily.is_empty():
        prov_daily = (panel.filter((pl.col("level") == "province")
                                   & pl.col("deaths_community").is_not_null()
                                   & pl.col("deaths_total").is_not_null())
                      .with_columns(pl.col("date").str.to_date())
                      .group_by("date")
                      .agg(pl.col("deaths_community").sum().alias("comm_p"),
                           pl.col("deaths_total").sum().alias("total_p")))
        chk = nat_daily.join(prov_daily, on="date", how="inner").sort("date")
        bad = chk.filter((pl.col("deaths_community") != pl.col("comm_p"))
                         | (pl.col("deaths_total") != pl.col("total_p")))
        weekly = (nat_daily.with_columns(
                      (((pl.col("date") - pl.lit(DAY0)).dt.total_days() - 1)
                       // BIN_DAYS).alias("bin"))
                  .group_by("bin")
                  .agg(pl.col("deaths_community").sum(),
                       pl.col("deaths_total").sum(),
                       pl.col("date").max().alias("time"),
                       pl.len().alias("n_report_days"),
                       pl.col("date").min().alias("first_day"))
                  .sort("bin"))
        weekly = carried(weekly, "community_deaths_national",
                         "community_deaths_national",
                         count_col="deaths_community")
        weekly = carried(weekly, "community_deaths_national",
                         "deaths_split_national", count_col="deaths_total")
        write_stream(
            weekly.with_columns(
                pl.Series("days_covered",
                          spans(weekly["time"].to_list(),
                                weekly["first_day"][0] - dt.timedelta(days=1))))
            .select(pl.col("time").dt.to_string("%Y-%m-%d"),
                    pl.col("deaths_community").alias("community_deaths_national"),
                    pl.col("deaths_total").alias("deaths_split_national"),
                    "days_covered", "n_report_days"),
            args.out_dir / "community_deaths_national.tsv", WEEKLY)
        recon["community_deaths_national"] = {
            "n_obs": weekly.height,
            "emitted": int(weekly["deaths_community"].sum()),
            "emitted_total": int(weekly["deaths_total"].sum()),
            **carry_note("community_deaths_national",
                         "community_deaths_national"),
            "vs_printed_daily": {
                "n_compared": chk.height,
                "n_equal": chk.height - bad.height,
                "dates_disagree": [str(x) for x in bad["date"].to_list()]},
        }
        if bad.height:
            print(f"  community_deaths_national: the printed national daily "
                  f"split disagrees with the sum of the printed province rows "
                  f"on {bad.height} of {chk.height} dates: "
                  f"{', '.join(str(x) for x in bad['date'].to_list())}",
                  file=sys.stderr)

    # ------------------------------------------------------------------
    # DAILY COMPANIONS. One row per report day, the increment since the
    # previous report day, `days_covered` naming the interval it covers, and
    # the source's own consolidation flags. Same construction as the weekly
    # streams -- same panel, same forward-filled grid, same registers -- so
    # the two resolutions cannot disagree about what a report said; a daily
    # stream's total is gated against the same cumulative movement. The
    # carry-forward runs on THESE rows, which is why a revision can appear
    # here and not in the weekly file: a week whose net is already
    # non-negative needs no correction.
    def emit_daily(name: str, obs: str, cum: pl.DataFrame, reps: pl.Series,
                   province: str) -> None:
        d = daily_increments(cum, reps)
        if d.is_empty():
            return
        d = d.with_columns(daily_flags(d["date"], caveat, exceptions, province))
        d = carried(d, name, obs, time_col="date", flags=d["flags"].to_list())
        emitted = int(d["count"].sum())
        delta = int(cum.filter(pl.col("date").is_in(reps.to_list()))["cum"][-1]
                    - cum.filter(pl.col("date").is_in(reps.to_list()))["cum"][0])
        recon[name] = {
            "n_obs": d.height, "emitted": emitted, "source_delta": delta,
            "difference": emitted - delta,
            "first_date": str(d["date"][0]), "last_date": str(d["date"][-1]),
            "days_covered": {"median": float(d["days_covered"].median()),
                             "max": int(d["days_covered"].max()),
                             "n_gt_1": int(d.filter(pl.col("days_covered") > 1).height)},
            "n_flagged": int(d.filter(pl.col("flags") != "-").height),
            **carry_note(name, obs),
        }
        if emitted != delta:
            failures.append(name)
        # THE COLUMN NAMES THE OBSERVABLE, NOT THE BINNING. `cases_ituri` is
        # `cases_ituri` in the weekly file and in the daily one: the binning
        # is a property of the table (its filename, and the per-row
        # `days_covered`), not of the variable, so a consumer reading both
        # needs one code path and a model can swap resolutions by changing a
        # path. It is also the honest name -- a "daily" row covers 2 or 3
        # days on 5 of 82, and a "weekly" row 4 to 8.
        write_stream(
            d.with_columns(pl.lit(1, pl.Int64).alias("n_report_days"))
            .select(pl.col("date").dt.to_string("%Y-%m-%d").alias("time"),
                    pl.col("count").alias(obs), "days_covered",
                    "n_report_days", "flags"),
            args.out_dir / f"{name}.tsv", DAILY)

    for prov, slug in STREAM_PROVINCES.items():
        for col, stem in (("cum_cases", "cases"), ("cum_deaths", "deaths")):
            cum = daily_cumulative(panel, prov, col)
            if cum.is_empty():
                continue
            reps = (panel.filter((pl.col("province") == prov)
                                 & pl.col("level").is_in(["zone", "unassigned"])
                                 & pl.col(col).is_not_null())
                    .select(pl.col("date").str.to_date()).unique()["date"])
            emit_daily(f"{stem}_daily_{slug}", f"{stem}_{slug}", cum, reps, prov)
    for col, stem in (("cum_cases", "cases"), ("cum_deaths", "deaths")):
        printed = national_printed(panel, summary, prose, col, banner)
        cum = national_cumulative_grid(printed)
        if not cum.is_empty():
            emit_daily(f"{stem}_daily_national", f"{stem}_national", cum,
                       printed["date"], "national")

    # ------------------------------------------------------------------
    # The day's own notification count, published beside the cumulative's
    # movement rather than inside it.
    #
    # Why a separate file and not a column. `cases_daily_national` is
    # differenced from a cumulative, so its value spans the *interval* since
    # the previous row; this figure is the count the banner states for the
    # report day itself, so its value spans *one report day*. They are the same events
    # measured two ways, and on the days they disagree they disagree by a lot
    # -- but a file mixing an `interval` column with a `report_day` column has
    # no single answer to "what does one row cover", which is the one question
    # `VALUE_SPAN` exists to answer. Two families, two files, two spans.
    #
    # The disagreement is the point. On 2026-07-22 the national confirmed
    # cumulative moved 369 while the banner says 97 were notified; the report's
    # footnote attributes the rest to integrating the harmonised Ituri and
    # Nord-Kivu provincial databases. A consumer with only the differenced
    # stream reads 369 as one day's incidence. The reconciliation below names
    # every day the two readings part company, so the disagreement travels in
    # `meta.json` rather than having to be rediscovered.
    def emit_notified(stem: str, place: str, slug: str) -> None:
        """One place's notified stream, and its reconciliation against the
        differenced stream for the same place and quantity."""
        q = (nd.filter((pl.col("quantity") == stem)
                       & (pl.col("place") == place)).sort("date"))
        if q.is_empty():
            return
        name = obs = f"{stem}_notified_{slug}"
        g = on_calendar_day_grid(
            q.select("date", pl.col("notified").alias(obs),
                     "harmonised_declared"),
            report_days, time_col="date")
        # The harmonisation count the source prints beside the day's own is a
        # statement about the row, not a second observation on it, so it
        # travels in `flags` with the report's other self-descriptions. As a
        # column it would be empty on all but two scored rows, which is
        # exactly the shape the empty-cell gate exists to reject: an
        # observation column blank on a row marked scored cannot be told from
        # a hole the source left.
        declared = dict(zip(g["date"].dt.to_string("%Y-%m-%d").to_list(),
                            g["harmonised_declared"].to_list()))
        g = g.with_columns(daily_flags(g["date"], caveat, exceptions, place))
        g = g.with_columns(
            pl.struct("date", "flags").map_elements(
                lambda r: _with_declared(r["flags"], declared.get(str(r["date"]))),
                return_dtype=pl.Utf8).alias("flags"))
        write_stream(
            g.select(pl.col("date").dt.to_string("%Y-%m-%d").alias("time"),
                     obs, "days_covered", "n_report_days",
                     "n_report_days_silent", "flags"),
            args.out_dir / f"{name}.tsv", DAILY)

        # Against the differenced stream for the SAME place. A row covering
        # more than one day is excluded rather than counted as a disagreement:
        # 2026-07-30 follows two days nobody published on, so its movement
        # holds three days of notifications against a banner figure covering
        # the last of them, and calling that a backlog would invent one.
        diff_path = args.out_dir / f"{stem}_daily_{slug}.tsv"
        entry = {
            "kind": "notified",
            "n_obs": int(g["n_report_days"].sum()), "n_rows": g.height,
            "first_date": str(g["date"][0]), "last_date": str(g["date"][-1]),
            "notified_total": int(q["notified"].sum()),
            "n_days_printed": int(q["printed"].sum()),
            "n_days_zero_implied": int((~q["printed"]).sum()),
            "harmonisation_declared_by_source": {
                str(r["date"]): int(r["harmonised_declared"])
                for r in q.filter(pl.col("harmonised_declared").is_not_null())
                .iter_rows(named=True)},
        }
        if diff_path.exists():
            diff = read_stream(diff_path)
            both = (diff.select(pl.col("time"),
                                pl.col(f"{stem}_{slug}").cast(pl.Int64)
                                .alias("moved"),
                                pl.col("days_covered").cast(pl.Int64))
                    .join(g.select(pl.col("date").dt.to_string("%Y-%m-%d")
                                   .alias("time"),
                                   pl.col(obs).alias("stated"),
                                   "harmonised_declared"),
                          on="time", how="inner")
                    .filter(pl.col("moved").is_not_null()
                            & pl.col("stated").is_not_null()))
            one_day = both.filter(pl.col("days_covered") == 1)
            apart = one_day.filter(pl.col("moved") != pl.col("stated"))
            entry["vs_cumulative"] = {
                "n_days_compared": one_day.height,
                "n_days_agreeing": one_day.height - apart.height,
                "n_days_excluded_multi_day": both.height - one_day.height,
                "days_apart": [
                    {"date": r["time"], "cumulative_moved": r["moved"],
                     "source_says_notified": r["stated"],
                     "difference": r["moved"] - r["stated"],
                     "source_declared_harmonisation": r["harmonised_declared"]}
                    for r in apart.sort("time").iter_rows(named=True)]}
        recon[name] = entry

    def emit_excluding_backlog(stem: str, slug: str) -> None:
        """The differenced daily series with the source's declared backlogs
        taken out, published as its own family.

        Every row is the differenced value, except on the days
        `registers/retrospective_batches.tsv` names -- where the report says
        in words that the cumulative's movement holds records belonging to
        earlier days -- which carry the report's own same-day count instead.
        Those records are then scored nowhere: the source never says which
        earlier days they belong to, so excluding them is the only treatment
        that does not invent a date.

        Left alone on purpose: every other day the two readings disagree.
        Those are the source moving records between zones or provinces, where
        the differenced value is the right count for the place, and a rule
        keyed on the size of the difference would have swept them up too.
        """
        base_path = args.out_dir / f"{stem}_daily_{slug}.tsv"
        note_path = args.out_dir / f"{stem}_notified_{slug}.tsv"
        if not base_path.exists():
            return
        base = read_stream(base_path)
        # A place with no notified stream still gets this family, identical to
        # the differenced one. The banner printed its 24-hour breakdown only for
        # sitreps 059-083 and only for the provinces affected then, so Bas-Uélé
        # and Sud-Kivu have none -- and requiring one silently skipped writing
        # their file, which broke a figure that reasonably expected the family
        # to cover every place. A consumer binding `cases_excluding_backlog_*`
        # across provinces should not find some of them absent; where no batch
        # is registered the series is the differenced one, which is exactly
        # what it means.
        if note_path.exists():
            note = read_stream(note_path)
        else:
            note = base.select("time").with_columns(
                pl.lit(None, pl.Int64).alias(f"{stem}_notified_{slug}"))
        obs, name = f"{stem}_{slug}", f"{stem}_excluding_backlog_{slug}"
        j = base.join(
            note.select("time", pl.col(f"{stem}_notified_{slug}")
                        .cast(pl.Int64).alias("stated")),
            on="time", how="left")
        dates = {d for d, q, places in batches
                 if q in (stem, "both") and slug in places}
        use = (pl.col("time").is_in(sorted(dates))
               & pl.col("stated").is_not_null()
               & (pl.col("days_covered").cast(pl.Int64) == 1))
        changed = j.filter(use & (pl.col(obs).cast(pl.Int64) != pl.col("stated")))
        out = j.with_columns(
            pl.when(use).then(pl.col("stated"))
            .otherwise(pl.col(obs).cast(pl.Int64)).alias(obs))
        write_stream(out.select("time", obs, "days_covered", "n_report_days",
                                "flags"),
                     args.out_dir / f"{name}.tsv", DAILY)
        recon[name] = {
            "kind": "excluding_backlog",
            "n_obs": out.height,
            "emitted": int(out[obs].sum()),
            "differenced_total": int(base[obs].cast(pl.Int64).sum()),
            "rows_substituted": [
                {"date": r["time"], "differenced": r[obs],
                 "source_says_notified": r["stated"],
                 "records_excluded": r[obs] - r["stated"]}
                for r in changed.sort("time").iter_rows(named=True)],
        }

    if notified is not None and not notified.is_empty():
        nd = notified.with_columns(pl.col("date").str.to_date())
        # National first, then each province the tile breaks its total into.
        # The province rows exist on every day the breakdown closes (22 of
        # 23); the one day licensed by the prose sentence alone carries a
        # national figure and no split, because apportioning it would
        # manufacture a division the source never made.
        for stem in ("cases", "deaths"):
            emit_notified(stem, "national", "national")
            for prov, slug in STREAM_PROVINCES.items():
                emit_notified(stem, prov, slug)
        for stem in ("cases", "deaths"):
            for slug in ("national", *STREAM_PROVINCES.values()):
                emit_excluding_backlog(stem, slug)

    # The daily ascertainment split: these columns are ALREADY the day's own
    # 24-hour flows as the source prints them, so a row covers ONE day and
    # `days_covered` says 1. The report days on which no page classified a
    # death this way are rows with both cells empty, so the interval a row
    # claims is the interval a model accumulates over.
    #
    # BOTH COLUMNS GO EMPTY TOGETHER on such a row. `deaths_split_*` is the
    # total the community count is drawn out of, and a model passes it as a
    # binomial size; a count in one cell and a hole in the other is a shape
    # nothing here has been tested against, and a fabricated trial count would
    # be worse than a hole.
    for prov, slug in list(STREAM_PROVINCES.items()) + [(None, "national")]:
        lvl = "national" if prov is None else "province"
        sel = panel.filter((pl.col("level") == lvl)
                           & pl.col("deaths_community").is_not_null()
                           & pl.col("deaths_total").is_not_null())
        if prov is not None:
            sel = sel.filter(pl.col("province") == prov)
        if sel.is_empty():
            continue
        d = (sel.with_columns(pl.col("date").str.to_date())
             .group_by("date")
             .agg(pl.col("deaths_community").last(), pl.col("deaths_total").last())
             .sort("date"))
        name = f"community_deaths_daily_{slug}"
        cname, tname = f"community_deaths_{slug}", f"deaths_split_{slug}"
        n_stated = d.height
        fl = daily_flags(d["date"], caveat, exceptions,
                         prov or "national").to_list()
        d = carried(d, name, cname, count_col="deaths_community",
                    time_col="date", flags=fl)
        d = carried(d, name, tname, count_col="deaths_total",
                    time_col="date", flags=fl)
        d = on_calendar_day_grid(
            d.select("date", pl.col("deaths_community").alias(cname),
                     pl.col("deaths_total").alias(tname)),
            report_days, time_col="date")
        d = d.with_columns(daily_flags(d["date"], caveat, exceptions,
                                       prov or "national"))
        write_stream(
            d.select(pl.col("date").dt.to_string("%Y-%m-%d").alias("time"),
                     cname, tname, "days_covered", "n_report_days",
                     "n_report_days_silent", "flags"),
            args.out_dir / f"{name}.tsv", DAILY)
        recon[name] = {"n_obs": n_stated, "n_rows": d.height,
                       "emitted": int(d[cname].sum()),
                       "emitted_total": int(d[tname].sum()),
                       "report_days_silent":
                           int(d["n_report_days_silent"].sum()),
                       "n_flagged": int(d.filter((pl.col("flags") != "-")
                                                 & (pl.col("n_report_days") > 0))
                                        .height),
                       **carry_note(name, cname)}

    # THE TESTING STREAM, from the laboratory prose (extract_lab_prose.py:
    # every row is licensed by the sentence's own printed positivity). This
    # is the scale anchor the national model class asked for: with no stream
    # observing absolute testing effort, ascertainment and outbreak size are
    # prior-driven. Weekly sums of the day's samples analysed and positives
    # across the provinces whose sentences licensed -- coverage is therefore
    # PARTIAL BY CONSTRUCTION (a wording the licence refuses drops out,
    # counted), and the per-bin province-day count in the meta file is the
    # completeness statement a model should weigh.
    if args.lab and args.lab.exists():
        lab = pl.read_csv(args.lab, infer_schema_length=None)
        if not lab.is_empty():
            daily = (lab.with_columns(pl.col("date").str.to_date())
                     .group_by("date")
                     .agg(pl.col("samples").sum(), pl.col("positives").sum(),
                          pl.len().alias("n_prov"),
                          pl.col("province").alias("provs")))
            weekly = (daily.with_columns(
                          (((pl.col("date") - pl.lit(DAY0)).dt.total_days() - 1)
                           // BIN_DAYS).alias("bin"))
                      .group_by("bin")
                      .agg(pl.col("samples").sum(), pl.col("positives").sum(),
                           pl.col("date").max().alias("time"),
                           pl.len().alias("n_report_days"),
                           pl.col("n_prov").sum().alias("n_province_days"),
                           pl.col("provs").flatten().n_unique()
                           .alias("n_provinces"))
                      .sort("bin"))
            weekly = carried(weekly, "lab_national", "positives_national",
                             count_col="positives")
            weekly = carried(weekly, "lab_national", "tests_national",
                             count_col="samples")
            # THE WEEKLY FILE WAS THE ONE WITHOUT A COVERAGE COLUMN, and it is
            # the one a consumer reaches for first. Its total is a sum over
            # however many report days AND however many provinces licensed a
            # sentence that week, and both vary; the daily companion has said
            # so since it was written, and the bin totals were only ever
            # recoverable from `meta.json`. `n_provinces` is how many distinct
            # provinces appear in the bin at all and `n_province_days` how
            # many province-days were summed, so `n_province_days /
            # n_report_days` is the mean breadth the bin's total rests on --
            # the number that decides whether a shortfall against the case
            # series is reporting or composition.
            lab_first = daily["date"].min() - dt.timedelta(days=1)
            write_stream(
                weekly.with_columns(
                    pl.Series("days_covered",
                              spans(weekly["time"].to_list(), lab_first)),
                    pl.Series("n_report_days_silent",
                              silent_report_days(
                                  weekly["time"].to_list(),
                                  weekly["n_report_days"].to_list(),
                                  report_days, lab_first)))
                .select(pl.col("time").dt.to_string("%Y-%m-%d"),
                        pl.col("positives").alias("positives_national"),
                        pl.col("samples").alias("tests_national"),
                        "days_covered", "n_report_days",
                        "n_report_days_silent", "n_provinces",
                        "n_province_days"),
                args.out_dir / "lab_national.tsv", WEEKLY)
            # THE DAILY FORM IS THE COVERAGE-HONEST ONE, and this stream needs
            # it most: a weekly total is the sum over however many report-days
            # and however many PROVINCES licensed a sentence that week, and
            # both vary -- the last weekly bins rest on one report-day each.
            # `n_provinces` is therefore emitted beside the counts: a day's
            # national total is the sum over exactly those provinces, and a
            # consumer that ignores it will read a composition change as a
            # change in testing effort.
            #
            # AND IT IS GRIDDED ONTO THE REPORT DAYS, because the paragraph
            # gives ONE DAY'S samples per report: a row is one day of testing
            # however long ago the paragraph last named a province, so the
            # report days it named none are rows with an empty
            # `positives_national`. `tests_national` is the one column that
            # does NOT go empty -- a model divides the modelled flow by it, and
            # that division is evaluated whether or not the row is scored.
            dl = daily.sort("date")
            n_stated = dl.height
            fl = daily_flags(dl["date"], caveat, exceptions,
                             "national").to_list()
            dl = carried(dl, "lab_daily_national", "positives_national",
                         count_col="positives", time_col="date", flags=fl)
            dl = carried(dl, "lab_daily_national", "tests_national",
                         count_col="samples", time_col="date", flags=fl)
            stated_prov = dl["n_prov"]
            dl = on_calendar_day_grid(
                dl.select("date", pl.col("positives").alias("positives_national"),
                          pl.col("samples").alias("tests_national"),
                          pl.col("n_prov").alias("n_provinces")),
                report_days, time_col="date", divisors=("tests_national",))
            dl = dl.with_columns(
                # Zero provinces fed a row no laboratory paragraph named one
                # on, which is what the column is for; a hole here would read
                # as coverage unknown rather than coverage none.
                pl.col("n_provinces").fill_null(0),
                daily_flags(dl["date"], caveat, exceptions, "national"))
            write_stream(
                dl.select(pl.col("date").dt.to_string("%Y-%m-%d").alias("time"),
                          "positives_national", "tests_national",
                          "days_covered", "n_report_days",
                          "n_report_days_silent", "n_provinces", "flags"),
                args.out_dir / "lab_daily_national.tsv", DAILY)
            recon["lab_daily_national"] = {
                "n_obs": n_stated, "n_rows": dl.height,
                "tests": int(dl.filter(pl.col("n_report_days") > 0)
                             ["tests_national"].sum()),
                "positives": int(dl["positives_national"].sum()),
                "n_provinces": {"median": float(stated_prov.median()),
                                "min": int(stated_prov.min()),
                                "max": int(stated_prov.max())},
                "report_days_silent":
                    int(dl["n_report_days_silent"].sum()),
                **carry_note("lab_daily_national", "positives_national"),
            }
            # PER-PROVINCE DAILY LABORATORY STREAMS, so a consumer never has
            # to model coverage at all. The national stream's coverage varies
            # (n_provinces runs 1 to 4) because the laboratory paragraph does
            # not always write out every province, and a model that fits the
            # national total against a national latent must either condition
            # on `n_provinces` or absorb the deficit into a free reporting
            # probability. The second is what happened downstream: the
            # national ratio of laboratory positives to new confirmed cases
            # is 0.404 on one-province days, 0.756 on two, and 0.997 on
            # three -- so a fitted "laboratory reporting probability" of
            # ~0.77 was measuring how much of the country the paragraph
            # described, not any property of the reporting pipeline.
            # Matched province against province, that parameter has nothing
            # left to explain.
            labp = lab.with_columns(pl.col("date").str.to_date())
            for prov, slug in STREAM_PROVINCES.items():
                d = (labp.filter(pl.col("province") == prov)
                     .group_by("date")
                     .agg(pl.col("samples").sum(), pl.col("positives").sum())
                     .sort("date"))
                if d.is_empty():
                    continue
                name = f"lab_daily_{slug}"
                # SINGLE-PROVINCE BY CONSTRUCTION, so `n_provinces` would say
                # 1 on every row and state nothing. The coverage question that
                # remains is the other one: the laboratory paragraph does not
                # write this province out every report day, and the report days
                # it skipped are rows with an empty `positives_{slug}` --
                # Haut-Uele's nine observations sat up to 20 days apart with
                # each row holding one day of testing, so a model accumulating
                # between rows compared 20 days of modelled specimens against
                # one day of real ones.
                n_stated = d.height
                d = on_calendar_day_grid(
                    d.select("date",
                             pl.col("positives").alias(f"positives_{slug}"),
                             pl.col("samples").alias(f"tests_{slug}")),
                    report_days, time_col="date",
                    divisors=(f"tests_{slug}",))
                d = d.with_columns(daily_flags(d["date"], caveat, exceptions,
                                               prov))
                write_stream(
                    d.select(pl.col("date").dt.to_string("%Y-%m-%d")
                             .alias("time"),
                             f"positives_{slug}", f"tests_{slug}",
                             "days_covered", "n_report_days",
                             "n_report_days_silent", "flags"),
                    args.out_dir / f"{name}.tsv", DAILY)
                recon[name] = {
                    "n_obs": n_stated, "n_rows": d.height,
                    "tests": int(d.filter(pl.col("n_report_days") > 0)
                                 [f"tests_{slug}"].sum()),
                    "positives": int(d[f"positives_{slug}"].sum()),
                    "report_days_silent":
                        int(d["n_report_days_silent"].sum()),
                }
            # Cross-check: a day's positives should be the day's newly
            # confirmed cases, province by province. Equality on most dates is
            # what licenses reading this stream as testing effort; the
            # disagreeing dates are results-vs-notification timing, recorded.
            newc = (panel.filter((pl.col("level") == "province")
                                 & pl.col("new_cases").is_not_null())
                    .with_columns(pl.col("date").str.to_date())
                    .group_by("date", "province")
                    .agg(pl.col("new_cases").last()))
            j = (lab.with_columns(pl.col("date").str.to_date())
                 .join(newc, on=["date", "province"], how="inner"))
            bad = j.filter(pl.col("positives") != pl.col("new_cases"))
            recon["lab_national"] = {
                "n_obs": weekly.height,
                "tests": int(weekly["samples"].sum()),
                "positives": int(weekly["positives"].sum()),
                "province_days": int(lab.height),
                "report_days": int(daily.height),
                "per_bin": [{"bin": int(r["bin"]), "time": str(r["time"]),
                             "n_report_days": int(r["n_report_days"]),
                             "n_provinces": int(r["n_provinces"]),
                             "n_province_days": int(r["n_province_days"])}
                            for r in weekly.iter_rows(named=True)],
                "positives_vs_new_cases": {
                    "n_compared": j.height,
                    "n_equal": j.height - bad.height,
                    "dates_disagree": sorted(
                        f"{r['date']}/{r['province']}"
                        for r in bad.iter_rows(named=True))},
            }

    # ---- national STOCK observations ---------------------------------
    # Readings at an instant, not counts accumulated over a window: no
    # differencing, and no `days_covered` (the rule uganda_exports follows).
    # `patients_isolated` counts CONFIRMED AND SUSPECTED people in care --
    # sitrep 070 prints 766 and its own occupancy table splits that into 278
    # confirmed and 488 suspects -- so a model observing a confirmed-case
    # compartment wants `patients_isolated_confirmed`, whose share of the
    # total runs 0.23 to 0.53.
    #
    # NO CARRY-FORWARD HERE, and none is possible: a stock is a reading, not a
    # sum over a window, so there is no later row for a deficit to come out of
    # and nothing to preserve a total of. A downward move in one of these is
    # the census falling, which is the observation. The non-negativity gate
    # still covers them, because a reading below zero would be an extraction
    # defect rather than a revision.
    if args.banner and args.banner.exists():
        bn = pl.read_csv(args.banner, infer_schema_length=None)
        for col in ("patients_isolated", "patients_isolated_confirmed",
                    "cumul_recovered"):
            d = bn.filter(pl.col(col).is_not_null()).sort("date")
            if d.is_empty():
                continue
            write_stream(d.select(pl.col("date").alias("time"), pl.col(col)),
                         args.out_dir / f"{col}.tsv", STOCK)
            recon[col] = {"n_obs": d.height, "kind": "stock",
                          "first_date": d["date"][0],
                          "last_date": d["date"][-1],
                          "first_value": int(d[col][0]),
                          "last_value": int(d[col][-1])}

    # ---- THE CARE LEDGER, PER PROVINCE -------------------------------
    # The care pillar states its ledger in words, one bullet per province, and
    # the bullets keep printing the confirmed isolation census after the
    # front-page tile stopped on 2 August. See CARE_STREAMS above for why the
    # confirmed census is the quantity this block exists for.
    #
    # NO CARRY-FORWARD, and none is possible or wanted. These are not
    # differences of a cumulative: every value is a figure the report states
    # for that day, so there is no revision for a deficit to represent and no
    # later row for one to come out of. A negative here would be an extraction
    # defect rather than the source withdrawing cases, and the non-negativity
    # gate reads these files back off disk like all the others.
    #
    # ONE FILE PER QUANTITY PER PLACE, never one wide file per province. The
    # bullets print different quantities on different days -- Ituri states a
    # census on 37 report days and its confirmed half on 23 -- so a shared
    # table would be mostly holes, and a hole in a stream file is a row a
    # consumer has to decide about. A file that carries only the days its
    # quantity was printed needs no such decision, and `n_report_days_silent`
    # is where the days it was not printed are stated.
    if care is not None and not care.is_empty():
        care_places = dict(STREAM_PROVINCES) | {CARE_NATIONAL: "national"}
        cd = care.with_columns(pl.col("date").str.to_date())
        for family, col, scope in CARE_STREAMS:
            stock = family in CARE_STOCK_FAMILIES
            for prov, slug in care_places.items():
                d = (cd.filter((pl.col("province") == prov)
                               & pl.col(col).is_not_null())
                     .sort("date"))
                if d.is_empty():
                    continue
                name = f"{family}_{slug}"
                obs = f"{col}_{slug}"
                n_stated = d.height
                state = [care_state(c, scope) for c in d["checks"].to_list()]
                d = d.with_columns(
                    pl.Series("checks", state, dtype=pl.Utf8),
                    pl.col(col).cast(pl.Int64).alias(obs))
                if stock:
                    # A reading at the end of the report day: no accumulation
                    # window at all, so no `days_covered` and no
                    # `n_report_days` -- the rule `uganda_exports` follows.
                    # AND NO GRID EITHER: a stock has no window to be wider
                    # than the one it claims, so a gap of 46 days is a reading
                    # taken 46 days later and nothing is lost by leaving it a
                    # gap. Rows are added only where a hole would otherwise
                    # widen an accumulation.
                    left = d["date"].min() - dt.timedelta(days=1)
                    silent = silent_report_days(d["date"].to_list(),
                                                [1] * d.height, report_days,
                                                left)
                    d = d.with_columns(
                        pl.Series("n_report_days_silent", silent))
                    cols = [pl.col("date").dt.to_string("%Y-%m-%d")
                            .alias("time"), obs,
                            "n_report_days_silent", "checks"]
                    resolution = STOCK
                else:
                    # THE REPORT DAYS THIS QUANTITY WAS NOT STATED ON BECOME
                    # ROWS WITH AN EMPTY OBSERVATION. The report states one
                    # 24-hour figure, so a row is one day of flow -- but the
                    # engine accumulates between rows, so leaving the silent
                    # days out made each next row's window as wide as the gap
                    # behind it while its count still covered a day.
                    # `care_admissions_nord_kivu` had 1 June and 19 July in
                    # consecutive rows: 48 days of modelled admissions against
                    # one day of observed ones. With a row on every report day
                    # in between, `days_covered` is the gap to the row before
                    # and the two agree.
                    d = on_calendar_day_grid(
                        d.select("date", obs, "checks"), report_days,
                        time_col="date")
                    d = d.with_columns(
                        pl.col("checks").fill_null("unchecked"),
                        daily_flags(d["date"], caveat, exceptions,
                                    prov if prov != CARE_NATIONAL
                                    else "national"))
                    silent = d["n_report_days_silent"].to_list()
                    cols = [pl.col("date").dt.to_string("%Y-%m-%d")
                            .alias("time"), obs, "days_covered",
                            "n_report_days", "n_report_days_silent",
                            "checks", "flags"]
                    resolution = DAILY
                write_stream(d.select(cols), args.out_dir / f"{name}.tsv",
                             resolution)
                recon[name] = {
                    "n_obs": n_stated, "kind": "care",
                    "resolution": resolution,
                    "n_rows": d.height,
                    "first_date": str(d["date"][0]),
                    "last_date": str(d["date"][-1]),
                    "total": int(d[obs].sum()),
                    "report_days_silent": int(sum(silent)),
                    "checks": {v: state.count(v)
                               for v in ("closes", "contradicts", "unchecked")
                               if state.count(v)},
                }

    # ---- THE RECORD OF WHAT THE CARRY-FORWARD DID --------------------
    # GENERATED, never hand-maintained. A curated list would go stale the first
    # time INSP prints a revision nobody had seen, and it would imply a
    # per-case human judgement that does not exist: there is one rule, applied
    # to every count column, and this file is its transcript. One row for every
    # published row a deficit was open at, keyed on (stream, column, time) --
    # the same key the stream file itself carries, so a consumer can join it
    # straight on and see which of its observations were corrected, by how
    # much, and whether the deficit was still outstanding when that row was
    # emitted. An empty file with its header is the normal, healthy state and
    # is written anyway, because a missing artefact and a clean build must not
    # look the same.
    REV_SCHEMA = {"stream": pl.Utf8, "column": pl.Utf8, "time": pl.Utf8,
                  "raw": pl.Int64, "emitted": pl.Int64,
                  "carry_after": pl.Int64, "flags": pl.Utf8}
    (pl.DataFrame(revisions, schema=REV_SCHEMA)
     .sort("stream", "column", "time")
     .write_csv(args.out_dir / "revisions.tsv", separator="\t"))

    # WHAT EACH PUBLISHED FILE IS, TRAVELLING WITH THE FILES. `meta.json` is
    # vendored and hash-verified downstream; `registers/stream_families.tsv`
    # is not. So the sentences that say how to read a stream stayed in this
    # repository while the numbers went out, and a consumer wiring a column
    # read its filename and its header instead. The `care_exits_deaths`
    # register entry has said "an upper bound on confirmed deaths in care"
    # since it was written, and that column was still fitted as confirmed-only
    # downstream -- documentation that does not travel is documentation that
    # does not arrive.
    fams = load_families(args.families)
    stream_docs = {}
    for w in written:
        fam, _ = stream_identity(w.path.stem)
        entry = fams.get(fam)
        if entry is None:
            continue
        stream_docs[w.path.name] = {
            "family": fam,
            "value_span": VALUE_SPAN[fam],
            "measures": entry["measures"],
            "interpretation": entry["interpretation"],
        }

    last = panel.filter(pl.col("date") == panel["date"].max())
    pops = populations(args.geojson, args.population)
    n_zones = len(json.loads(args.geojson.read_text())["features"])
    meta = {
        "day0": str(DAY0),
        "bin_days": BIN_DAYS,
        # One entry per published file: what family it belongs to, what one
        # row's value covers, and the register's two sentences verbatim.
        "streams": stream_docs,
        "tool_versions": {"pdftotext": pdftotext_version,
                          "polars": pl.__version__},
        "n_days": int((dt.date.fromisoformat(panel["date"].max())
                       - DAY0).days) + 1,
        "provinces": list(STREAM_PROVINCES.values()),
        "population": pops,
        # What that table is a population OF, stated rather than inferred. A
        # consumer needs a national susceptible pool and would otherwise sum
        # the dict, which is only correct as long as the dict's keys happen to
        # be the right frame -- exactly the coupling that made this number move
        # when a publication decision changed.
        # How far apart the report instant and the confirmation instant are.
        # Carried here so a consumer pins it by tag rather than deriving it.
        "reporting_delay": json.loads(rd.read_text()) if (
            rd := ROOT / "data/build/series/reporting_delay.json").exists() else {},
        "swab_coverage": swab_coverage(
            args.burial_alerts if args.burial_alerts
            else ROOT / "data/build/series/burial_alerts.csv"),
        "population_frame": {
            "provinces": len(pops),
            "health_zones": n_zones,
            "national": sum(pops.values()),
            "definition":
                "The six provinces of the response geography, all 151 health "
                "zones, affected or not. This is the source's own frame: "
                "sitrep 108 reads «60 des 151 (39,7%) zones de sante des six "
                "provinces restent affectees depuis le debut de l'epidemie en "
                "RDC». It is fixed by the geography, not by which provinces "
                "this build publishes streams for, and a seventh province "
                "reporting a case does not move it.",
            "source":
                "WorldPop raster counts aggregated to health zone; see "
                "data/raw/PROVENANCE.tsv for the pinned file and its hash. "
                "Provinces are rounded to whole people and `national` is the "
                "sum of the rounded provinces, so the parts add to the whole.",
        },
        "dropped_provinces": {(r[0] or "unattributed"): r[1]
                              for r in dropped.iter_rows()},
        "reconciliation": recon,
        # Is the front-page tile the same quantity as the table it fills gaps
        # in? Re-established here on every build, never assumed.
        "banner_vs_table": banner_vs_table,
    }
    (args.out_dir / "meta.json").write_text(json.dumps(meta, indent=2,
                                                       sort_keys=True) + "\n")

    # ---- THE PER-RELEASE DATA DICTIONARY -----------------------------
    # Written HERE, by the run that wrote the streams, so it ships with the
    # vendored data rather than describing some other vintage of it. Written
    # BEFORE the gates for the same reason `revisions.tsv` is: a failing build
    # should still leave behind the evidence of what it produced. It has its
    # own gate -- a written stream with no sentence stops the build -- which
    # fires here rather than joining the block below, because a data
    # dictionary missing one of its files must not be written at all.
    if args.uganda_stream is not None and not args.uganda_stream.exists():
        sys.exit(f"--uganda-stream {args.uganda_stream.name} was named but "
                 "does not exist; run build_uganda_stream.py before this "
                 "script, as the Makefile does.")
    (args.out_dir / DICTIONARY).write_text(data_dictionary(
        written, args.families, data_date=panel["date"].max(),
        revisions=args.out_dir / "revisions.tsv",
        uganda=args.uganda_stream))

    for name, r in sorted(recon.items()):
        if r.get("kind") == "care":
            ch = ", ".join(f"{k} {v}" for k, v in r["checks"].items())
            print(f"  {name:<34} {r['n_obs']:>3} obs   {r['first_date']} -> "
                  f"{r['last_date']}   {r['report_days_silent']:>3} report "
                  f"day(s) silent   [{ch}]")
            continue
        if r.get("kind") == "stock":
            print(f"  {name:<26} {r['n_obs']:>3} obs   {r['first_value']} "
                  f"({r['first_date']}) -> {r['last_value']} ({r['last_date']})"
                  f"   [stock, no accumulation window]")
            continue
        if r.get("kind") == "excluding_backlog":
            sub = ", ".join(f"{x['date']} {x['differenced']}->"
                            f"{x['source_says_notified']}"
                            for x in r["rows_substituted"]) or "none"
            print(f"  {name:<34} {r['n_obs']:>3} obs   emitted "
                  f"{r['emitted']:>5} of the differenced "
                  f"{r['differenced_total']:>5}   substituted {sub}")
            continue
        if r.get("kind") == "notified":
            v = r["vs_cumulative"]
            apart = ", ".join(f"{d['date']} ({d['cumulative_moved']} moved "
                              f"vs {d['source_says_notified']} notified)"
                              for d in v["days_apart"]) or "none"
            print(f"  {name:<26} {r['n_obs']:>3} obs   notified "
                  f"{r['notified_total']:>5}   vs cumulative: "
                  f"{v['n_days_agreeing']}/{v['n_days_compared']} equal, "
                  f"apart on {apart}")
            continue
        if "tests" in r:                 # a testing stream
            pv = r.get("positives_vs_new_cases")
            cov = r.get("n_provinces")
            tail = (f"vs new cases: {pv['n_equal']}/{pv['n_compared']} equal"
                    if pv else
                    f"{cov['min']}-{cov['max']} provinces/day" if cov else "")
            print(f"  {name:<26} {r['n_obs']:>3} obs   tests {r['tests']:>5}  "
                  f"positives {r['positives']:>4}   {tail}")
            continue
        if "source_delta" not in r:      # an ascertainment stream
            av = r.get("vs_printed_daily")
            if av is None:               # the daily form carries no such check
                print(f"  {name:<26} {r['n_obs']:>3} obs   community "
                      f"{r['emitted']:>4} of {r.get('emitted_total', 0):>4}"
                      + (f"   {r['n_flagged']} flagged"
                         if r.get("n_flagged") else ""))
                continue
            print(f"  {name:<22} {r['n_obs']:>3} obs   community {r['emitted']:>4} "
                  f"of {r['emitted_total']:>4}   vs printed daily: "
                  f"{av['n_equal']}/{av['n_compared']} equal")
            continue
        flag = "" if r["difference"] == 0 else "   <-- DOES NOT RECONCILE"
        vp = r.get("vs_printed", {})
        vs = (f"   vs printed: {vp['n_equal']}/{vp['n_compared']} equal, "
              f"worst {vp['worst_gap']:+d} ({vp['worst_gap_date']}), "
              f"final {vp['final_gap']:+d}" if vp else "")
        print(f"  {name:<22} {r['n_obs']:>3} obs   emitted {r['emitted']:>5}  "
              f"source delta {r['source_delta']:>5}{flag}{vs}")

    if revisions:
        by = sorted({(r["stream"], r["column"]) for r in revisions})
        print(f"  {len(revisions)} row(s) across {len(by)} stream column(s) "
              f"carry a downward revision forward; "
              f"see {(args.out_dir / 'revisions.tsv').name}")
        for r in sorted(revisions, key=lambda r: (r["stream"], r["column"],
                                                  r["time"])):
            print(f"    {r['stream']}:{r['column']} {r['time']}  "
                  f"raw {r['raw']:+d} -> emitted {r['emitted']}"
                  f"   carry {r['carry_after']}")

    # ---- THE GATES ---------------------------------------------------
    # Six of them, all fatal, reported together so one run names every
    # problem rather than the first one:
    #   1. what a stream emits sums to what the source's cumulative moved;
    #   2. nothing published is negative -- read back off the files, so a
    #      column that never passed through the carry is covered too;
    #   3. every deficit the carry opened was discharged before the series
    #      ended. A residual means part of a revision was dropped on the
    #      floor, which also breaks (1) -- this names the cause;
    #   4. every scored row on a flow file claims the window it actually
    #      sits in, so a model accumulating between rows scores each count
    #      over the interval its own row states;
    #   5. an unscored row is unscored in every observation cell, and any
    #      divisor beside it is present and positive;
    #   6. a file with two observation columns has said which of them is the
    #      denominator, so no divisor can ship undeclared.
    #
    # (4) IS THE ONE WITH A BODY COUNT. Four published streams held rows 11 to
    # 48 days apart while claiming `days_covered` of 1, which asked the model
    # to explain up to 48 days of accumulated flow with a single day of it;
    # the consumer measured a 13-day version of the same defect refusing 23 of
    # 24 chains at initialisation. Nothing in the files said so, and no
    # existing gate could see it -- the counts were right, the totals
    # reconciled, and every column was populated.
    negatives = negative_values([w.path for w in written])
    windows = accumulation_windows(written)
    unscored = unscored_rows(written)
    undeclared = no_declared_denominator(written)
    if failures or negatives or carry_failures or windows or unscored \
            or undeclared:
        msg = []
        if failures:
            msg.append(f"STREAMS DO NOT RECONCILE: {failures}. "
                       "What is emitted must sum to what the cumulative moved.")
        if negatives:
            msg.append("A PUBLISHED COUNT IS NEGATIVE, which no count "
                       "likelihood can evaluate:\n  " + "\n  ".join(negatives))
        if carry_failures:
            msg.append("A DOWNWARD REVISION NEVER DISCHARGED by the end of "
                       "its series, so the emitted total is short of the "
                       "source's movement by that much:\n  "
                       + "\n  ".join(carry_failures))
        if windows:
            msg.append(
                "A SCORED ROW DOES NOT SIT WHERE ITS `days_covered` SAYS IT "
                "DOES. A model accumulates a modelled flow from the previous "
                "ROW of the stream, scored or not, so a row further from its "
                "predecessor than the window it claims is scored against more "
                "flow than it represents. Emit a row -- with an empty "
                "observation -- on every report day in the gap:\n  "
                + "\n  ".join(windows))
        if unscored:
            msg.append(
                "AN UNSCORED ROW IS MALFORMED. A row is either an observation "
                "in every one of its observation columns or an observation in "
                "none of them, and a divisor stays positive either way:\n  "
                + "\n  ".join(unscored))
        if undeclared:
            msg.append(
                "A DENOMINATOR IS UNDECLARED. A file publishing two "
                "observation columns has one that is the total the other is "
                "drawn out of; say which in DENOMINATOR_OF, and what a model "
                "does with it, before it ships:\n  " + "\n  ".join(undeclared))
        sys.exit("\n".join(msg))


if __name__ == "__main__":
    main()
