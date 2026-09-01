# The day the books caught up: 22 July, and where those cases belong in time

Date: 2026-08-30 Project: ebola-bdbv-data Tags: reconciliation, notification,
onset-curve, banner, provenance

## Context / question

The modelling side asked three things about 2026-07-22, the day the national
confirmed cumulative moved 369 against neighbours of 63 and 68: does the source
say what period the reconciliation covered, were cases and deaths reconciled
over the same period, and is 22 July the only such day. They had opened a
ten-day window backwards over the flagged region and let one row carry the
total, choosing the width on the ground that ten days is where the implied daily
rate stops carrying an excess. They could not make the deaths absorb under any
width.

They were solving the wrong problem, and so were we by not having read the page
closely enough.

## What the source actually prints

For sitreps 059–083 — 2026-07-12 to 2026-08-05 — the front-page banner states
the day's own notification count beside the cumulative, with a province
breakdown:

```
+97 nouveaux cas (Ituri 73 · N-Kivu 18 · Haut-Uele 6)
+62 décès (Ituri 45 · Nord-Kivu 14 · Haut-Uele 3)
```

and, on sitrep 069, an asterisked footnote saying why the cumulative moved four
times as far: "l'intégration des bases provinciales harmonisées … ne reflètent
pas uniquement les nouvelles notifications des dernières 24 heures."

The banner prints this in those 25 reports and nowhere else in the archive of
100. That window is the one the reports flag as consolidating. The source
started printing the day's own count exactly when its cumulative stopped being
safe to difference, and stopped when it was safe again. Whoever was compiling
these reports knew what the reader's problem was.

## The reconciliation

Over the 22 single-day report days where both readings exist, 16 agree exactly.

| date       | cases moved | notified | deaths moved | notified |
| ---------- | ----------- | -------- | ------------ | -------- |
| 2026-07-12 | 37          | 31       | 16           | 10       |
| 2026-07-13 | 48          | 54       | 36           | 28       |
| 2026-07-16 | 57          | 56       | —            | —        |
| 2026-07-18 | 77          | 83       | 37           | 40       |
| 2026-07-22 | 369         | 97       | 236          | 62       |
| 2026-08-02 | 54          | 58       | 50           | 40       |
| 2026-08-04 | —           | —        | 50           | 52       |

Everything but 22 July is ±10 and sits on a day the source footnotes a
reclassification. On 2026-08-02 the source prints both halves — "+40 décès du
jour … · +10 par harmonisation" — and 40 + 10 is the 50 the cumulative moved.
That closure is the best evidence available that the two readings differ by
retrospective attribution and by nothing else, so it is pinned in a test.

## Where the 272 cases belong in time, and why we cannot say

This is the part worth keeping. The source names a mechanism and an as-at date,
never a period. Two independent attempts to place them failed, informatively:

**The national series carries no accruing deficit.** On 12–21 July the printed
notifications reproduce the cumulative movement exactly. The backlog was never
visible as a national shortfall — the provincial databases were ahead of the
national aggregate and were merged in. So there is nothing in the national
series to invert.

**The epidemic curve did not receive them.** Figure 4 (by symptom onset, from
the DHIS2 line list) is the only object in the report that places cases in time.
Across the 21 → 22 July vintages it gained 22 cases, against 192 and 248 on the
transitions either side, at an ordinary mean onset-to-report delay of 10 days.
The line list holds ~53% of the national cumulative throughout; on 22 July that
share drops to 48% and recovers over the following fortnight as the harmonised
cases trickle in at the ordinary rate.

So the aggregate count and the line list are two pipelines with different
latencies, and the harmonisation moved only the first. **The published record
places those 272 cases in no interval.** Any window is our assumption, and the
right move is to say so rather than to pick one.

At zone level the addition is almost all Ituri — Mongbwalu +116, Nizi +60,
Mangala +23, Lita +20, Tchomia +16, Nyankunde +15, Nia-Nia +14, Kilo +12 — with
a separate reallocation of deaths from Bunia (−60) to Rwampara (+80) that nets
small. That is a spatial answer to a temporal question, and it does not
substitute.

## Why the deaths would not absorb

The modelling side's difficulty was structural, not arithmetical. They were
looking for a window over which the excess deaths implied a plausible daily
rate, having calibrated "plausible" against the local flow. But the excess is
not a flow: it is one lump whose composition differs from the flow. The backlog
runs 174 deaths on 272 cases, 64.0%; the window's other printed notifications
run 817 on 1,595, 51.2%. No width was going to reconcile those, because the
retrospectively integrated records are enriched for deaths — which is what you
would expect if the provincial books held community deaths confirmed post mortem
that the national aggregate had not taken up.

The general lesson: when a correction is a batch rather than a rate, checking it
against a rate will always leave a residual, and the residual is the composition
difference rather than a mis-specified window.

## Reading the banner

The banner is a dashboard in columns, and a tile wraps onto the lines below it
while other tiles occupy those lines further right. Flattening sitrep 069's
whitespace splices the suspected-case tile's "318 Ituri 188 · N-Kivu 119" into
the deaths tile, whose breakdown then cannot sum to 62 — so a licence built on
flat text refuses a perfectly well-formed page. Tiles are assembled by column
position instead. Two further shapes cost a province each until they were
handled: a name wrapping mid-word ("Nord-Kivu 6 – Haut-" / "Uele 4)") and a
footnote marker standing between name and count ("Nord-Kivu* 8").

A total ships only where its own province breakdown sums to it (44 of 46 case
and death readings) or the report's separate 24-hour sentence states the same
number (the other 2). 36 of 46 are corroborated both ways.

## An aside found on the way

Sitreps 079 and 080 both head the indicator block "cumul au 31 juillet 2026",
which is sitrep 078's heading, while their own `Date de rapportage` reads 1 and
2 August. The figures beneath move normally (cumulative deaths 1,621 → 1,657 →
1,707), so this is a heading nobody updated. They are the only two such reports
in the archive, and nothing here is affected because every series is dated from
`Date de rapportage`. Worth recording only because a reader dating the banner
figures by the heading above them would collapse three reports onto one day —
the same class of error as trusting the filename date, which cost this project
three whole days of series once already.

## Next

- The check owed from the previous channel exchange: whether
  `prose deaths − confirmed deaths` tracks `care_exits_noncase` in time rather
  than only in total. Not started.
- Whether the notified/cumulative comparison can be extended before 12 July by
  some other printed daily figure. The laboratory positives are the obvious
  candidate but they measure a different thing (they include re-swabs), so this
  is not a substitution to make casually.
