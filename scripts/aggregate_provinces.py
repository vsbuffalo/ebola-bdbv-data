"""Aggregate the health-zone extraction to province level, and fail if it does not add up.

WHY AGGREGATE AT ALL, WHEN THE SOURCE PRINTS PROVINCE TOTALS
Because the printed province row is the CHECK, not the input. The reports print
each province's total alongside its health zones, so summing the zones ourselves
and comparing gives an independent statement about whether we read the table
correctly. Taking the printed total directly would be less work and would tell
us nothing: a missed zone row would pass silently, which is exactly the failure
that motivates this whole pipeline.

So the province series is BUILT from the zone rows, and the province row the
source prints is spent on validating it rather than on producing it.

WHAT COUNTS AS A PART
A province's parts are its health zones plus the rows the source counts but has
not yet assigned to a zone -- `Autres ZS (données non ventilées)`, `A ventiler`,
`Non identifiées`. Those rows are inside the printed province total, so leaving
them out understates the sum by exactly their value, and folding them into a
zone would invent a place. They are carried at their own level and added here.

THIS STEP IS LOUD BY DESIGN
Every discrepancy is a finding about the extraction or about the report, and
neither is something to average away. The exit codes distinguish them:

    0   every province in every report reconciles
    1   some reports could not be checked -- the page printed no total to
        compare against. Not a failure; a gap in the evidence, reported.
    2   a province total disagrees with the sum of its parts. STOP AND LOOK.

Nothing is silently dropped, clipped or repaired. A province that does not
reconcile is still written out, flagged, so the disagreement is visible to
whatever reads the file rather than hidden by its absence.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import polars as pl

REGISTER_COLUMNS = ("sitrep", "date", "sha256_16", "unit", "column",
                    "expected_gap", "verified_by", "note")


def load_exceptions(path: Path, pdfs: Path | None) -> pl.DataFrame:
    """Read the hand-verified exception register, and refuse a stale one.

    An entry asserts that a named PDF does not agree with itself. That claim is
    about ONE VERSION of the document, and INSP revises reports and republishes
    them under the same number -- so the file's hash is checked against the
    entry, and a mismatch stops the build. A corrected report must return to the
    failing set and be read again, not inherit the exception its predecessor was
    granted.

    With no `--pdfs` the hashes cannot be checked, and the register is refused
    rather than applied unverified: an exception that has not been tied to a
    document is not an exception, it is a suppression.
    """
    if not path.exists():
        return pl.DataFrame(schema={c: pl.Utf8 for c in REGISTER_COLUMNS})
    ex = pl.read_csv(path, separator="\t", comment_prefix="#",
                     infer_schema_length=None)
    missing = set(REGISTER_COLUMNS) - set(ex.columns)
    if missing:
        raise SystemExit(f"{path}: missing column(s) {sorted(missing)}")
    if ex.is_empty():
        return ex
    if pdfs is None:
        raise SystemExit(
            f"{path} holds {ex.height} exceptions but --pdfs was not given, so "
            "their hashes cannot be verified. An exception not tied to a "
            "document is a suppression; pass --pdfs or move the register aside.")

    stale, absent = [], []
    for e in ex.iter_rows(named=True):
        hits = sorted(pdfs.glob(f"sitrep_{int(e['sitrep']):03d}_*.pdf"))
        if not hits:
            absent.append(e)
            continue
        got = hashlib.sha256(hits[0].read_bytes()).hexdigest()[:16]
        if got != e["sha256_16"]:
            stale.append((e, got, hits[0].name))
    if absent:
        raise SystemExit(
            "the exception register names reports that are not in the archive:\n"
            + "\n".join(f"  sitrep {e['sitrep']} ({e['unit']}, {e['column']})"
                        for e in absent))
    if stale:
        lines = "\n".join(
            f"  sitrep {e['sitrep']} {name}: register says {e['sha256_16']}, "
            f"file is {got}" for e, got, name in stale)
        raise SystemExit(
            "EXCEPTIONS ARE STALE -- the documents they describe have changed:\n"
            + lines
            + "\n\nEach was a claim about one version of a page. Re-read the new "
              "version and update or remove the entry; do not just refresh the "
              "hash.")
    return ex


PARTS = ("zone", "unassigned")
COUNTS = ("cum_cases", "cum_deaths", "new_cases", "deaths_community",
          "deaths_treatment_centre", "deaths_total")


SUBTOTAL_PREFIX = r"(?i)^\s*sous[-\s]?total\s*"

#: The affected provinces, and every spelling the reports print them under. The
#: set is CLOSED: a province row naming something not here stops the build
#: rather than becoming a sixteenth province. Without that, `ITURI`, `Ituri`,
#: `Nord-Kivu*` and the source's own typo `Nord-Kivi` each aggregated
#: separately, and the series for the largest province was split three ways
#: while every total still looked plausible.
#:
#: Case and accents are folded before lookup, and a trailing footnote marker is
#: typography rather than name, so neither needs an entry. What remains here is
#: only what folding cannot reach: hyphen-versus-space, and the misprints.
PROVINCE_ALIASES = {
    "ituri": "Ituri",
    "nord-kivu": "Nord-Kivu",
    "nord kivu": "Nord-Kivu",
    "nord-kivi": "Nord-Kivu",        # misprint, sitrep 090
    "sud-kivu": "Sud-Kivu",
    "sud kivu": "Sud-Kivu",
    "haut-uele": "Haut-Uélé",
    "haut uele": "Haut-Uélé",
    "tshopo": "Tshopo",
    "bas-uele": "Bas-Uélé",
    "bas uele": "Bas-Uélé",
    "kinshasa": "Kinshasa",
    "maniema": "Maniema",
}


def canonical_province(name: str) -> str | None:
    """One spelling per province, or None if the name is not one we know."""
    import unicodedata
    s = unicodedata.normalize("NFKD", (name or "").strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.strip("*†‡ ").lower()
    s = re.sub(r"\s+", " ", s)
    return PROVINCE_ALIASES.get(s)


def carry_province(panel: pl.DataFrame) -> pl.DataFrame:
    """Give every zone row the province it was printed under.

    The province is not a column in this table; it is a ROW, and its health
    zones are the rows adjacent to it. So the carry runs over the order the
    table prints, not over a zone-to-province lookup -- which matters because
    the source reassigns zones between provinces as investigations proceed, and
    a lookup would impose today's assignment on every past report. What the page
    says is what the page said at the time.

    THE PROVINCE ROW SITS ON DIFFERENT SIDES OF ITS ZONES IN THE TWO LAYOUTS,
    and the source says which by how it labels the row. A bare province name
    (`Ituri`) OPENS the block and its zones follow, so the carry runs forward. A
    row labelled `Sous-total Ituri` CLOSES the block and its zones precede it,
    so the carry runs backward. Filling in one direction only would attach every
    zone in the early layout to the previous province -- and since those reports
    list Ituri first, the error would be invisible in the totals for the largest
    province and wrong for every other one.

    Some reports print both forms. The direction is therefore decided per block,
    not per report: each province row claims the run of zone rows on its own
    side, and a zone claimed from both sides keeps the nearer.
    """
    panel = panel.with_row_index("_ord")
    named = pl.col("zone_reported").str.replace(SUBTOTAL_PREFIX, "").str.strip_chars()
    is_sub = ((pl.col("level") == "province")
              & pl.col("zone_reported").str.contains(SUBTOTAL_PREFIX))
    is_prov = pl.col("level") == "province"

    # THE MERGED PROVINCE CELL DOES NOT SIT ON THE ROW THAT NAMES THE SUBTOTAL.
    # In the early layout the province is printed once, in its own column,
    # against a cell that spans the whole block -- so it lands on whichever row
    # that cell happens to centre on, which on sitrep 013 is `Mongbwalu`, four
    # rows above the `Sous total` it belongs to. Filling from the adjacent row
    # therefore finds nothing.
    #
    # The block is what the province labels, so the fill is over the block: rows
    # are grouped by how many subtotal rows precede them, and the one province
    # printed anywhere in a block names every row in it, its subtotal included.
    panel = panel.with_columns(
        (is_sub.cast(pl.Int32).cum_sum().over("sitrep")
         - is_sub.cast(pl.Int32)).alias("_blk"))
    panel = panel.with_columns(
        pl.col("province_printed").str.strip_chars().replace("", None)
          .max().over(["sitrep", "_blk"]).alias("_merged"))

    return (panel
            .with_columns(
                pl.when(is_prov & (named != "")).then(named)
                  .otherwise(None).alias("_prov"),
                is_sub.alias("_sub"))
            .with_columns(
                # A leading province row hands its name forward; a trailing
                # subtotal hands its name backward.
                pl.when(pl.col("_sub")).then(None).otherwise(pl.col("_prov"))
                  .fill_null(strategy="forward").over("sitrep").alias("_fwd"),
                pl.when(pl.col("_sub")).then(pl.col("_prov")).otherwise(None)
                  .fill_null(strategy="backward").over("sitrep").alias("_bwd"),
            )
            .with_columns(pl.coalesce("_prov", "_merged", "_bwd", "_fwd").alias("_raw"))
            .with_columns(pl.col("_raw")
                          .map_elements(canonical_province, return_dtype=pl.Utf8)
                          .alias("province"))
            .drop("_prov", "_sub", "_fwd", "_bwd", "_merged", "_blk"))


def apply_exceptions(check: pl.DataFrame, ex: pl.DataFrame) -> pl.DataFrame:
    """Mark a residual the page itself produces, and only that residual.

    A row is re-labelled `verified_exception` when an entry names its report,
    its province and its column AND the residual equals the entry's
    `expected_gap` exactly. A gap that has moved -- because our reading changed
    -- is NOT excused: it goes back to `fails`, which is the point of recording
    the number rather than the report.
    """
    if ex.is_empty():
        return check.with_columns(pl.lit(None, pl.Utf8).alias("exception_note"))

    wide = {}
    for e in ex.iter_rows(named=True):
        wide[(int(e["sitrep"]), e["unit"], e["column"])] = (
            int(e["expected_gap"]), e["note"])

    verdicts, notes = [], []
    for r in check.iter_rows(named=True):
        v, n = r["reconciled"], None
        if v == "fails":
            hit_c = wide.get((r["sitrep"], r["province"], "cum_cases"))
            hit_d = wide.get((r["sitrep"], r["province"], "cum_deaths"))
            rc, rd = r.get("residual_cases"), r.get("residual_deaths")
            ok_c = (rc in (0, None)) or (hit_c is not None and hit_c[0] == rc)
            ok_d = (rd in (0, None)) or (hit_d is not None and hit_d[0] == rd)
            if ok_c and ok_d and (hit_c or hit_d):
                v = "verified_exception"
                n = (hit_c or hit_d)[1]
        verdicts.append(v)
        notes.append(n)
    return check.with_columns(pl.Series("reconciled", verdicts),
                              pl.Series("exception_note", notes, dtype=pl.Utf8))


def aggregate(panel: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Sum the parts to province level, and compare against the printed row."""
    if "province" not in panel.columns:
        panel = carry_province(panel)

    unknown = panel.filter((pl.col("level") == "province")
                           & pl.col("province").is_null())
    if unknown.height:
        names = sorted(set(unknown["zone_reported"].to_list()))
        raise SystemExit(
            "province rows name places that are not in the closed province set:\n"
            + "\n".join(f"  {n!r}" for n in names)
            + "\n\nEither a province joined the outbreak, in which case add it to "
              "PROVINCE_ALIASES, or a row was misclassified as a province.")

    parts = panel.filter(pl.col("level").is_in(PARTS))
    present = [c for c in COUNTS if c in panel.columns]

    summed = (parts.group_by(["sitrep", "date", "province"])
              .agg([pl.col(c).sum().alias(c) for c in present]
                   + [pl.len().alias("n_parts"),
                      (pl.col("level") == "unassigned").sum().alias("n_unassigned")])
              .sort(["sitrep", "province"]))

    # The printed province row, keyed on the province it names. `Sous-total
    # Ituri` and `Ituri` are the same province stated two ways, so the prefix is
    # stripped before joining rather than being carried into the key.
    printed = (panel.filter(pl.col("level") == "province")
               .filter(pl.col("province").is_not_null())
               .group_by(["sitrep", "province"])
               .agg([pl.col(c).last().alias(f"{c}_printed") for c in present]))

    check = summed.join(printed, on=["sitrep", "province"], how="left")
    check = check.with_columns(
        (pl.col("cum_cases") - pl.col("cum_cases_printed")).alias("residual_cases"),
        (pl.col("cum_deaths") - pl.col("cum_deaths_printed")).alias("residual_deaths"),
    ).with_columns(
        pl.when(pl.col("cum_cases_printed").is_null())
        .then(pl.lit("not_checkable"))
        .when((pl.col("residual_cases") == 0)
              & (pl.col("residual_deaths").fill_null(0) == 0))
        .then(pl.lit("ok"))
        .otherwise(pl.lit("fails"))
        .alias("reconciled")
    )
    return summed, check


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", required=True, type=Path,
                    help="the health-zone extraction (zone_table.csv)")
    ap.add_argument("--out", required=True, type=Path,
                    help="province series; a _reconciliation.csv sibling is written beside it")
    ap.add_argument("--exceptions", type=Path,
                    default=Path("registers/reconciliation_exceptions.tsv"),
                    help="TSV of reports whose OWN arithmetic does not close, "
                         "verified by hand against the page and keyed on the "
                         "PDF's hash. An entry asserts a claim about the "
                         "document -- that its printed rows do not sum to its "
                         "printed total -- not a licence to silence the check.")
    ap.add_argument("--pdfs", type=Path, default=Path("data/raw/sitrep_pdfs"),
                    help="the archive, so each exception's hash can be verified")
    ap.add_argument("--allow-unchecked", type=int, default=None,
                    help="how many province-reports may lack a printed total to "
                         "compare against. Absent, any number is allowed and "
                         "reported; set it to hold a floor that must not slip.")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    ex = load_exceptions(args.exceptions,
                         args.pdfs if args.pdfs and args.pdfs.is_dir() else None)
    panel = pl.read_csv(args.panel, infer_schema_length=None)
    panel = carry_province(panel)
    summed, check = aggregate(panel)
    check = apply_exceptions(check, ex)

    summed.write_csv(args.out)
    check.write_csv(args.out.with_name(args.out.stem + "_reconciliation.csv"))

    # A part with no province is not aggregable and must not vanish into a
    # null group. It means the report printed zone rows with no province row and
    # no merged province label anywhere above or below them, so there is nothing
    # to attribute them to -- a gap in the source or in the reading of it, and
    # either way something to say out loud rather than to leave as a null key.
    orphan = panel.filter(pl.col("level").is_in(PARTS)
                          & pl.col("province").is_null()) \
        if "province" in panel.columns else pl.DataFrame()
    if orphan.height:
        reps = sorted(set(orphan["sitrep"].to_list()))
        print(f"\n{orphan.height} zone rows across {len(reps)} reports carry no "
              f"province and are aggregated under no province: "
              f"{', '.join(str(r) for r in reps)}", file=sys.stderr)

    tally = dict(check.group_by("reconciled").len().iter_rows())
    ok = tally.get("ok", 0)
    bad = tally.get("fails", 0)
    unchecked = tally.get("not_checkable", 0)
    excused = tally.get("verified_exception", 0)
    print(f"{check.height} province-reports: {ok} reconcile, "
          f"{excused} carry a verified exception, {bad} disagree, "
          f"{unchecked} have no printed total to check against")

    if bad:
        print("\nPROVINCE TOTALS THAT DO NOT MATCH THE SUM OF THEIR PARTS:",
              file=sys.stderr)
        cols = ["sitrep", "date", "province", "n_parts", "cum_cases",
                "cum_cases_printed", "residual_cases", "residual_deaths"]
        with pl.Config(tbl_rows=60):
            print(check.filter(pl.col("reconciled") == "fails")
                  .select([c for c in cols if c in check.columns])
                  .sort(["sitrep", "province"]), file=sys.stderr)
        sys.exit(2)

    if args.allow_unchecked is not None and unchecked > args.allow_unchecked:
        print(f"\n{unchecked} province-reports could not be checked, above the "
              f"declared limit of {args.allow_unchecked}.", file=sys.stderr)
        sys.exit(1)
    if unchecked:
        sys.exit(1)


if __name__ == "__main__":
    main()
