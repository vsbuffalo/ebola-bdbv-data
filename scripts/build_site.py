"""The project website: figures, every data release, and its release notes.

Generates a Quarto website project under `data/build/site/` (gitignored, like
everything derived) and leaves rendering to `quarto render`, which `make site`
runs. Every page is assembled from files the repository already keeps, so the
site cannot say anything the repository does not:

  index        what this is, the latest release, its headline figures;
  figures      every committed figure in `figures/`, each with its caption
               section from `figures/README.md`, so no figure travels without
               its caveats;
  releases     every tag in `registers/released_tags.tsv`, with its data date,
               cut date and commit, its notes from `CHANGELOG.md`, and a link to
               its figure gallery;
  releases/<tag>  that release's figures, as rebuilt by `make figures-release
               DISTINCT=1` from the tag's own pinned inputs. Tags that read the
               same reports share one gallery, because their figures cannot
               differ;
  data.html, explore.html  the rendered documents, copied with the site's
               navigation bar added.

A release with no CHANGELOG section says so, rather than borrowing another's
notes. A release whose figure set has not been rebuilt says that too.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The "mostly written by AI" box: one source, shared with analysis/*.qmd.
NOTICE = (ROOT / "analysis" / "_ai_notice.md").read_text()
sys.path.insert(0, str(ROOT / "scripts"))
from build_release_figures import FIGURES, input_sets, slug  # noqa: E402

#: The figures the home page leads with, in order.
HEADLINE = ("epi_curve", "province_overview", "ascertainment")

#: Where the repository is published, for commit links.
REPO_URL = "https://github.com/vsbuffalo/ebola-bdbv-data"

#: The site's top navigation, in order: (page, label). One list for both the
#: Quarto navbar and the bar written into data.html and explore.html, which are
#: rendered on their own (self-contained, outside this project) and so would
#: otherwise arrive with no way back to the rest of the site.
NAV = (("index.qmd", "Home"), ("figures.qmd", "Figures"),
       ("releases.qmd", "Releases"), ("engineering.qmd", "How it's built"),
       ("data.html", "Data document"), ("explore.html", "Explorer"))


def with_site_nav(html: str, page: str) -> str:
    """`html` with the site's navigation bar as the first thing in its body,
    styled inline to match the Quarto navbar (cosmo's light bar), with `page`
    marked current. Raises if the page has no `<body>` tag, rather than
    shipping a page with no way back."""
    links = "".join(
        f'<a href="{h.replace(".qmd", ".html")}" style="color:'
        f'{"#1f4db5" if h == page else "#545555"};text-decoration:none;'
        f'padding:.5em .6em"{' aria-current="page"' if h == page else ""}>{t}</a>'
        for h, t in NAV)
    bar = ('<nav aria-label="Site" style="background:#f8f9fa;'
           'border-bottom:1px solid #dee2e6;display:flex;flex-wrap:wrap;'
           'align-items:center;padding:.3em 1em;font-size:.95rem">'
           '<a href="index.html" style="color:#545555;text-decoration:none;'
           'font-size:1.1em;margin-right:1em">ebola-bdbv-data</a>'
           f'{links}<a href="{REPO_URL}" style="color:#545555;'
           'text-decoration:none;margin-left:auto;padding:.5em .6em">GitHub</a></nav>')
    new, n = re.subn(r"<body[^>]*>", lambda m: m.group(0) + bar, html, count=1)
    if not n:
        raise SystemExit(f"{page}: no <body> tag to put the site navigation in")
    return new


def released_tags() -> list[dict]:
    with (ROOT / "registers/released_tags.tsv").open() as fh:
        rows = [ln for ln in fh if not ln.startswith("#") and ln.strip()]
    return [dict(zip(("tag", "cut", "commit"), r.rstrip("\n").split("\t")))
            for r in rows if not r.startswith("tag\t")]


def changelog_sections() -> dict[str, str]:
    """Release notes per tag, from the CHANGELOG's `## \\`data/...\\`` sections,
    with headings demoted one level so they nest under the release."""
    text = (ROOT / "CHANGELOG.md").read_text()
    out: dict[str, str] = {}
    parts = re.split(r"(?m)^## ", text)
    for p in parts[1:]:
        head, _, body = p.partition("\n")
        m = re.match(r"`(data/[^`]+)`\s*—\s*[0-9-]+\s*—\s*(.*)", head)
        if m:
            body = re.sub(r"(?m)^(#{3,5}) ", r"#\1 ", body.strip().rstrip("-").strip())
            # Repo-relative links (`notes/...`) resolve on GitHub, not on the site.
            body = re.sub(r"\]\((?!https?:|#)([^)]+)\)", rf"]({REPO_URL}/blob/main/\1)", body)
            out[m.group(1)] = f"**{m.group(2).strip()}**\n\n{body}"
    return out


def captions() -> dict[str, str]:
    """`name.png` -> its caption section from figures/README.md."""
    text = (ROOT / "figures/README.md").read_text()
    out = {}
    for p in re.split(r"(?m)^## ", text)[1:]:
        head, _, body = p.partition("\n")
        m = re.match(r"`([^`]+\.png)`", head)
        if m:
            out[m.group(1)] = re.sub(r"(?m)^(#{3,5}) ", r"#\1 ", body.strip())
    return out


def data_date(tag: str) -> str:
    m = re.match(r"data/(\d{4}-\d{2}-\d{2})", tag)
    return m.group(1) if m else ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "data/build/site")
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "figures").mkdir(parents=True)
    (out / "releases").mkdir()

    tags = released_tags()
    notes = changelog_sections()
    caps = captions()
    groups = input_sets()                          # manifest -> [tags...]
    gallery_of = {t: ts[0] for ts in groups.values() for t in ts}
    shares = {ts[0]: ts for ts in groups.values()}

    (out / "_quarto.yml").write_text("""project:
  type: website
  output-dir: _site
  resources: [data.html, explore.html]
website:
  title: "ebola-bdbv-data"
  navbar:
    left:
""" + "".join(f"      - href: {h}\n        text: {t}\n" for h, t in NAV) + """    right:
      - icon: github
        href: """ + REPO_URL + """
  page-footer:
    center: "Independent work by Vince Buffalo. Not an official product of INSP, WHO or any ministry of health."
format:
  html:
    theme: cosmo
    toc: true
""")

    # --- committed figures, with captions
    for png in sorted((ROOT / "figures").glob("*.png")):
        shutil.copy2(png, out / "figures" / png.name)
    fig_md = ["---", 'title: "Figures"', "---", "", NOTICE,
              "Every figure this repository commits, drawn from the current "
              "build, each with the caption that should travel with it wherever "
              "it's used. Each release's own version of these figures is on "
              "that release's page.", ""]
    for png in sorted((ROOT / "figures").glob("*.png")):
        fig_md += [f"## `{png.name}` {{#{png.stem}}}", "",
                   f"![](figures/{png.name}){{width=100%}}", "",
                   caps.get(png.name, "*No caption recorded.*"), ""]
    (out / "figures.qmd").write_text("\n".join(fig_md))

    # --- per-release galleries
    built = {}
    for first, ts in shares.items():
        src = ROOT / "data/build/figures" / slug(first)
        if not src.is_dir():
            continue
        dst = out / "releases" / slug(first)
        dst.mkdir()
        have = [f for f in FIGURES if (src / f"{f}.png").exists()]
        for f in have:
            shutil.copy2(src / f"{f}.png", dst / f"{f}.png")
        built[first] = have
        md = ["---", f'title: "{first}"', "---", "", NOTICE,
              f"Data date **{data_date(first)}**. "
              + (f"These tags read exactly the same reports, so their figures "
                 f"can't differ: {', '.join(f'`{t}`' for t in ts)}. "
                 if len(ts) > 1 else "")
              + "These are drawn by today's code from this release's own pinned "
                "inputs. So if two releases' galleries look different, it's "
                "because they read different reports, not because the code "
                "changed. The captions are on the "
                "[figures page](../figures.qmd).", ""]
        for f in have:
            md += [f"## `{f}.png`", "", f"![]({slug(first)}/{f}.png){{width=100%}}", ""]
        (out / "releases" / f"{slug(first)}.qmd").write_text("\n".join(md))

    # --- releases index and notes
    rel = ["---", 'title: "Releases"', "---", "", NOTICE,
           "Every data release is a git tag named `data/<date>-r<n>` (six tags from "
           "August are plain `data/<date>`), where the "
           "date is that of the newest report the build read. Once I publish a "
           "tag I never move it or delete it, so a downstream model pinned to a "
           "tag can always get back to the same data. To rebuild a release "
           "byte for byte, check out its tag and run `make fetch-pinned`, then "
           "`make build streams`. In the table, *Cut* is the day the release "
           "was published.", "",
           "| Release | Data date | Cut | Commit | Figures |",
           "| --- | --- | --- | --- | --- |"]
    for t in reversed(tags):
        g = gallery_of.get(t["tag"])
        fig = (f"[gallery](releases/{slug(g)}.qmd)" if g in built
               else "not rebuilt")
        anchor = slug(t["tag"])
        rel.append(f"| [`{t['tag']}`](#{anchor}) | {data_date(t['tag'])} | "
                   f"{t['cut']} | [`{t['commit'][:7]}`]({REPO_URL}/commit/{t['commit']}) | {fig} |")
    rel += ["", "## Release notes", ""]
    for t in reversed(tags):
        rel += [f"### `{t['tag']}` {{#{slug(t['tag'])}}}", "",
                notes.get(t["tag"], "*No release notes were recorded for this tag.*"), ""]
    (out / "releases.qmd").write_text("\n".join(rel))

    # --- home
    latest = tags[-1]["tag"] if tags else "none"
    home = ["---", 'title: "ebola-bdbv-data"',
            'subtitle: "Case data for the 2026 Bundibugyo virus outbreak in the DRC, extracted from the INSP situation reports"',
            "---", "", NOTICE,
            "Case counts for the outbreak, ready for analysis, for the whole "
            "country, for each province, and for each health zone (the DRC's "
            "district-level unit of health administration). They're extracted "
            "from the daily situation reports published by INSP, the DRC's "
            "national public health institute, and every number is checked "
            "against the page that printed it. This is my own independent work "
            "(I'm Vince Buffalo). A scheduled job releases each new day's data once every check "
            "passes. The [repository](" + REPO_URL + ") explains how it all "
            "works and how to get the data.", "",
            f"**Latest release:** [`{latest}`](releases.qmd#{slug(latest)}) · "
            f"[all releases](releases.qmd) · [every figure](figures.qmd) · "
            "[data document](data.html) · [explorer](explore.html)", ""]
    for h in HEADLINE:
        if (ROOT / "figures" / f"{h}.png").exists():
            home += [f"![](figures/{h}.png){{width=100%}}", "",
                     f"[Caption and caveats](figures.qmd#{h})", ""]
    (out / "index.qmd").write_text("\n".join(home))

    # --- how it's built: docs/engineering.md, readable on GitHub and here
    eng = (ROOT / "docs" / "engineering.md").read_text().split("\n", 1)
    (out / "engineering.qmd").write_text(
        "---\ntitle: \"" + eng[0].lstrip("# ") + "\"\n---\n" + eng[1])

    for doc in ("data.html", "explore.html"):
        p = ROOT / "analysis" / doc
        if p.exists():
            (out / doc).write_text(with_site_nav(p.read_text(), doc))
    print(f"site project -> {out}: {len(tags)} releases, "
          f"{len(built)} galleries, {len(list((ROOT / 'figures').glob('*.png')))} figures")


if __name__ == "__main__":
    main()
