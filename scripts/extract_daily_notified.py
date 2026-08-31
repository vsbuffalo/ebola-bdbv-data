"""The day's own notification count, read from the front-page banner tiles.

SOURCE       The INSP situation reports' page-1 banner. Primary -- read from
             the tile the page draws, not from anyone's transcription and not
             by differencing anything.
PRODUCES     One row per (report, quantity, place) for `cases`, `deaths` and
             `recovered`: how many the source says were notified in the last
             24 hours, nationally and for each province. These are daily
             *flows* stated outright, and they are a different measurement
             from the differenced cumulative streams even though they measure
             the same events.
FITTED       Not itself fitted. It exists so a consumer can tell the day's
             notifications apart from the cumulative's movement, which are
             the same number on most days and are not on the days that
             matter. `build_streams.py` publishes the pair and their
             difference.
VALIDATED BY the tile's own province breakdown, which must sum to the tile's
             total, and independently by the report's "au cours des dernières
             24 heures" sentence, which states the same three counts in prose
             several paragraphs later. A row is published only when one of
             those corroborates the total; a bare number nothing agrees with
             is refused and counted.

Why this series exists. The national cumulative is published every day and the
obvious daily incidence is its first difference. That reading is correct on
almost every day of the archive and badly wrong on a few, because a cumulative
moves for two reasons: cases notified today, and cases notified earlier that
were added to the books today. On 2026-07-22 the national confirmed cumulative
moved 369 while this banner says 97 were notified that day; the report's own
footnote attributes the rest to integrating the harmonised Ituri and Nord-Kivu
provincial databases. A consumer differencing the cumulative -- following the
stated invariant that a row covers the interval since the previous row -- reads
369 as one day's incidence and fits a transmission spike that did not occur.

The two numbers together are what a consumer needs, because neither alone is
the quantity of interest: the cumulative movement is complete but misdated, the
notification count is correctly dated but omits the backlog. Publishing both,
per row, lets the consumer decide; publishing either alone decides for them.

The source prints this only while it was reconciling. The banner increments
appear in sitreps 059-083 (2026-07-12 to 2026-08-05) and nowhere else in the
archive. That window is the one the reports flag as "consolidation progressive
des données", and the coincidence is not one: the day's own count is printed
exactly when the cumulative stopped being a safe thing to difference. Outside
that window this file has no rows and the check it enables cannot be run --
which is a gap in the evidence, not a licence to assume the two agree.

How a tile is read. The banner is a dashboard laid out in *columns*, and a tile
wraps onto the lines below it while *other* tiles occupy the same lines further
right. Flattening the page's whitespace therefore splices a neighbour's
numbers into the tile: on sitrep 069 the deaths tile's parenthesis closes two
lines down, and flat text puts the suspected-case tile's "318 Ituri 188 ·
N-Kivu 119" inside it. So a tile is assembled by column -- the fields on the
following lines that begin at the same character position -- and only then
parsed. The tile is followed until its parenthesis closes.

A province name can wrap mid-word. Sitrep 071 prints "Nord-Kivu 6 - Haut-" and
closes "Uele 4)" on the next line, so the name is matched across an arbitrary
run of hyphens and spaces; sitrep 073 prints "Nord-Kivu* 8", a footnote marker
standing between the name and its count. Neither is announced and both silently
drop a province from the sum, which fails the licence rather than publishing a
short total -- but a licence that refuses a well-formed page is a bad licence,
so both shapes are read.

What is not done here. The harmonisation the source declares separately
("+24 décès (Ituri 20 · Nord-Kivu 4) + 7 harmonisés (Haut-Uélé)") is recorded
in `harmonised_declared` and *not* added to the notification count: it is the
source stating that those deaths belong to earlier days, which is precisely
the distinction this file exists to keep. Where the source moves a backlog
without declaring a number -- 2026-07-22 -- nothing is inferred here; the
difference against the cumulative is computed downstream, where both series
live.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.report_date import FILENAME, report_key

#: The five provinces the banner names, under every abbreviation it uses.
#: Keyed on the accent-stripped, punctuation-stripped name so "Haut-Uélé",
#: "Haut-Uele", "H-Uélé" and "H- Uele" are one province.
PROVINCES = {
    "ituri": "Ituri",
    "nordkivu": "Nord-Kivu", "nkivu": "Nord-Kivu",
    "sudkivu": "Sud-Kivu", "skivu": "Sud-Kivu",
    "hautuele": "Haut-Uélé", "huele": "Haut-Uélé",
    "tshopo": "Tshopo",
}
#: The five provinces in the order the banner totals them, deduplicated from
#: the alias table above -- `PROVINCES.values()` repeats a name once per
#: abbreviation, which would emit a province twice.
PLACES = ("Ituri", "Nord-Kivu", "Haut-Uélé", "Sud-Kivu", "Tshopo")

PROVINCE = re.compile(
    r"(Ituri|Nord[-\s]*Kivu|N[-\s]*Kivu|Sud[-\s]*Kivu|S[-\s]*Kivu"
    r"|Haut[-\s]*U[ée]l[ée]|H[-\s]*U[ée]l[ée]|Tshopo)[\s*:.\-]*(\d{1,4})", re.I)

#: What opens a tile: a signed count and the noun naming what was counted.
#: "du jour" and "notifiés" are the same statement and are not required.
TILE = re.compile(r"\+\s?(\d{1,4})\s*(nouveaux?\s+cas|cas\b|d[ée]c[èe]s"
                  r"|gu[ée]ris|gu[ée]risons)", re.I)
#: A count the source itself attributes to harmonisation, printed beside the
#: day's count rather than inside it.
HARMONISED = re.compile(r"\+\s?(\d{1,4})\s*(?:par\s+)?harmonis", re.I)

#: The same three counts stated again away from the banner. An independent
#: printing of the same quantity, and the only corroboration available on a
#: report whose tile prints no province breakdown.
#:
#: Two wordings, both national by construction. The usual one opens on "au
#: cours des dernières 24 heures"; sitrep 059 instead restates the pair in its
#: own banner footnote, "Le 12/07 : +31 nouveaux cas confirmés et +10 décès
#: notifiés". The second is admitted only with *both* counts signed, which is
#: what keeps it national: the per-province sentences in the highlights state
#: the same nouns and never sign them, so "Ituri : 73 nouveaux cas confirmés
#: ... 45 décès" cannot be read as the country's total.
PROSE = (
    re.compile(r"derni[èe]res\s+24\s+heures\s*,?\s*(\d{1,4})\s+nouveaux\s+cas"
               r"\s+confirm[ée]s\s*,?\s*(?:et\s+)?(\d{1,4})\s+d[ée]c[èe]s",
               re.I),
    re.compile(r"\+\s?(\d{1,4})\s+nouveaux\s+cas\s+confirm[ée]s\s+et\s+"
               r"\+\s?(\d{1,4})\s+d[ée]c[èe]s", re.I),
)
#: The recoveries, when the same sentence goes on to state them. Searched
#: separately rather than as an optional tail: an optional group matches empty
#: at the first position it is tried, so the sentence would never be read that
#: far and the count would be silently absent on every report.
PROSE_RECOVERED = re.compile(r"et\s+(\d{1,4})\s+gu[ée]ri", re.I)


def _key(s: str) -> str:
    t = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z]", "", "".join(c for c in t if not unicodedata.combining(c)).lower())


def _quantity(noun: str) -> str:
    k = _key(noun)
    return "cases" if "cas" in k else "deaths" if "dec" in k else "recovered"


def fields(line: str) -> list[tuple[int, str]]:
    """The (start column, text) of each column-separated field on a layout
    line. Three or more spaces is a column gap; fewer is word spacing inside
    one tile."""
    return [(m.start(), m.group())
            for m in re.finditer(r"\S(?:.*?\S)?(?=\s{3,}|$)", line)]


def tiles(text: str, n_lines: int = 60) -> list[str]:
    """Every banner tile on the front page, each joined with its own
    continuation lines and none of its neighbours'.

    A tile is a field that opens with "+<n> <noun>". Its continuation is the
    field starting at the same character column on a following line, taken
    while the tile is visibly unfinished and for at most three lines -- the
    banner never wraps a tile further than that, and an unbounded search would
    walk into the section below.

    Unfinished means one of two things. An open parenthesis is the obvious
    one: sitrep 069's deaths tile closes two lines down. The other is a
    trailing signed count whose noun has not arrived -- sitrep 077 ends a line
    on "(Ituri 20 · Nord-Kivu 4) + 7" and opens the next with "harmonisés
    (Haut-Uélé)". Its parentheses balance, so a parenthesis-only rule stops
    early and silently loses the harmonisation the source went out of its way
    to declare separately.
    """
    unfinished = re.compile(r"\+\s?\d{1,4}\s*$")
    grid = [fields(ln) for ln in text.splitlines()[:n_lines]]
    out: list[str] = []
    for i, row in enumerate(grid):
        for col, txt in row:
            if not TILE.search(txt):
                continue
            tile = txt
            for j in range(i + 1, min(i + 4, len(grid))):
                if not (tile.count("(") > tile.count(")")
                        or unfinished.search(tile)):
                    break
                cont = [t for c, t in grid[j] if abs(c - col) <= 2]
                if not cont:
                    break
                tile = f"{tile} {cont[0]}"
            out.append(tile)
    return out


def read_prose(flat: str) -> dict[str, int]:
    """The sentence restating the day's counts, under either wording."""
    for pattern in PROSE:
        m = pattern.search(flat)
        if m is None:
            continue
        got = {"cases": int(m.group(1)), "deaths": int(m.group(2))}
        tail = PROSE_RECOVERED.search(flat[m.end():m.end() + 60])
        if tail:
            got["recovered"] = int(tail.group(1))
        return got
    return {}


def extract(pdf: Path) -> tuple[list[dict], list[dict]]:
    text = subprocess.run(["pdftotext", "-q", "-layout", str(pdf), "-"],
                          capture_output=True, text=True).stdout
    prose = read_prose(re.sub(r"\s+", " ", text))
    rows: list[dict] = []
    refused: list[dict] = []
    seen: set[str] = set()
    for tile in tiles(text):
        m = TILE.search(tile)
        assert m is not None
        quantity, total = _quantity(m.group(2)), int(m.group(1))
        if quantity in seen:
            continue
        seen.add(quantity)
        inner = re.search(r"\((.*?)\)", tile[m.end():], re.S)
        pairs = [(PROVINCES[_key(p)], int(v))
                 for p, v in (PROVINCE.findall(inner.group(1)) if inner else [])
                 if _key(p) in PROVINCES]
        breakdown = sum(v for _, v in pairs) if pairs else None
        harmonised = HARMONISED.search(tile)
        stated = prose.get(quantity)

        # The licence. The tile's own breakdown summing to its total is the
        # strongest corroboration the page offers, because the two numbers are
        # printed by different parts of the same tile. The highlights sentence
        # is a second, independent printing several paragraphs away. Either
        # licenses the total; both agreeing is recorded but demands nothing
        # extra. Nothing corroborating it refuses -- a banner number no other
        # part of the report repeats is exactly the case where a misread digit
        # would ship silently.
        if breakdown is not None and breakdown == total:
            licence = "breakdown_and_prose" if stated == total else "breakdown"
        elif stated is not None and stated == total:
            licence = "prose"
        else:
            refused.append({
                "quantity": quantity, "total": total,
                "why": ("breakdown_disagrees" if breakdown is not None
                        else "prose_disagrees" if stated is not None
                        else "uncorroborated"),
                "tile": re.sub(r"\s+", " ", tile)[:150]})
            continue
        rows.append({
            "quantity": quantity, "place": "national", "notified": total,
            "printed": True,
            "breakdown_sum": breakdown,
            "breakdown": "; ".join(f"{p} {v}" for p, v in pairs),
            "harmonised_declared": int(harmonised.group(1)) if harmonised else None,
            "prose_notified": stated,
            "licence": licence,
            "tile": re.sub(r"\s+", " ", tile)[:220]})

        # The province split, which the tile prints beside its total and which
        # is the same reading that licensed the total. Emitted only where the
        # breakdown closes: on a row licensed by prose alone there is no split
        # to publish, and apportioning the national figure would manufacture a
        # division the source never made.
        #
        # A province the tile does NOT name is a zero, not a hole, and the
        # arithmetic is what says so rather than any judgement about coverage.
        # The tile states a total over five provinces and a breakdown that sums
        # to it exactly, so a province missing from the breakdown contributed
        # nothing to the total. The reports corroborate it in words on the same
        # days -- sitrep 074, "Haut-Uélé : Aucun nouveau cas confirmé ni décès
        # n'a été rapporté"; sitrep 070 prints "Haut-Uélé : 2 nouveaux cas
        # confirmés ... et 0 décès" against a deaths tile naming only Ituri and
        # Nord-Kivu. This is the opposite of the coverage situation in the
        # laboratory and care families, where a province going unmentioned is
        # silence with no total to close against, and `printed` keeps the two
        # cases apart on the row rather than in a reader's memory.
        if licence != "prose":
            named = dict(pairs)
            for province in PLACES:
                rows.append({
                    "quantity": quantity, "place": province,
                    "notified": named.get(province, 0),
                    "printed": province in named,
                    "breakdown_sum": None, "breakdown": "",
                    "harmonised_declared": None, "prose_notified": None,
                    "licence": licence, "tile": ""})
    return rows, refused


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdfs", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows, status = [], []
    for pdf in sorted(args.pdfs.glob("*.pdf")):
        if not FILENAME.search(pdf.stem):
            continue
        num, date = report_key(pdf)
        got, refused = extract(pdf)
        for r in got:
            rows.append({"sitrep": num, "date": date, **r})
        n_tiles = sum(1 for r in got if r["place"] == "national")
        status.append({"sitrep": num, "date": date, "n_parsed": n_tiles,
                       "n_refused": len(refused),
                       "refused": "; ".join(f"{r['why']}({r['quantity']}"
                                            f"={r['total']})"
                                            for r in refused[:4])})
        if not args.quiet and (got or refused):
            print(f"  {pdf.stem}  {n_tiles} tile(s)"
                  + (f", refused {len(refused)}" if refused else ""))

    schema = {"sitrep": pl.Int64, "date": pl.Utf8, "quantity": pl.Utf8,
              "place": pl.Utf8, "notified": pl.Int64, "printed": pl.Boolean,
              "breakdown_sum": pl.Int64, "breakdown": pl.Utf8,
              "harmonised_declared": pl.Int64, "prose_notified": pl.Int64,
              "licence": pl.Utf8, "tile": pl.Utf8}
    out = pl.DataFrame(rows, schema=schema).sort("date", "quantity", "place")
    out.write_csv(args.out)
    st = pl.DataFrame(status)
    st.write_csv(args.out.with_name(args.out.stem + "_status.csv"))

    nat = out.filter(pl.col("place") == "national")
    days = nat.filter(pl.col("quantity").is_in(["cases", "deaths"]))["date"]
    n_ref = st.filter(pl.col("n_refused") > 0).height
    print(f"\n{st.height} reports scanned; {nat['date'].n_unique()} print a "
          f"daily notification tile ({out.height} rows, "
          f"{days.n_unique()} days carrying cases or deaths); "
          f"{n_ref} carry a tile no other part of the report corroborates "
          "(see the status file -- a refusal is never a guessed number)")
    if out.height and days.n_unique():
        split = out.filter((pl.col("place") != "national")
                           & (pl.col("quantity") != "recovered"))
        print(f"span {out['date'].min()} .. {out['date'].max()}; "
              f"province split on {split['date'].n_unique()} of "
              f"{days.n_unique()} days "
              f"({split.filter(pl.col('printed')).height} printed values, "
              f"{split.filter(~pl.col('printed')).height} zeros implied by a "
              "breakdown that closes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
