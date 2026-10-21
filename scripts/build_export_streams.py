"""Cases outside the DRC: per-destination cumulative streams, the per-case
reference table, and the gap between the two.

INPUTS, all hand-authored and committed (data/raw/exports/):
  sources.tsv  every document cited, primary or a check, with how its text can
               be verified;
  counts.tsv   every printed total, one row per source and as-of date;
  cases.tsv    every case the sources individuate.

OUTPUTS:
  data/build/streams/exports_<country>.tsv, one per destination country that
      counts at least one case in its OWN tally. A stock read at instants, like
      uganda_exports.tsv: one row per printed total, NA where that source did
      not print that number. No row is interpolated; a moment no source pins
      is not a row.
  data/build/series/export_cases.csv           the per-case table, validated;
  data/build/series/export_counts.csv          the printed totals, validated;
  data/build/series/export_reconciliation.csv  per printed total, how many
      individuated cases it is matched by, and the gap. `build_streams.py`
      publishes all three under streams/reference/.

WHAT IS AND IS NOT AN EXPORT HERE. `tally_country` decides which stream a case
belongs to, and it is the source's decision, not ours: WHO counts the three
medical evacuations in the DRC's tally ("will not be reported as a local case
of BVD in the Netherlands"), so Germany and the Netherlands get no stream and
those cases appear only in the reference table. Whether a case observes DRC
prevalence is a separate question with three answers kept in three columns --
the destination's `class`, the stated `infection_country`, and the exit
`mechanism` -- because the sources answer them separately: Nigeria's case is
imported into Nigeria by WHO's own headline while "investigations are ongoing
to establish the likely source of her infection".

GAPS ARE RECORDED, NEVER RESOLVED. A printed total larger than the cases
individuated by that date is a reconciliation row, not a build failure: Kenya's
eight confirmed cases on 18 October are matched by three individuated ones
because no primary source we could read describes the other five. What does
fail the build is the tables disagreeing with themselves -- an unknown source,
a duplicate case, a malformed date or count, a case whose class is not one of
the declared values.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

CLASSES = {"imported", "linked", "medically_evacuated", "unstated"}
CLASS_BASIS = {"stated", "inferred"}
INFECTION = {"DRC", "unstated", "under_investigation"}
MECHANISM = {"traveller", "medical_evacuation", "unstated"}
EXPOSURE = {"occupational", "contact", "unstated"}
STATUS = {"confirmed", "probable"}
QUOTE_CHECK = {"snapshot", "transcribed"}
KINDS = {"primary", "secondary"}
LAYERS = {"html", "pdf", "scanned"}
IMPORTED_BASIS = {"", "confirmed", "confirmed_and_probable"}
COUNT_FIELDS = ("confirmed", "probable", "deaths", "imported",
                "imported_from_drc", "linked", "under_investigation")
DATE_FIELDS = ("report_date", "confirmation_date", "onset_date",
               "arrival_date", "care_date", "outcome_date")

#: The stream's columns, in order. `time` is the as-of date the source states
#: its total for; a stock has no window, so there is no `days_covered`.
STREAM_COLUMNS = ("time", "cum_confirmed", "cum_imported", "imported_basis",
                  "cum_imported_from_drc", "cum_linked",
                  "cum_under_investigation", "source_id", "published")


def read_tsv(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader((ln for ln in fh if not ln.startswith("#")),
                                   delimiter="\t"))


def slug(country: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", country.lower()).strip("_")


def _date(value: str, where: str) -> None:
    if value:
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            sys.exit(f"{where}: `{value}` is not an ISO date")


def _enum(value: str, allowed: set[str], where: str) -> None:
    if value not in allowed:
        sys.exit(f"{where}: `{value}` is not one of {sorted(allowed)}")


def validate(sources: list[dict], counts: list[dict], cases: list[dict]) -> dict:
    by_id = {}
    for s in sources:
        if s["source_id"] in by_id:
            sys.exit(f"sources.tsv: duplicate source_id {s['source_id']}")
        _enum(s["kind"], KINDS, f"sources.tsv {s['source_id']} kind")
        _enum(s["text_layer"], LAYERS, f"sources.tsv {s['source_id']} text_layer")
        _date(s["published"], f"sources.tsv {s['source_id']} published")
        by_id[s["source_id"]] = s

    for i, c in enumerate(counts, start=1):
        where = f"counts.tsv row {i} ({c['country']} {c['as_of']})"
        if c["source_id"] not in by_id:
            sys.exit(f"{where}: unknown source {c['source_id']}")
        if by_id[c["source_id"]]["kind"] != "primary":
            sys.exit(f"{where}: {c['source_id']} is a check, not a primary "
                     "source; a printed total is taken only from a primary one")
        _date(c["as_of"], where)
        _enum(c["quote_check"], QUOTE_CHECK, f"{where} quote_check")
        _enum(c["imported_basis"], IMPORTED_BASIS, f"{where} imported_basis")
        if bool(c["imported"]) != bool(c["imported_basis"]):
            sys.exit(f"{where}: an imported count needs its basis, and a basis "
                     "needs a count")
        for f in COUNT_FIELDS:
            if c[f] and not c[f].isdigit():
                sys.exit(f"{where}: {f} `{c[f]}` is not a non-negative integer")
        if not c["quote"]:
            sys.exit(f"{where}: every printed total carries the sentence it "
                     "was read from")

    seen = set()
    for c in cases:
        where = f"cases.tsv {c['case_id']}"
        if c["case_id"] in seen:
            sys.exit(f"{where}: duplicate case_id")
        seen.add(c["case_id"])
        _enum(c["status"], STATUS, f"{where} status")
        _enum(c["class"], CLASSES, f"{where} class")
        _enum(c["class_basis"], CLASS_BASIS, f"{where} class_basis")
        _enum(c["infection_country"], INFECTION, f"{where} infection_country")
        _enum(c["mechanism"], MECHANISM, f"{where} mechanism")
        _enum(c["exposure"], EXPOSURE, f"{where} exposure")
        _enum(c["quote_check"], QUOTE_CHECK, f"{where} quote_check")
        for f in DATE_FIELDS:
            _date(c[f], f"{where} {f}")
        for sid in [c["quote_source"], *c["sources"].split(";")]:
            if sid not in by_id:
                sys.exit(f"{where}: unknown source {sid}")
        if c["quote_source"] not in c["sources"].split(";"):
            sys.exit(f"{where}: quote_source {c['quote_source']} is not among "
                     "its sources")
        if c["class"] == "medically_evacuated" and c["mechanism"] != "medical_evacuation":
            sys.exit(f"{where}: class and mechanism disagree")
    return by_id


def known_by(case: dict) -> str | None:
    """The date a tally can first include the case: when it was REPORTED.

    Confirmation can precede the report by a day (UG-02 is confirmed on 15 May
    by SR01 and reported on 16 May by DON602), and a total published on the
    confirmation day does not yet hold it. The confirmation date stands in only
    where no report date is printed.
    """
    return case["report_date"] or case["confirmation_date"] or None


def reconcile(counts: list[dict], cases: list[dict]) -> list[dict]:
    """One row per printed total: how many individuated cases match it.

    Matched means: counted in that country's tally, of the right status, and
    known by the as-of date. A case with no date cannot be placed, so it is
    counted separately rather than assumed to fall either side.
    """
    out = []
    for c in counts:
        tallied = [k for k in cases if k["tally_country"] == c["country"]]
        for status, field in (("confirmed", "confirmed"),
                              ("probable", "probable")):
            if not c[field]:
                continue
            mine = [k for k in tallied if k["status"] == status]
            dated = [k for k in mine if known_by(k) and known_by(k) <= c["as_of"]]
            undated = [k for k in mine if not known_by(k)]
            printed = int(c[field])
            out.append({
                "country": c["country"], "as_of": c["as_of"],
                "source_id": c["source_id"], "quantity": status,
                "printed": printed, "individuated_by_date": len(dated),
                "individuated_undated": len(undated),
                "gap": printed - len(dated),
                "case_ids": ";".join(k["case_id"] for k in dated)})
        if c["imported"] and c["imported_basis"] == "confirmed":
            imp = [k for k in tallied if k["status"] == "confirmed"
                   and k["class"] == "imported"
                   and known_by(k) and known_by(k) <= c["as_of"]]
            out.append({
                "country": c["country"], "as_of": c["as_of"],
                "source_id": c["source_id"], "quantity": "imported",
                "printed": int(c["imported"]), "individuated_by_date": len(imp),
                "individuated_undated": 0,
                "gap": int(c["imported"]) - len(imp),
                "case_ids": ";".join(k["case_id"] for k in imp)})
    return out


def write_csv(path: Path, rows: list[dict], columns) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exports", type=Path, required=True,
                    help="data/raw/exports, holding sources/counts/cases.tsv")
    ap.add_argument("--series-dir", type=Path, required=True)
    ap.add_argument("--streams-dir", type=Path, required=True)
    args = ap.parse_args()

    sources = read_tsv(args.exports / "sources.tsv")
    counts = read_tsv(args.exports / "counts.tsv")
    cases = read_tsv(args.exports / "cases.tsv")
    by_id = validate(sources, counts, cases)

    counts.sort(key=lambda c: (c["country"], c["as_of"], c["source_id"]))
    cases.sort(key=lambda c: (c["country"], c["case_id"]))
    write_csv(args.series_dir / "export_counts.csv", counts, counts[0].keys())
    write_csv(args.series_dir / "export_cases.csv", cases, cases[0].keys())
    recon = reconcile(counts, cases)
    write_csv(args.series_dir / "export_reconciliation.csv", recon,
              recon[0].keys())

    # A stream per country that tallies at least one case as its own.
    destinations = sorted({k["tally_country"] for k in cases} - {"DRC"})
    for stale in args.streams_dir.glob("exports_*.tsv"):
        stale.unlink()   # a destination that no longer qualifies leaves no file
    for country in destinations:
        rows = [{
            "time": c["as_of"],
            "cum_confirmed": c["confirmed"] or "NA",
            "cum_imported": c["imported"] or "NA",
            "imported_basis": c["imported_basis"] or "NA",
            "cum_imported_from_drc": c["imported_from_drc"] or "NA",
            "cum_linked": c["linked"] or "NA",
            "cum_under_investigation": c["under_investigation"] or "NA",
            "source_id": c["source_id"],
            "published": by_id[c["source_id"]]["published"] or "NA",
        } for c in counts if c["country"] == country]
        if not rows:
            sys.exit(f"{country} tallies a case in cases.tsv but counts.tsv "
                     "prints no total for it; a stream with no rows would "
                     "assert the country was never counted")
        path = args.streams_dir / f"exports_{slug(country)}.tsv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(STREAM_COLUMNS),
                               delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"  {path.name:28s} {len(rows):>3d} rows  {rows[0]['time']} -> {rows[-1]['time']}")

    gaps = [r for r in recon if r["gap"] != 0]
    print(f"  {len(cases)} individuated cases, {len(counts)} printed totals; "
          f"{len(gaps)} printed total(s) not matched by individuated cases "
          "(recorded in export_reconciliation.csv, not resolved)")
    for r in gaps:
        print(f"    {r['country']:8s} {r['as_of']} {r['quantity']:10s} "
              f"printed {r['printed']:>3d}, individuated {r['individuated_by_date']:>3d}"
              f"{' + %d undated' % r['individuated_undated'] if r['individuated_undated'] else ''}"
              f"  ({r['source_id']})")


if __name__ == "__main__":
    main()
