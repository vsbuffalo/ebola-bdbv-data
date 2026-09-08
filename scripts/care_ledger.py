"""How long a confirmed patient stays in care, and how that stay ends.

WHICH SOURCE: our own `patients_isolated_confirmed`, `cumul_recovered` and
`community_deaths_daily_national` streams (primary).

WHAT IT PRODUCES: two constraints the national fit needs and the epidemic
growth rate cannot supply -- the care exit rate (delta) and the fatality among
those who reach care (f_cfr).

WHY THE OBVIOUS LEDGER IS WRONG. Total confirmed deaths are NOT exits from
care. A community death is confirmed by post-mortem swab on someone who was
never isolated, so it never entered the census and cannot leave it. Charging
all deaths against the census inflates both quantities badly -- on this window
it gives delta = 0.227/day (a 4.4-day stay) and f_cfr = 0.718, against 0.112
(8.9 days) and 0.456 once community deaths are held out. Only

    exits from care = treatment-centre deaths + recoveries

belongs in the numerator, and treatment-centre deaths are the classified split
minus the community column, not the death total.

IS IT FITTED: no. It is a ratio of published stocks and flows over the window
where all three series exist.

WHAT VALIDATES IT: the modelling repository's confirmed-only census fit puts
the facility stay at 8.8 d; this ledger gives 8.9 d from the published series
alone, which is an independent route to the same number. For f_cfr, Kratz et
al. (PLOS ONE 2015) report 50.0% (9/18) in the Isiro treatment centre, the
only other Bundibugyo outbreak.

A KNOWN BIAS, AND THE SOURCE DOES COUNT WHAT WOULD FIX IT. Patients who
abscond leave care without recovering or dying, so they are missing from
`exits`: this delta is a LOWER bound on the true exit rate (the stay an UPPER
bound), and this f_cfr is an UPPER bound on the fatality among those who reach
care.

These bounds are not permanent. The care/occupancy table (TABLEAU 6) prints
`Sorties — évadés` as a daily per-province count on 54 of the 87 reports --
355 absconders in total, median 5 per report, max 41 -- alongside
`Total sorties (24 h)`, which measures the exit rate directly rather than by
differencing stocks. We do not yet extract that table, which is why this
script differences stocks at all. Once `extract_care_table.py` exists, both
quantities become point estimates and this docstring should shrink.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from lib import streams as streams_lib


def ledger(streams: Path) -> dict:
    rec = streams_lib.read(streams / "cumul_recovered.tsv", dates=True)
    cen = streams_lib.read(
        streams / "patients_isolated_confirmed.tsv", dates=True)
    # `null_values="NA"`, and then only the scored rows: the daily flow files
    # carry a row on every report day they span and hole the ones the source
    # said nothing on. Without the token the counts read back as strings and
    # the subtraction below fails; without the filter the holes would enter a
    # sum as nulls and quietly void it.
    dth = streams_lib.read(
        streams / "community_deaths_daily_national.tsv", dates=True
    ).filter(pl.col("n_report_days") > 0)

    lo = max(rec["time"].min(), cen["time"].min(), dth["time"].min())
    hi = min(rec["time"].max(), cen["time"].max(), dth["time"].max())
    span = (hi - lo).days

    r = rec.filter(pl.col("time").is_between(lo, hi)).sort("time")
    c = cen.filter(pl.col("time").is_between(lo, hi)).sort("time")
    d = dth.filter(pl.col("time").is_between(lo, hi)).sort("time")

    etc = int((d["deaths_split_national"] - d["community_deaths_national"]).sum())
    community = int(d["community_deaths_national"].sum())
    recovered = int(r["cumul_recovered"].max() - r["cumul_recovered"].min())
    census = float(c["patients_isolated_confirmed"].mean())
    exits = etc + recovered

    return {
        "from": lo, "to": hi, "span_days": span, "report_days": d.height,
        "etc_deaths": etc, "community_deaths": community, "recovered": recovered,
        "exits": exits, "mean_census": census, "census_readings": c.height,
        "delta": exits / (census * span),
        "mean_stay_days": census * span / exits,
        "f_cfr": etc / exits,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--streams", type=Path, default=Path("data/build/streams"))
    args = ap.parse_args()
    L = ledger(args.streams)

    print("Care ledger: how a confirmed patient's stay ends")
    print("=" * 66)
    print(f"window {L['from']} to {L['to']}  ({L['span_days']} days, "
          f"{L['report_days']} report-days, {L['census_readings']} census readings)")
    print()
    print(f"  treatment-centre deaths          {L['etc_deaths']:>6}")
    print(f"  recoveries gained                {L['recovered']:>6}")
    print(f"  EXITS FROM CARE                  {L['exits']:>6}")
    print(f"  community deaths (never in care) {L['community_deaths']:>6}   held out")
    print(f"  mean confirmed census            {L['mean_census']:>9.1f}")
    print()
    print(f"  delta = {L['delta']:.4f} /day   -> mean stay {L['mean_stay_days']:.1f} d"
          "   (delta a LOWER bound: absconders uncounted)")
    print(f"  f_cfr = {L['f_cfr']:.4f}        (an UPPER bound, same reason)")


if __name__ == "__main__":
    main()
