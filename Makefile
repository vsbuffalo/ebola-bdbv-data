# Data pipeline entry points. Networked steps are separate from ordinary builds
# by design: `build` and `doc` never touch the network, so a rebuild can never
# silently change what the source says.

.PHONY: check fetch verify build streams compare figures external doc test

## check   -- is the archive current, and does the source still look the same?
##            Exit 0 current, 1 behind, 2 the source moved, 3 unreachable.
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

## verify  -- OFFLINE. Every held PDF hashes to what the manifest records.
verify:
	uv run python scripts/verify_archive.py --pdfs data/raw/sitrep_pdfs \
		--manifest data/raw/sitrep_pdfs.manifest.tsv

## build   -- OFFLINE. PDFs -> health-zone extraction -> province aggregation.
##            Stops with exit 2 if a province total disagrees with the sum of
##            its parts; that is a finding, not a nuisance.
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
	uv run python scripts/aggregate_provinces.py \
		--panel data/build/series/zone_table.csv \
		--pdfs data/raw/sitrep_pdfs \
		--exceptions registers/reconciliation_exceptions.tsv \
		--out data/build/series/province_series.csv
	# sibling outputs of the steps above:
	#   data/build/series/zone_table_status.csv
	#   data/build/series/province_summary_status.csv
	#   data/build/series/prose_provinces_status.csv
	#   data/build/series/province_series_reconciliation.csv

## streams -- OFFLINE. The weekly observation streams the models fit.
##            Fails unless every stream's emitted total equals what the
##            source's cumulative moved; the grid is also checked against
##            every printed province row and the gaps land in meta.json.
streams:
	uv run python scripts/build_streams.py \
		--panel data/build/series/zone_table.csv \
		--geojson data/raw/health_zones.geojson \
		--population data/raw/zone_population.csv \
		--out-dir data/build/streams
	# writes, one file per stream:
	#   data/build/streams/cases_ituri.tsv      data/build/streams/deaths_ituri.tsv
	#   data/build/streams/cases_nord_kivu.tsv  data/build/streams/deaths_nord_kivu.tsv
	#   data/build/streams/cases_haut_uele.tsv  data/build/streams/deaths_haut_uele.tsv
	#   data/build/streams/community_deaths_ituri.tsv
	#   data/build/streams/community_deaths_nord_kivu.tsv
	#   data/build/streams/meta.json
	uv run python scripts/build_uganda_stream.py \
		--uganda data/raw/uganda_cases.toml \
		--out data/build/streams/uganda_exports.tsv

## compare -- ours against the two other extraction lineages of the same PDFs.
##            Paths default to sibling checkouts; override INRB_DIR / SCAN.
##            Agreement is evidence about transcription, never about the counts;
##            a disagreement is always a finding and lands in compare/.
INRB_DIR ?= external/BDBV2026-Data
SCAN     ?= ../epiforecast-repro/raw/insp_sitrep_scanned.csv

## external -- clone the comparison sources into external/ (gitignored).
##            INRB-UMIE's transcription comes from its own repository;
##            the epiforecasts scan lives in the local epiforecast-repro
##            checkout, whose path SCAN can override.
external:
	mkdir -p external
	test -d external/BDBV2026-Data || \
		git clone --depth 1 https://github.com/INRB-UMIE/BDBV2026-Data \
		external/BDBV2026-Data
	cd external/BDBV2026-Data && git log -1 --format='%H %cs' \
		> ../BDBV2026-Data.commit
compare:
	uv run python scripts/compare_extractions.py \
		--zone-table data/build/series/zone_table.csv \
		--summary data/build/series/province_summary.csv \
		--inrb $(INRB_DIR) --scan $(SCAN) \
		--out-dir data/build/compare \
		--figure data/build/compare/comparison.png
	# also writes: data/build/compare/inrb_disagreements.csv
	#              data/build/compare/scan_comparison.csv
	#              data/build/compare/zone_comparison.csv

## figures -- OFFLINE. The EDA figures, from the built series.
figures: 
	uv run python scripts/plot_figures.py --figure availability \
		--out data/build/figures/availability.png
	uv run python scripts/plot_figures.py --figure province_series \
		--out data/build/figures/province_series.png
	uv run python scripts/plot_figures.py --figure streams_detail \
		--out data/build/figures/streams_detail.png
	uv run python scripts/plot_figures.py --figure residuals \
		--out data/build/figures/residuals.png

## doc     -- render analysis/data.html against the built artefacts.
##            Every read the document makes is fail-closed through _guard.py:
##            an artefact no rule produces, or one not yet built, stops the
##            render rather than shipping a stale page.
doc:
	cd analysis && QUARTO_PYTHON=$$(cd .. && uv run python -c 'import sys;print(sys.executable)') \
		quarto render data.qmd --to html
	cd analysis && QUARTO_PYTHON=$$(cd .. && uv run python -c 'import sys;print(sys.executable)') \
		quarto render explore.qmd --to html

## test    -- the pure-function tests.
test:
	uv run pytest tests/ -q
