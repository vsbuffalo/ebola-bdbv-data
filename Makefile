# Data pipeline entry points. Networked steps are separate from ordinary builds
# by design: `build` and `doc` never touch the network, so a rebuild can never
# silently change what the source says.

.PHONY: verdict figures-release figures-compare watch-data-channel release-check escape-fraction care-ledger oneoff-testing oneoff-death-split oneoff-death-flow cron-install cron-uninstall check fetch refresh manifest verify build streams compare figures onset external \
	external-update scan-refresh doc serve test

# WHERE A FIGURE LANDS SAYS WHICH DATA MADE IT. Every figure this repository
# draws goes into a directory named for the release it was drawn from, so a PNG
# is never a bare file whose vintage you have to remember. `git describe` names
# a tagged build by its tag (`data-2026-08-29-r3`) and an untagged one by the
# tag it descends from plus the commit (`data-2026-08-29-r3-3-g4bae79e`) --
# which is the honest label for a build between releases, and not a release
# name pretending to be one.
#
# `make figures-release TAG=...` writes into the SAME shape, so a reconstructed
# release and the current build are peers rather than an archive and a special
# case. `latest` points at whichever was built last, for anything that wants a
# stable path.
RELEASE := $(shell git describe --tags --always 2>/dev/null | tr '/' '-')
FIGDIR  := data/build/figures/$(RELEASE)


## check   -- is the archive current, and does the source still look the same?
##            Exit 0 current, 1 behind, 2 the source moved, 3 unreachable,
##            4 current-but-the-source-has-gone-quiet.
##            The ONLY check here that looks outward: everything else asks
##            whether the reports we hold are consistent, not whether we hold
##            the reports that exist.
check:
	@uv run python scripts/check_upstream.py

## fetch   -- NETWORKED. Re-read the index and fetch any PDF we do not hold.
##            Run `check` first: when it reports CHANGED, this may do the wrong
##            thing quietly, because the predicate that decides what a report
##            IS is the thing that moved.
fetch:
	uv run python scripts/fetch_sitrep_index.py --out data/raw/insp_sitrep_index.tsv
	uv run python scripts/fetch_sitrep_pdfs.py --index data/raw/insp_sitrep_index.tsv \
		--out data/raw/sitrep_pdfs --manifest data/raw/sitrep_pdfs.manifest.tsv

## refresh -- what `make check` tells you to run when BEHIND: fetch, then the
##            whole offline rebuild. (This target existed only in check's
##            advice for a while; advice must name a target that exists.)
refresh: fetch build streams figures compare doc

## cron-install -- schedule `make check` every six hours via launchd (macOS).
##            The plist template is committed; the absolute repo path is
##            substituted here at install time, never committed. Output lands
##            in logs/check_upstream.log; a non-CURRENT verdict raises a
##            macOS notification. `make cron-uninstall` removes it.
CRON_LABEL = com.vsb.ebola-bdbv-check
cron-install:
	mkdir -p logs
	sed "s|@REPO@|$$(pwd)|g" scripts/launchd/$(CRON_LABEL).plist.in \
		> ~/Library/LaunchAgents/$(CRON_LABEL).plist
	launchctl bootout gui/$$(id -u)/$(CRON_LABEL) 2>/dev/null || true
	launchctl bootstrap gui/$$(id -u) ~/Library/LaunchAgents/$(CRON_LABEL).plist
	@echo "installed; first run fires now, then every 6 h. Log: logs/check_upstream.log"

cron-uninstall:
	launchctl bootout gui/$$(id -u)/$(CRON_LABEL) 2>/dev/null || true
	rm -f ~/Library/LaunchAgents/$(CRON_LABEL).plist
	@echo "removed"

## manifest -- OFFLINE. Rewrite data/raw/sitrep_pdfs.manifest.tsv from the
##            archive, reconciling it against the index and against
##            registers/external_sitreps.tsv. Same code path `fetch` ends with,
##            minus the network: the manifest is a pure function of those three
##            inputs, so changing the register must not require re-downloading
##            anything to make the committed manifest true again.
manifest:
	uv run python scripts/fetch_sitrep_pdfs.py --no-fetch \
		--index data/raw/insp_sitrep_index.tsv \
		--out data/raw/sitrep_pdfs --manifest data/raw/sitrep_pdfs.manifest.tsv

## verify  -- OFFLINE. Every held PDF hashes to what the manifest records.
verify:
	uv run python scripts/verify_archive.py --pdfs data/raw/sitrep_pdfs \
		--manifest data/raw/sitrep_pdfs.manifest.tsv

## build   -- OFFLINE. PDFs -> health-zone extraction -> province aggregation.
##            Stops with exit 2 if a province total disagrees with the sum of
##            its parts; that is a finding, not a nuisance. The extraction
##            stops with exit 2 for the same reason if a report's printed
##            case-fatality column disagrees with more than half of its own
##            rows -- see registers/rejected_routes.tsv for what to do about it.
build:
	uv run python scripts/extract_zone_table.py \
		--pdfs data/raw/sitrep_pdfs --out data/build/series/zone_table.csv
	uv run python scripts/extract_zone_table.py \
		--pdfs data/raw/sitrep_pdfs --spec provincial_summary \
		--out data/build/series/province_summary.csv --quiet
	uv run python scripts/parse_provisional_caveat.py \
		--pdfs data/raw/sitrep_pdfs \
		--out data/build/series/provisional_caveat.csv
	uv run python scripts/extract_prose_provinces.py \
		--pdfs data/raw/sitrep_pdfs --only 12 14 16 \
		--out data/build/series/prose_provinces.csv
	uv run python scripts/extract_lab_prose.py \
		--pdfs data/raw/sitrep_pdfs --quiet \
		--out data/build/series/lab_prose.csv
	# The care ledger the reports state in words: admissions, exits and how
	# they end, the end-of-day census with its confirmed/suspected split, the
	# beds and the printed occupancy. It exists because the front-page
	# ISOLEMENT/CTE tile stops after 2 August while the prose carries the same
	# quantities per province to the end of the archive; `streams` publishes
	# the parts of it that stand as observations.
	uv run python scripts/extract_care_prose.py \
		--pdfs data/raw/sitrep_pdfs --quiet \
		--out data/build/series/care_prose.csv
	uv run python scripts/extract_banner.py \
		--pdfs data/raw/sitrep_pdfs --quiet \
		--out data/build/series/banner.csv
	# The count the banner states for the report day itself, which exists
	# only for sitreps 059-083 -- the stretch the source was reconciling
	# over, and the only stretch in which differencing its cumulative is
	# not a safe reading of one day's incidence.
	uv run python scripts/extract_daily_notified.py \
		--pdfs data/raw/sitrep_pdfs --quiet \
		--out data/build/series/daily_notified.csv
	# exit 1 = some reports print no total to check against (a reported gap
	# in the evidence, not a failure); exit 2 = a total disagrees, stop.
	uv run python scripts/aggregate_provinces.py \
		--panel data/build/series/zone_table.csv \
		--pdfs data/raw/sitrep_pdfs \
		--exceptions registers/reconciliation_exceptions.tsv \
		--out data/build/series/province_series.csv || [ $$? -eq 1 ]
	# sibling outputs of the steps above:
	#   data/build/series/zone_table_status.csv
	#   data/build/series/zone_table_letality.csv
	#   data/build/series/province_summary_status.csv
	#   data/build/series/province_summary_letality.csv
	#   data/build/series/prose_provinces_status.csv
	#   data/build/series/lab_prose_status.csv
	#   data/build/series/care_prose_status.csv
	#   data/build/series/banner_status.csv
	#   data/build/series/daily_notified_status.csv
	#   data/build/series/province_series_reconciliation.csv

## streams -- OFFLINE. The weekly observation streams the models fit.
##            Fails unless every stream's emitted total equals what the
##            source's cumulative moved, no published count is negative, and
##            every downward revision the source made has been fully carried
##            into later rows; the grid is also checked against every printed
##            province row and the gaps land in meta.json. Fails too if a
##            stream it writes has no sentence in registers/stream_families.tsv
##            saying what it measures -- a new stream must not ship
##            undocumented, so adding one means adding a sentence.
##            AND FAILS UNLESS EVERY SCORED ROW ON A FLOW FILE SITS EXACTLY
##            `days_covered` DAYS AFTER THE ROW BEFORE IT. A model accumulates
##            a modelled flow between the ROWS that are present -- an NA row
##            resets the accumulator just as a scored one does -- so a row
##            further from its predecessor than the window it claims is scored
##            against more flow than it represents, and no other gate here can
##            see it: the counts are right and the totals reconcile.
streams:
	# FIRST, because build_streams.py writes the data dictionary that
	# documents every published file and reads this one's span off it.
	uv run python scripts/build_uganda_stream.py \
		--uganda data/raw/uganda_cases.toml \
		--out data/build/streams/uganda_exports.tsv
	uv run python scripts/build_streams.py \
		--panel data/build/series/zone_table.csv \
		--summary data/build/series/province_summary.csv \
		--prose data/build/series/prose_provinces.csv \
		--lab data/build/series/lab_prose.csv \
		--caveat data/build/series/provisional_caveat.csv \
		--banner data/build/series/banner.csv \
		--notified data/build/series/daily_notified.csv \
		--batches registers/retrospective_batches.tsv \
		--care data/build/series/care_prose.csv \
		--geojson data/raw/health_zones.geojson \
		--population data/raw/zone_population.csv \
		--uganda-stream data/build/streams/uganda_exports.tsv \
		--out-dir data/build/streams
	# writes, one file per stream (this list is load-bearing: the document
	# guard derives the declared-artefact set from these paths):
	#   data/build/streams/cases_ituri.tsv      data/build/streams/deaths_ituri.tsv
	#   data/build/streams/cases_nord_kivu.tsv  data/build/streams/deaths_nord_kivu.tsv
	#   data/build/streams/cases_haut_uele.tsv  data/build/streams/deaths_haut_uele.tsv
	#   data/build/streams/cases_national.tsv   data/build/streams/deaths_national.tsv
	#   data/build/streams/community_deaths_ituri.tsv
	#   data/build/streams/community_deaths_nord_kivu.tsv
	#   data/build/streams/community_deaths_haut_uele.tsv
	#   data/build/streams/community_deaths_national.tsv
	#   data/build/streams/lab_national.tsv
	# and the DAILY companions, one row per report day:
	#   data/build/streams/cases_daily_{ituri,nord_kivu,haut_uele,national}.tsv
	#   data/build/streams/deaths_daily_{ituri,nord_kivu,haut_uele,national}.tsv
	#   data/build/streams/community_deaths_daily_{ituri,nord_kivu,haut_uele,national}.tsv
	#   data/build/streams/lab_daily_{ituri,nord_kivu,haut_uele,national}.tsv
	# and the national STOCK observations (a reading at an instant, so no
	# days_covered -- see uganda_exports for the same rule):
	#   data/build/streams/patients_isolated.tsv
	#   data/build/streams/patients_isolated_confirmed.tsv
	#   data/build/streams/cumul_recovered.tsv
	#   data/build/streams/meta.json
	# and THE CARE LEDGER, from the care pillar's prose: the isolation census
	# as a STOCK per province, and the day's admissions and exits as flows the
	# report states for the report day. One file per quantity per place,
	# written only where the source states that quantity for that place at
	# all -- a file that would be empty is not written. THE FLOW FILES CARRY A
	# ROW ON EVERY REPORT DAY THEY SPAN, holding NA where the source said
	# nothing, because a model accumulates between the rows that are present
	# and a file holding only the stated days makes each next row's window as
	# wide as the silence behind it. The census files are stocks and are NOT
	# gridded: they accumulate over nothing, so a gap in one costs nothing:
	#   data/build/streams/care_census_{ituri,nord_kivu,haut_uele,national}.tsv
	#   data/build/streams/care_census_confirmed_{ituri,nord_kivu,haut_uele,national}.tsv
	#   data/build/streams/care_census_suspect_{ituri,nord_kivu,haut_uele,national}.tsv
	#   data/build/streams/care_admissions_{ituri,nord_kivu,haut_uele}.tsv
	#   data/build/streams/care_exits_{ituri,nord_kivu,national}.tsv
	#   data/build/streams/care_exits_recovered_{ituri,nord_kivu,haut_uele,national}.tsv
	#   data/build/streams/care_exits_noncase_{ituri,nord_kivu,national}.tsv
	#   data/build/streams/care_exits_absconded_{ituri,nord_kivu,national}.tsv
	#   data/build/streams/care_exits_deaths_{ituri,nord_kivu,haut_uele,national}.tsv
	# and the record of every downward revision the source made and this
	# build carried forward -- one row per published row a deficit was open
	# at, generated by the same run, never hand-maintained:
	#   data/build/streams/revisions.tsv
	# and the per-release data dictionary: one row per published file, its
	# span read back off that file, the sentence saying what each family
	# measures taken from registers/stream_families.tsv. Generated, and it
	# stops the build if a stream this run wrote has no such sentence:
	#   data/build/streams/README.md

## compare -- ours against the two other extraction lineages of the same PDFs.
##            Paths default to sibling checkouts; override INRB_DIR / SCAN.
##            Agreement is evidence about transcription, never about the counts;
##            a disagreement is always a finding and lands in compare/.
INRB_DIR ?= external/BDBV2026-Data
SCAN     ?= data/raw/scan/insp_sitrep_scanned.csv

## external -- clone the comparison sources into external/ (gitignored), at
##            EXACTLY the commits pinned in external.lock (committed). A clone
##            at any other commit fails: "pinned" must mean checkout-able and
##            verified, not merely recorded into a gitignored file.
external:
	mkdir -p external
	test -d external/BDBV2026-Data || git clone \
		$$(awk -F'\t' '$$1=="BDBV2026-Data"{print $$2}' external.lock) \
		external/BDBV2026-Data
	cd external/BDBV2026-Data && \
		git fetch -q origin && \
		git checkout -q $$(awk -F'\t' '$$1=="BDBV2026-Data"{print $$3}' ../../external.lock) && \
		test "$$(git rev-parse HEAD)" = \
		     "$$(awk -F'\t' '$$1=="BDBV2026-Data"{print $$3}' ../../external.lock)"

## external-update -- move the pin to the remote head and rewrite the lock;
##            the lock diff is the record of what upstream changed.
external-update: external
	git -C external/BDBV2026-Data fetch -q origin
	git -C external/BDBV2026-Data checkout -q origin/main
	{ grep '^#' external.lock; printf 'name\turl\tcommit\tlocked\n'; \
	  printf '%s\t%s\t%s\t%s\n' BDBV2026-Data \
	    "$$(git -C external/BDBV2026-Data remote get-url origin)" \
	    "$$(git -C external/BDBV2026-Data rev-parse HEAD)" \
	    "$$(date +%Y-%m-%d)"; } > external.lock.tmp
	mv external.lock.tmp external.lock

## scan-refresh -- update the committed copy of the epiforecasts scan from a
##            sibling checkout; commit the diff.
scan-refresh:
	cp ../epiforecast-repro/raw/insp_sitrep_scanned.csv data/raw/scan/insp_sitrep_scanned.csv

compare:
	@mkdir -p $(FIGDIR) && ln -sfn $(RELEASE) data/build/figures/latest
	uv run python scripts/compare_extractions.py \
		--zone-table data/build/series/zone_table.csv \
		--summary data/build/series/province_summary.csv \
		--prose data/build/series/prose_provinces.csv \
		--banner data/build/series/banner.csv \
		--province-series data/build/series/province_series_reconciliation.csv \
		--geojson data/raw/health_zones.geojson \
		--inrb $(INRB_DIR) --scan $(SCAN) \
		--out-dir data/build/compare \
		--figure $(FIGDIR)/comparison.png \
		--series-figure $(FIGDIR)/comparison_series.png
	# also writes: data/build/compare/inrb_disagreements.csv
	#              data/build/compare/scan_comparison.csv
	#              data/build/compare/banner_comparison.csv
	#              data/build/compare/zone_comparison.csv
	#              data/build/compare/compare_meta.json
	# COMMITTED COPIES of the two comparison figures, so the README's
	# validation section travels with the repository (data/build is
	# gitignored). Refreshed on every compare; a diff here is a change in
	# what the comparison shows, and belongs in the commit that caused it.
	# These three carry captions in figures/README.md like the rest,
	# and `make test` fails if one of them stops having a section there.
	# SLIDE FIGURE, 16:9, drawn HERE rather than in `figures` because it reads
	# this target's outputs: three lineages against each other, and what each
	# one covers. Like every other figure it lands in $(FIGDIR) first and is
	# copied to figures/ from there, so the release directory is a strict
	# superset of what is committed -- which `make test` checks.
	uv run python scripts/plot_figures.py --figure validation \
		--out $(FIGDIR)/validation.png
	mkdir -p figures
	cp $(FIGDIR)/validation.png figures/
	cp $(FIGDIR)/comparison.png $(FIGDIR)/comparison_series.png figures/

## onset -- OFFLINE. The symptom-onset reporting triangle, read out of the
##          sitrep figures' pixels. The chart is an embedded raster with no
##          data table anywhere; the reader fits every bar as a pair of
##          integer counts, checks each figure against its own printed
##          total, and gates every vintage against its temporal neighbours.
##          Design: notes/2026-08-28-onset-digitiser-design.md. The one
##          manual input is registers/onset_axis_anchors.tsv (printed tick
##          labels, machine-validated); everything else is measured from
##          the figure being read. Outputs under data/build/onset/ --
##          vintages.csv, snapshots.csv (levels), triangle.csv (derived
##          increments), images/ (the exact pixels read), proof/ (the
##          reader's conclusions drawn onto them, for the human check).
onset:
	uv run python scripts/extract_onset_curve.py
	# THE TRIANGLE, DRAWN: every vintage on one axis (the fan closing is
	# the reporting process completing) and the empirical delay shape
	# (each settled onset date's climb to its final count).
	uv run python scripts/plot_figures.py --figure onset_vintages \
		--out data/build/onset/figures/onset_vintages.png
	uv run python scripts/plot_figures.py --figure onset_delay \
		--out data/build/onset/figures/onset_delay.png
	# THE CROSS-REPOSITORY COMPARISON: our measured completion curve
	# against the paper's fitted onset-to-sample Gamma and the mixture
	# the transmission model implements for it.
	uv run python scripts/plot_figures.py --figure onset_delay_vs_model \
		--out data/build/onset/figures/onset_delay_vs_model.png
	# THE COHORT SPLIT: whether reporting sped up after the window the
	# paper's delay was fitted on. Left-truncated cohorts appear as
	# initial-stock points, not curves.
	uv run python scripts/plot_figures.py --figure onset_delay_cohorts \
		--out data/build/onset/figures/onset_delay_cohorts.png

## figures -- OFFLINE. The EDA figures, from the built series.
figures:
	@mkdir -p $(FIGDIR) && ln -sfn $(RELEASE) data/build/figures/latest
	uv run python scripts/plot_figures.py --figure availability \
		--out $(FIGDIR)/availability.png
	# SLIDE FIGURE, 16:9 at PowerPoint widescreen size (13.333 x 7.5 in).
	# One cell per released stream x report day, over the format eras and the
	# days whose own arithmetic does not close.
	uv run python scripts/plot_figures.py --figure release_grid \
		--out $(FIGDIR)/release_grid.png
	# SLIDE FIGURE, 16:9. The outbreak itself -- the opening slide.
	uv run python scripts/plot_figures.py --figure epi_curve \
		--out $(FIGDIR)/epi_curve.png
	# SLIDE FIGURE, 16:9. The community share of confirmed deaths -- the
	# quantity the models most need and the reason every page's arithmetic
	# is checked.
	uv run python scripts/plot_figures.py --figure ascertainment \
		--out $(FIGDIR)/ascertainment.png
	# SLIDE FIGURE, 16:9. Of everyone ever confirmed, who appears in one of
	# the published outcome ledgers and who appears in none of them. An
	# arithmetic residual over four printed counts, so the top band is a
	# count of people rather than a gap between two estimates.
	uv run python scripts/plot_figures.py --figure outcomes \
		--out $(FIGDIR)/outcomes.png
	# SLIDE FIGURE, 16:9. The same split per province: the national share is a
	# weighted average over provinces 18 points apart, so a model fitting one
	# national ascertainment probability is fitting that average.
	uv run python scripts/plot_figures.py --figure ascertainment_provinces \
		--out $(FIGDIR)/ascertainment_provinces.png
	# SLIDE FIGURE, 16:9. Where the outbreak was, fortnight by fortnight, and
	# which health zones reported their first case in each. Fill is the zone's
	# cumulative cases; the outline is the arrival, which the fill cannot show
	# because a zone going 0 -> 3 barely changes colour.
	uv run python scripts/plot_figures.py --figure zone_spread \
		--out $(FIGDIR)/zone_spread.png
	uv run python scripts/plot_figures.py --figure province_series \
		--out $(FIGDIR)/province_series.png
	# THE PROVINCE FLOWS AND THE NATIONAL-ONLY SERIES ARE TWO FIGURES, not
	# one. They were one, at 11 x 25.6 inches, which is not a readable aspect
	# for either half; they still share a calendar so the two can be read
	# against each other.
	uv run python scripts/plot_figures.py --figure streams_detail \
		--out $(FIGDIR)/streams_detail.png
	uv run python scripts/plot_figures.py --figure national_detail \
		--out $(FIGDIR)/national_detail.png
	# The care ledger the reports state in words: what validates the prose
	# census against the front-page tile, occupancy against capacity per
	# province, and the ledger flows with the absconder counts drawn as the
	# isolated marks they are.
	uv run python scripts/plot_figures.py --figure care_ledger \
		--out $(FIGDIR)/care_ledger.png
	uv run python scripts/plot_figures.py --figure residuals \
		--out $(FIGDIR)/residuals.png
	# SLIDE FIGURE, 16:9. Whether a claimed response scale-up can be checked
	# against the reports at all, and what the epidemic did over the window
	# it is claimed for. The middle panel is the load-bearing one: it dates
	# the first appearance of every response quantity we extract, and all but
	# one of them begin after the window closes.
	uv run python scripts/plot_figures.py --figure response_timeline \
		--out $(FIGDIR)/response_timeline.png
	# SLIDE FIGURE, 16:9. The share of samples returning positive, and what
	# the positives were. THE NUMERATOR SPLITS AND THE DENOMINATOR DOES NOT:
	# the laboratory paragraph prints one pool of samples per province with
	# no indication of origin, so a positivity rate for suspected cases and
	# another for community deaths cannot be formed. The lower panel is
	# therefore a composition and not a second rate.
	uv run python scripts/plot_figures.py --figure test_positivity \
		--out $(FIGDIR)/test_positivity.png
	# SLIDE FIGURE, 16:9. THE SECOND HALF OF A PAIR with the figure above and
	# only meaningful as one: the same samples split by province, showing that
	# the national rate is a weighted average of provinces three-fold apart
	# over weights that swing between weeks. The grey dashed line here is the
	# blue line there, so the two can be read against each other.
	uv run python scripts/plot_figures.py --figure positivity_provinces \
		--out $(FIGDIR)/positivity_provinces.png
	# THE SAME FIGURE WITHOUT THE CAPACITY REGISTER. Shown first and then
	# replaced by the annotated one, the pair makes visible what reading the
	# reports bought: a mark nothing else in the pipeline could supply.
	uv run python scripts/plot_figures.py --figure positivity_provinces_annotated \
		--out $(FIGDIR)/positivity_provinces_annotated.png
	# SLIDE FIGURE, 16:9. The two parts of the positivity ratio drawn apart,
	# because a falling ratio is compatible with less disease OR more testing
	# and only the parts separate them.
	uv run python scripts/plot_figures.py --figure lab_effort \
		--out $(FIGDIR)/lab_effort.png
	# COMMITTED COPIES, so the README, the data document and the cross-repo
	# channel can link to figures that survive (data/build is gitignored).
	# Everything copied here is gated twice: by `release-check`, which
	# requires it to rebuild byte-identically from a fresh clone of the
	# committed state, and by `make test`, which requires it to have a
	# section in figures/README.md saying what it shows and what it does
	# not license anyone to conclude. Adding a `cp` here without adding that
	# section fails the suite.
	mkdir -p figures
	cp $(FIGDIR)/streams_detail.png figures/
	cp $(FIGDIR)/national_detail.png figures/
	cp $(FIGDIR)/care_ledger.png figures/
	cp $(FIGDIR)/release_grid.png figures/
	cp $(FIGDIR)/ascertainment.png figures/
	cp $(FIGDIR)/ascertainment_provinces.png figures/
	cp $(FIGDIR)/zone_spread.png figures/
	cp $(FIGDIR)/outcomes.png figures/
	cp $(FIGDIR)/epi_curve.png figures/
	cp $(FIGDIR)/response_timeline.png figures/
	cp $(FIGDIR)/test_positivity.png figures/
	cp $(FIGDIR)/positivity_provinces.png figures/
	cp $(FIGDIR)/positivity_provinces_annotated.png figures/
	cp $(FIGDIR)/lab_effort.png figures/

## figures-release -- OFFLINE. Rebuild a past release's figures into
##            data/build/figures/<tag>/ -- the same shape `make figures`
##            writes the current build into -- so two releases can be
##            looked at side by side.
##              make figures-release TAG=data/2026-08-22
##              make figures-release DISTINCT=1     # one set per input set
##            TODAY's extraction over THAT RELEASE's inputs, recovered from
##            the manifest its tag pinned. A difference between two directories
##            is therefore a difference in the reports read, never in the code
##            that read them -- which is the only comparison that can be
##            interpreted. What a release published AT THE TIME would need its
##            code too, and mixing the two makes a moved line unattributable.
##            Nothing here is committed: a figure set is 3.4 MB and the
##            manifests make every set reconstructible on demand.
##            THIRTY PUBLISHED TAGS SHARE NINE MANIFESTS, because most
##            revisions fix an extraction rather than add a report, so
##            DISTINCT=1 builds the nine that can differ and writes an index
##            naming the tags that share each.
figures-release:
	uv run python scripts/build_release_figures.py \
		$(if $(DISTINCT),--distinct,--tag $(TAG))

## figures-compare -- OFFLINE. Which figures differ between two rebuilt
##            releases, by bytes. Names where to look; it does not say how.
##              make figures-compare FROM=data/2026-08-22 TO=data/2026-08-29-r1
figures-compare:
	@a="data/build/figures/$(subst /,-,$(FROM))"; \
	 b="data/build/figures/$(subst /,-,$(TO))"; \
	 test -d "$$a" || { echo "not built: $$a -- run make figures-release TAG=$(FROM)"; exit 2; }; \
	 test -d "$$b" || { echo "not built: $$b -- run make figures-release TAG=$(TO)"; exit 2; }; \
	 echo "$(FROM) -> $(TO)"; \
	 for f in $$(ls "$$a"); do \
		if [ ! -f "$$b/$$f" ]; then echo "  only in $(FROM): $$f"; \
		elif cmp -s "$$a/$$f" "$$b/$$f"; then echo "  unchanged  $$f"; \
		else echo "  CHANGED    $$f"; fi; \
	 done

## verdict -- OFFLINE. One screen: is this build safe to release? Reads the
##            status files the build already wrote and sorts what it found into
##            BLOCKING (stop), SOURCE (the reports contradict themselves —
##            expected, recorded, not ours) and READER (a wording we refused
##            rather than guessed — costs coverage, never correctness). Exits 1
##            if anything is blocking, so CI can use it. Colour only at a
##            terminal; NO_COLOR is honoured.
verdict:
	@uv run python scripts/build_verdict.py

## watch-data-channel -- poll the shared data channel (which lives in the
##            modelling repo's tree) and exit as soon as they write, printing
##            the added lines. Run it in the background; the exit is the
##            notification. Copied from their watcher so both sides behave
##            the same way.
CHANNEL ?= ../ebola-bdbv-camdl/data-agent-channel.md
watch-data-channel:
	# ONE-SHOT BY DEFAULT, because the exit IS the notification: a harness
	# that re-invokes on completion wakes with the added lines in hand.
	# `--loop` re-arms instead, which is right for a human watching a
	# terminal and WRONG for an agent -- it fires, prints, re-arms, and
	# nobody is woken. That is what this target used to do. LOOP=1 restores
	# it for the human case. `--state` persists the last REPORTED line
	# count, so re-arming between runs loses nothing.
	uv run python scripts/watch_data_channel.py --file $(CHANNEL) --notify \
		$(if $(LOOP),--loop,) --state logs/.data_channel_seen \
		--interval $(or $(INTERVAL),60) --timeout $(or $(TIMEOUT),21600)

## release-check -- build the COMMITTED state in a scratch clone before
##            tagging. Exists because r5 shipped a build that crashed after
##            writing its files: the working tree masked the exit code, and
##            only the consumer's clean-clone rebuild caught it. The PDF
##            archive is not committed, so it is shared into the clone.
##            It also regenerates the COMMITTED figures in the clone and
##            requires them to be byte-identical to the ones in git. Those
##            figures are published artefacts -- the README embeds them and
##            the cross-repo channel links them -- so a stale one is a wrong
##            claim that travels. They went stale exactly once, silently:
##            figures/streams_detail.png still showed the pre-r1
##            laboratory series after the death-split fix landed. Figure
##            output is byte-deterministic (verified: two builds from
##            identical data hash the same), so equality is a fair test and a
##            diff here means the committed copy was not refreshed.
##            Ephemeral EDA figures under data/build are NOT gated: nothing
##            links them and they are rebuilt on demand.
RC_DIR ?= /tmp/ebola-bdbv-release-check
release-check:
	rm -rf $(RC_DIR)
	git clone -q . $(RC_DIR)
	# THE ARCHIVE IS SHARED FILE BY FILE, not by symlinking the directory.
	# Three reports (001, 002, 004) are COMMITTED -- INSP does not serve them
	# and nothing can fetch them again -- so the clone already has a real
	# `data/raw/sitrep_pdfs/` holding them, and `ln -s src dir` would put the
	# link INSIDE it and leave the gate reading three PDFs. Linking only what
	# the clone lacks also keeps the committed three as the real bytes git
	# holds, which is what this gate is supposed to be testing.
	@mkdir -p $(RC_DIR)/data/raw/sitrep_pdfs
	@for f in $$(pwd)/data/raw/sitrep_pdfs/*.pdf; do \
		b=$$(basename $$f); \
		test -e $(RC_DIR)/data/raw/sitrep_pdfs/$$b \
			|| ln -s $$f $(RC_DIR)/data/raw/sitrep_pdfs/$$b; \
	done
	@echo "--- the committed reports must be the bytes their register names ---"
	cd $(RC_DIR) && uv run python scripts/verify_archive.py \
		--pdfs data/raw/sitrep_pdfs --manifest data/raw/sitrep_pdfs.manifest.tsv
	# external/ is gitignored but pinned in external.lock, so share the
	# verified checkout rather than re-cloning it over the network: an
	# offline gate must stay offline.
	@test -d external || { echo "release-check needs external/ -- run 'make external'"; exit 2; }
	ln -s $$(pwd)/external $(RC_DIR)/external
	cd $(RC_DIR) && make build && make streams && make figures && make compare
	@echo "--- committed figures must match what the committed state produces ---"
	@for f in $$(git ls-files 'figures/*.png'); do \
		cmp -s "$$f" "$(RC_DIR)/$$f" \
			&& echo "    ok    $$f" \
			|| { echo "    STALE $$f -- rebuild and commit it"; exit 3; }; \
	done
	@echo "release-check PASSED: the committed state builds from a fresh clone,"
	@echo "and every committed figure is reproducible from it"

## escape-fraction -- the share of confirmed cases first ascertained AT DEATH
##            rather than alive, reported under four exclusion rules because
##            backlog releases and span mismatches both bias it downward.
##            Read-only diagnostic over the built streams; pins gamma*q/tau
##            for the modelling repo without any disease-course assumption.
escape-fraction:
	uv run python scripts/escape_fraction.py --streams data/build/streams

## care-ledger -- the care exit rate (delta) and the fatality among those who
##            reach care (f_cfr), from the census, recovery and death-split
##            streams. Community deaths are held OUT: they never entered the
##            census, and charging them against it inflates both.
care-ledger:
	uv run python scripts/care_ledger.py --streams data/build/streams

## oneoff-death-flow -- DISPOSABLE diagram: where a death goes, from the
##            event to the likelihood, with the two lossy edges named.
oneoff-death-flow:
	uv run python scripts/oneoff_death_flow.py \
		--out data/build/figures/oneoff_death_flow.png

## oneoff-death-split -- DISPOSABLE question figure: what the community-death
##            streams contain (two counts, not a percentage). Delete with
##            scripts/oneoff_death_split.py when settled.
oneoff-death-split:
	uv run python scripts/oneoff_death_split.py \
		--out data/build/figures/oneoff_death_split.png

## oneoff-testing -- DISPOSABLE question figure: did testing keep pace with
##            incidence? Not part of `figures`, not referenced by any
##            document. Delete scripts/oneoff_testing_effort.py and this
##            target together when the question is settled.
oneoff-testing:
	uv run python scripts/oneoff_testing_effort.py \
		--out data/build/figures/oneoff_testing_effort.png

## doc     -- render analysis/data.html against the built artefacts.
##            Every read the document makes is fail-closed through _guard.py:
##            an artefact no rule produces, or one not yet built, stops the
##            render rather than shipping a stale page.
doc:
	cd analysis && QUARTO_PYTHON=$$(cd .. && uv run python -c 'import sys;print(sys.executable)') \
		quarto render data.qmd --to html
	cd analysis && QUARTO_PYTHON=$$(cd .. && uv run python -c 'import sys;print(sys.executable)') \
		quarto render explore.qmd --to html

## serve   -- serve the rendered pages on PORT (default 8790).
##            Check the port first; if something else holds it, override:
##            `make serve PORT=8791`. Serves analysis/ only; both pages are
##            self-contained, so nothing else needs to resolve.
PORT ?= 8790
serve:
	@lsof -iTCP:$(PORT) -sTCP:LISTEN -n -P >/dev/null 2>&1 \
		&& echo "port $(PORT) is already in use -- reuse it if it is ours, or: make serve PORT=<other>" \
		|| (nohup python3 -m http.server $(PORT) --bind 0.0.0.0 \
			--directory analysis </dev/null >/tmp/ebola-bdbv-serve.log 2>&1 & \
			echo "serving: http://thuja:$(PORT)/data.html and /explore.html")

## test    -- the pure-function tests.
test:
	uv run pytest tests/ -q
