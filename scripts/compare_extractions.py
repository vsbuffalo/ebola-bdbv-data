"""Our extraction against the two others that exist: INRB-UMIE's and the
epiforecasts scan.

WHAT AGREEMENT HERE MEANS, AND WHAT IT DOES NOT
All three lineages read the same INSP situation-report PDFs. Agreement between
them is therefore evidence about TRANSCRIPTION -- that we and they read the
printed page the same way -- and never corroboration of the counts themselves.
A disagreement, though, is always a finding: one of the readings is wrong, or
the two read different versions of a revised report, and either is worth
knowing. That asymmetry is the point of this comparison.

THE THREE LINEAGES
  ours      the geometric extraction in this repository: per health zone, from
            the drawn table rules, validated against each page's own arithmetic.
  INRB      INRB-UMIE's transcription (github.com/INRB-UMIE/BDBV2026-Data):
            per health zone, daily. The national laboratory's own reading.
  scan      the epiforecasts reproduction's `insp_sitrep_scanned.csv`: national
            headline values read from the PDFs by an LLM agent and re-scanned
            by a second, with a notes column recording revisions and misprints.

Comparisons are made at the level each lineage natively provides -- ours vs
INRB per (zone, date); ours vs the scan per report at national level -- and
every disagreement is written to a CSV with both values, not summarised away.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))


#: One canonical key per PLACE across lineages, applied to BOTH sides after
#: folding. A zone the two lineages spell differently never joins, so it can
#: never DISAGREE -- the divergence vanishes from the comparison instead of
#: appearing in it, which is precisely backwards: a cross-lineage spelling
#: difference is itself a transcription disagreement. Mapping the four known
#: divergent spellings recovered eight zone-days, one of which is a genuine
#: value disagreement no earlier run ever saw (sitrep 064, Lubunga, deaths).
#: These mappings exist for the COMPARISON only; they assert the two spellings
#: name one place, not that either spelling is correct.
CROSS_ALIASES = {
    "manguripa": "manguredjipa",
    "rimba": "rumba",
    "nainia": "niania",
    "lubungatshopo": "lubunga",
    # BOTH lineages print both spellings, never on the same date (checked both
    # sides); without the fold, a date where we print `Gethy` and they print
    # `Gety` silently fails to join.
    "gethy": "gety",
}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    k = re.sub(r"[^a-z0-9]+", "", s.lower())
    return CROSS_ALIASES.get(k, k)


def load_ours_zone(path: Path) -> pl.DataFrame:
    d = pl.read_csv(path, infer_schema_length=None)
    return (d.filter(pl.col("level") == "zone")
            .with_columns(pl.col("zone_reported")
                          .map_elements(fold, return_dtype=pl.Utf8).alias("key"))
            .select("sitrep", "date", "key", "zone_reported",
                    pl.col("cum_cases").cast(pl.Int64, strict=False),
                    pl.col("cum_deaths").cast(pl.Int64, strict=False)))


def load_inrb(dirpath: Path) -> pl.DataFrame:
    """The INRB-UMIE per-zone series, under either of the layouts they have used.

    The upstream repository restructured between the reference pin (2026-08-10,
    `data/insp_sitrep/processed/...__daily.csv`) and the current head
    (2026-08-13, `build/long/...` without the suffix). Both are tried; which one
    loaded is part of the comparison's provenance, so it is printed.
    """
    def find(stem: str) -> Path:
        for cand in (dirpath / f"{stem}__daily.csv",
                     dirpath / f"{stem}.csv",
                     dirpath / "data" / "insp_sitrep" / "processed" / f"{stem}__daily.csv",
                     dirpath / "build" / "long" / f"{stem}.csv"):
            if cand.exists():
                print(f"  [inrb] {cand}")
                return cand
        raise SystemExit(f"no INRB file for {stem} under {dirpath}")
    def read(path: Path, value_name: str) -> pl.DataFrame:
        d = pl.read_csv(path, infer_schema_length=None)
        if value_name not in d.columns:
            # The 2026-08-13 restructure dropped the header row and prepended a
            # byte-order mark. A file whose first row is data must not lose it
            # to a guessed header, so it is re-read headerless with the columns
            # stated.
            d = pl.read_csv(path, has_header=False, infer_schema_length=None,
                            new_columns=["nom", "date", value_name])
        return d.with_columns(pl.col("nom").str.replace("\ufeff", ""))
    cases = read(find("insp_sitrep__cumulative_confirmed_cases"),
                 "cumulative_confirmed_cases")
    deaths = read(find("insp_sitrep__cumulative_confirmed_deaths"),
                  "cumulative_confirmed_deaths")
    j = (cases.rename({"cumulative_confirmed_cases": "inrb_cases"})
         .join(deaths.rename({"cumulative_confirmed_deaths": "inrb_deaths"}),
               on=["nom", "date"], how="full", coalesce=True))
    return j.with_columns(
        pl.col("nom").map_elements(fold, return_dtype=pl.Utf8).alias("key"),
        pl.col("inrb_cases").cast(pl.Int64, strict=False),
        # `ND` and kin in the INRB files are read as strings; a non-numeric
        # cell becomes null here rather than an error, and a null never counts
        # as a comparison.
        pl.col("inrb_deaths").cast(pl.Int64, strict=False))


def compare_zone(ours: pl.DataFrame, inrb: pl.DataFrame) -> pl.DataFrame:
    j = ours.join(inrb, on=["key", "date"], how="inner")
    return j.with_columns(
        (pl.col("cum_cases") - pl.col("inrb_cases")).alias("diff_cases"),
        (pl.col("cum_deaths") - pl.col("inrb_deaths")).alias("diff_deaths"))


def compare_national(ours_zone_path: Path, summary_path: Path,
                     scan_path: Path,
                     prose_path: Path | None = None) -> pl.DataFrame:
    d = pl.read_csv(ours_zone_path, infer_schema_length=None)
    nat = (d.filter(pl.col("level") == "national")
           .group_by("sitrep", "date")
           .agg(pl.col("cum_cases").cast(pl.Int64, strict=False).last()))
    summ = pl.read_csv(summary_path, infer_schema_length=None)
    nat_s = (summ.filter(pl.col("level") == "national")
             .group_by("sitrep", "date")
             .agg(pl.col("cum_cases").cast(pl.Int64, strict=False).last()
                  .alias("cum_cases_summary")))
    # THE PROSE ROUTE JOINS THE COMPARISON. The three prose-only reports are
    # the route with the weakest internal guard, and they were the only route
    # with an independent check available and unused -- the scan carries
    # their national figures.
    nat_p = None
    if prose_path is not None and prose_path.exists():
        pr = pl.read_csv(prose_path, infer_schema_length=None)
        nat_p = (pr.filter(pl.col("level") == "national")
                 .group_by("sitrep", "date")
                 .agg(pl.col("cum_cases").cast(pl.Int64, strict=False).last()
                      .alias("cum_cases_prose")))
    scan = pl.read_csv(scan_path, infer_schema_length=None)
    # `012_v2` and kin: a revised re-issue is a separate row in the scan. Our
    # archive holds one version per report, so compare against the LAST row per
    # number and keep the notes, which say what the revision changed.
    scan = (scan.with_columns(pl.col("sitrep").cast(pl.Utf8)
                              .str.extract(r"^(\d+)").cast(pl.Int64))
            .group_by("sitrep")
            .agg(pl.col("confirmed_cases").cast(pl.Int64, strict=False).last()
                 .alias("scan_cases"),
                 pl.col("notes").last()))
    out = nat.join(nat_s, on=["sitrep", "date"], how="full", coalesce=True)
    if nat_p is not None:
        out = out.join(nat_p, on=["sitrep", "date"], how="full", coalesce=True)
    else:
        out = out.with_columns(pl.lit(None, pl.Int64).alias("cum_cases_prose"))
    out = (out
           .with_columns(pl.coalesce("cum_cases", "cum_cases_summary",
                                     "cum_cases_prose")
                         .alias("ours_national"))
           .join(scan, on="sitrep", how="inner")
           .with_columns((pl.col("ours_national") - pl.col("scan_cases"))
                         .alias("diff")))
    return out.select("sitrep", "date", "ours_national", "scan_cases",
                      "diff", "notes").sort("sitrep")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zone-table", required=True, type=Path)
    ap.add_argument("--summary", required=True, type=Path)
    ap.add_argument("--inrb", required=True, type=Path,
                    help="directory of INRB-UMIE insp_sitrep__*.csv extractions")
    ap.add_argument("--scan", required=True, type=Path,
                    help="epiforecasts insp_sitrep_scanned.csv")
    ap.add_argument("--prose", type=Path, default=None,
                    help="prose_provinces.csv, so the prose-only reports "
                         "enter the national comparison")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--figure", type=Path, default=None,
                    help="also draw the comparison figure to this path")
    ap.add_argument("--series-figure", type=Path, default=None,
                    help="also draw the three-lineage SERIES figure "
                         "(needs --province-series and --geojson)")
    ap.add_argument("--province-series", type=Path, default=None,
                    help="province_series_reconciliation.csv: our summed "
                         "province series beside the printed rows")
    ap.add_argument("--geojson", type=Path, default=None,
                    help="health-zone geojson, to place INRB's zone rows in "
                         "provinces (their file carries no province column)")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    ours = load_ours_zone(args.zone_table)
    inrb = load_inrb(args.inrb)
    z = compare_zone(ours, inrb)

    z_cases = z.filter(pl.col("cum_cases").is_not_null()
                       & pl.col("inrb_cases").is_not_null())
    z_deaths = z.filter(pl.col("cum_deaths").is_not_null()
                        & pl.col("inrb_deaths").is_not_null())
    dis = z.filter((pl.col("diff_cases").fill_null(0) != 0)
                   | (pl.col("diff_deaths").fill_null(0) != 0))
    dis.sort(["date", "key"]).write_csv(args.out_dir / "inrb_disagreements.csv")
    # The FULL join too, not only the disagreements: an identity-line scatter
    # needs the agreeing mass behind the disagreeing points, or thirteen red
    # dots float in space with no sense of the two thousand that matched.
    (z.select("sitrep", "date", "zone_reported", "cum_cases", "inrb_cases",
              "cum_deaths", "inrb_deaths", "diff_cases", "diff_deaths")
     .sort(["date", "zone_reported"])
     .write_csv(args.out_dir / "zone_comparison.csv"))

    n = compare_national(args.zone_table, args.summary, args.scan, args.prose)
    n.write_csv(args.out_dir / "scan_comparison.csv")
    n_dis = n.filter(pl.col("diff").fill_null(0) != 0)

    # THE DENOMINATOR IS DISCLOSED, MACHINE-READABLY. "2,118 of 2,127 agree"
    # is a statement about the inner join, and the inner join is a
    # survivorship set: our newest reports have no INRB counterpart yet (their
    # series currently ends earlier than ours), and those rows -- the most
    # recent, least-reviewed fifth of the data -- are outside every agreement
    # figure. The meta file states the compared mass AND the uncompared mass,
    # and the document reads its numbers from here rather than typing them.
    import json
    ours_keys = ours.select("key", "date").unique()
    inrb_keys = inrb.select("key", "date").unique()
    joined = ours_keys.join(inrb_keys, on=["key", "date"], how="inner")
    meta = {
        "inrb": {
            "ours_zone_days": ours.height,
            "inrb_zone_days": inrb.height,
            "joined": joined.height,
            "ours_unmatched": ours.height - joined.height,
            "inrb_unmatched": inrb.height - joined.height,
            "cases_compared": z_cases.height,
            "cases_equal": z_cases.filter(pl.col("diff_cases") == 0).height,
            "deaths_compared": z_deaths.height,
            "deaths_equal": z_deaths.filter(pl.col("diff_deaths") == 0).height,
            "rows_disagreeing": dis.height,
            "ours_last_date": str(ours["date"].max()),
            "inrb_last_date": str(inrb["date"].max()),
        },
        "scan": {
            "compared": n.height,
            "equal": n.filter(pl.col("diff") == 0).height,
            "differ": n_dis.height,
        },
    }
    (args.out_dir / "compare_meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n")

    print("== ours vs INRB-UMIE, per (zone, date) ==")
    print(f"  cases : {z_cases.height} compared, "
          f"{z_cases.filter(pl.col('diff_cases') == 0).height} equal")
    print(f"  deaths: {z_deaths.height} compared, "
          f"{z_deaths.filter(pl.col('diff_deaths') == 0).height} equal")
    print(f"  rows disagreeing on either: {dis.height} "
          f"-> {args.out_dir / 'inrb_disagreements.csv'}")
    print("== ours vs epiforecasts scan, national cumulative cases ==")
    print(f"  {n.height} reports compared, "
          f"{n.filter(pl.col('diff') == 0).height} equal, "
          f"{n_dis.height} differ -> {args.out_dir / 'scan_comparison.csv'}")
    if n_dis.height:
        with pl.Config(tbl_rows=20, fmt_str_lengths=60):
            print(n_dis)

    if args.figure:
        draw_figure(z, n, args.figure)
        print(f"  figure -> {args.figure}")
    if args.series_figure:
        if not (args.province_series and args.geojson):
            sys.exit("--series-figure needs --province-series and --geojson")
        draw_series(inrb, args.province_series, args.geojson, args.inrb, n,
                    args.series_figure)
        print(f"  series figure -> {args.series_figure}")


def draw_figure(z: pl.DataFrame, n: pl.DataFrame, out: Path) -> None:
    """The three-lineage comparison, drawn.

    Left: every (zone, date) pair, ours against INRB's, on the identity line --
    log axes, so the whole four-orders-of-magnitude range is visible, and the
    thirteen disagreeing pairs in colour with the rest in grey. A caption that
    must travel with this figure: agreement here is evidence about
    TRANSCRIPTION, never corroboration of the counts, because every lineage
    read the same documents.

    Right: the signed difference over time, which is where structure would
    show -- a transcription slip is a lone point, a revised-report mismatch is
    a run. The national-scan comparison is stated in the title rather than
    plotted: sixty-seven reports at exactly zero difference draw as a line on
    the axis, and a sentence carries it better.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    both = z.filter(pl.col("cum_cases").is_not_null()
                    & pl.col("inrb_cases").is_not_null())
    ok = both.filter((pl.col("diff_cases") == 0)
                     & (pl.col("diff_deaths").fill_null(0) == 0))
    bad = both.filter((pl.col("diff_cases") != 0)
                      | (pl.col("diff_deaths").fill_null(0) != 0))

    fig, (ax, at) = plt.subplots(1, 2, figsize=(11, 4.6),
                                 constrained_layout=True)
    ax.plot([1, 5000], [1, 5000], color="#bbbbbb", linewidth=1, zorder=1)
    ax.scatter(ok["inrb_cases"], ok["cum_cases"], s=6, color="#c4c4c4",
               zorder=2, label=f"agree exactly ({ok.height:,})")
    ax.scatter(bad["inrb_cases"], bad["cum_cases"], s=22, color="#D55E00",
               zorder=3, label=f"disagree ({bad.height})")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("INRB-UMIE transcription (cumulative cases, zone-day)")
    ax.set_ylabel("this extraction")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title("On the identity line", loc="left", fontsize=10)

    xs = [mdates.datestr2num(d) for d in bad["date"].to_list()]
    at.axhline(0, color="#bbbbbb", linewidth=1)
    at.scatter(xs, bad["diff_cases"].to_list(), s=24, color="#D55E00",
               label="cases (ours − INRB)")
    xd = bad.filter(pl.col("diff_deaths").fill_null(0) != 0)
    at.scatter([mdates.datestr2num(d) for d in xd["date"].to_list()],
               xd["diff_deaths"].to_list(), s=24, facecolors="none",
               edgecolors="#0072B2", label="deaths")
    for r in bad.filter(pl.col("diff_cases").abs() > 5).iter_rows(named=True):
        at.annotate(f"{r['zone_reported']} s{r['sitrep']:03d}",
                    (mdates.datestr2num(r["date"]), r["diff_cases"]),
                    xytext=(5, 0), textcoords="offset points",
                    fontsize=7.5, va="center")
    at.set_title("The disagreements, signed, over time", loc="left",
                 fontsize=10)
    at.legend(frameon=False, fontsize=8)
    at.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    eq = n.filter(pl.col("diff") == 0).height
    fig.suptitle(
        f"Two extractions of one source are not independent evidence — "
        f"agreement is about transcription, disagreement is a finding\n"
        f"Zone-day values vs INRB-UMIE; national cumulative vs the "
        f"epiforecasts scan agrees on {eq} of {n.height} reports exactly.",
        x=0.01, ha="left", fontsize=10, fontweight="bold")
    for a in (ax, at):
        a.grid(True, color="#e6e6e6", linewidth=0.6)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)


def draw_series(inrb: pl.DataFrame, recon_path: Path, geojson: Path,
                inrb_dir: Path, n: pl.DataFrame, out: Path) -> None:
    """The three lineages as SERIES: our summed cumulative, INRB's summed
    cumulative, and the province row INSP itself prints, overlaid -- then the
    differences, which is where anything interesting lives.

    Top row: cumulative confirmed cases for Ituri, Nord-Kivu, and the nation.
    Our line is the sum of extracted zone rows; the black rings are the
    printed province/national totals (INSP's own statement, the check every
    build runs); INRB's line is their zone rows summed through the same
    zone-to-province mapping (their file carries no province column, so the
    geojson places each zone -- their literal `NA` zone cannot be placed and
    is excluded, which is one visible reason their sum can sit below the
    printed row).

    Bottom row: ours minus INRB per date, and ours minus the printed row.
    The ours-INRB difference mixes VALUE disagreements with ROW-COVERAGE
    differences (a zone-day absent from their file lowers their sum); the
    ours-printed difference is pure arithmetic against the page and is zero
    everywhere except the registered source self-disagreements.
    """
    import json
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    geo = json.loads(Path(geojson).read_text())
    zone_prov = {fold(f["properties"]["nom"]): f["properties"]["province"]
                 for f in geo["features"]}
    placed = inrb.with_columns(
        pl.col("key").map_elements(lambda k: zone_prov.get(k, ""),
                                   return_dtype=pl.Utf8).alias("prov"))
    dropped = placed.filter(pl.col("prov") == "")
    if dropped.height:
        print(f"  [series] {dropped.height} INRB zone-days in no geojson "
              f"province (excluded): "
              f"{sorted(set(dropped['nom'].to_list()))}")
    # Their file carries one malformed date (`2026-06-25]`, a bracket artefact
    # of their own build); it can never join anything and cannot be plotted.
    bad_dates = placed.filter(~pl.col("date").str.contains(r"^\d{4}-\d{2}-\d{2}$"))
    if bad_dates.height:
        print(f"  [series] {bad_dates.height} INRB row(s) with malformed "
              f"dates excluded: {sorted(set(bad_dates['date'].to_list()))}")
    placed = placed.filter(pl.col("date").str.contains(r"^\d{4}-\d{2}-\d{2}$"))
    inrb_prov = (placed.filter(pl.col("prov") != "")
                 .group_by("prov", "date")
                 .agg(pl.col("inrb_cases").sum()).sort("date"))

    rec = pl.read_csv(recon_path, infer_schema_length=None)

    # INRB's own national series, a separate file in their build.
    natl = None
    for cand in (Path(inrb_dir) / "build" / "long"
                 / "insp_sitrep__national_cumulative_confirmed_cases.csv",
                 Path(inrb_dir)
                 / "insp_sitrep__national_cumulative_confirmed_cases.csv"):
        if cand.exists():
            natl = pl.read_csv(cand, has_header=False,
                               new_columns=["nom", "date", "v"],
                               infer_schema_length=None)
            break
    if natl is None:
        print("  [series] NOTE: no INRB national file found; national panel "
              "draws without their line")

    OURS, INRB_C = "#0072B2", "#D55E00"
    fig, axes = plt.subplots(2, 3, figsize=(12.5, 7), constrained_layout=True,
                             height_ratios=[2.2, 1])

    def x(dates):
        return [mdates.datestr2num(d) for d in dates]

    panels = [("Ituri", "Ituri"), ("Nord-Kivu", "Nord-Kivu")]
    for ci, (prov, geo_prov) in enumerate(panels):
        ax, ad = axes[0][ci], axes[1][ci]
        o = (rec.filter(pl.col("province") == prov)
             .select("date", "cum_cases", "cum_cases_printed").sort("date"))
        i = inrb_prov.filter(pl.col("prov") == geo_prov).sort("date")
        ax.plot(x(o["date"]), o["cum_cases"], color=OURS, linewidth=1.6,
                label="ours (zone rows summed)", zorder=3)
        pr = o.filter(pl.col("cum_cases_printed").is_not_null())
        ax.scatter(x(pr["date"]), pr["cum_cases_printed"], s=26,
                   facecolors="none", edgecolors="#222222", linewidths=0.9,
                   label="INSP printed province row", zorder=4)
        ax.plot(x(i["date"]), i["inrb_cases"], color=INRB_C, linewidth=1.4,
                linestyle="--", label="INRB zone rows summed", zorder=2)
        ax.set_title(f"{prov} — cumulative confirmed cases", loc="left",
                     fontsize=10)
        if ci == 0:
            ax.legend(frameon=False, fontsize=8, loc="upper left")

        j = (o.join(i.rename({"date": "date"}), on="date", how="inner")
             .with_columns((pl.col("cum_cases") - pl.col("inrb_cases"))
                           .alias("d_inrb"),
                           (pl.col("cum_cases")
                            - pl.col("cum_cases_printed")).alias("d_printed")))
        ad.axhline(0, color="#bbbbbb", linewidth=1)
        ad.plot(x(j["date"]), j["d_inrb"], color=INRB_C, linewidth=1.1,
                label="ours − INRB (value + coverage)")
        jp = o.filter(pl.col("cum_cases_printed").is_not_null())
        ad.scatter(x(jp["date"]),
                   (jp["cum_cases"] - jp["cum_cases_printed"]).to_list(),
                   s=12, color="#222222", label="ours − printed")
        if ci == 0:
            ad.legend(frameon=False, fontsize=7.5)

    # National panel: ours (zone/summary/prose national), the scan, INRB's file.
    ax, ad = axes[0][2], axes[1][2]
    ns = n.sort("date")
    ax.plot(x(ns["date"]), ns["ours_national"], color=OURS, linewidth=1.6,
            label="ours (national rows)", zorder=3)
    ax.scatter(x(ns["date"]), ns["scan_cases"], s=26, facecolors="none",
               edgecolors="#222222", linewidths=0.9,
               label="epiforecasts scan", zorder=4)
    if natl is not None:
        nn = natl.sort("date")
        ax.plot(x(nn["date"]), nn["v"], color=INRB_C, linewidth=1.4,
                linestyle="--", label="INRB national file", zorder=2)
        jn = (ns.select("date", "ours_national")
              .join(nn.select("date", "v"), on="date", how="inner"))
        ad.plot(x(jn["date"]), (jn["ours_national"] - jn["v"]).to_list(),
                color=INRB_C, linewidth=1.1, label="ours − INRB")
        # Days BEFORE OUR ARCHIVE BEGINS (the scan frame starts later still,
        # so anchor on the first data date we hold, not on `ns`): these are
        # sitreps 001-004, which INSP's site no longer lists -- INRB's file
        # is the only lineage that has them, and nothing can check it.
        pre = nn.filter(pl.col("date") < rec["date"].min())
        if pre.height:
            ax.annotate(f"{pre.height} INRB-only days\n(sitreps 001–004; "
                        "no PDF public)", (x(pre["date"])[0], pre["v"][0]),
                        xytext=(8, 28), textcoords="offset points",
                        fontsize=7.5, color=INRB_C)
    ax.set_title("National — cumulative confirmed cases", loc="left",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ad.axhline(0, color="#bbbbbb", linewidth=1)
    ad.scatter(x(ns["date"]), ns["diff"].to_list(), s=12, color="#222222",
               label="ours − scan")
    ad.legend(frameon=False, fontsize=7.5)
    lo, hi = ad.get_ylim()
    if max(abs(lo), abs(hi)) < 1:
        ad.set_ylim(-3, 3)      # an all-zero panel must read as zero, not 1e-17

    for a in axes.flat:
        a.grid(True, color="#e6e6e6", linewidth=0.6)
        a.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    for a in axes[1]:
        a.set_title("differences", loc="left", fontsize=8.5, color="#555555")
    fig.suptitle(
        "Three readings of the same pages, as series — ours, INSP's own "
        "printed totals, and INRB-UMIE's transcription\n"
        "Agreement is evidence about transcription, never about the counts; "
        "the bottom row is where the lineages actually differ.",
        x=0.01, ha="left", fontsize=10, fontweight="bold")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
