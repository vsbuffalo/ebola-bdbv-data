"""ONE-OFF: when does INSP upload a situation report, and how long does our
daily run take to notice?

DISPOSABLE BY DESIGN. A question figure, not a pipeline artefact: delete this
file and `make oneoff-upload-timing` together once the schedule question is
settled.

THE QUESTION. The daily release runs at 14:00 and 22:00 Pacific. Whether to
run it more often depends on how INSP's uploads are spread: if each report
arrives on a steady daily rhythm, two runs a day lose little; if uploads come
in bursts after silences, at any hour, the wait between an upload and our
release is set by our schedule, not by INSP's.

THE SOURCE. INSP's WordPress media endpoint (the one `fetch_sitrep_index.py`
reads) records each PDF's upload time to the second; the committed index keeps
only the date. `--fetch` downloads those times (NETWORKED) to a disposable
JSON under data/build/oneoff/; drawing reads that file and the committed
index, offline. The site's `date` equals its `date_gmt`, so the times are UTC.
A report uploaded as a draft and then a final counts from its first upload,
because the daily run would act on either.

WHAT IS PLOTTED.
  A  days from the end of each report's data day to its first upload;
  B  hours between consecutive new reports' uploads (a burst is a short gap
     after a long one);
  C  the hour of day of uploads, in Kinshasa time (UTC+1), against our runs;
  D  the wait from upload to our next run, under the current schedule and two
     denser ones, replayed over the same uploads.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_sitrep_index import UA  # noqa: E402  the header INSP's server requires

ROOT = Path(__file__).resolve().parents[1]
API = ("https://insp.cd/wp-json/wp/v2/media?after=2026-05-01T00:00:00"
       "&per_page=100&orderby=date&order=asc&_fields=date_gmt,source_url&page={}")

#: The daily run's launchd times, 14:00 and 22:00 Pacific, in UTC. Pacific is
#: UTC-7 through 1 November 2026 and UTC-8 after; every upload here is before.
CURRENT_UTC_HOURS = (21, 5)
SCHEDULES = {"twice a day (current)": CURRENT_UTC_HOURS,
             "every 6 hours": (3, 9, 15, 21),
             "hourly": tuple(range(24))}
COLORS = ("#2a6fdb", "#e07b39", "#7a7a7a")
KINSHASA = timedelta(hours=1)


def fetch(out: Path) -> None:
    """Every media item since May, all pages (the endpoint caps a page at 100
    and returns an error past the last)."""
    items, page = [], 1
    while True:
        try:
            req = urllib.request.Request(API.format(page), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                batch = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 400:
                break
            raise
        items += batch
        page += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, indent=0))
    print(f"{len(items)} media items -> {out}")


def first_uploads(media: Path) -> pl.DataFrame:
    """One row per report: its data date and its first upload (UTC)."""
    m = pl.DataFrame(json.loads(media.read_text())).select("source_url", "date_gmt")
    idx = pl.read_csv(ROOT / "data/raw/insp_sitrep_index.tsv", separator="\t",
                      infer_schema_length=0)
    j = idx.join(m, left_on="url", right_on="source_url", how="inner")
    missing = idx.height - j.height
    if missing:
        raise SystemExit(f"{missing} index rows have no upload time")
    return (j.with_columns(pl.col("sitrep").cast(pl.Int32, strict=False),
                           pl.col("data_date").str.to_date(),
                           pl.col("date_gmt").str.to_datetime())
            .filter(pl.col("sitrep").is_not_null())
            .group_by("sitrep")
            .agg(pl.col("data_date").first(), pl.col("date_gmt").min().alias("up"))
            .sort("up"))


def next_run(t: datetime, hours: tuple[int, ...]) -> datetime:
    day = t.replace(minute=0, second=0, microsecond=0, hour=0)
    for d in range(3):
        for h in sorted(hours):
            c = day + timedelta(days=d, hours=h)
            if c >= t:
                return c
    raise AssertionError("no run within three days")


def draw(df: pl.DataFrame, out: Path) -> None:
    up = df["up"].to_list()
    lag = [(u - (datetime.combine(d, datetime.min.time()) + timedelta(days=1)))
           .total_seconds() / 86400 for u, d in zip(up, df["data_date"])]
    gaps = np.diff([u.timestamp() for u in up]) / 3600
    hours = [((u + KINSHASA).hour + (u + KINSHASA).minute / 60) for u in up]

    fig, ax = plt.subplots(2, 2, figsize=(13, 8.5))
    fig.suptitle(f"INSP situation-report uploads, sitreps {df['sitrep'].min()}–"
                 f"{df['sitrep'].max()} ({df.height} reports)", fontsize=13)

    a = ax[0, 0]
    a.scatter(up, lag, s=14, color=COLORS[0])
    a.axhline(np.median(lag), color="#444", lw=1, ls="--")
    a.text(up[0], np.median(lag) + 0.08, f"median {np.median(lag):.1f} days",
           fontsize=9, color="#444")
    a.set_ylabel("days after the data day ended")
    a.set_title("A. Upload lag per report", loc="left")
    a.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    a.set_ylim(0, None)

    b = ax[0, 1]
    b.scatter(up[1:], gaps, s=14, color=COLORS[0])
    b.axhline(24, color="#444", lw=1, ls="--")
    b.text(up[1], 26, "one day", fontsize=9, color="#444")
    b.set_yticks(range(0, int(gaps.max()) + 13, 12))
    b.set_ylim(0, None)
    b.set_ylabel("hours since the previous report's upload")
    b.set_title(f"B. Spacing: {int((gaps < 1).sum())} of {len(gaps)} within an "
                f"hour of the last; {int((gaps > 36).sum())} after 36+ h",
                loc="left")
    b.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    c = ax[1, 0]
    c.hist(hours, bins=np.arange(0, 25, 1), color=COLORS[0], edgecolor="white")
    for h in CURRENT_UTC_HOURS:
        c.axvline((h + 1) % 24, color=COLORS[1], lw=2)
    c.text(((CURRENT_UTC_HOURS[1] + 1) % 24) + 0.3, c.get_ylim()[1] * 0.95,
           "our runs (06:00, 22:00)", color=COLORS[1], fontsize=9)
    c.set_xticks(range(0, 25, 3))
    c.set_xlabel("hour of upload, Kinshasa time (UTC+1)")
    c.set_ylabel("reports")
    c.set_title("C. Time of day", loc="left")

    d = ax[1, 1]
    for (name, hrs), col in zip(SCHEDULES.items(), COLORS):
        w = np.sort([(next_run(u, hrs) - u).total_seconds() / 3600 for u in up])
        d.step(w, np.arange(1, len(w) + 1) / len(w), where="post", color=col,
               lw=2, label=f"{name}: median {np.median(w):.1f} h, "
                           f"max {w.max():.1f} h")
    d.set_xlabel("hours from upload to our next run")
    d.set_ylabel("share of reports")
    d.set_title("D. Wait for our run, replayed over these uploads", loc="left")
    d.legend(frameon=False, fontsize=9, loc="lower right")
    d.set_xlim(0, None)

    for a_ in ax.flat:
        a_.spines[["top", "right"]].set_visible(False)
        a_.grid(alpha=0.25, lw=0.5)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"-> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--media", type=Path,
                    default=ROOT / "data/build/oneoff/insp_media_times.json")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data/build/figures/oneoff_upload_timing.png")
    args = ap.parse_args()
    if args.fetch:
        fetch(args.media)
    else:
        draw(first_uploads(args.media), args.out)


if __name__ == "__main__":
    main()
