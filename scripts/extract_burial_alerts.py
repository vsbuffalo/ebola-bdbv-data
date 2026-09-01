"""The safe-burial pillar's death-alert ledger, one row per province-day.

WHICH SOURCE: the situation-report PDFs themselves (primary), read with
`pdftotext -q` for the same reason `extract_care_prose.py` uses it -- the
reports are two-column and `-layout` welds the columns together line by line.

WHAT IT PRODUCES: `data/build/series/burial_alerts.csv`, one row per province
per report day, carrying the pillar's own counts along the path a death takes
before it can be laboratory-confirmed:

    alerts raised  ->  bodies the team reached  ->  bodies swabbed

EDS -- *équipe de désinfection et sécurisation*, the team that disinfects a
site and secures a body for dignified burial -- is the pillar's name for itself,
and `eds_done` is how many burials it carried out. That is a sibling activity
to swabbing, not a step on the path: a body can be swabbed and not yet buried
by the team, or buried without a usable swab.

WHY IT MATTERS: a death that is never swabbed can never become a confirmed
case, so this ratio bounds how much of the true mortality the confirmed-death
series can see. A model that declares an ascertainment constant is declaring
this quantity, and until now it has been declared from prose read by hand.

IS IT FITTED: no. Every number here is printed on a page. The only arithmetic
is adding a carried-over alert count to the day's, and only where the source's
own wording says the two are separate.

WHAT VALIDATES IT: the reports frequently print their own percentage --
"56 EDS réalisés sur 74 alertes de décès (76 %)". Where they do, the parse is
checked against it and a row that disagrees is refused rather than published.
That is the licence: a row survives because the document's own arithmetic
agrees with our reading of it, not because a regex matched.

THE CONSTRUCTION THAT COSTS A NUMBER. The pillar states carried-over alerts
(`reports`, from *reporter*, to postpone -- a body not reached that day) in two
grammatically opposite ways, and the difference is real:

    "72 alertes de décès du jour **et** 23 reports"      -> 72 + 23 = 95
    "93 alertes de décès reçues, **dont** 13 reports"    -> 93 already

Adding unconditionally inflates the denominator and deflates the ratio. Every
row records which construction it read, in `alert_construction`, so the choice
is inspectable rather than buried.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.report_date import report_key                            # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

PROVINCES = {
    "ituri": "Ituri", "nordkivu": "Nord-Kivu", "sudkivu": "Sud-Kivu",
    "hautuele": "Haut-Uélé", "basuele": "Bas-Uélé", "tshopo": "Tshopo",
}
PROV_RE = re.compile(r"\b(Ituri|Nord[-\s]?Kivu|Sud[-\s]?Kivu"
                     r"|Haut[-\s]?U[ée]l[ée]|Bas[-\s]?U[ée]l[ée]|Tshopo)\b", re.I)
SLUG = {"ituri": "ituri", "nordkivu": "nord_kivu", "sudkivu": "sud_kivu",
        "hautuele": "haut_uele", "basuele": "bas_uele", "tshopo": "tshopo"}

NUM = r"\d{1,4}"

#: Alerts raised. `du jour` and `reçues`/`enregistrées`/`au total` all appear;
#: the qualifier does not change what the number counts, only whether a
#: carried-over count is inside it, which `CARRIED_*` below decides.
ALERTS = re.compile(
    rf"(?:sur\s+)?({NUM})\s+alertes?\s+de\s+d[ée]c[èe]s"
    rf"|le\s+pilier\s+EDS\s+a\s+re[çc]u\s+({NUM})\s+alertes?", re.I)

#: Carried-over alerts, in the two constructions that mean opposite things.
CARRIED_ADD = re.compile(
    rf"(?:du\s+jour\s+)?et\s+({NUM})\s+reports?"
    rf"|avec\s+({NUM})\s+reports?", re.I)
#: `dont N reports` and the parenthetical `N alertes (M reports)` both put the
#: carried-over count *inside* the alert total. The parenthetical reads as
#: though it could be either, and the source settles it: 25 August, Nord-Kivu,
#: "le pilier EDS a reçu 37 alertes (15 reports) : 36 corps swabés, un échec de
#: swab" -- 36 swabbed plus 1 failure is 37, the stated total, not 37 + 15.
#: Adding it would have inflated five Nord-Kivu and Ituri denominators by
#: between 10 and 17 alerts each.
CARRIED_INSIDE = re.compile(
    rf"dont\s+({NUM})\s+reports?"
    rf"|{NUM}\s+alertes?[^:.]{{0,40}}?\(\s*({NUM})\s+reports?\s*\)", re.I)

#: Bodies swabbed, across every phrasing the corpus uses.
SWABBED = re.compile(
    rf"({NUM})\s+corps\s+(?:ont\s+[ée]t[ée]\s+)?(?:swab|pr[ée]lev)"
    rf"|({NUM})\s+swabs?\s+effectu[ée]s"
    rf"|({NUM})\s+corps\s+(?:a\s+[ée]t[ée]\s+)?pr[ée]lev", re.I)
#: "toutes ont été prélevées par swab" -- every alert was swabbed. A word, not
#: a number, and dropping it would lose a 100% day and bias the pooled ratio
#: downward.
SWABBED_ALL = re.compile(
    r"tou(?:te)?s\s+ont\s+[ée]t[ée]\s+(?:swab|pr[ée]lev)"
    r"|les\s+\d{1,3}\s+corps\s+ont\s+[ée]t[ée]\s+swab", re.I)

#: The inner step: bodies the team actually reached. Printed rarely.
REACHED = re.compile(rf"sur\s+({NUM})\s+pris\s+en\s+charge", re.I)

EDS_DONE = re.compile(rf"({NUM})\s+EDS\s+(?:ont\s+[ée]t[ée]\s+)?r[ée]alis", re.I)
FAILURES = re.compile(rf"({NUM})\s+[ée]checs?|(aucun|sans)\s+[ée]chec", re.I)

#: A percentage the report prints for itself, used as the check.
PCT = re.compile(r"\((\d{1,3}(?:[.,]\d)?)\s*%\)")

#: The pillar's own heading, across every vintage that carries one. Scoping to
#: it is not tidiness: the laboratory section a page earlier prints sentences
#: like "Bas-Uélé : 1 swab reçu et testé", where a swab is a *specimen arriving
#: at a bench*, not a body reached by a burial team. Parsed unscoped, that
#: sentence becomes a burial row asserting one body swabbed in Bas-Uélé, which
#: is a different quantity and a wrong one.
SECTION = re.compile(
    r"Pr[ée]vention\s+et\s+Contr[ôo]le\s+d[eu]s?\s+l?[’']?Infections?"
    r"|ENTERREMENTS\s+DIGNES?\s+ET\s+SECURIS[EÉ]S"
    r"|Enterrements\s+Digne?s?\s+et\s+S[ée]curis[ée]s", re.I)
#: Where it ends: the next numbered pillar heading, or the surveillance,
#: laboratory or vaccination sections if the numbering is absent.
SECTION_END = re.compile(
    r"\d\.\d+\.?\s+(?:Surveillance|Laboratoire|Prise\s+en\s+charge"
    r"|Vaccination|Communication|Logistique|Coordination|Recherche)"
    r"|RECHERCHE,\s+INNOVATION|SURVEILLANCE\s+[ÉE]PID[ÉE]MIOLOGIQUE"
    r"|COMMUNICATION\s+DES\s+RISQUES", re.I)

#: What opens a province's paragraph inside the pillar. The corpus uses four
#: forms and all four must match, because the numbers sit in the fragment
#: *after* the marker's own clause and inherit from it:
#:
#:   "• En Ituri, 18 rings ... ; 62 EDS réalisées sur 83 alertes"
#:   "→ Nord-Kivu : 33 alertes de décès, 33 corps swabés"
#:   "Au Haut-Uélé, 3 alertes de décès ont été enregistrées"
#:   "• Bas-Uélé : 3 corps swabés"
#:
#: The name must be followed by a comma or colon. A province named mid-clause
#: -- "les décès se concentrant à Beni" or "résistances à Bambu" -- is an aside
#: about a place, not a heading, and must not reassign the rows that follow.
PROV_MARKER = re.compile(
    r"(?:^|[•→;.]\s*)(?:En\s+|Au\s+|Dans\s+l[ae'’]\s*)?"
    r"(Ituri|Nord[-\s]?Kivu|Sud[-\s]?Kivu|Haut[-\s]?U[ée]l[ée]"
    r"|Bas[-\s]?U[ée]l[ée]|Tshopo)\s*[,:]", re.I)


def fold(s: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", s or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", t.lower())


def first(m: re.Match | None) -> int | None:
    if not m:
        return None
    for g in m.groups():
        if g and g.isdigit():
            return int(g)
    return None


def text_of(pdf: Path) -> str:
    r = subprocess.run(["pdftotext", "-q", str(pdf), "-"],
                       capture_output=True, text=True)
    return " ".join(r.stdout.split())


def pillar_sections(text: str) -> list[str]:
    """Every stretch of the document belonging to the burial pillar.

    A report can carry the pillar twice -- an actions subsection and a
    challenges one -- so this returns a list rather than the first match.
    """
    out = []
    for m in SECTION.finditer(text):
        rest = text[m.end():]
        stop = SECTION_END.search(rest)
        out.append(rest[:stop.start()] if stop else rest[:4000])
    return out


def sentences(text: str) -> list[tuple[str, str | None]]:
    """`(sentence, province-or-None)`, province carried down from the marker
    that most recently opened a paragraph, and only within the pillar."""
    out: list[tuple[str, str | None]] = []
    for section in pillar_sections(text):
        current: str | None = None
        for part in re.split(r"(?<=[.;])\s+|(?=[•→])", section):
            m = PROV_MARKER.search(part)
            if m:
                current = SLUG.get(fold(next(g for g in m.groups() if g)))
            out.append((part, current))
    return out


def parse(sentence: str) -> dict | None:
    """One pillar sentence to a row, or `None` if it is not one.

    A sentence qualifies when it carries a swab count or an alert count; the
    pillar's other prose (rings opened, households decontaminated, providers
    briefed) is left alone.
    """
    if not re.search(r"alertes?\s+de\s+d[ée]c[èe]s|corps|swab|EDS", sentence, re.I):
        return None
    alerts = first(ALERTS.search(sentence))
    swabbed = first(SWABBED.search(sentence))
    if alerts is None and swabbed is None:
        return None

    add = first(CARRIED_ADD.search(sentence))
    inside = first(CARRIED_INSIDE.search(sentence))
    construction = "none"
    carried = None
    if inside is not None:
        construction, carried = "dont (already inside)", inside
    elif add is not None:
        construction, carried = "et (added)", add
        if alerts is not None:
            alerts = alerts + add

    if swabbed is None and alerts is not None and SWABBED_ALL.search(sentence):
        swabbed = alerts

    fail = FAILURES.search(sentence)
    failures = first(fail) if fail and first(fail) is not None else (
        0 if fail else None)

    return {
        "alerts_total": alerts,
        "alerts_carried": carried,
        "alert_construction": construction,
        "bodies_reached": first(REACHED.search(sentence)),
        "bodies_swabbed": swabbed,
        "eds_done": first(EDS_DONE.search(sentence)),
        "failures": failures,
        "printed_pct": ", ".join(m.group(1) for m in PCT.finditer(sentence)) or None,
        "quote": sentence.strip()[:400],
    }


def check(row: dict) -> tuple[str, str]:
    """`(status, checks)`. A row is licensed by the document's own arithmetic.

    Where the report prints a percentage, one of the ratios this row can form
    must reproduce it to within half a point. Where it prints none, the row is
    published as `unchecked` -- present, usable, and honestly labelled -- but
    an impossible row (more bodies swabbed than alerts raised, with no
    carried-over count to explain it) is refused outright.
    """
    a, s, e = row["alerts_total"], row["bodies_swabbed"], row["eds_done"]
    r = row["bodies_reached"]
    if a is not None and s is not None and s > a and not row["alerts_carried"]:
        return "refused", "swabbed exceeds alerts with no carried-over count"

    # An identity the pillar's own sentence can carry: every alert it reached
    # either yielded a swab or was recorded as a failure. Where all three
    # numbers are printed this licenses the row without any percentage.
    f = row["failures"]
    if a is not None and s is not None and f is not None and s + f == a:
        return "ok", f"swabbed+failures={s}+{f} reproduces alerts={a}"

    if not row["printed_pct"]:
        return "ok", "unchecked (the report prints no percentage)"
    printed = [float(p.replace(",", ".")) for p in row["printed_pct"].split(", ")]
    cands: list[tuple[str, float]] = []
    for name, num, den in (("swabbed/alerts", s, a), ("eds/alerts", e, a),
                           ("swabbed/reached", s, r)):
        if num is not None and den:
            cands.append((name, 100.0 * num / den))
    hit = [f"{n}={v:.1f}%" for p in printed for n, v in cands if abs(v - p) <= 0.5]
    if hit:
        return "ok", "matches printed " + "; ".join(sorted(set(hit)))
    # A percentage that none of our ratios reproduces means we have not
    # understood the sentence. Publishing it would be a guess.
    return ("refused",
            f"printed {printed} matches none of "
            + (", ".join(f"{n}={v:.1f}" for n, v in cands) or "(no ratio formable)"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--status", required=True, type=Path)
    args = ap.parse_args()

    rows, status = [], []
    pdfs = sorted((args.pdf_dir if args.pdf_dir.is_absolute()
                   else REPO_ROOT / args.pdf_dir).glob("sitrep_*.pdf"))
    for pdf in pdfs:
        # The page's own `Date de rapportage`, not the filename -- the two
        # disagree on eleven reports and the filename is the unreliable half.
        num, date = report_key(pdf)
        if not date:
            status.append({"sitrep": num, "date": "", "n_rows": 0,
                           "n_refused": 0, "note": "no page-derived date"})
            continue
        seen: dict[str, dict] = {}
        refused = 0
        for sent, prov in sentences(text_of(pdf)):
            if not prov:
                continue
            row = parse(sent)
            if not row:
                continue
            st, why = check(row)
            if st == "refused":
                refused += 1
                continue
            row |= {"sitrep": num, "date": date, "province": prov, "checks": why}
            # One row per province-day. The pillar sometimes states the same
            # province twice -- a summary line and a detail line -- and the
            # richer of the two is the one to keep.
            filled = sum(row[k] is not None for k in
                         ("alerts_total", "bodies_swabbed", "eds_done",
                          "bodies_reached"))
            prev = seen.get(prov)
            if prev is None or filled > prev["_filled"]:
                seen[prov] = row | {"_filled": filled}
        for prov, row in seen.items():
            row.pop("_filled")
            rows.append(row)
        status.append({"sitrep": num, "date": date, "n_rows": len(seen),
                       "n_refused": refused, "note": ""})

    rows.sort(key=lambda r: (r["date"], r["province"]))
    cols = ["date", "sitrep", "province", "alerts_total", "alerts_carried",
            "alert_construction", "bodies_reached", "bodies_swabbed",
            "eds_done", "failures", "printed_pct", "checks", "quote"]
    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    st = args.status if args.status.is_absolute() else REPO_ROOT / args.status
    with st.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["sitrep", "date", "n_rows",
                                           "n_refused", "note"])
        w.writeheader()
        w.writerows(status)

    n_ref = sum(s["n_refused"] for s in status)
    print(f"  burial alerts: {len(rows)} province-day row(s) from "
          f"{len(pdfs)} report(s); {n_ref} sentence(s) refused")
    by = {}
    for r in rows:
        by[r["province"]] = by.get(r["province"], 0) + 1
    print("    " + " · ".join(f"{k} {v}" for k, v in sorted(by.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
