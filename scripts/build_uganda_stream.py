"""Cumulative Uganda importations, as an observation stream.

Derived from `data/raw/uganda_cases.toml`, which is a hand transcription of the
WHO Disease Outbreak News with a `source` string on every field. Small, but this
is the ONLY stream that scales with TRUE rather than confirmed prevalence: the
DRC series constrains how many cases were *found*, and exported cases detected in
Uganda constrain how many infections there *were*. Everything the model says
about outbreak size rests on it.

It previously existed as a two-row file with no rule behind it. That is exactly
the class of artefact this pipeline refuses to carry, hence this script.

WHY CUMULATIVE COUNTS AT TWO MOMENTS, NOT A DATED SERIES
--------------------------------------------------------
Uganda recorded 15 importations. Only THREE importation dates are published; the
remaining twelve appear in the bulletins as a total. Fitting the three known
dates as a daily series would assert zero importations on every day we have no
information about. A cumulative count at a known moment asserts nothing about
the undated ones while still carrying the timing.

WHY THE SERIES STOPS
--------------------
Uganda's last case was identified 21 June and the outbreak was declared over on
28 July after the 42-day countdown, so the absence of later cases is real rather
than a lapse in surveillance. But over the same period Ituri's prevalence roughly
tripled, and a model fitted without any Uganda data puts most of its export flow
AFTER 21 June. Exports stopped while the source epidemic accelerated.

The likeliest reason is border screening and travel measures following the May
Disease Outbreak News and the WHO ministerial briefing of 25 May. Scoring the
full window would force the model to suppress late Ituri transmission to explain
the missing late exports -- attributing a border-control effect to transmission.
So scoring stops at `--last-scored-day`.

The honest caveat, carried here because it belongs with the data: that cut-off is
set by the last observed export, not by a known policy date. Measures plausibly
began in late May, inside the window being treated as unrestricted, so the fitted
export rate is a LOWER bound on the true unrestricted rate and the prevalence it
implies is a lower bound on true prevalence.

NO `days_covered` / `n_report_days` HERE, DELIBERATELY. Every other stream
file carries the span of the window its count accumulates over; these rows
are CUMULATIVE importation counts read at two bulletin moments -- a stock,
not an interval count -- so a span column would assert a window that does
not exist. The absence is the signal that this file follows a different
convention from the incidence streams beside it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import tomllib
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uganda", required=True, type=Path)
    ap.add_argument("--last-scored-date", default=None,
                    help="stop scoring after this date; defaults to the last "
                         "moment a bulletin pins. See the module docstring for "
                         "why the series stops and what that costs.")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    d = tomllib.load(args.uganda.open("rb"))
    pinned = [(dt.date.fromisoformat(x), int(n))
              for x, n in d["cumulative_detected"]["value"]]

    # EMITTED AT THE MOMENTS THE BULLETINS PIN, NOT ON A GRID.
    #
    # This used to snap each pinned moment onto a 14-day lattice anchored at a
    # `--day0` default, to match the model's `emit_schedule`. Two things were
    # wrong with that. The lattice is not consulted when fitting -- the camdl
    # language spec is explicit that "when fitting with `--data`, the data
    # file's time column supplies the observation times and the declared
    # `emit_schedule` is not consulted; the schedule is used only for forward
    # synthetic-data generation under `simulate`". And the anchor was a default
    # in this file, so when the model's origin moved from 14 May to 19 May the
    # lattice did not, leaving the second observation four days after the date
    # its own source pins it. Four extra days of modelled export accumulation
    # were charged against the same count of 15, biasing the export rate low --
    # on the one stream that constrains true rather than confirmed prevalence.
    #
    # Nothing is emitted BETWEEN the pinned moments. Between 2 and 21 June the
    # total rose from 4 to 15 and no bulletin says by how much; emitting an
    # interpolated point would assert information we do not have, which is the
    # same error as fitting the three dated importations as a daily series.
    last = (dt.date.fromisoformat(args.last_scored_date)
            if args.last_scored_date else max(d for d, _ in pinned))
    rows = [(when, n) for when, n in sorted(pinned) if when <= last]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        fh.write("time\tuganda_exports\n")   # ISO dates: the model is anchored
        for when, n in rows:
            fh.write(f"{when}\t{n}\n")

    print(f"{len(rows)} scored points -> {args.out}")
    for when, n in rows:
        print(f"  {when}: {n} cumulative importations")
    print(f"  source: {args.uganda}; pinned moments "
          + ", ".join(f"{d} -> {n}" for d, n in pinned))
    skipped = [str(d) for d, _ in pinned if d > last]
    if skipped:
        print(f"  emission points NOT scored (cumulative not pinned there): {skipped}")


if __name__ == "__main__":
    main()
