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

CUMULATIVE DECREASES ARE KEPT, AS NEGATIVE INCIDENCE. A fall in a cumulative
column is the source's own downward revision -- sitrep 073 prints Katwa's
daily deaths as `-2` under a note declaring two deaths removed -- and clipping
it would keep cases the source deleted, erring upward only.

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

import polars as pl

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
    weekly = (printed.with_columns(
                  (((pl.col("date") - pl.lit(DAY0)).dt.total_days() - 1)
                   // BIN_DAYS).alias("bin"))
              .group_by("bin")
              .agg(pl.col("deaths_community").sum(),
                   pl.col("deaths_total").sum(),
                   pl.col("date").max().alias("time"))
              .sort("bin"))
    return weekly, vs


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
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    ALIASES.update(load_aliases(Path("data/raw/zone_aliases.csv"),
                                Path("registers/zone_aliases_local.csv")))
    panel = carry_province(pl.read_csv(args.panel, infer_schema_length=None))

    dropped = (panel.filter(pl.col("level").is_in(["zone", "unassigned"])
                            & ~pl.col("province").is_in(list(STREAM_PROVINCES))
                            & pl.col("cum_cases").is_not_null())
               .group_by("province").agg(pl.col("cum_cases").max()))

    recon: dict[str, dict] = {}
    failures: list[str] = []
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
            emitted = int(weekly["count"].sum())
            source_delta = int(cum["cum"][-1] - cum["cum"][0])
            recon[name] = {
                "emitted": emitted, "source_delta": source_delta,
                "difference": emitted - source_delta,
                "first_date": str(cum["date"][0]),
                "last_date": str(cum["date"][-1]),
                "n_obs": weekly.height,
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
            (weekly.select(pl.col("time").dt.to_string("%Y-%m-%d"),
                           pl.col("count").alias(name))
             .write_csv(args.out_dir / f"{name}.tsv", separator="\t"))

        asc, asc_vs = ascertainment(panel, prov)
        if not asc.is_empty():
            (asc.select(pl.col("time").dt.to_string("%Y-%m-%d"),
                        pl.col("deaths_community")
                        .alias(f"community_deaths_{slug}"),
                        pl.col("deaths_total").alias(f"deaths_split_{slug}"))
             .write_csv(args.out_dir / f"community_deaths_{slug}.tsv",
                        separator="\t"))
            recon[f"community_deaths_{slug}"] = {
                "n_obs": asc.height,
                "emitted": int(asc["deaths_community"].sum()),
                "emitted_total": int(asc["deaths_total"].sum()),
                "vs_printed_daily": asc_vs,
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
    }
    (args.out_dir / "meta.json").write_text(json.dumps(meta, indent=2,
                                                       sort_keys=True) + "\n")

    for name, r in sorted(recon.items()):
        if "source_delta" not in r:      # an ascertainment stream
            av = r["vs_printed_daily"]
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
    if failures:
        sys.exit(f"STREAMS DO NOT RECONCILE: {failures}. "
                 "What is emitted must sum to what the cumulative moved.")


if __name__ == "__main__":
    main()
