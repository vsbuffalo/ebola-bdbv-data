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
STREAM_PROVINCES = {"Ituri": "ituri", "Nord-Kivu": "nord_kivu",
                    "Haut-Uélé": "haut_uele"}


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


# ---- THE VOCABULARY THE PUBLISHED FILES ARE DOCUMENTED IN ----------------
# `data/build/streams/README.md` travels with the vendored data and answers
# the question `meta.json` cannot: what is `community_deaths_daily_ituri`, and
# what dates does it cover? Everything in it is read back off the files this
# run wrote; the one thing no build can generate -- the sentence saying what a
# quantity MEASURES -- comes from `registers/stream_families.tsv`.

#: `time` aside, these columns describe the ROW rather than observing
#: anything: how wide its window is, how much of that window the source
#: reported on, what the page said about that day, and how many provinces fed
#: it. Every other column in a stream file is an observation.
METADATA_COLUMNS = ("days_covered", "n_report_days", "flags", "n_provinces")

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
        t = pl.read_csv(path, separator="\t", infer_schema_length=None)
        for col in t.columns:
            if not t[col].dtype.is_numeric():
                continue
            for r in t.filter(pl.col(col) < 0).iter_rows(named=True):
                out.append(f"{path.name}: {col} = {r[col]} at {r['time']}")
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
    """What a published file says about itself: how many rows, which `time`
    values it spans, and which of its columns are observations.

    READ OFF THE FILE, not off `meta.json`. The reconciliation block carries a
    date range for the streams built by differencing a cumulative, but not for
    the community-death or laboratory streams, so keying documentation off it
    would leave thirteen of the published files with no stated span. A
    document that states the range of the file it documents, measured from
    that file, is also simply the more honest construction.
    """
    t = pl.read_csv(path, separator="\t", infer_schema_length=None)
    times = sorted(str(x) for x in t["time"].to_list())
    return {"n_obs": t.height,
            "first": times[0] if times else "-",
            "last": times[-1] if times else "-",
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
            + f". {span}.", ""]


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
        "- **No published count is negative.** Where the source revised its "
        "own cumulative downward, the deficit is carried into later rows "
        "rather than clipped, so a stream still totals exactly what the "
        "source's cumulative moved. `revisions.tsv` below is the row-by-row "
        "record of every row that touched.",
        "- **Observation columns and metadata columns.** The first column is "
        "always `time`. "
        + ", ".join(f"`{c}`" for c in METADATA_COLUMNS)
        + " describe the row rather than the epidemic; every other column is "
        "an observation, and each is named below.", "",
    ]

    # A STREAM THAT STOPS EARLY LOOKS EXACTLY LIKE ONE THAT IS UP TO DATE
    # unless the reader compares two dates in a table, which is precisely the
    # comparison a consumer skips. `patients_isolated_confirmed` ends 20 days
    # before the rest of this release because the source stopped printing its
    # tile after sitrep 080; nothing in a per-file row says so. Derived rather
    # than written into the register, because it must stop being true the day
    # the source resumes -- and a hand-kept note would not.
    behind = []
    for w in written:
        if w.path.name == DICTIONARY:
            continue
        last = stream_facts(w.path)["last"]
        if last < data_date:
            gap = (dt.date.fromisoformat(data_date)
                   - dt.date.fromisoformat(last)).days
            behind.append((w.path.name, last, gap))
    if behind:
        out += [
            "## Streams with no observation at the data date", "",
            "These stop before the rest of the release. A gap of this size is "
            "normally the SOURCE having stopped publishing the quantity, not "
            "this pipeline having failed to read it — but the two look "
            "identical in the tables below, so check the `written_from` note "
            "in `registers/stream_families.tsv` before fitting the tail.", "",
        ]
        out += _table(
            [[f"`{n}`", last, f"{gap} days"] for n, last, gap in sorted(behind)],
            ["File", "Last `time`", "Behind the data date"],
            ["---", "---", "---:"])
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
                         str(f["n_obs"]), f["first"], f["last"],
                         ", ".join(f"`{c}`" for c in f["columns"])])
        out += [f"## {entry['title']}", "", entry["measures"], ""]
        out += _table(rows,
                      ["File", "Place", "Resolution", "Obs", "First `time`",
                       "Last `time`", "Observation column(s)"],
                      ["---", "---", "---", "---:", "---", "---", "---"])
        out += [""]

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


def populations(geojson: Path, pop_csv: Path) -> dict[str, float]:
    """Full-province denominators: every zone in the province, affected or not.

    Accent folding runs on BOTH sides, through one folding function. The old
    comparison folded one accent on one side only, so a geojson spelling
    `Haut-Uélé` produced a denominator of ZERO -- `sum()` over an empty
    generator -- and the zero went into the meta file as a population. A
    denominator of zero is never a population; it stops the build.
    """
    import unicodedata

    def fold(s: str) -> str:
        t = unicodedata.normalize("NFKD", s or "")
        t = "".join(c for c in t if not unicodedata.combining(c))
        return t.lower().replace("-", " ").strip()

    geo = json.loads(geojson.read_text())
    zone_prov = {f["properties"]["nom"]: f["properties"]["province"]
                 for f in geo["features"]}
    pop = dict(pl.read_csv(pop_csv).iter_rows())
    out: dict[str, float] = {}
    for prov, slug in STREAM_PROVINCES.items():
        total = sum(v for z, v in pop.items()
                    if fold(zone_prov.get(z, "")) == fold(prov))
        if not total > 0:
            sys.exit(f"population for {prov} came out {total}: the geojson "
                     "province spellings no longer match STREAM_PROVINCES, "
                     "and zero is not a population")
        out[slug] = total
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", required=True, type=Path)
    ap.add_argument("--geojson", required=True, type=Path)
    ap.add_argument("--population", required=True, type=Path)
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
    ap.add_argument("--caveat", type=Path, default=None,
                    help="provisional_caveat.csv, so daily rows carry the "
                         "source's own consolidation flags")
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

    dropped = (panel.filter(pl.col("level").is_in(["zone", "unassigned"])
                            & ~pl.col("province").is_in(list(STREAM_PROVINCES))
                            & pl.col("cum_cases").is_not_null())
               .group_by("province").agg(pl.col("cum_cases").max()))

    summary = (pl.read_csv(args.summary, infer_schema_length=None)
               if args.summary and args.summary.exists() else None)
    prose = (pl.read_csv(args.prose, infer_schema_length=None)
             if args.prose and args.prose.exists() else None)
    banner = (pl.read_csv(args.banner, infer_schema_length=None)
              if args.banner and args.banner.exists() else None)

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
        d.write_csv(path, separator="\t")
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
        prov_names = [f"{stem}_{s}" for s in STREAM_PROVINCES.values()]
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

    # The daily ascertainment split: these columns are ALREADY the day's own
    # 24-hour flows as the source prints them, so a row covers one day
    # whatever the gap before it -- `days_since_prev_report` says how far
    # back the previous observation sits without claiming the interval.
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
             .sort("date")
             .with_columns((pl.col("date") - pl.col("date").shift(1))
                           .dt.total_days().fill_null(1)
                           .alias("days_covered")))
        d = d.with_columns(daily_flags(d["date"], caveat, exceptions,
                                       prov or "national"))
        name = f"community_deaths_daily_{slug}"
        cname, tname = f"community_deaths_{slug}", f"deaths_split_{slug}"
        fl = d["flags"].to_list()
        d = carried(d, name, cname, count_col="deaths_community",
                    time_col="date", flags=fl)
        d = carried(d, name, tname, count_col="deaths_total",
                    time_col="date", flags=fl)
        write_stream(
            d.with_columns(pl.lit(1, pl.Int64).alias("n_report_days"))
            .select(pl.col("date").dt.to_string("%Y-%m-%d").alias("time"),
                    pl.col("deaths_community").alias(cname),
                    pl.col("deaths_total").alias(tname),
                    "days_covered", "n_report_days", "flags"),
            args.out_dir / f"{name}.tsv", DAILY)
        recon[name] = {"n_obs": d.height,
                       "emitted": int(d["deaths_community"].sum()),
                       "emitted_total": int(d["deaths_total"].sum()),
                       "n_flagged": int(d.filter(pl.col("flags") != "-").height),
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
                          pl.len().alias("n_prov")))
            weekly = (daily.with_columns(
                          (((pl.col("date") - pl.lit(DAY0)).dt.total_days() - 1)
                           // BIN_DAYS).alias("bin"))
                      .group_by("bin")
                      .agg(pl.col("samples").sum(), pl.col("positives").sum(),
                           pl.col("date").max().alias("time"),
                           pl.len().alias("n_report_days"),
                           pl.col("n_prov").sum().alias("n_province_days"))
                      .sort("bin"))
            weekly = carried(weekly, "lab_national", "positives_national",
                             count_col="positives")
            weekly = carried(weekly, "lab_national", "tests_national",
                             count_col="samples")
            write_stream(
                weekly.with_columns(
                    pl.Series("days_covered",
                              spans(weekly["time"].to_list(),
                                    daily["date"].min() - dt.timedelta(days=1))))
                .select(pl.col("time").dt.to_string("%Y-%m-%d"),
                        pl.col("positives").alias("positives_national"),
                        pl.col("samples").alias("tests_national"),
                        "days_covered", "n_report_days"),
                args.out_dir / "lab_national.tsv", WEEKLY)
            # THE DAILY FORM IS THE COVERAGE-HONEST ONE, and this stream needs
            # it most: a weekly total is the sum over however many report-days
            # and however many PROVINCES licensed a sentence that week, and
            # both vary -- the last weekly bins rest on one report-day each.
            # `n_provinces` is therefore emitted beside the counts: a day's
            # national total is the sum over exactly those provinces, and a
            # consumer that ignores it will read a composition change as a
            # change in testing effort.
            dl = daily.sort("date").with_columns(
                (pl.col("date") - pl.col("date").shift(1)).dt.total_days()
                .fill_null(1).alias("days_covered"))
            dl = dl.with_columns(daily_flags(dl["date"], caveat, exceptions,
                                             "national"))
            fl = dl["flags"].to_list()
            dl = carried(dl, "lab_daily_national", "positives_national",
                         count_col="positives", time_col="date", flags=fl)
            dl = carried(dl, "lab_daily_national", "tests_national",
                         count_col="samples", time_col="date", flags=fl)
            write_stream(
                dl.with_columns(pl.lit(1, pl.Int64).alias("n_report_days"))
                .select(pl.col("date").dt.to_string("%Y-%m-%d").alias("time"),
                        pl.col("positives").alias("positives_national"),
                        pl.col("samples").alias("tests_national"),
                        "days_covered", "n_report_days",
                        pl.col("n_prov").alias("n_provinces"), "flags"),
                args.out_dir / "lab_daily_national.tsv", DAILY)
            recon["lab_daily_national"] = {
                "n_obs": dl.height,
                "tests": int(dl["samples"].sum()),
                "positives": int(dl["positives"].sum()),
                "n_provinces": {"median": float(dl["n_prov"].median()),
                                "min": int(dl["n_prov"].min()),
                                "max": int(dl["n_prov"].max())},
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
                d = d.with_columns(
                    (pl.col("date") - pl.col("date").shift(1)).dt.total_days()
                    .fill_null(1).alias("days_covered"))
                d = d.with_columns(daily_flags(d["date"], caveat, exceptions,
                                               prov))
                name = f"lab_daily_{slug}"
                write_stream(
                    d.with_columns(pl.lit(1, pl.Int64).alias("n_report_days"))
                    .select(pl.col("date").dt.to_string("%Y-%m-%d")
                            .alias("time"),
                            pl.col("positives").alias(f"positives_{slug}"),
                            pl.col("samples").alias(f"tests_{slug}"),
                            "days_covered", "n_report_days", "flags"),
                    args.out_dir / f"{name}.tsv", DAILY)
                recon[name] = {
                    "n_obs": d.height,
                    "tests": int(d["samples"].sum()),
                    "positives": int(d["positives"].sum()),
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

    last = panel.filter(pl.col("date") == panel["date"].max())
    meta = {
        "day0": str(DAY0),
        "bin_days": BIN_DAYS,
        "tool_versions": {"pdftotext": pdftotext_version,
                          "polars": pl.__version__},
        "n_days": int((dt.date.fromisoformat(panel["date"].max())
                       - DAY0).days) + 1,
        "provinces": list(STREAM_PROVINCES.values()),
        "population": populations(args.geojson, args.population),
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
        if r.get("kind") == "stock":
            print(f"  {name:<26} {r['n_obs']:>3} obs   {r['first_value']} "
                  f"({r['first_date']}) -> {r['last_value']} ({r['last_date']})"
                  f"   [stock, no accumulation window]")
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
    # Three of them, all fatal, reported together so one run names every
    # problem rather than the first one:
    #   1. what a stream emits sums to what the source's cumulative moved;
    #   2. nothing published is negative -- read back off the files, so a
    #      column that never passed through the carry is covered too;
    #   3. every deficit the carry opened was discharged before the series
    #      ended. A residual means part of a revision was dropped on the
    #      floor, which also breaks (1) -- this names the cause.
    negatives = negative_values([w.path for w in written])
    if failures or negatives or carry_failures:
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
        sys.exit("\n".join(msg))


if __name__ == "__main__":
    main()
