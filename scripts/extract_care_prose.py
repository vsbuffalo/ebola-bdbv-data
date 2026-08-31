"""The daily care ledger the reports state in words, per province.

SOURCE       The INSP situation reports' care pillar -- headed "Continuité des
             soins", "Prise en charge holistique" or "PRISE EN CHARGE
             HOLISTIQUE (PECH)" depending on the vintage. PRIMARY.
PRODUCES     One row per (report, province), in three groups of columns.

               FLOWS over the report day: `admissions` and its
               confirmed/suspected split, `admissions_readmitted`, `exits`
               (the source's `sorties`) and the four ways out of a treatment
               centre -- `exits_recovered` (guéris), `exits_noncase` (a
               suspected case discharged after testing negative),
               `exits_absconded` (évadés) and `exits_deaths` -- plus
               `exits_transferred`, a fifth route to a general hospital that
               a few reports print.

               STOCKS at the end of the report day: `census`, the patients in
               the treatment and transit centres, with its confirmed and
               suspected halves; `beds`, the installed capacity, likewise
               split; and `printed_occupancy_pct`, the occupancy the report
               itself computes from the two.

               and the CONTACT FOLLOW-UP proportion where the report prints
               it, with the pair (`contacts_followed` of
               `contacts_to_follow`) that makes it.

             `province` is one of the six affected provinces, or `Ensemble`
             -- the word the reports' own tables use for the all-provinces
             column -- for the whole-response summary sentence and the
             national contact-follow-up figure.
FITTED       No. Nothing here is published as an observation stream; this is an
             extraction into data/build/series/. The confirmed census is the
             quantity a fit would want -- it separates the rate at which
             infectious people are confirmed and isolated from the rate at
             which they leave infectiousness unconfirmed, which the case and
             death series alone cannot -- but publishing it as a stream is a
             contract change and a separate decision.
VALIDATED BY the passage's own arithmetic, first and mainly. Every check a
             row's numbers make available is run and written into `checks`,
             pass or fail, so a disagreement can be adjudicated from the CSV
             without re-running anything; the passage travels in `sentence`
             for the same reason. The CLOSURES, which can only hold if the
             reading is right, are

               census_split        confirmed + suspected  =  census
               beds_split          confirmed + suspected beds  =  beds
               occupancy           census / beds  reproduces the printed %
               occupancy_confirmed confirmed / confirmed beds  reproduces its %
               occupancy_suspect   suspected / suspected beds  reproduces its %
               exits_split         recovered + non-case + absconded + died
                                     + transferred  =  exits
               admissions_split    confirmed + suspected admissions = admissions
               contacts_rate       followed / to follow reproduces its %

             and the BOUNDS, which pass on almost any reading but catch the
             source contradicting itself, are `confirmed_le_census`,
             `deaths_conf_le_deaths`, `recovered_le_exits` and
             `exits_over_total`. `licensed` is true where a closure passed and
             nothing failed; `census_licensed` says the same of the census
             alone, because a row whose exit decomposition disagrees with
             itself can still carry a census that closes twice over.

             INDEPENDENTLY, against the front-page ISOLEMENT/CTE tile, which
             this repository already reads by a different route. Over the 27
             report days where both exist the whole-response summary sentence
             gives the same national census as the tile on 25 and the same
             confirmed census on all 24 it prints, and both disagreements fall
             on days this route had already flagged: the sentence's own split
             does not sum to its own total there, and the tile agrees with the
             split. Agreement is evidence about transcription rather than
             about the counts -- it is one organisation's figures on one page,
             read twice -- but a wrong reading could not produce it.

WHY THIS EXISTS. The front-page tile stops after sitrep 080 (2 August); the
prose carries the same quantities, per province, to the end of the archive.

WHY THE PRINTED PERCENTAGE IS THE LOAD-BEARING CHECK. The failure mode of this
source is not a misread number, it is a STALE one: the report reuses the
previous day's clause and edits only part of it. Sitrep 097 prints the
Haut-Uélé sentence of sitrep 096 verbatim -- "53 patients sont pris en charge
(36 confirmés et 17 suspects) ... 130 lits" -- but with the occupancy changed
from 40,8 % to 44,6 %; 53/130 is 40,8 %, so the census is the stale half. The
same report prints the Tshopo census against 14 beds while carrying forward the
percentage computed on the previous day's 12. Neither is visible without the
percentage, and both are caught by it.

WHY SEGMENTS RATHER THAN SENTENCES. The wording varies enormously across
vintages -- "l'occupation atteint 438 patients pour 973 lits (45 %), soit 179
confirmés sur 496 lits (36,1 %)", "Ainsi, 528 patients sont hospitalisés pour
965 lits", "portent à 4 le nombre de patients isolés (1 confirmé et 3
suspects)", "471 patients en isolement (302 confirmés, 169 suspects) sur 833
lits" -- and a province's figures are spread over several sentences of one
bullet. What is stable is that each province's bullet opens with its name and
runs to the next province's. So each province mention that OPENS a passage --
one preceded by a bullet or the end of a sentence, not one used mid-clause --
begins a segment that ends at the next such mention, and the fields are
harvested from the segment.

WHAT IS DELIBERATELY NOT READ. The care pillar's second subsection, `Défis`, is
prose about problems rather than a ledger, and it names absconders attributed
to individual centres ("Trois patients se sont évadés en Ituri (1 à Kigonze et
2 à Nizi)", sitrep 097). Those are a subset of the day's, counted a second way,
and adding them to the bullet's own figure would double count wherever both
appear -- sitrep 099 prints 14 in both places. The section therefore ends at
that heading, and three further report-days' absconder counts are left unread.
The patient-movement TABLE (sitreps 018-058, and TABLEAU 6 in 059-080) is not
read either: it is a richer source of exactly this ledger, but reading a table
with prose patterns is not reading it, and a reader for it belongs in its own
script.

STOCKS AND FLOWS ARE NOT MIXED. The reports also print CUMULATIVE care figures
in the same bullets -- "235 admissions cumulées", "le cumul provincial des
guéris atteint 1 000", "cumul des évadés : 22", "Cumul de 142 cas confirmés
admis en CTE/CT pour 48 décès". Those are stocks over the whole outbreak and
putting them in a daily column is the defect this rule exists to prevent, so
cumulative clauses are excised from the harvest pool before any pattern runs,
and an `admissions` reading immediately followed by "cumulées" is refused.

THE PDF IS READ IN READING ORDER, NOT LAYOUT ORDER. Sitreps 059-083 are set in
two columns and `pdftotext -layout` interleaves them line by line, welding the
community-engagement column onto the care column mid-sentence. Plain
`pdftotext` follows the text objects and keeps each column's paragraphs whole.
The rest of the pipeline uses `-layout` because it reads TABLES, where the
column positions are the structure; this route reads prose, where they are not.
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
from lib.archive import held_pdfs, report_skipped  # noqa: E402

#: Keyed on the name with accents, spaces and hyphens removed, because the
#: reports print all of them: `Haut-Uélé`, `Haut Uélé` and -- where a line
#: break was closed up -- `HautUélé` and `SudKivu`, all in the same vintage.
PROVINCES = {
    "ituri": "Ituri", "nordkivu": "Nord-Kivu", "sudkivu": "Sud-Kivu",
    "hautuele": "Haut-Uélé", "basuele": "Bas-Uélé", "tshopo": "Tshopo",
}
PROV_RE = re.compile(r"\b(Ituri|Nord[-\s]?Kivu|Sud[-\s]?Kivu"
                     r"|Haut[-\s]?U[ée]l[ée]|Bas[-\s]?U[ée]l[ée]|Tshopo)\b", re.I)

#: The care pillar's heading, across the three vintages that carry one.
SECTION = re.compile(r"Continuit[ée]\s+des\s+soins"
                     r"|PRISE\s+EN\s+CHARGE\s+HOLISTIQUE"
                     r"|Prise\s+en\s+charge\s+holistique", re.I)
#: Where it stops. `Défis` is the care pillar's own second subsection and it is
#: PROSE ABOUT PROBLEMS, not a ledger: it says things like "Trois patients se
#: sont évadés en Ituri" and "Deux patients se sont évadés du CTE de Bambu
#: faute de nourriture", which are a subset of the day's absconders attributed
#: to named centres. Harvesting there would double-count them against the
#: bullet's own `évadés` figure, so the section ends at the heading.
SECTION_END = re.compile(
    r"D[ée]fis\b|RECHERCHE|COMMUNICATION\s+SUR\s+LES\s+RISQUES|VACCINATION"
    r"|LOGISTIQUE\b|SURVEILLANCE\b|CONTINUITE\s+DES\s+SERVICES", re.I)

#: A province's bullet can run long -- sitrep 093's Ituri bullet is 900
#: characters -- so the cap is generous and the real boundary is the next
#: province mention that OPENS a passage.
SEGMENT_CAP = 1300

#: A PROVINCE NAME IS ONLY A SEGMENT BOUNDARY WHERE IT OPENS ONE. Sitrep 068
#: writes "→ Ituri : 24 nouveaux guéris dont 23 en Ituri et 1au Nord Kivu, 70
#: admissions, 556 patients en isolement, ...": the mid-sentence "Nord Kivu"
#: cut the Ituri bullet in two and filed Ituri's census of 556 under Nord-Kivu,
#: which held 175 that day. So a mention opens a passage only where what
#: precedes it is a bullet or the end of a sentence, allowing for the
#: preposition the name is introduced with ("• En Ituri,", "→ Nord-Kivu :",
#: "• À la Tshopo,"). Sitrep 087's "spécifiquement en Ituri" and sitrep 050's
#: "dans la province du NordKivu" fail the test, as they should.
LEAD_IN = re.compile(r"\b(?:en|au|aux|[àa]\s+la|dans\s+l[ae]|du|de\s+la|le|la)\s*$",
                     re.I)
OPENER = re.compile(r"(?:^|[→➔•●▪.;:!?])\s*$")
#: "→ Haut-Uélé et Tshopo : 2 confirmés ont été admis ... pour 37 malades
#: hospitalisés" (sitrep 079). One passage, two provinces, one set of numbers:
#: there is no way to split 37 between them, and filing it under either is a
#: wrong number, so both are refused.
JOINED = re.compile(r"^\s*(?:et|/|,)\s*(?:l[ae]\s+)?"
                    r"(?:Ituri|Nord[-\s]?Kivu|Sud[-\s]?Kivu|Haut[-\s]?U[ée]l[ée]"
                    r"|Bas[-\s]?U[ée]l[ée]|Tshopo)\b", re.I)


def opens_passage(block: str, at: int) -> bool:
    """Does the province mention at `at` begin a passage about that province?"""
    before = block[max(0, at - 24):at]
    return bool(OPENER.search(LEAD_IN.sub("", before)))

CARE_WORD = re.compile(r"hospitalis|isolement|isol[ée]s?\b|lits?\b|admissions?"
                       r"|sorties?\b|[ée]vad|gu[ée]ri|occupation|non-?cas"
                       r"|pris\s+en\s+charge", re.I)

#: THE PATIENT-MOVEMENT TABLE IS NOT PROSE, and on several reports it sits
#: inside the care section, so a province mention in it opens a segment whose
#: "sentence" is a row of flattened cells: "Sud-Kivu 6 0 Ensemble 233 62
#: Décédés (Suspects/Conf.) 6 0 0 6 Non-cas / Guéris 17 0 0 17 ... Total
#: sorties 37 0 0 37". Every number in such a segment belongs to a column this
#: reader cannot see, and sitrep 021 read 5 186 exits out of one. The table is
#: a legitimate source and a richer one -- it prints the same ledger in
#: columns, per province, on the reports that carry it -- but reading a table
#: by prose patterns is not reading it, so these segments are refused here.
TABLE_ROW = re.compile(r"Patients?\s+au\s+lit|Total\s+sorties|Total\s+admissions"
                       r"|\(Suspects?\s*/\s*Conf|Indicateur\b|\(J-1\)"
                       r"|Fin\s+J\)|dont\s+confirm[ée]s\s+\(|Tx\s+d.occup", re.I)
#: and its shape, for the vintages whose header words this reader has not seen:
#: four or more bare integers in a row is a flattened row of cells, never a
#: French sentence. Sitreps 013 and 014 put "10 39 6 2 101" into a Nord-Kivu
#: segment that then reported thirteen recoveries and four transfers.
DIGIT_RUN = re.compile(r"(?:\b\d{1,4}\b[    ]){3,}\b\d{1,4}\b")

# --------------------------------------------------------------------------
# Normalising the harvest pool
# --------------------------------------------------------------------------

#: French spells small counts in words, and the reports mix the two freely
#: within one bullet: "une nouvelle admission de cas suspect ... et une sortie
#: de guérison portent à 4 le nombre de patients isolés". `aucun` is a printed
#: ZERO and is the only way several reports state that nobody absconded --
#: sitrep 100's "dont 14 guéris et aucun évadé" is the day's absconder count,
#: not a missing value, and dropping it would bias the absconder series up.
WORDS = {
    "aucun": 0, "aucune": 0, "un": 1, "une": 1, "deux": 2, "trois": 3,
    "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
    "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16, "vingt": 20,
}
WORD_RE = re.compile(r"\b(" + "|".join(WORDS) + r")\b", re.I)
#: "Vingt-et-un (21) décès", "Quinze (15) patients": the digits are already
#: there, so the word is dropped rather than translated.
WORD_THEN_DIGITS = re.compile(r"\b[A-Za-zÀ-ÿ]+(?:-[A-Za-zÀ-ÿ]+)*\s*\((\d+)\)")

#: A parenthesised cumulative first -- "(cumul des évadés : 22)" sits inside a
#: clause whose other numbers are the day's, so excising to the clause end
#: would take them with it.
CUMUL_PAREN = re.compile(r"\([^()]*cumul\w*[^()]*\)", re.I)
#: then the clause tail. Every cumulative idiom the reports use puts its number
#: AFTER the word: "portant le cumul provincial à 374", "le cumul des guéris
#: s'élève à 955", "Cumul de 142 cas confirmés admis en CTE/CT pour 48 décès",
#: "Au total, 102 PPLs sont confirmés parmi lesquels, 33 décès et 36 guéris",
#: "Au total de 392 décès sont enregistré". The last two are outbreak-to-date
#: figures for a subpopulation, and read as the day's they put 392 deaths in a
#: Nord-Kivu row for 3 July.
STOCK_TAIL = re.compile(
    r"(?:le\s+|un\s+|du\s+)?\b(?:cumul\w*|au\s+total|depuis\s+le\s+d[ée]but)"
    r"\b[^;.]*", re.I)
#: A clause reporting the in-facility case fatality is cumulative even when it
#: does not say so. Sitrep 079 writes "→ Nord-Kivu : 155 cas confirmés admis en
#: CTE/CT pour 55 décès, soit une mortalité intra-CTE de 35 %" with no
#: `cumul` anywhere, and 55 outbreak-to-date deaths entered the daily column
#: for 1 August -- a day on which the same bullet reports four. The ratio is
#: the tell: a deaths-over-admissions percentage is a stock over a stock.
MORTALITY_CLAUSE = re.compile(r"[^;.]*mortalit[ée]\s+intra[^;.]*", re.I)

#: French thousands separators: ASCII space, no-break, narrow no-break.
_TH = "[    ]"
#: wrapped non-capturing so `({NUM})` is exactly one group wherever it is
#: interpolated, and a bare `{NUM}` cannot split the pattern it sits in.
NUM = rf"(?:\d{{1,3}}(?:{_TH}\d{{3}})+|\d+)"


def _int(s: str) -> int:
    return int(re.sub(r"\D", "", s))


def _norm_prov(s: str) -> str:
    t = unicodedata.normalize("NFKD", s)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return PROVINCES[re.sub(r"[^a-z]", "", t.lower())]


def pool(seg: str) -> str:
    """The segment with cumulative clauses removed and number words in digits.

    The stored `sentence` stays whole: what licensed or refused a row has to be
    auditable against the page, and a pre-processed string is not the page.
    """
    p = CUMUL_PAREN.sub(" ", seg)
    p = MORTALITY_CLAUSE.sub(" ", p)
    p = STOCK_TAIL.sub(" ", p)
    p = WORD_THEN_DIGITS.sub(lambda m: " " + m.group(1) + " ", p)
    return WORD_RE.sub(lambda m: str(WORDS[m.group(1).lower()]), p)


# --------------------------------------------------------------------------
# The fields, each anchored on the noun that names it
# --------------------------------------------------------------------------
#
# Every pattern below binds a number to the WORD THAT SAYS WHAT IT COUNTS.
# That is the difference from the laboratory route, where the numbers carry no
# nouns and a combinatoric licence has to choose between them: here
# "528 patients sont hospitalisés" cannot be read as anything but a census, and
# the risk is not misassignment but the source printing a stale figure -- which
# is what the closures catch.

CENSUS = [
    # "l'occupation atteint 438 patients pour 973 lits"
    rf"occupation\s+(?:atteint|est\s+de|de)\s+({NUM})\s+(?:patients?|malades?)",
    # "L'occupation ... atteint 488 lits sur 833 (59 %)" -- occupied beds ARE
    # the census; the second number is the capacity.
    rf"occupation[^.;]{{0,60}}?atteint\s+({NUM})\s+lits\s+sur\s+{NUM}",
    # "528 patients sont hospitalisés", "167 malades sont hospitalisés",
    # "196 malades en isolement en fin de journée", "471 patients en isolement"
    rf"({NUM})\s+(?:patients?|malades?)\s+(?:y\s+)?(?:sont|est|restent|reste"
    rf"|[ée]taient|sortis)?\s*(?:en\s+)?(?:hospitalis[ée]s?|hospitalisation"
    rf"|isolement|isol[ée]s?|pris\s+en\s+charge)",
    # "portent à 4 le nombre de patients isolés", "porte à 5 le nombre de
    # patients isolés", "portant à 8 le nombre de patients en isolement"
    rf"port(?:ent|e|ant)\s+[àa]\s+({NUM})[,\s]+le\s+nombre\s+de\s+patients?",
    # "53 patients sont pris en charge", "8 patients sont en isolement au CTE"
    rf"({NUM})\s+patients?\s+sont\s+en\s+isolement",
    # "Quatre patients occupent les 20 lits disponibles (20 %)"
    rf"({NUM})\s+patients?\s+occupent",
]
#: A census stated only for suspected patients -- "29 cas suspects restent
#: hospitalisés", "11 cas suspects sont suivis en hospitalisation". The
#: confirmed count is NOT inferred to be zero: the sentence does not say so,
#: and on several of these days the same report says elsewhere that the
#: province holds no confirmed case. Inferring it here would put an unstated
#: number in a column the model would read as printed.
CENSUS_SUSPECT_ONLY = [
    rf"({NUM})\s+cas\s+suspects?\s+(?:actuellement\s+|toujours\s+)?"
    rf"(?:restent\s+|sont\s+|y\s+sont\s+)?(?:actuellement\s+)?"
    rf"(?:suivis\s+(?:en\s+|[àa]\s+l.)?)?(?:hospitalis[ée]s?|hospitalisation"
    rf"|isolement|isol[ée]s?)",
    rf"({NUM})\s+suspects?\s+isol[ée]s",
]
#: "(179 confirmés ... 259 suspects)", "(173 suspects et 32 confirmés)",
#: "dont 20 confirmés et 161 suspects", "302 confirmés, 169 suspects",
#: "(5 cas confirmés et 3 suspects)". Both orders occur; sitrep 083 prints the
#: suspects first.
SPLIT_CS = re.compile(rf"({NUM})\s+(?:cas\s+)?confirm[ée]s?[\s,]+(?:et\s+)?"
                      rf"({NUM})\s+(?:cas\s+)?suspects?", re.I)
SPLIT_SC = re.compile(rf"({NUM})\s+(?:cas\s+)?suspects?[\s,]+(?:et\s+)?"
                      rf"({NUM})\s+(?:cas\s+)?confirm[ée]s?", re.I)
#: "173 patients hospitalisés, dont 17 confirmés" -- the confirmed half alone,
#: with no suspected count to close it against. Kept because the confirmed
#: census is the quantity this extraction exists for; unlicensed, and the
#: `checks` column says so by carrying no closure for it.
SPLIT_CONF_ONLY = re.compile(rf"dont\s+({NUM})\s+(?:cas\s+)?confirm[ée]s?", re.I)
#: A census stated for the confirmed alone: "2 confirmés hospitalisés".
CENSUS_CONFIRMED_ONLY = [
    rf"({NUM})\s+(?:cas\s+)?confirm[ée]s?\s+(?:sont\s+)?"
    rf"(?:hospitalis[ée]s?|isol[ée]s?|en\s+isolement|en\s+hospitalisation)",
]

BEDS = [
    # "pour 965 lits", "sur 833 lits", "pour 78 lits montés"
    rf"(?:pour|sur)\s+({NUM})\s+lits",
    # "atteint 488 lits sur 833 (59 %)"
    rf"atteint\s+{NUM}\s+lits\s+sur\s+({NUM})",
    # "portant la capacité provinciale à 130 lits", "la capacité installée de
    # prise en charge atteint 833 lits"
    rf"capacit[ée][^.;]{{0,60}}?(?:[àa]|atteint)\s+({NUM})\s+lits",
    # "Quatre patients occupent les 20 lits disponibles (20 %)"
    rf"occupent\s+(?:les\s+)?({NUM})\s+lits",
]
#: "soit 179 confirmés sur 496 lits (36,1 %) et 259 suspects sur 477 lits
#: (54,3 %)": census, beds and rate for one side of the centre, in one clause.
BEDS_CONF = rf"({NUM})\s+confirm[ée]s?\s+sur\s+({NUM})\s+lits"
BEDS_SUSP = rf"({NUM})\s+suspects?\s+sur\s+({NUM})\s+lits"
#: "pour 84 lits montés (46 pour les confirmés et 38 pour les suspects)": the
#: same split of the CAPACITY only. Anchored on `lits` and read as one
#: parenthetical, because the bare "N pour les suspects" is not a bed count
#: anywhere else -- sitrep 082's "et un pour les suspects (Logo, 150 %)" counts
#: SATURATED CENTRES, and read loosely it put one suspect bed in the Ituri row.
BEDS_SPLIT_LITS = re.compile(
    rf"lits(?:\s+mont[ée]s)?\s*\(\s*({NUM})\s+pour\s+les\s+confirm[ée]s?"
    rf"\s+et\s+({NUM})\s+pour\s+les\s+suspects?\s*\)", re.I)

ADMISSIONS = [
    # The negative lookahead is the whole stock/flow guard for this field:
    # "235 admissions cumulées" is the outbreak total, "94 nouvelles
    # admissions" is the day's. `\b` before it is load-bearing -- without it
    # the optional plural lets the match end at "admission" and the lookahead
    # then reads "s cumulées", which is not the word it is looking for, and
    # sitrep 089's cumulative 219 entered the daily column.
    rf"({NUM})\s+(?:nouvelles?\s+)?admissions?\b(?!\s+cumul)",
    rf"({NUM})\s+admissions?\s+du\s+jour",
]
#: "79 nouvelles admissions toutes suspectes et 11 réadmissions": a patient
#: coming BACK is a distinct flow, and folding it into admissions would double
#: count someone the census already holds. Kept in its own column, and kept out
#: of the admissions pattern -- which is why that pattern does not allow the
#: `ré` prefix.
READMISSIONS = [rf"({NUM})\s+r[ée]admissions?\b"]
#: "(5 confirmés et 14 suspects)" after an admissions count, and the other
#: shape "4 admissions de confirmés et 18 de suspects".
ADM_SPLIT_PAREN = re.compile(
    rf"admissions?[^.;()]{{0,60}}?\(\s*({NUM})\s+confirm[ée]s?[^)]*?"
    rf"({NUM})\s+suspects?", re.I)
ADM_SPLIT_DE = re.compile(
    rf"({NUM})\s+admissions?\s+de\s+(?:cas\s+)?confirm[ée]s?\s+et\s+({NUM})"
    rf"\s+(?:de\s+)?(?:cas\s+)?suspects?", re.I)

#: "4 sorties non-cas" is one CATEGORY of exit, not the day's total, and read
#: as a total it makes the decomposition exceed it (sitrep 094: 4 exits, of
#: which 4 non-cases and 1 death). The lookahead keeps the two apart.
EXITS = [rf"({NUM})\s+sorties?\b(?!\s+non-?\s?cas)"]
#: `nouv\w+` rather than `nouveaux?`: the July vintage is typeset with an
#: accent fault that prints "nouvéaux", and an exact spelling dropped sitrep
#: 063's twenty recoveries.
RECOVERED = [rf"({NUM})\s+(?:nouv\w+\s+)?gu[ée]ris\b",
             rf"({NUM})\s+(?:nouv\w+\s+)?gu[ée]ri\b"]
ABSCONDED = [rf"({NUM})\s+[ée]vad[ée]s?\b"]
NONCASE = [rf"({NUM})\s+(?:cas\s+|suspects?\s+)?non-?\s?cas\b",
           rf"({NUM})\s+sorties?\s+non-?\s?cas\b"]
DEATHS = [rf"({NUM})\s+d[ée]c[èe]s\b"]
DEATHS_CONF = [rf"d[ée]c[èe]s[^.;]{{0,30}}?dont\s+({NUM})\s+confirm[ée]s?",
               rf"({NUM})\s+d[ée]c[èe]s\s+confirm[ée]s?"]
TRANSFERRED = [rf"({NUM})\s+transferts?\b", rf"({NUM})\s+transf[ée]r[ée]s?\b"]

#: The percentage that belongs to the bed count is the first one printed after
#: it: "(69,2 %)", ", soit 81,1 % d'occupation", ", soit un taux d'occupation
#: global de 54,7%", " montés (67,9 %)", " (occupation 40,8 %)". A later
#: percentage in the same bullet is a different quantity -- the per-centre
#: saturation figures, or the share of patients fed -- so the window is short.
PCT = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*%")
PCT_WINDOW = 70
#: One vintage puts the rate BEFORE the pair it is computed from -- "pour un
#: taux d'occupation global de 89,1 % (766 patients pour 860 lits)" -- so where
#: nothing follows the bed count, a named occupancy rate anywhere in the
#: passage is taken instead. Named, not any percentage: the same passages carry
#: per-centre saturation figures and the share of patients fed.
OCC_NAMED = re.compile(r"taux\s+d.occupation[^%]{0,50}?"
                       r"(\d{1,3}(?:[.,]\d{1,2})?)\s*%", re.I)


def _first(patterns: list[str], text: str) -> tuple[int, int, int] | None:
    """The earliest match of any pattern, as (value, start, end).

    Earliest rather than first-pattern-wins: the patterns are alternative
    WORDINGS of one field, not a preference order, and taking whichever the
    report happened to use keeps the reading independent of the list's order.
    """
    best = None
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m and (best is None or m.start() < best[1]):
            best = (_int(m.group(1)), m.start(), m.end())
    return best


def _val(patterns: list[str], text: str) -> int | None:
    got = _first(patterns, text)
    return None if got is None else got[0]


def _distinct(patterns: list[str], text: str) -> set[int]:
    """Every distinct value the patterns find, for the ambiguity rule below."""
    return {_int(m.group(1)) for pat in patterns
            for m in re.finditer(pat, text, re.I)}


# --------------------------------------------------------------------------
# Harvest
# --------------------------------------------------------------------------

FIELDS = ("admissions", "admissions_confirmed", "admissions_suspect",
          "admissions_readmitted",
          "exits", "exits_recovered", "exits_noncase", "exits_absconded",
          "exits_deaths", "exits_deaths_confirmed", "exits_transferred",
          "census", "census_confirmed", "census_suspect",
          "beds", "beds_confirmed", "beds_suspect",
          "printed_occupancy_pct", "printed_occupancy_confirmed_pct",
          "printed_occupancy_suspect_pct")

#: AMBIGUITY IS REFUSAL UNLESS A CLOSURE PICKS THE VALUE OUT. A bullet can
#: state a field twice with different numbers -- sitrep 053 writes "Deux (2)
#: nouvelles admissions concernaient des PPL et sont incluses dans les 67
#: admissions enregistrées au cours de la journée", where the subset is printed
#: first and the earliest-match rule takes it. Where the passage also prints a
#: closure that USES that field and the closure holds, the arithmetic has
#: chosen between the candidates and the value stands; where it does not, the
#: field is dropped and the refusal is counted.
RESOLVED_BY = {"admissions": ("admissions_split",),
               "exits": ("exits_split",),
               "census": ("census_split", "occupancy")}

#: The stocks and gross flows: a passage that states one of these is reporting
#: the ledger, whatever else it says.
GROSS = ("census", "census_confirmed", "census_suspect", "admissions",
         "admissions_confirmed", "exits", "beds")
#: and the components, which a passage can mention without reporting anything.
COMPONENTS = RECOVERED + DEATHS + ABSCONDED + NONCASE + TRANSFERRED


def harvest(seg: str) -> dict:
    """Every field the segment states, with no judgement about whether they
    agree; `checks` decides that afterwards."""
    p = pool(seg)
    r: dict = {f: None for f in FIELDS}

    adm = _first(ADMISSIONS, p)
    r["admissions"] = None if adm is None else adm[0]
    m = ADM_SPLIT_PAREN.search(p)
    if m:
        r["admissions_confirmed"] = _int(m.group(1))
        r["admissions_suspect"] = _int(m.group(2))
    else:
        m = ADM_SPLIT_DE.search(p)
        if m:
            r["admissions_confirmed"] = _int(m.group(1))
            r["admissions_suspect"] = _int(m.group(2))
            # "4 admissions de confirmés et 18 de suspects" states the two
            # halves and NEVER their sum, so there is no printed total here.
            # The admissions pattern matches the confirmed half of it, and
            # carrying that forward published the confirmed count as the day's
            # admissions on sitreps 079, 081, 082 and 083.
            if adm is not None and m.start() <= adm[1] < m.end():
                r["admissions"] = None

    r["admissions_readmitted"] = _val(READMISSIONS, p)

    r["exits"] = _val(EXITS, p)
    r["exits_recovered"] = _val(RECOVERED, p)
    r["exits_noncase"] = _val(NONCASE, p)
    r["exits_absconded"] = _val(ABSCONDED, p)
    r["exits_deaths"] = _val(DEATHS, p)
    r["exits_deaths_confirmed"] = _val(DEATHS_CONF, p)
    r["exits_transferred"] = _val(TRANSFERRED, p)

    census = _first(CENSUS, p)
    if census is not None:
        r["census"] = census[0]
    else:
        only = _first(CENSUS_SUSPECT_ONLY, p)
        if only is not None:
            r["census_suspect"] = only[0]
        conf = _first(CENSUS_CONFIRMED_ONLY, p)
        if conf is not None:
            r["census_confirmed"] = conf[0]

    # The confirmed/suspected split is read from the clause that FOLLOWS the
    # census, not from anywhere in the bullet: the same shape describes the
    # day's admissions ("5 confirmés et 14 suspects") and would otherwise be
    # picked up as the census split on every report that prints both.
    if census is not None:
        # THE SPLIT MUST BE THE CENSUS'S OWN. The tail stops at the first word
        # that starts a different quantity, because "553 patients en isolement,
        # 17 décès parmi les sorties dont 12 confirmés" (sitreps 066 and 067)
        # otherwise reads the twelve confirmed DEATHS as a confirmed census of
        # twelve, on a day the province held 553 patients.
        tail = p[census[2]:census[2] + 160]
        cut = re.search(r"d[ée]c[èe]s|sorties?\b|admissions?\b|gu[ée]ri", tail, re.I)
        if cut:
            tail = tail[:cut.start()]
        mc, ms = SPLIT_CS.search(tail), SPLIT_SC.search(tail)
        if mc and (not ms or mc.start() <= ms.start()):
            r["census_confirmed"], r["census_suspect"] = _int(mc.group(1)), _int(mc.group(2))
        elif ms:
            r["census_suspect"], r["census_confirmed"] = _int(ms.group(1)), _int(ms.group(2))
        else:
            mo = SPLIT_CONF_ONLY.search(tail)
            if mo:
                r["census_confirmed"] = _int(mo.group(1))

    beds = _first(BEDS, p)
    if beds is not None:
        r["beds"] = beds[0]
        m = PCT.search(p[beds[2]:beds[2] + PCT_WINDOW]) or OCC_NAMED.search(p)
        if m:
            r["printed_occupancy_pct"] = float(m.group(1).replace(",", "."))
    else:
        # The rate does not need the bed count. Some passages state occupancy
        # in words and print no capacity at all, and reading the rate only as
        # a companion to a bed count dropped them: four province-days, among
        # them the whole-response figure on 13-15 July.
        #
        # This does NOT recover the days the reports put Nord-Kivu over
        # capacity in July -- 123% to 143% between 16 July and 1 August. Those
        # fail earlier, in passage segmentation: sitrep 077 yields no
        # Nord-Kivu care row at all, so there is no passage for this to read.
        # That is a separate defect and it is still open.
        #
        # Only the NAMED rate is taken here, never a bare percentage: with no
        # bed count to anchor a window, the passage's other percentages -- the
        # share of patients fed, per-centre saturation -- are equally close and
        # nothing would tell them apart. `beds` stays null, because the source
        # did not print one.
        m = OCC_NAMED.search(p)
        if m:
            r["printed_occupancy_pct"] = float(m.group(1).replace(",", "."))

    # "179 confirmés sur 496 lits (36,1 %)" states the confirmed census, its
    # beds and its rate in one clause -- three numbers that check each other.
    for pat, cen_key, bed_key, pct_key in (
            (BEDS_CONF, "census_confirmed", "beds_confirmed",
             "printed_occupancy_confirmed_pct"),
            (BEDS_SUSP, "census_suspect", "beds_suspect",
             "printed_occupancy_suspect_pct")):
        m = re.search(pat, p, re.I)
        if not m:
            continue
        if r[cen_key] is None:
            r[cen_key] = _int(m.group(1))
        r[bed_key] = _int(m.group(2))
        mm = PCT.search(p[m.end():m.end() + 24])
        if mm:
            r[pct_key] = float(mm.group(1).replace(",", "."))
    m = BEDS_SPLIT_LITS.search(p)
    if m:
        r["beds_confirmed"] = r["beds_confirmed"] or _int(m.group(1))
        r["beds_suspect"] = r["beds_suspect"] or _int(m.group(2))
    return r


def pct_ok(num: int, den: int, printed: float) -> bool:
    """Does num/den reproduce the printed percentage?

    Same tolerance rule as the laboratory route, and for the same reason: the
    source both rounds and truncates, so one decimal place gets 0.15 and a
    bare integer percent gets 0.55.
    """
    if den == 0:
        return False
    tol = 0.55 if float(printed).is_integer() else 0.15
    return abs(100.0 * num / den - printed) <= tol


def checks(r: dict) -> list[tuple[str, bool]]:
    """Every closure the row's own numbers make available, pass or fail."""
    out: list[tuple[str, bool]] = []
    if r["census"] is not None and None not in (r["census_confirmed"], r["census_suspect"]):
        out.append(("census_split",
                    r["census_confirmed"] + r["census_suspect"] == r["census"]))
    if r["beds"] is not None and None not in (r["beds_confirmed"], r["beds_suspect"]):
        out.append(("beds_split",
                    r["beds_confirmed"] + r["beds_suspect"] == r["beds"]))
    if None not in (r["census"], r["beds"], r["printed_occupancy_pct"]):
        out.append(("occupancy",
                    pct_ok(r["census"], r["beds"], r["printed_occupancy_pct"])))
    if None not in (r["census_confirmed"], r["beds_confirmed"],
                    r["printed_occupancy_confirmed_pct"]):
        out.append(("occupancy_confirmed",
                    pct_ok(r["census_confirmed"], r["beds_confirmed"],
                           r["printed_occupancy_confirmed_pct"])))
    if None not in (r["census_suspect"], r["beds_suspect"],
                    r["printed_occupancy_suspect_pct"]):
        out.append(("occupancy_suspect",
                    pct_ok(r["census_suspect"], r["beds_suspect"],
                           r["printed_occupancy_suspect_pct"])))
    # THE EXIT DECOMPOSITION IS A CHECK ONLY WHEN IT IS COMPLETE. Most reports
    # name a subset -- "87 sorties, dont 14 guéris et aucun évadé" -- and a
    # subset is SUPPOSED to fall short of the total, so scoring it as a failed
    # closure would mark two thirds of the rows unlicensed for saying less
    # than everything. The four ways out of a CTE are recovery, discharge as a
    # non-case, absconding and death; a transfer to a general hospital is a
    # fifth the source prints occasionally and is optional here. Where all
    # four are printed the sum must be the total; where fewer are, the only
    # thing the arithmetic can still refute is a sum that EXCEEDS it.
    parts = (r["exits_recovered"], r["exits_noncase"], r["exits_absconded"],
             r["exits_deaths"])
    total = sum(x or 0 for x in parts) + (r["exits_transferred"] or 0)
    if r["exits"] is not None:
        if all(x is not None for x in parts):
            out.append(("exits_split", total == r["exits"]))
        elif any(x is not None for x in parts) and total > r["exits"]:
            out.append(("exits_over_total", False))
    if r["admissions"] is not None and None not in (r["admissions_confirmed"],
                                                    r["admissions_suspect"]):
        out.append(("admissions_split",
                    r["admissions_confirmed"] + r["admissions_suspect"]
                    == r["admissions"]))
    # A PART CANNOT EXCEED ITS WHOLE, and where it does the report has printed
    # two numbers that cannot both be about the same day. Sitrep 068 writes
    # "16 décès parmi les sorties dont 68 confirmés"; sixty-eight confirmed
    # deaths among sixteen is not a reading of anything, and this is the only
    # check that passage offers.
    for part, whole, name in (("census_confirmed", "census", "confirmed_le_census"),
                              ("exits_deaths_confirmed", "exits_deaths",
                               "deaths_conf_le_deaths"),
                              ("exits_recovered", "exits", "recovered_le_exits")):
        if None not in (r[part], r[whole]):
            out.append((name, r[part] <= r[whole]))
    return out


#: A CLOSURE is an equality or a printed ratio that the row's own numbers must
#: reproduce; it can only hold if the reading is right, so passing one licenses
#: the row. The rest are BOUNDS -- "a part is no larger than its whole" -- which
#: are worth recording because they catch the source contradicting itself, but
#: which pass on almost any reading and license nothing.
CLOSURES = frozenset({"census_split", "beds_split", "occupancy",
                      "occupancy_confirmed", "occupancy_suspect",
                      "exits_split", "admissions_split", "contacts_rate"})


#: The closures the CENSUS takes part in. The confirmed census is the reason
#: this extraction exists, and a row whose exit decomposition disagrees with
#: itself can still carry a census that closes twice over -- so the census gets
#: its own verdict rather than being condemned by a neighbour's failure.
CENSUS_CLOSURES = frozenset({"census_split", "occupancy", "occupancy_confirmed",
                             "occupancy_suspect"})


def licensed(cs: list[tuple[str, bool]]) -> bool:
    """Every check this row offered passed, and at least one was a closure."""
    return (any(ok and n in CLOSURES for n, ok in cs)
            and all(ok for _, ok in cs))


def census_licensed(cs: list[tuple[str, bool]]) -> bool:
    rel = [(n, ok) for n, ok in cs if n in CENSUS_CLOSURES]
    return bool(rel) and all(ok for _, ok in rel)


def score(cs: list[tuple[str, bool]]) -> tuple[int, int, int]:
    """How well a segment's numbers hang together, for choosing between two
    passages that both claim to describe one province on one day. Closures
    outrank bounds, and any failure counts against."""
    return (sum(ok and n in CLOSURES for n, ok in cs),
            sum(ok and n not in CLOSURES for n, ok in cs),
            -sum(not ok for _, ok in cs))


# --------------------------------------------------------------------------
# The whole-response summary sentence
# --------------------------------------------------------------------------
#
# Sitreps 063 to 080 close the care section with one sentence that states the
# ledger for the WHOLE RESPONSE, not for a province: "Au total, 766 patients
# étaient en isolement, dont 278 cas confirmés et 488 cas suspects, pour un
# taux d'occupation global de 89,1 % (766 patients pour 860 lits), pour 893
# admissions et 127 sorties (21 guéris, 24 décès, 78 non-cas et 4 évadés)."
# Two of the earlier ones say it of Ituri instead ("L'Ituri concentre
# l'essentiel de la charge avec 541 malades en isolement (248 confirmés, 293
# suspects) sur 693 lits, ...").
#
# It is the richest passage in the whole archive: it carries the confirmed
# census AND the absconder count AND a complete exit decomposition, and it
# closes three ways at once -- the split sums to the census, the census over
# the beds reproduces the printed rate, and the four exit categories sum to the
# exits. It is also the ONLY prose source of a national absconder count.
#
# ITS ADMISSIONS FIGURE IS NOT TAKEN. On sitrep 070 the "893 admissions" in
# this sentence is the outbreak-to-date total (the table beside it prints 893
# under `Total admissions` and 169 under `Total admissions (24 h)`), while on
# sitrep 077 the "118 admissions" is the day's. Nothing in the sentence
# distinguishes the two, so neither is published: an admissions column that is
# a stock on some days and a flow on others is worse than an empty one.

SUMMARY = re.compile(r"Au\s+total,\s*(?=\d)"
                     r"|L['’]\s*(Ituri|Tshopo|Nord[-\s]?Kivu|Sud[-\s]?Kivu"
                     r"|Haut[-\s]?U[ée]l[ée]|Bas[-\s]?U[ée]l[ée])\s+concentre", re.I)
SUMMARY_CAP = 460


def summary_rows(flat: str) -> list[dict]:
    """The whole-response summary sentence, as a row keyed `Ensemble` -- the
    word the reports' own tables use for the all-provinces column -- unless the
    sentence names a province as its subject."""
    out = []
    for m in SUMMARY.finditer(flat):
        seg = flat[m.end():m.end() + SUMMARY_CAP]
        stop = re.search(r"\.\s", seg)
        if stop:
            seg = seg[:stop.start()]
        if not re.search(r"en\s+isolement|hospitalis", seg, re.I):
            continue
        r = harvest(seg)
        if r["census"] is None:
            continue
        for f in ("admissions", "admissions_confirmed", "admissions_suspect",
                  "admissions_readmitted"):
            r[f] = None
        out.append({"province": _norm_prov(m.group(1)) if m.group(1) else "Ensemble",
                    **r, "sentence": " ".join(seg.split())[:400]})
    return out


# --------------------------------------------------------------------------
# The contact follow-up proportion
# --------------------------------------------------------------------------
#
# A surveillance figure rather than a care one, but per-province, per-day, and
# printed with the pair that makes it -- "Ituri 89,8 % (13 582/15 126)" -- so
# it licenses itself exactly the way the occupancy percentage does. It rides on
# the same (report, province) row. The national figure rides on a row whose
# province is `Ensemble`, which is the word the reports' own summary column
# uses, and whose care columns are empty.

CONTACT_HEAD = re.compile(
    rf"proportion\s+des?\s+contacts\s+suivis[^.]{{0,120}}?"
    rf"({NUM})\s+vus\s+sur\s+({NUM})", re.I)
CONTACT_PROV = re.compile(
    rf"(Ituri|Nord[-\s]Kivu|Sud[-\s]Kivu|Haut[-\s]?U[ée]l[ée]|Bas[-\s]?U[ée]l[ée]"
    rf"|Tshopo)\s+(\d{{1,3}}(?:[.,]\d{{1,2}})?)\s*%\s*\(\s*({NUM})\s*/\s*({NUM})\s*\)",
    re.I)


def contacts(flat: str) -> dict[str, dict]:
    """(followed, to_follow, printed %) per province, and for `Ensemble`.

    Kept only where followed/to_follow reproduces the printed percentage: the
    pair and the rate are printed side by side, so a passage that does not
    close is one this reader has misread and must not publish.
    """
    out: dict[str, dict] = {}
    m = CONTACT_HEAD.search(flat)
    if m:
        n, d = _int(m.group(1)), _int(m.group(2))
        p = PCT.search(flat[max(0, m.start()): m.start(1)])
        if p is not None:
            pv = float(p.group(1).replace(",", "."))
            if pct_ok(n, d, pv):
                out["Ensemble"] = {"contacts_followed": n,
                                   "contacts_to_follow": d,
                                   "contacts_followed_pct": pv,
                                   "contacts_sentence": flat[m.start():m.end() + 2]}
    if m:
        for mm in CONTACT_PROV.finditer(flat[m.start():m.start() + 700]):
            pv = float(mm.group(2).replace(",", "."))
            n, d = _int(mm.group(3)), _int(mm.group(4))
            if pct_ok(n, d, pv):
                out[_norm_prov(mm.group(1))] = {
                    "contacts_followed": n, "contacts_to_follow": d,
                    "contacts_followed_pct": pv,
                    "contacts_sentence": mm.group(0)}
    return out


# --------------------------------------------------------------------------

CONTACT_FIELDS = ("contacts_followed", "contacts_to_follow",
                  "contacts_followed_pct")


def _row(prov: str, r: dict, sentence: str) -> dict:
    cs = checks(r)
    return {"province": prov, **{f: r[f] for f in FIELDS},
            "checks": ";".join(f"{n}={'pass' if ok else 'fail'}" for n, ok in cs),
            "licensed": licensed(cs), "census_licensed": census_licensed(cs),
            "sentence": sentence}


def offer(best: dict[str, dict], refused: list[dict], prov: str, r: dict,
          cs: list[tuple[str, bool]], sentence: str) -> None:
    """Put one passage's reading forward as the row for this province.

    TWO PASSAGES, ONE PROVINCE, ONE DAY. Sitrep 097 prints the Haut-Uélé bullet
    twice with different censuses (53 and 4); the two-column vintages put a
    province's care bullet and its community-engagement bullet in the same
    section; and the whole-response summary sentence describes Ituri on the
    four reports that name it as its subject.

    WHERE THEY DISAGREE the arithmetic decides: the passage whose numbers close
    best wins the fields both state, and a passage that loses while asserting a
    different census is recorded rather than dropped in silence. WHERE THEY DO
    NOT they are merged, because they are two sentences about the same province
    on the same day and each says something the other omits: on sitrep 068 the
    summary sentence carries Ituri's census, beds and occupancy while the care
    bullet carries its admissions, recoveries and deaths. Both sentences are
    kept in `sentence`, separated by ` | `, so every number in the row can
    still be traced to the words that produced it.
    """
    cand = _row(prov, r, sentence)
    prev = best.get(prov)
    if prev is None:
        best[prov] = cand
        return
    cand_wins = score(cs) > score(checks(prev))
    keep, drop = (cand, prev) if cand_wins else (prev, cand)
    if None not in (r["census"], prev["census"]) and r["census"] != prev["census"]:
        refused.append({
            "why": "superseded_by_better_licensed" if cand_wins
                   else "conflicting_passages",
            "prov": prov, "sent": drop["sentence"][:160]})
        # A passage asserting a DIFFERENT census is describing something else
        # (or the report contradicts itself); nothing of it is merged in.
        best[prov] = keep
        return
    merged = {f: keep[f] if keep[f] is not None else drop[f] for f in FIELDS}
    filled = any(keep[f] is None and drop[f] is not None for f in FIELDS)
    best[prov] = _row(prov, merged,
                      keep["sentence"] + (" | " + drop["sentence"] if filled else ""))


def extract(pdf: Path) -> tuple[list[dict], list[dict]]:
    text = subprocess.run(["pdftotext", "-q", str(pdf), "-"],
                          capture_output=True, text=True).stdout
    flat = re.sub(r"\s+", " ", text)
    refused: list[dict] = []

    best: dict[str, dict] = {}
    for sm in SECTION.finditer(flat):
        end = SECTION_END.search(flat, sm.end())
        hi = end.start() if end else min(len(flat), sm.end() + 2500)
        block = flat[sm.end():hi]
        mentions = [m for m in PROV_RE.finditer(block)
                    if opens_passage(block, m.start())]
        for i, m in enumerate(mentions):
            stop = mentions[i + 1].start() if i + 1 < len(mentions) else len(block)
            seg = block[m.start():min(stop, m.start() + SEGMENT_CAP)]
            if not CARE_WORD.search(seg):
                continue
            prov = _norm_prov(m.group(1))
            if JOINED.match(block[m.end():m.end() + 20]):
                refused.append({"why": "two_provinces_one_passage", "prov": prov,
                                "sent": " ".join(seg.split())[:160]})
                continue
            if TABLE_ROW.search(seg) or DIGIT_RUN.search(seg):
                refused.append({"why": "table_not_prose", "prov": prov,
                                "sent": " ".join(seg.split())[:160]})
                continue
            r = harvest(seg)
            if all(r[f] is None for f in FIELDS):
                continue
            # THE LEDGER IS WHAT A CARE BULLET LEADS WITH. In the two-column
            # vintages the community-engagement bullets land inside the care
            # section once the columns are read in order, and they mention
            # recoveries and deaths in passing -- sitrep 082's Haut-Uélé
            # engagement bullet runs 1 271 people reached, 458 households, 23
            # at talks, and only then "causeries autour de 2 guéris à Wamba",
            # which read as the day's recoveries. A passage that states no
            # stock and no gross flow is therefore admitted only if the
            # component it does state opens the passage.
            if all(r[f] is None for f in GROSS) \
                    and (_first(COMPONENTS, pool(seg)) or (0, 10**6, 0))[1] > 120:
                refused.append({"why": "no_ledger_lead", "prov": prov,
                                "sent": " ".join(seg.split())[:160]})
                continue
            cs = checks(r)
            passed = {n for n, ok in cs if ok}
            for field, pats in (("admissions", ADMISSIONS), ("exits", EXITS),
                                ("census", CENSUS)):
                if r[field] is None or len(_distinct(pats, pool(seg))) <= 1:
                    continue
                if passed & set(RESOLVED_BY[field]):
                    continue
                refused.append({"why": f"ambiguous_{field}", "prov": prov,
                                "sent": " ".join(seg.split())[:160]})
                r[field] = None
                cs = checks(r)
            if all(r[f] is None for f in FIELDS):
                continue
            offer(best, refused, prov, r, cs,
                  " ".join(seg.split())[:400])

    # The whole-response summary sentence, offered on the same terms as any
    # other passage: it wins where its arithmetic closes better.
    for s in summary_rows(flat):
        r = {f: s[f] for f in FIELDS}
        offer(best, refused, s["province"], r, checks(r), s["sentence"])

    con = contacts(flat)
    for prov, c in con.items():
        row = best.get(prov)
        if row is None:
            best[prov] = {"province": prov, **{f: None for f in FIELDS},
                          "checks": "contacts_rate=pass", "licensed": True,
                          "census_licensed": False,
                          "sentence": c["contacts_sentence"][:400],
                          **{f: c[f] for f in CONTACT_FIELDS}}
        else:
            row.update({f: c[f] for f in CONTACT_FIELDS})
            row["checks"] = ";".join(x for x in (row["checks"],
                                                 "contacts_rate=pass") if x)
    for row in best.values():
        for f in CONTACT_FIELDS:
            row.setdefault(f, None)
    return list(best.values()), refused


SCHEMA = {"sitrep": pl.Int64, "date": pl.Utf8, "province": pl.Utf8,
          "admissions": pl.Int64, "admissions_confirmed": pl.Int64,
          "admissions_suspect": pl.Int64, "admissions_readmitted": pl.Int64,
          "exits": pl.Int64,
          "exits_recovered": pl.Int64, "exits_noncase": pl.Int64,
          "exits_absconded": pl.Int64, "exits_deaths": pl.Int64,
          "exits_deaths_confirmed": pl.Int64, "exits_transferred": pl.Int64,
          "census": pl.Int64, "census_confirmed": pl.Int64,
          "census_suspect": pl.Int64, "beds": pl.Int64,
          "beds_confirmed": pl.Int64, "beds_suspect": pl.Int64,
          "printed_occupancy_pct": pl.Float64,
          "printed_occupancy_confirmed_pct": pl.Float64,
          "printed_occupancy_suspect_pct": pl.Float64,
          "contacts_followed": pl.Int64, "contacts_to_follow": pl.Int64,
          "contacts_followed_pct": pl.Float64,
          "checks": pl.Utf8, "licensed": pl.Boolean,
          "census_licensed": pl.Boolean, "sentence": pl.Utf8}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
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
        got, refused = extract(pdf)
        for r in got:
            rows.append({"sitrep": num, "date": date, **r})
        status.append({
            "sitrep": num, "date": date, "n_provinces": len(got),
            "n_licensed": sum(r["licensed"] for r in got),
            "n_census": sum(r["census"] is not None for r in got),
            "n_census_confirmed": sum(r["census_confirmed"] is not None for r in got),
            "n_census_licensed": sum(r["census_licensed"] for r in got),
            "n_exits": sum(r["exits"] is not None for r in got),
            "n_absconded": sum(r["exits_absconded"] is not None for r in got),
            "n_failed_checks": sum("fail" in (r["checks"] or "") for r in got),
            "provinces": ",".join(sorted(r["province"] for r in got)),
            "n_refused": len(refused),
            "refused": "; ".join(f"{x['why']}({x['prov']})" for x in refused[:4]),
        })
        if not args.quiet and got:
            print(f"  {pdf.stem}  {len(got)} province(s), "
                  f"{sum(r['licensed'] for r in got)} licensed")

    pl.DataFrame(rows, schema=SCHEMA).sort("date", "province").write_csv(args.out)
    st = pl.DataFrame(status)
    st.write_csv(args.out.with_name(args.out.stem + "_status.csv"))

    d = pl.DataFrame(rows, schema=SCHEMA)
    print(f"\n{st.height} reports scanned; {st.filter(pl.col('n_provinces') > 0).height} "
          f"carry a care passage ({d.height} province-days, "
          f"{d['date'].min()} to {d['date'].max()}).")
    for name, col in (("census", "census"),
                      ("confirmed census", "census_confirmed"),
                      ("beds", "beds"), ("admissions", "admissions"),
                      ("exits", "exits"), ("absconders", "exits_absconded"),
                      ("contacts followed", "contacts_followed")):
        got = d.filter(pl.col(col).is_not_null())
        print(f"  {name:<18} {got.height:>4} province-days"
              + (f", {got['date'].min()} to {got['date'].max()}" if got.height else ""))
    print(f"\n{int(d['licensed'].sum())} rows license fully; "
          f"{int(d['census_licensed'].sum())} carry a census whose own closures "
          f"hold; {d.filter(pl.col('checks').str.contains('fail')).height} carry "
          "a failed closure -- the REPORT's numbers disagree with each other "
          "there, not this reader's, and the `checks` column names which one "
          "with the sentence beside it. "
          f"{int(st['n_refused'].sum())} passages were refused outright "
          "(see the status file).")


if __name__ == "__main__":
    main()
