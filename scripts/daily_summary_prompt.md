# Summarise today's situation report for a modeller

You are reading a new situation report ("sitrep") from INSP, the DRC's national
public health institute, on the 2026 Bundibugyo virus disease outbreak. The
reader is an epidemic modeller who fits the case and death series this
repository extracts from these reports. They have the numbers already. What
they need from you is what the numbers alone do not tell them: changes in how
the source reports, signs that cases or deaths are being missed, response
changes that alter transmission or detection, and anything suggesting our
extracted series are wrong.

Release `{tag}`. New report(s): {reports}. For each, in
`data/build/summaries/sitrep_<N>/`:

- `digest.md`: every sentence of report N, compared mechanically with the
  previous reports we hold, and sorted into **new** (like nothing in the last
  five reports), **updated** (a sentence from the previous report with
  different numbers or light rewording, shown before and after) and
  **returning** (absent yesterday, present earlier). Sentences repeated word
  for word from yesterday are left out. Start here: this is where today's news
  is.
- `text.txt`: the full report, with its tables laid out as printed. Use it to
  check numbers, read tables, and confirm context for anything in the digest.
- `previous.txt`: the previous report, the same way.

Read only these files. Do not use anything you know about this outbreak from
elsewhere, apart from the background notes at the end of this prompt.

## How the reports work, and how they mislead

- **Find sections by their heading words, never their numbers.** The numbering
  is often broken. Look for «FAITS SAILLANTS» (highlights), «Résumé des points
  clés» (summary), «Surveillance», «Laboratoire», «PCI» / «EDS» (infection
  control, safe burials), «Prise en charge» (clinical care), «Vaccination»,
  «Sécurité», and «Défis» (challenges, a sub-heading under each section).
- **INSP copies text forward**, sometimes for weeks, including numbers that
  should have changed. A sentence in the digest's "updated" list with
  unchanged numbers is not news. A number that ought to move daily but sits
  unchanged (a care census, a vaccination total) is worth reporting as
  possibly carried forward.
- **«ND» means not available. It is not zero.** A province with ND cells, or a
  sentence saying data «ne sont pas parvenues» or «n'ont pas été transmises»
  (did not arrive, were not sent), or that values were «reportés» (carried
  over from the previous day), is always reportable.
- **Rates are computed over whichever provinces reported that day.** Contact
  follow-up and alert totals often say «dans les N provinces ayant transmis
  leurs données» (in the N provinces that sent data). If the set of provinces
  changed from the previous report, say so: the national rate is then not
  comparable day to day.
- **Laboratory «positifs» are not new cases.** They can include repeat samples
  («reprélèvements») from patients already confirmed.
- **A day's confirmed deaths have two parts:** deaths among newly confirmed
  cases, often confirmed after death («décès communautaires», community
  deaths), and deaths of previously confirmed patients in treatment centres
  («intra-CTE»). Report which the page gives.
- **Prose and tables in the same report disagree.** Where they do, give both
  numbers and where each appears.
- **Dates.** «Date de rapportage» is the date the data refer to. «Date de
  publication» is usually a day later. The date inside the «SitRep N°…» code
  sometimes differs from both. A date in the text that matches neither
  usually means the sentence was copied from an earlier report.

## What to write

The reader skims this in an email. Optimise for signal at a glance: short
bullets, one fact each, the place first, the number next, the consequence
last. Plain English for someone who does not read French.

Start with one line:

`Headline: <the single most important thing for a modeller>`

It becomes the email subject: at most 12 words, no quotes, no second
sentence. Name the province. Example: `Headline: Haut-Uélé care data missing;
more bodies unswabbed in Ituri`.

Then, for each new report, oldest first, a title line
`# Sitrep <N>, data for <D Month YYYY>` followed by these sections in this
order. Use these headings exactly. Leave out a section with nothing in it,
except the first two.

1. `## What affects our extracted series`. Put this first: it is what the
   reader acts on. Anything that means a value we publish may be wrong or
   misleading: a value carried forward that will look like a fresh
   observation; flows missing that would read as zero; a table total that
   does not equal its rows; a care census that does not follow from the
   day's admissions and exits; a batch that will look like one day's
   incidence; a shift between columns; a reclassification or retroactive
   revision; a cumulative count that fell; a change to the «A ventiler» row
   (treatment-centre deaths not yet assigned to a health zone). Name the
   quantity and the province. If nothing, one bullet: `- Nothing found.`
2. `## Counts: arithmetic checks pass`, or
   `## Counts: <k> arithmetic failures`. Check that the previous report's
   cumulative plus today's new equals today's cumulative, nationally and for
   each province, and that each case and death table's printed total equals
   the sum of its rows. Then a table in a fenced code block (three
   backticks), one row per province with any new case or death, then
   `Total` and `Cumulative`:

   ```
                  cases   deaths   community   in treatment centres
     Ituri           37       29          15                     14
     Total           67       41          23                     18
     Cumulative   9,704    4,687
   ```

   Right-align the numbers. Below the table, bullets only for failures
   (what was expected, what is printed) and for the unassigned-deaths row
   if it changed.
3. `## Deaths probably undercounted`. Bodies not swabbed or taken by
   families; safe burials failed or postponed; community deaths not
   investigated.
4. `## Cases possibly missed or delayed`. Suspects not investigated or not
   transferred; confirmed patients who absconded or are lost to follow-up;
   laboratory backlogs; areas not reporting (insecurity, strikes, no
   network); refusals and community resistance.
5. `## Rates not comparable with the previous report`. A changed set of
   provinces behind a national rate; ND cells; a table, column or tile
   added or dropped; a changed denominator such as the number of health
   zones in the affected provinces; a batch of results or alerts released
   at once.
6. `## Response`. Vaccination (which vaccine, who receives it, doses,
   coverage, stock-outs, pauses); therapeutics and post-exposure
   prophylaxis; treatment-centre openings, beds and occupancy, including
   patients cared for outside treatment centres; new laboratories;
   infections among health workers.
7. `## Spread`. Newly affected health zones or provinces, imported or
   exported cases, events at borders.

After the last report, one section:

`## Evidence`: a numbered Markdown list, one item per quote, in the order
first cited: `1. <heading it sits under>: «<French text>»`.

## Rules

- **Bullets.** One fact per bullet, at most about 30 words. Lead with the
  place or quantity. Show change from the previous report inline, as
  `(was 44)` or `from 77.8% to 79.7%`. Do not tag items as new or changed,
  and do not repeat anything unchanged unless it still matters for fitting.
- **References.** Each bullet ends with one or more references `[n]` to the
  Evidence list. A bullet that only does arithmetic on numbers already cited
  needs none. The counts table cites the highlights sentence in its heading,
  for example `## Counts: arithmetic checks pass [1]`, never on a line of its
  own.
- **Each fact once,** in the section where it matters most for fitting.
- **Quotes** go only in the Evidence list, never in the bullets. Each is
  French text copied exactly from `text.txt`, short enough to check (one
  sentence or less). A program checks every quote against the report after
  you finish and marks any that do not match word for word. Do not
  translate, tidy, or correct the spelling or number formatting inside a
  quote.
- **Number formatting.** The report prints numbers the French way: a space
  between thousands (`9 704`) and a decimal comma (`25,4 %`). Outside the
  quotes, write them the English way: `9,704` and `25.4%`. Inside the
  quotes, keep them exactly as printed.
- **Computed numbers.** If you compute one (a sum, a difference, a rate), say
  `(my arithmetic)` and show the calculation or the numerator and
  denominator, for example `18 of 71 (25.4%)` or `509 + 87 − 106 = 490`.
- **Do not guess.** If something is ambiguous, say what is ambiguous in one
  bullet. A short summary on a quiet day is correct.
- **Length.** At most about 400 words per report, excluding the Evidence
  list. Leave out routine activity counts (people sensitised, radio
  broadcasts, kits delivered, training sessions, PSEA, mental-health
  activity) unless they reveal a problem: a strike, resistance, missing data.
- Output only the summary, in Markdown, starting with the `Headline:` line.
  No preamble, no closing remarks.

## Background notes you may use

- The vaccine in use is Ervebo (rVSV-ZEBOV), developed against Zaire
  ebolavirus, not Bundibugyo virus; its protection against Bundibugyo is not
  established. Report vaccination as an intervention whose effect on
  transmission is uncertain. A Bundibugyo-specific candidate vaccine trial for
  contacts has also been mentioned in the reports.
- A body that is not swabbed is a death that may never be confirmed, so
  confirmed deaths undercount in proportion.
- Infections among health workers («PPL», front-line workers) indicate
  transmission inside health facilities.
- The onset-date epidemic curve (Figure 1) is an image. If its caption or
  subtitle text gives a count n of cases with an onset date, compare it with
  the cumulative confirmed count: the difference is the cases with no onset
  date.
- The extraction already publishes, by province: confirmed cases and deaths
  (cumulative and daily), the community/treatment-centre split of deaths,
  laboratory samples and positivity, patients in isolation and the care census,
  admissions and exits (deaths, recoveries, non-cases, absconders). These are
  what the first section is about. It does not publish alerts, contact
  follow-up, safe burials, swabbing, vaccination, therapeutics or bed capacity:
  for those, the prose is the only record.
