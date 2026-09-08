"""Reading a published stream file, in one place.

A stream states its position in time in one of two forms, and which one it
uses is a property of the quantity rather than of the file's name. A FLOW
carries `window_start` and `window_stop`, the half-open interval
`[window_start, window_stop)` its count accumulated over. A STOCK carries
`time`, the instant it was read at, because a reading accumulates over nothing.
No file carries both, so there is never a question of which column is
authoritative.

WHY THIS MODULE EXISTS RATHER THAN A `read_csv` AT EACH SITE. Two traps sit
between a reader and these files, and both are silent:

  * `NA` is the null token on every published stream, and polars does not
    treat it as one by default. One hole turns an integer column into a string
    column, and a plotting library draws those strings at the axis baseline --
    a missing observation rendered as an observed zero.
  * `window_stop` is EXCLUSIVE, so it is one day after the day the source
    spoke. A report whose figures are stated for 13 July closes a window at
    14 July. Anything that dates an observation -- an axis, a join against the
    report calendar, a comparison against a data date -- wants that report day,
    not the edge. Using the edge shifts every point one day later than the
    report it came from, which is the same class of error as labelling a
    weekly bin with its nominal end: nothing fails, every series just slides.

`observation_day` is the recovered report day, and it is exactly the value the
`time` column held before these files stated their windows -- so a consumer
written against the old form keeps its numbers by reading through here.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

NULL_TOKEN = "NA"

#: The two columns a flow file states its window in.
WINDOW_COLUMNS = ("window_start", "window_stop")


def observation_day() -> pl.Expr:
    """The day a row observes: `window_stop` minus one on a flow, `time` on a
    stock. A date expression, so a caller that wants a string can format it."""
    if_flow = pl.col("window_stop").str.to_date("%Y-%m-%d") - pl.duration(days=1)
    return if_flow


def read(path: Path | str, *, dates: bool = False) -> pl.DataFrame:
    """A published stream with `time` restored as the day each row observes.

    The window columns are left in place: they are what the file states and a
    caller reasoning about accumulation intervals should read them. `time` is
    added back because most callers here are asking what the source said on a
    given report day, which is the question the pages and every register are
    keyed on.

    `dates=True` returns `time` as a date rather than a `YYYY-MM-DD` string,
    which is what `try_parse_dates=True` used to give these call sites.
    """
    d = pl.read_csv(Path(path), separator="\t", infer_schema_length=None,
                    null_values=NULL_TOKEN)
    day = (observation_day() if "window_stop" in d.columns
           else pl.col("time").str.to_date("%Y-%m-%d"))
    return d.with_columns(
        day.alias("time") if dates
        else day.dt.to_string("%Y-%m-%d").alias("time"))
