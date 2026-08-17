# Data pipeline entry points. Networked steps are separate from ordinary builds
# by design: `build` and `doc` never touch the network, so a rebuild can never
# silently change what the source says.

.PHONY: check fetch refresh verify build streams compare figures external \
	external-update scan-refresh doc serve test

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
	# exit 1 = some reports print no total to check against (a reported gap
	# in the evidence, not a failure); exit 2 = a total disagrees, stop.
	uv run python scripts/aggregate_provinces.py \
		--panel data/build/series/zone_table.csv \
		--pdfs data/raw/sitrep_pdfs \
		--exceptions registers/reconciliation_exceptions.tsv \
		--out data/build/series/province_series.csv || [ $$? -eq 1 ]
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
	uv run python scripts/compare_extractions.py \
		--zone-table data/build/series/zone_table.csv \
		--summary data/build/series/province_summary.csv \
		--prose data/build/series/prose_provinces.csv \
		--inrb $(INRB_DIR) --scan $(SCAN) \
		--out-dir data/build/compare \
		--figure data/build/compare/comparison.png
	# also writes: data/build/compare/inrb_disagreements.csv
	#              data/build/compare/scan_comparison.csv
	#              data/build/compare/zone_comparison.csv
	#              data/build/compare/compare_meta.json

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
