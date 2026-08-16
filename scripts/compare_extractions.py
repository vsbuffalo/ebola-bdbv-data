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


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s.lower())


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
                     scan_path: Path) -> pl.DataFrame:
    d = pl.read_csv(ours_zone_path, infer_schema_length=None)
    nat = (d.filter(pl.col("level") == "national")
           .group_by("sitrep", "date")
           .agg(pl.col("cum_cases").cast(pl.Int64, strict=False).last()))
    summ = pl.read_csv(summary_path, infer_schema_length=None)
    nat_s = (summ.filter(pl.col("level") == "national")
             .group_by("sitrep", "date")
             .agg(pl.col("cum_cases").cast(pl.Int64, strict=False).last()
                  .alias("cum_cases_summary")))
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
    out = (nat.join(nat_s, on=["sitrep", "date"], how="full", coalesce=True)
           .with_columns(pl.coalesce("cum_cases", "cum_cases_summary")
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
    ap.add_argument("--out-dir", required=True, type=Path)
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

    n = compare_national(args.zone_table, args.summary, args.scan)
    n.write_csv(args.out_dir / "scan_comparison.csv")
    n_dis = n.filter(pl.col("diff").fill_null(0) != 0)

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


if __name__ == "__main__":
    main()
