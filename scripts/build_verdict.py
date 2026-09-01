"""One screen at the end of a build saying whether it is safe to release.

Why this exists. `make build` prints everything it learns, which is the right
default for a pipeline whose whole point is that nothing is silently dropped —
but it means a person reading the tail of a run cannot tell a source defect we
expect from a reader failure we do not. Both look like a line of text. This
reads the status files the build already writes and sorts what it finds into
three kinds, which are genuinely different and were previously indistinguishable:

  BLOCKING   the release must not be cut. A published stream disagrees with the
             source's own arithmetic, or a gate the build owns has failed.
  SOURCE     the reports contradict themselves. Not ours to fix, expected, and
             recorded — a page whose rows do not sum to its own total, a
             letality column that is last week's. These are findings about the
             documents and they do not stop a release.
  READER     a wording this extraction has not seen, refused rather than
             guessed. Costs coverage, never correctness. Worth watching because
             a jump means the source changed its phrasing.

Nothing here computes anything. Every number is read back off a file the build
wrote, so this cannot disagree with the build; if it seems to, the status file
is the truth and this is the bug.

Colour is used only to separate the three kinds, and only when stdout is a
terminal — piping this into a file or a log gets plain text, because a build
log full of escape sequences is worse than one without colour.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
SERIES = ROOT / "data/build/series"
STREAMS = ROOT / "data/build/streams"


def _colour() -> bool:
    """Colour only for a human at a terminal. `NO_COLOR` is honoured because it
    is the convention every other tool on the machine honours."""
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


class Paint:
    def __init__(self, on: bool) -> None:
        self.on = on

    def __call__(self, s: str, code: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def red(self, s): return self(s, "1;31")
    def green(self, s): return self(s, "1;32")
    def yellow(self, s): return self(s, "33")
    def blue(self, s): return self(s, "36")
    def dim(self, s): return self(s, "2")


def _read(name: str) -> pl.DataFrame | None:
    p = SERIES / name
    if not p.exists():
        return None
    return pl.read_csv(p, infer_schema_length=20000)


def collect() -> tuple[list[str], list[str], list[str], dict[str, str]]:
    """`(blocking, source, reader, facts)` — every entry a sentence."""
    blocking: list[str] = []
    source: list[str] = []
    reader: list[str] = []
    facts: dict[str, str] = {}

    # Is this build even current? Nothing in the Makefile makes `figures`
    # depend on `streams`, or `streams` on `build` -- they are phony targets a
    # person runs in order. That works until it doesn't, and the failure is
    # silent: `make figures` over a stale data/build draws yesterday's numbers
    # with today's date on the file. Checked on CONTENT, not timestamps, which
    # lie after a checkout: the series must have read every report the manifest
    # pins, and the streams must reach the same day the series do.
    man = ROOT / "data/raw/sitrep_pdfs.manifest.tsv"
    zs = _read("zone_table_status.csv")
    if man.exists() and zs is not None:
        listed = sum(1 for i, l in enumerate(man.open()) if i and l.strip())
        if zs.height != listed:
            blocking.append(
                f"the series were built from {zs.height} report(s) but the "
                f"manifest pins {listed} — run `make build`")
    zt_all = _read("zone_table.csv")
    nat = STREAMS / "cases_daily_national.tsv"
    if zt_all is not None and nat.exists():
        newest_series = zt_all["date"].max()
        newest_stream = pl.read_csv(nat, separator="\t",
                                    null_values="NA")["time"].max()
        if newest_stream != newest_series:
            blocking.append(
                f"the streams end {newest_stream} but the series reach "
                f"{newest_series} — run `make streams`")

    # Places the source reports and this build does not publish. The build
    # itself stops on this, so it should never fire here -- it is stated
    # because a reader of the verdict should be able to see that the check ran
    # and found nothing, rather than infer it from silence.
    ps = _read("province_series.csv")
    if ps is not None and "province" in ps.columns:
        rep = {p for p, n in ps.drop_nulls("province").group_by("province")
               .agg(pl.col("cum_cases").max()).iter_rows() if n and n > 0}
        pub = {f.stem.replace("cases_daily_", "")
               for f in STREAMS.glob("cases_daily_*.tsv")}
        facts["provinces reported / published"] = f"{len(rep)} / {len(pub) - 1}"

    zt = _read("zone_table_status.csv")
    if zt is not None:
        facts["reports read"] = str(zt.height)
        bad = zt.filter(pl.col("identity") != "ok") if "identity" in zt.columns else None
        if bad is not None and bad.height:
            n = bad.filter(pl.col("identity") == "fails").height
            if n:
                source.append(f"{n} report(s) whose health-zone rows do not sum "
                              "to the province total the same page prints")
        none = zt.filter(pl.col("status") == "no_matching_table").height
        if none:
            reader.append(f"{none} report(s) print no health-zone table this "
                          "reader recognises")

    lt = _read("zone_table_letality.csv")
    if lt is not None and "verdict" in lt.columns:
        n = lt.filter(pl.col("verdict") == "inconsistent").height
        carried = lt.filter(pl.col("verdict") == "carried_forward").height
        if n:
            source.append(f"{n} printed case-fatality value(s) disagree with "
                          "the two counts on their own row")
        if carried:
            source.append(f"{carried} case-fatality value(s) are the previous "
                          "report's figure left standing")

    rec = SERIES / "province_series_reconciliation.csv"
    if rec.exists():
        r = pl.read_csv(rec, infer_schema_length=20000)
        if "status" in r.columns:
            dis = r.filter(pl.col("status") == "disagrees").height
            facts["province reconciliations"] = str(r.height)
            if dis:
                blocking.append(f"{dis} province total(s) disagree with the sum "
                                "of their parts and carry no verified exception")

    for name, what in (("lab_prose_status.csv", "laboratory sentence"),
                       ("care_prose_status.csv", "care passage"),
                       ("daily_notified_status.csv", "banner tile"),
                       ("burial_alerts_status.csv", "safe-burial sentence")):
        st = _read(name)
        if st is None:
            continue
        col = next((c for c in st.columns if c.startswith("n_refused")), None)
        if col:
            n = int(st[col].sum())
            if n:
                reader.append(f"{n} {what}(s) refused — a wording the licence "
                              "has not seen, never a guessed number")

    meta = STREAMS / "meta.json"
    if meta.exists():
        import json
        m = json.loads(meta.read_text())
        # The newest report the build read, taken off a published stream
        # rather than from a meta field, because meta carries `day0` and the
        # window length and it is the LAST date a reader wants here.
        nat = STREAMS / "cases_daily_national.tsv"
        if nat.exists():
            facts["data date"] = pl.read_csv(
                nat, separator="\t", null_values="NA")["time"].max()
        rc = m.get("reconciliation", {})
        off = [k for k, v in rc.items()
               if isinstance(v, dict) and v.get("difference") not in (None, 0)]
        if off:
            blocking.append(f"{len(off)} stream(s) do not sum to the movement "
                            f"of the source's cumulative: {', '.join(sorted(off)[:4])}")
        facts["streams published"] = str(len(list(STREAMS.glob("*.tsv"))))

    return blocking, source, reader, facts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--gate", action="store_true",
                    help="print nothing unless the build is stale or a gate "
                         "failed, and exit 1 if so. For use as a guard in front "
                         "of a target that reads the build, where the full "
                         "screen would be noise on every run.")
    args = ap.parse_args()
    c = Paint(_colour() and not args.no_color)

    blocking, source, reader, facts = collect()
    if args.gate:
        if not blocking:
            return 0
        print()
        for i in blocking:
            print("  " + c.red("STALE OR BROKEN") + f"  {i}")
        print()
        return 1
    w = 74
    print()
    print(c.dim("─" * w))
    if blocking:
        print(c.red("  NO-GO") + "   this build must not be released")
    else:
        print(c.green("  GO") + "      every gate this build owns has passed")
    print(c.dim("─" * w))

    if facts:
        print("  " + c.dim(" · ".join(f"{k} {v}" for k, v in facts.items())))
        print()

    def block(title: str, items: list[str], paint, note: str) -> None:
        if not items:
            return
        print(f"  {paint(title)}  {c.dim(note)}")
        for i in items:
            print(f"    • {i}")
        print()

    block("BLOCKING", blocking, c.red, "fix before releasing")
    block("SOURCE", source, c.yellow,
          "the reports contradict themselves — recorded, not ours to fix")
    block("READER", reader, c.blue,
          "coverage we do not have; correctness is unaffected")

    if not (blocking or source or reader):
        print("  " + c.dim("nothing to report"))
        print()
    print(c.dim("  detail: data/build/series/*_status.csv, "
                "data/build/streams/meta.json"))
    print()
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
