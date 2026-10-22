#!/bin/zsh
# Publish the rendered site to the gh-pages branch, which GitHub Pages serves.
#
#   scripts/publish_site.sh data/build/site/_site
#
# The branch holds exactly one commit, replaced on every publish: the site is
# ~50 MB, mostly figure galleries, and keeping each version would grow the
# repository by that much per release. The site is derived -- `make site`
# rebuilds any version from its tag -- so its history is worth nothing here.
set -eu
SITE="${1:?usage: publish_site.sh <rendered site dir>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="$(git -C "$ROOT" remote get-url origin)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp -R "$SITE"/. "$STAGE"/
touch "$STAGE/.nojekyll"        # serve _files/ and friends as they are
git -C "$STAGE" init -q -b gh-pages
git -C "$STAGE" add -A
git -C "$STAGE" -c user.name="$(git -C "$ROOT" config user.name)" \
    -c user.email="$(git -C "$ROOT" config user.email)" \
    commit -q -m "site: $(git -C "$ROOT" describe --tags --match 'data/*' --abbrev=0) ($(git -C "$ROOT" rev-parse --short HEAD))"
git -C "$STAGE" push -q -f "$REMOTE" gh-pages
echo "published $(du -sh "$SITE" | cut -f1) to gh-pages"
