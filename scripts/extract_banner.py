"""The front-page dashboard banner: patients in isolation, recoveries, deaths.

SOURCE       The INSP situation reports' page-1 banner. PRIMARY -- read from
             the tiles the page draws, not from anyone's transcription.
PRODUCES     One row per report: `patients_isolated` (everyone in isolation
             or a treatment centre AT THAT MOMENT -- confirmed AND suspected),
             `patients_isolated_confirmed` (of those, the confirmed ones),
             `cumul_recovered` (recoveries to date, national), and
             `cumul_deaths` (confirmed deaths to date, national -- the same
             quantity the zone and province tables print, and read here only
             so the national death series can start where the SOURCE starts
             rather than where its tables gain a death column).

             THE TWO ISOLATION SERIES ARE NOT INTERCHANGEABLE, and only the
             second observes a compartment of confirmed cases. Sitrep 070
             prints the banner tile as 766 and its own occupancy table breaks
             that figure into 278 confirmed and 488 suspects -- the narrative
             says so in words. The suspect share is large and moves with
             testing and triage rather than with transmission (36% confirmed
             on sitrep 070, 43% in Ituri on 093), so fitting the tile to an
             isolated-case compartment would score a mostly-suspect census
             against a confirmed-case state.
FITTED       Intended for the model class that observes the isolated
             compartment and the recovered compartment directly.
VALIDATED BY two independent readings, neither consumed here:
             the epiforecasts scan, which read the same pages
             (`data/raw/scan/insp_sitrep_scanned.csv`, columns
             `patients_isolated`, `cumul_recovered` and `confirmed_deaths`),
             reported per report by `compare_extractions.py --banner`; and,
             for `cumul_deaths`, the report's own zone and province tables,
             checked on every build by `build_streams.py` and recorded in
             `meta.json` under `deaths_national_banner_vs_table`.

             AGREEING WITH THE SCAN IS EVIDENCE ABOUT TRANSCRIPTION, NOT
             ABOUT THE CENSUS. Both readings come from the same PDFs, so a
             match says the tile was located and copied correctly and says
             nothing about whether the source counted right.

WHY EXTRACT WHAT THE SCAN ALREADY HAS. Because a third party's reading is a
check and never a trunk: adopting it would leave us unable to audit our own
series against the page, and would end these streams eleven reports early
(the scan stops at 085; the archive runs to 096). Reading the banner
ourselves makes the scan an independent validation whose disagreements are
findings.

WHAT THE ISOLATION CENSUS IS NOT. It is not a count of active confirmed
cases. Beyond the suspect share above, the published books do not close
around it: at 15 August the national figures imply ~1,580 active confirmed
cases (4,945 - 2,325 deaths - 1,040 recovered) against an isolation census of
730 including suspects. Roughly 1,300 confirmed cases sit in no published
outcome -- not dead, not recovered, not in care -- so neither this series nor
`cumul_recovered` is a complete accounting of exits.

BOTH QUANTITIES ARE STOCKS, NOT FLOWS. `patients_isolated` is a prevalence --
how many people are in care right now -- and `cumul_recovered` is a running
total. Neither accumulates over an interval, so neither is differenced and
neither carries the `days_covered` span the incidence streams do; each row is
a reading at an instant.

HOW A TILE IS READ. The banner is a dashboard laid out in COLUMNS: a tile's
label and its value share a horizontal position, with other tiles' labels and
values to the left and right on the same lines. So the value is found by
COLUMN ALIGNMENT -- the number whose field lines up with the label's, on a
nearby line.

THE PAGE DRAWS THE TILE BOTH WAYS UP, and which way is a property of the
report, not of its number or its date. Two arrangements occur:

  values above labels          labels above values
  ---------------------        ---------------------
      344*    60    173        PATIENTS EN ISOLEMENT   GUERIS - CUMUL
  Cumul   Cumul    Patients
   cas     décès   en isole-        766                    540
  confir- parmi    ment -
   més    les ...  hospital.

The first is sitrep 018 (1 June); the second is sitrep 070 (23 July). Both
occur across the archive and neither is announced. So the value is searched
in BOTH directions from the label and the NEARER one wins -- a tile is a
label and a value adjacent in one column, and the adjacent number is the
tile's. If the two are equidistant the tile refuses rather than guess.

THE TWO DIRECTIONS ARE NOT SEARCHED ALIKE, deliberately. Downward, any line
may carry the value: the later vintages draw a tile as a block of heading,
number and commentary, so the value's line also holds neighbouring tiles'
HEADINGS ("725   390   SUIVI DES CONTACTS NATIONAL"). Upward, only a
DASHBOARD ROW is accepted -- a line whose every field is a count, a rate or a
missing marker -- because above a label lies the report's header block, whose
dates and zone counts are numbers that are not tile values.

READING ACROSS INSTEAD OF DOWN IS THE FAILURE THE COLUMN RULE AVOIDS. A first
version searched the whitespace-collapsed page text for the first number
after the label and produced `725390` for sitrep 062: the isolation tile's
725 and the recovery tile's 390, adjacent on one line, glued into a single
plausible five-digit number.

WHAT THE LABEL SAYS DECIDES WHETHER THE TILE IS THE QUANTITY WE WANT. A tile
label wraps over as many as five lines, interleaved with its neighbours'
(sitrep 055 prints "Nombre cumulé" two lines above "des guéris", with another
tile's "jour" between them), so the label is reassembled from every
short text field aligned with the tile's column before it is judged. That
matters twice, and both are recorded below: `_is_ward_census` and
`_bare_label_is_cumulative`.

A tile whose label appears with no aligned number on either side refuses, and
the refusal is written to the status file; nothing reaches further down the
page for something plausible.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pdftable import read as read_tables
from lib.report_date import FILENAME, report_key
from lib.archive import held_pdfs, report_skipped  # noqa: E402
from extract_zone_table import to_int

#: The tiles we read, by every spelling the series prints. `GUÉRIS` must not
#: match the daily-recoveries phrasings ("nouveaux guéris", "guéris du jour"),
#: which are a FLOW and belong to a different quantity.
TILES = {
    # The tile is found by its distinctive WORD, because the labels wrap:
    # "Patients en / isolement - / hospitalisation" spans three lines, and
    # "Nombre cumulé / des guéris" two, so no whole-phrase pattern matches
    # every vintage. The assembled label then decides whether the tile is the
    # quantity we want -- see `_is_ward_census`.
    "patients_isolated": re.compile(r"isolement", re.I),
    "cumul_recovered": re.compile(
        r"cumul\s+des\s+gu[ée]ris|gu[ée]ris\s*[—–-]\s*cumul"
        r"|^(?:des\s+)?gu[ée]ris$|^cumul[ée]?\s+des\s+gu[ée]ris", re.I),
    # Every vintage's cumulative-confirmed-death tile: "Cumul décès parmi les
    # confirmés" (sitreps 007-058), "DECES CONFIRMES · LETALITE" (059-083) and
    # "CUMUL DES / DÉCÈS / CONFIRMÉS" wrapped over three lines (084-096), plus
    # the "Décès confirmés" of the two opening reports.
    #
    # `décès.` IS PROSE, NOT A LABEL. Sitreps 143-147 overlay a highlight
    # bullet on the tile row («Nouvelle zone de santé touchée : Alimbongo
    # (Nord-Kivu), avec 4 cas confirmés dont 2 décès.»), whose last word sits
    # above the recovery tile; read as the death label it took the recovery
    # count, 2 235 where the page prints 4 148. A label never ends a sentence.
    "cumul_deaths": re.compile(
        r"^cumul\s+(?:des\s+)?d[ée]c[èe]s|^d[ée]c[èe]s\b(?!\.)", re.I),
}

#: TILES WE DELIBERATELY DO NOT READ. The suspected-case tile is a different
#: quantity in each vintage under near-identical wording, and no stream
#: observes any of them:
#:
#:   "Cumul cas suspects"                    (007-015)  a running total
#:   "Cas suspects en cours d'investigation" (016-018)  a STOCK, under way now
#:   "Cas suspects du jour" / "Nouveaux cas
#:    suspects du jour"                      (021-)     a FLOW, one day
#:   "Cas suspects en isolement"             (016-017)  suspects in the ward
#:
#: Reading them into one column would splice a stock onto a flow. If a stream
#: ever wants suspected cases, each vintage needs its own declared column;
#: this reader must not start publishing one as a side effect of a geometry
#: fix. `Cas confirmés actifs` (016-017) is likewise left alone: it is a
#: prevalence of active confirmed cases, not a census of the ward.

#: THE ISOLATION TILE MUST COUNT THE WARD, NOT A CLASS OF CASE INSIDE IT.
#: Sitreps 016 and 017 print `Cas suspects en isolement` -- 101 and 104,
#: suspects only -- beside a separate `Cas confirmés actifs` tile, and print
#: no ward total at all; the all-patients wording `Patients en isolement -
#: hospitalisation` appears from sitrep 018 (173). Publishing 101 and 104
#: into a series of ward totals would put a sub-count where a total belongs,
#: at exactly the point the series begins. The epiforecasts scan reached the
#: same conclusion independently and excludes those two reports for the same
#: stated reason.
#:
#: THE CASE CLASS MUST QUALIFY THE ISOLATION WORD, not merely appear near it.
#: The later vintages draw the banner as a grid whose other headings include
#: `CAS CONFIRMES — 5 PROVINCES`, and a rule that fired on the words alone
#: would refuse a perfectly good ward census the moment the layout shifted a
#: line.
ISOLATION_SUBSET = re.compile(
    r"cas\s+(?:suspects?|confirm[ée]s?)\s+(?:en\s+)?"
    r"(?:isolement|hospitalis)", re.I)
#: The care-occupancy table, a second and older route to the same census:
#: one row per province ending in a national total. It carries the
#: confirmed/suspect split the banner tile does not.
OCCUPANCY = {
    "patients_isolated": re.compile(
        r"patients?\s+en\s+isolement\s*\(?\s*fin\s*J", re.I),
    "patients_isolated_confirmed": re.compile(r"dont\s+confirm[ée]s", re.I),
}
#: Every number on a line of the occupancy table.
ROW_NUMS = re.compile(r"(?<![\d,.%])(\d{1,3}(?:[\u00a0\u202f ]\d{3})*)(?![\d%])")


def _national(nums: list[int]) -> int | None:
    """The national figure from one occupancy row: the printed total where the
    table has a total column, otherwise the provinces summed.

    THE ROW'S OWN ARITHMETIC DECIDES WHICH IT IS, because the table gained a
    sixth province and lost its total column without announcing either. Taking
    the last number unconditionally read sitrep 080's Bas-Uele column, 20, as
    the national census of 707."""
    if not nums:
        return None
    if len(nums) >= 2 and nums[-1] == sum(nums[:-1]):
        return nums[-1]
    return sum(nums)
#: A LABEL IS A SHORT FIELD. Both keywords also occur in the front page's
#: prose ("...ont été déclarés guéris après avoir obtenu des tests..."), and
#: the discriminator that holds across every vintage is length: a dashboard
#: tile's label is a few words in its own column, prose is a paragraph in
#: one field. Measured across the archive, tile labels run to 31 characters.
LABEL_MAX = 34

#: The thousands separator is a space, in three flavours across the archive.
_SEP = "\u00a0\u202f "
#: An integer as the banner prints it: either an unbroken run of digits
#: (`1441`, the early vintage) or groups of three behind a separator
#: (`1 333`). Allowing the separator ONLY before exactly three digits is what
#: stops two adjacent tiles' values from reading as one number.
_INT = rf"(?:\d+|\d{{1,3}}(?:[{_SEP}]\d{{3}})+)"
#: Footnote markers, which attach to a value as readily as to a name and are
#: typography rather than value.
_MARK = r"*†‡§"
#: A field that is a tile's COUNT. The count may be followed by footnote
#: markers, and by a second figure the tile prints beside it -- a letality
#: (`202(23,1%)`), a bed-occupancy rate (`609(92,7%)`) or a sub-count
#: (`192(46 décès) **`) -- optionally introduced by a bullet
#: (`1 309 · (44,0%)`), and optionally without the brackets (sitrep 059
#: prints `719 · 36,6 %**` where its neighbours print `(38,4 %)`).
#:
#: THE SECOND FIGURE MUST BE A RATE OR BRACKETED, never a bare integer, so
#: that two adjacent tiles' counts can never read as one. A trailing footnote
#: DIGIT is accepted only once a bracket has closed the count (sitrep 040
#: prints `291(26,0%)1`); without that restriction `2911` would read as 291.
NUM = re.compile(rf"^[{_MARK}]?\s*(?P<n>{_INT})\s*[{_MARK}]*"
                 rf"(?:\s*[\u00b7\u2022]?\s*(?:\([^)]*\)|{_INT}\s*[.,]?\s*\d*\s*%)"
                 rf"\s*[\d{_MARK}]*)?\s*$")
#: The other two things a dashboard row may hold: a rate, and a marker for a
#: figure the report did not have. A rate is never taken as a count -- the
#: percent sign is optional in print (sitrep 048 ends its row with `82,7`),
#: so a decimal point alone marks it.
RATE = re.compile(rf"^{_INT}[.,]\d+\s*%?\s*[\d{_MARK}]*$"
                  rf"|^{_INT}\s*%\s*[\d{_MARK}]*$")
#: `?` IS ONE OF THE SPELLINGS, and it appears on exactly one page in the
#: archive: sitrep 001, the outbreak's first report, writes `?` in the three
#: tiles it had no figure for (both bed-occupancy rates and recoveries) while
#: printing counts in the other four. Without it that value row is not a
#: dashboard row at all, and the `D\u00e9c\u00e8s confirm\u00e9s` tile beside them -- 4
#: deaths at 14 May, a real printed count on the first day of the series --
#: refused for want of an aligned number above it. Admitting the marker reads
#: the neighbouring tile; it does not read the `?` as anything, and the
#: recoveries tile still refuses, because a report that says it does not know
#: has not said zero.
MISSING = re.compile(
    r"^(?:ND|N\.?D\.?|NA|N\s*/\s*[AD]|\?|[\u2014\u2013-]+)$", re.I)
#: A parenthetical or a marker stranded on its own continuation line, e.g.
#: sitrep 055 prints `227` on one line and `(60 décès)**` on the next.
STRANDED = re.compile(rf"^(?:[{_MARK}]+|\([^)]*\)\s*[\d{_MARK}]*)$")

#: How far a value's column may drift from its label's before it belongs to
#: somebody else's tile.
COL_TOL = 8
#: How many lines to search each way. DOWN is the shipped distance and the
#: later vintages' tiles sit three lines under their heading. UP must clear
#: the deepest label stack in the archive: sitreps 055-057 wrap the recovery
#: label over lines interleaved with a neighbour's, putting the value seven
#: lines above the label field that anchors it.
LOOK_AHEAD, LOOK_BEHIND = 6, 8


def _fields(line: str) -> list[tuple[int, int, str]]:
    """(start column, end column, text) for each run of text separated by 2+
    spaces -- the layout's own column structure, which collapsing whitespace
    destroys.

    THE QUANTIFIER SHAPE IS LOAD-BEARING. The previous form,
    `\\S(?:.*?\\S)?(?=\\s{2,}|$)`, welded a ONE-CHARACTER field to everything
    after it: the optional group is greedy, so for a lone `0` the engine
    preferred any longer span that could reach a terminator over matching
    nothing at all. Sitrep 008's recovery tile came out as the single field
    `'0                  16'` -- the recovery count fused to the next tile's
    -- and matched no number, so the tile refused. The same happened to
    sitrep 018's `6`, sitrep 013's `1` and sitrep 021's `8`: every
    single-digit tile value in the archive. Consuming characters only while
    no 2+-space run begins cannot do that."""
    out = []
    for m in re.finditer(r"\S(?:(?!\s{2,}).)*", line):
        t = m.group(0).rstrip()
        if t:
            out.append((m.start(), m.start() + len(t), t))
    return out


def _aligned(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Do two fields belong to the same tile column?

    Either their spans overlap, or they start within `COL_TOL` of each other.
    Overlap is needed because a tile's value is CENTRED over its label block
    and the label wraps to a different width: sitrep 046 prints `1 333*` at
    columns 15-21 above `Cumul cas confirmés` at 3-22, twelve columns of
    start-drift but wholly inside the label. Start proximity is kept because
    it is the rule the shipped reader used and it is the tighter test for the
    narrow tiles."""
    return (a[0] < b[1] and b[0] < a[1]) or abs(a[0] - b[0]) <= COL_TOL


def _dashboard_row(line: str) -> bool:
    """Is this line nothing but a row of tile values?

    A count, a rate, a missing marker or a stranded parenthetical -- and at
    least two of them, so that a lone number somewhere else on the page is
    not mistaken for the banner. This is what separates the banner's value
    row from the report header above it, whose zone counts and dates are
    numbers that belong to no tile."""
    fs = _fields(line)
    return len(fs) >= 2 and all(
        NUM.match(t) or RATE.match(t) or MISSING.match(t) or STRANDED.match(t)
        for _, _, t in fs)


def _to_count(txt: str) -> int | None:
    """The count a tile-value field carries, or None if the field is not one.
    A rate is refused outright: `82,7` is a contact-tracing percentage, not
    eighty-two people."""
    if RATE.match(txt):
        return None
    m = NUM.match(txt)
    return to_int(m.group("n")) if m else None


def _label_fragment(t: str) -> bool:
    """Could this field be part of a tile's printed label? Short, and not a
    value of any kind."""
    return (len(t) <= LABEL_MAX and _to_count(t) is None and not RATE.match(t)
            and not MISSING.match(t) and not STRANDED.match(t))


def _label_stack(lines: list[str], li: int, span: tuple[int, int],
                 anchor: str) -> str:
    """The tile's whole printed label, reassembled from the page.

    A label wraps over up to five lines, and neighbouring tiles' lines are
    INTERLEAVED with it -- sitrep 055 prints `Nombre cumulé` on one line,
    another tile's `jour` on the next, and `des guéris` on the third -- so
    lines carrying nothing in this tile's column are skipped rather than
    ending the stack.

    THE WALK STOPS AT THE FIRST THING IN THE COLUMN THAT IS NOT A LABEL: a
    count (the tile's own value, or the next tile's), or a field too long to
    be a heading. Without that stop the walk crossed whole tiles in the
    later vintages, which draw a 2x3 grid of `heading / value / commentary`
    blocks, and reached a NEIGHBOUR'S HEADING -- `CAS CONFIRMES — 5
    PROVINCES` sits ten to twelve lines above `PATIENTS EN ISOLEMENT` in the
    same column. A tile must be judged on its own label.

    THE RESULT IS NOT PERFECT AND DOES NOT NEED TO BE. Six of the eighty-
    seven reports still prefix a commentary line the stop rule cannot reach
    (`+32 décès (Ituri 24 · Nord-Kivu 8) GUÉRIS — CUMUL`), and three lose a
    trailing wrap (`Patients en isolement -`). Both judgements made on this
    string are written to be insensitive to that: the recovery vintage is
    decided by an EXACT match on the bare word, and the isolation subset by
    a phrase that must qualify the isolation word rather than merely sit
    near it."""
    sides = []
    for step, limit in ((-1, LOOK_BEHIND), (+1, LOOK_AHEAD)):
        got: list[tuple[int, list[str]]] = []
        for d in range(1, limit + 1):
            j = li + step * d
            if not 0 <= j < len(lines):
                break
            here = [t for s, e, t in _fields(lines[j]) if _aligned((s, e), span)]
            if not here:
                continue                       # this tile's column is empty
            if not all(map(_label_fragment, here)):
                # A value, or prose. A SHORT FRAGMENT TOUCHING THAT PROSE IS
                # ITS WRAPPED TAIL, not a heading: the grid vintages print a
                # tile's commentary under its value, and its last line
                # (`Haut-Uélé 4)`, `H-Uélé 3) · +10 par harmonisation)`) is
                # short enough and aligned enough to pass for a label. So the
                # run of fragments adjacent to the stopping line is dropped.
                while got and abs(got[-1][0] - j) <= 1:
                    j = got.pop()[0]
                break
            got.append((j, here))
        sides.append([t for _, ts in got for t in ts])
    return " ".join(sides[0][::-1] + [anchor] + sides[1])


def _is_ward_census(label: str) -> bool:
    """Does this isolation tile count everyone in the ward? See
    ISOLATION_SUBSET for why sitreps 016 and 017 do not."""
    return not ISOLATION_SUBSET.search(label)


#: The recovery tile's label says `cumul` from sitrep 019 onward ("Nombre
#: cumulé des guéris", later "GUÉRIS — CUMUL", "CUMUL DES GUÉRIS"). Before
#: that it is the bare word `Guéris`, and the page never says whether that is
#: a running total or the day's recoveries.
BARE_RECOVERY_LABEL = re.compile(r"^gu[ée]ris$", re.I)


def _bare_label_is_cumulative(d: "pl.DataFrame") -> tuple[bool, str]:
    """May the bare-label recovery tiles be published as a cumulative?

    THIS IS A GATE, NOT A COMMENT. Reading a daily flow as a stock would
    corrupt the recovery series silently, and the bare-label pages do not say
    which they are, so the archive is made to say it -- and if it ever stops
    saying it, the bare-label values are dropped instead of published.

    Two things must hold across the label change:

      1. The last bare-label report and the first explicitly-cumulative one
         must print the SAME value. Sitrep 018 (`Guéris`) and sitrep 019
         (`Nombre cumulé des guéris`) are consecutive days and both print 6.
         Under a daily-flow reading the day before an explicit cumulative of
         6 would have to be a flow of 6 arriving on top of everything
         earlier -- and sitrep 017 already printed 6, and 013 printed 1.
      2. The bare-label values must never fall: 0, 0, 0, 0, 0, 1, 1, 2, 2, 6,
         6 over sitreps 005-018 (007 prints ND). A flow that repeats 0 on
         five consecutive days and then 6 on two is not a flow.

    A third fact, which the archive cannot be made to check but the page
    states plainly: those same pages carry a SEPARATE per-zone column headed
    `Guéris du jour`. The day's recoveries already have their own home, so the
    banner tile is not them."""
    bare = d.filter(pl.col("_recovery_label_is_bare")
                    & pl.col("cumul_recovered").is_not_null()).sort("sitrep")
    named = d.filter(~pl.col("_recovery_label_is_bare")
                     & pl.col("cumul_recovered").is_not_null()).sort("sitrep")
    if bare.is_empty():
        return True, "no bare-label recovery tile in the archive"
    v = bare["cumul_recovered"].to_list()
    if any(b < a for a, b in zip(v, v[1:])):
        return False, (f"the bare-label `Guéris` tiles do not form a "
                       f"non-decreasing series ({v}), so they cannot be read "
                       f"as a running total")
    if named.is_empty():
        return False, ("no report labels the recovery tile as cumulative, so "
                       "nothing establishes what the bare `Guéris` counts")
    last_bare, first_named = bare.row(-1, named=True), named.row(0, named=True)
    if last_bare["cumul_recovered"] != first_named["cumul_recovered"]:
        return False, (
            f"the label changes from `Guéris` to a cumulative wording between "
            f"sitreps {last_bare['sitrep']} and {first_named['sitrep']} and "
            f"the value changes with it "
            f"({last_bare['cumul_recovered']} -> "
            f"{first_named['cumul_recovered']}), so the two vintages are not "
            f"shown to be the same series")
    return True, (
        f"sitrep {last_bare['sitrep']} (`Guéris`) and sitrep "
        f"{first_named['sitrep']} (cumulative wording) both print "
        f"{last_bare['cumul_recovered']}, and the bare-label values never "
        f"fall")


def extract(pdf: Path) -> tuple[dict, list[str], dict]:
    """The banner's values, the tiles that refused, and each tile's label."""
    # The banner tiles are page 1; the occupancy table sits deeper in the
    # report (page 6 to 9 depending on vintage), so the two routes read
    # different extents of the same document.
    def _text(*extent: str) -> str:
        return subprocess.run(["pdftotext", "-q", "-layout", *extent,
                               str(pdf), "-"],
                              capture_output=True, text=True).stdout
    lines = _text("-f", "1", "-l", "1").splitlines()
    all_lines = _text().splitlines()
    out: dict[str, int] = {}
    why: list[str] = []

    # ROUTE 2 FIRST, because it is the one that separates confirmed from
    # suspected. The table prints a row per province ending in the national
    # total, and where it prints all three rows the page checks itself:
    # confirmed + suspects must equal the total.
    occ: dict[str, int] = {}
    for name, pat in OCCUPANCY.items():
        for line in all_lines:
            if not pat.search(line):
                continue
            nums = [n for n in (to_int(x) for x in ROW_NUMS.findall(line))
                    if n is not None]
            got = _national(nums)
            if got is not None:
                occ[name] = got
                break
    susp = None
    for line in all_lines:
        if re.search(r"dont\s+suspects?", line, re.I):
            nums = [n for n in (to_int(x) for x in ROW_NUMS.findall(line))
                    if n is not None]
            susp = _national(nums)
            break
    if (susp is not None and "patients_isolated" in occ
            and "patients_isolated_confirmed" in occ
            and occ["patients_isolated_confirmed"] + susp != occ["patients_isolated"]):
        why.append(f"occupancy table does not close: "
                   f"{occ['patients_isolated_confirmed']} confirmed + {susp} "
                   f"suspect != {occ['patients_isolated']} total")
        occ = {}
    out.update(occ)

    labels: dict[str, str] = {}
    for name, pat in TILES.items():
        hit = None
        for li, line in enumerate(lines):
            for s, e, txt in _fields(line):
                if len(txt) <= LABEL_MAX and pat.search(txt):
                    hit = (li, (s, e), txt)
                    break
            if hit:
                break
        if hit is None:
            why.append(f"{name}: tile absent")
            continue
        li, span, txt = hit
        labels[name] = label = _label_stack(lines, li, span, txt)

        if name == "patients_isolated" and not _is_ward_census(label):
            why.append(f"{name}: the tile is `{label}` -- a class of case "
                       f"inside the ward, not the ward census")
            continue

        val, note = _tile_value(lines, li, span, pat, txt)
        if note:
            why.append(f"{name}: {note}")
        if val is None:
            continue
        if name in out:
            if out[name] != val:
                # Two independent tables in one report. Recorded, never
                # silently reconciled: the occupancy table keeps precedence
                # because it is the one carrying the confirmed/suspect split.
                why.append(f"{name}: the occupancy table says {out[name]} and "
                           f"the front-page tile says {val}; the table's "
                           f"stands")
        else:
            out[name] = val
    return out, why, labels


def _tile_value(lines: list[str], li: int, span: tuple[int, int],
                pat: re.Pattern, txt: str) -> tuple[int | None, str]:
    """The count belonging to the tile whose anchoring label field is `span`
    on line `li` -- searched BOTH ways, nearer wins. Returns (value, note),
    where a note is a refusal reason or an arbitration worth recording."""
    # Same field first, for a tile drawn as ONE cell holding label and value
    # together ("PATIENTS EN ISOLEMENT / CTE 730"). NO REPORT IN THE ARCHIVE
    # takes this path today -- measured over all 87 -- but the newest vintage
    # is drifting toward it (sitreps 087-093 print `ISOLEMENT / CTE` as a
    # single label field with the value two lines under), and without the
    # branch such a tile would refuse rather than read.
    m = pat.search(txt)
    same = re.match(rf"[^\d]{{0,12}}?({_INT})\s*[{_MARK}]*$", txt[m.end():])
    if same:
        return to_int(same.group(1)), ""

    def look(step: int, limit: int) -> tuple[int | None, int]:
        """The nearest aligned count `limit` lines away at most, and how far.

        Upward the line must be a DASHBOARD ROW; downward it need not be --
        see the module docstring for why the two directions differ."""
        for d in range(1, limit + 1):
            j = li + step * d
            if not 0 <= j < len(lines):
                break
            if step < 0 and not _dashboard_row(lines[j]):
                continue
            best = None
            for s, e, t in _fields(lines[j]):
                if not _aligned((s, e), span):
                    continue
                v = _to_count(t)
                if v is None:
                    continue
                # A wide label can align with more than one field; the tile's
                # is the one whose centre sits closest to the label's.
                gap = abs((s + e) - (span[0] + span[1]))
                if best is None or gap < best[0]:
                    best = (gap, v)
            if best is not None:
                return best[1], d
        return None, 0

    below, d_below = look(+1, LOOK_AHEAD)
    above, d_above = look(-1, LOOK_BEHIND)
    if below is None and above is None:
        return None, "label with no aligned number above or beneath it"
    if below is None:
        return above, ""
    if above is None:
        return below, ""
    if d_below == d_above:
        return None, (f"a number is aligned {d_below} line(s) above ({above}) "
                      f"and as near beneath ({below}); the page does not say "
                      f"which is the tile's")
    return (below, "") if d_below < d_above else (above, "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdfs", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows, status = [], []
    pdfs, extra = held_pdfs(args.pdfs)
    report_skipped(extra)
    for pdf in pdfs:
        if not FILENAME.search(pdf.stem):
            continue
        num, date = report_key(pdf)
        got, why, labels = extract(pdf)
        rows.append({"sitrep": num, "date": date,
                     "patients_isolated": got.get("patients_isolated"),
                     "patients_isolated_confirmed":
                         got.get("patients_isolated_confirmed"),
                     "cumul_recovered": got.get("cumul_recovered"),
                     "cumul_deaths": got.get("cumul_deaths"),
                     "_recovery_label_is_bare": bool(BARE_RECOVERY_LABEL.match(
                         labels.get("cumul_recovered", "")))})
        status.append({"sitrep": num, "date": date, "n_read": len(got),
                       "recovery_label": labels.get("cumul_recovered", ""),
                       "isolation_label": labels.get("patients_isolated", ""),
                       "refused": "; ".join(why)})
        if not args.quiet and why:
            print(f"  {pdf.stem}  read {len(got)}/{len(TILES) + 1}  "
                  f"({'; '.join(why)})")

    schema = {"sitrep": pl.Int64, "date": pl.Utf8,
              "patients_isolated": pl.Int64,
              "patients_isolated_confirmed": pl.Int64,
              "cumul_recovered": pl.Int64,
              "cumul_deaths": pl.Int64,
              "_recovery_label_is_bare": pl.Boolean}
    d = pl.DataFrame(rows, schema=schema).sort("sitrep")

    # THE DEFINITIONAL GATE, run over the whole archive because that is the
    # only place the evidence lives. See `_bare_label_is_cumulative`.
    # A BARE LABEL AFTER THE CUMULATIVE WORDING IS A BROKEN STACK, not the
    # early vintage. Sitreps 143-147 print `CUMUL DES / GUÉRIS`, but the
    # overlaid bullet's prose stops the label walk before `CUMUL DES`, so the
    # tile assembles as bare `GUÉRIS` -- and the gate below, which judges the
    # 005-018 vintage by its last bare tile, then compared sitrep 147 against
    # 019 and dropped the whole early series. Those late tiles are refused on
    # their own, and the gate judges only the vintage it was written for.
    named_from = d.filter(~pl.col("_recovery_label_is_bare")
                          & pl.col("cumul_recovered").is_not_null())["sitrep"].min()
    if named_from is not None:
        late = (pl.col("_recovery_label_is_bare")
                & (pl.col("sitrep") > named_from))
        late_bare = set(d.filter(late & pl.col("cumul_recovered").is_not_null())
                        ["sitrep"].to_list())
        d = d.with_columns(
            pl.when(late).then(None).otherwise(pl.col("cumul_recovered"))
            .alias("cumul_recovered"),
            pl.when(late).then(False).otherwise(pl.col("_recovery_label_is_bare"))
            .alias("_recovery_label_is_bare"))
        status = [s | {"refused": "; ".join(filter(None, [
            s["refused"], f"cumul_recovered refused: the label assembles as "
            f"bare `{s['recovery_label']}` on a report after sitrep "
            f"{named_from} established the cumulative wording, so the label "
            f"stack was cut short and the page's own label is unread"]))}
            if s["sitrep"] in late_bare else s for s in status]
    ok, verdict = _bare_label_is_cumulative(d)
    n_bare = int((d["_recovery_label_is_bare"]
                  & d["cumul_recovered"].is_not_null()).sum())
    if not ok:
        d = d.with_columns(
            pl.when(pl.col("_recovery_label_is_bare"))
            .then(None).otherwise(pl.col("cumul_recovered"))
            .alias("cumul_recovered"))
        status = [s | {"refused": "; ".join(
            filter(None, [s["refused"],
                          f"cumul_recovered dropped: {verdict}"]))}
            if BARE_RECOVERY_LABEL.match(s["recovery_label"]) else s
            for s in status]
    print(f"  bare-label `Guéris` tiles: {n_bare} report(s), "
          f"{'PUBLISHED' if ok else 'DROPPED'} -- {verdict}")

    d = d.drop("_recovery_label_is_bare")
    d.write_csv(args.out)
    pl.DataFrame(status).write_csv(
        args.out.with_name(args.out.stem + "_status.csv"))

    print(f"\n{d.height} reports scanned; "
          f"patients_isolated on {d['patients_isolated'].is_not_null().sum()}, "
          f"of which confirmed split on "
          f"{d['patients_isolated_confirmed'].is_not_null().sum()}, "
          f"cumul_recovered on {d['cumul_recovered'].is_not_null().sum()}, "
          f"cumul_deaths on {d['cumul_deaths'].is_not_null().sum()} "
          "(a figure the page does not print is null, never inferred)")


if __name__ == "__main__":
    main()
