# Registers — the hand-authored record

Everything else in this repository is fetched or derived. These files are
neither: each row is a judgement someone made after reading a page, and no
pipeline can regenerate one. Deleting a register loses knowledge; deleting
anything under `data/build/` costs a rebuild.

That is why they live here rather than under `data/raw/`, which holds what the
source published and what our own fetchers wrote.

| File                            | What each row asserts                                                                                                                                                                                                                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `reconciliation_exceptions.tsv` | *I opened this page, added the printed rows, and the source does not agree with itself.* A claim about one document, keyed on its SHA-256.                                                                                                                                                             |
| `sitrep_number_overrides.tsv`   | *This upload's filename does not state its report number or data date correctly; the page says otherwise.*                                                                                                                                                                                             |
| `external_sitreps.tsv`          | *INSP does not serve this report; we hold it from a secondary archive, its PDF is committed because nothing can fetch it again, and here is where it came from.* Also carries the one place this project files a report against its own printed date, with the argument for it.                        |
| `printed_date_errata.tsv`       | *This report's front page prints a data date that its own title, table captions and narrative contradict; it is filed under the date they state.* Keyed on the SHA-256, and void the day the page stops printing the recorded date.                                                                    |
| `rejected_routes.tsv`           | *This extraction route reads this document's values as something they are not, in a way no identity can catch from inside.*                                                                                                                                                                            |
| `withdrawn_values.tsv`          | *This report printed a cumulative that the following reports do not build on: they continue from the value before it, so it is treated as unobserved and the next report's daily row spans both days.* Keyed on the SHA-256; an entry that removes no printed value stops the build.                   |
| `zone_province_overrides.tsv`   | *The page states which province this row belongs to, but the table's geometry does not carry it.*                                                                                                                                                                                                      |
| `zone_aliases_local.csv`        | *This printed spelling and this shapefile name are the same health zone.*                                                                                                                                                                                                                              |
| `stream_families.tsv`           | *This is what the streams of this observation family measure, in one sentence.* Keyed on the family, never on the file, so four province variants of one quantity cannot drift apart.                                                                                                                  |
| `window_merged_rows.tsv`        | *This row is a clamped zero whose deficit is fully discharged by the very next row, so it is deleted rather than published — the following row's window widens to span both.* Keyed on (stream, column, date); re-verified against the built series on every run, not trusted from the register alone. |
| `retrospective_batches.tsv`     | *On this report date the source says, in its own words, that the cumulative's movement holds records belonging to earlier days.* Quoted, and scoped by quantity and place. Builds the `*_excluding_backlog` families and marks those days on the epidemic-curve figure.                                |
| `excluded_places.tsv`           | *This place carries confirmed cases and is deliberately not published as a stream, for this reason.* Empty in the steady state; the build stops on a place with cases that is neither published nor listed.                                                                                            |
| `lab_capacity_events.tsv`       | *This report states that laboratory testing capacity itself changed on this date*, with the sentence it came from. Never inferred from a jump in volume. Read only by the positivity figures, which mark the events.                                                                                   |
| `onset_axis_anchors.tsv`        | *This symptom-onset figure's x axis runs from this printed tick label to that one.* Read by a person against saved crops, keyed on the image's hash, and checked by the build against the detected ticks and the neighbouring vintages.                                                                |
| `onset_redraws.tsv`             | *Between these two symptom-onset charts the source redrew bars lower.* Keyed on the two images' hashes, with the chart's printed total before and after. The reporting-delay table counts a fall in a named pair as cases withdrawn by the source; a fall anywhere else is a dip it records and does not count. |
| `released_tags.tsv`             | *This `data/*` tag was published and names this commit.* Append-only; a test fails if a recorded tag is deleted or moved.                                                                                                                                                                              |

`stream_families.tsv` and `window_merged_rows.tsv` are not judgements about a
page: the first is a judgement about a **quantity**, the second about a **row
already built**. `released_tags.tsv` is not a judgement at all but a record of
what this repository has published, kept here because no rule can regenerate it
either. `stream_families.tsv` exists because the generated data dictionary at
`data/build/streams/README.md` can measure a stream's span, its row count and
its columns off the file itself, but cannot say what the numbers mean — a stream
this pipeline publishes whose family has no row there stops the build, so a new
stream cannot ship undocumented. `window_merged_rows.tsv` exists because
deleting a row from an `incidence(...)` stream changes what the file's schedule
asserts, which is a decision the arithmetic alone does not make — see
`merge_windows` in `build_streams.py`.

## Rules that apply to every register here

- **Keyed on the document, not on the report number.** INSP revises reports and
  republishes them under the same number. An entry names a file hash so a
  corrected report returns to the failing set instead of inheriting a judgement
  made about its predecessor.
- **Exact, not permissive.** An entry licenses one specific value — a residual
  of exactly +5, a specific report number — and nothing else. If our reading
  changes, the entry stops matching and the report fails again. That is the
  difference between a record and a mute button.
- **Every row carries who checked and against what.** An entry without
  provenance cannot be re-examined, and these are exactly the claims that will
  need re-examining when a report is revised.
- **Inference is labelled as inference.** Where an entry generalises from what a
  page states to a neighbouring case the page does not mention, it says so in
  the note.
