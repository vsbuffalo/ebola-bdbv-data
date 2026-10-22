"""The daily update: fetch new reports, gate them, release or ask for a fix.

    python scripts/daily_update.py              # the scheduled run
    python scripts/daily_update.py --dry-run    # everything local, nothing pushed

Scheduled by `make daily-install` (launchd, 14:00 and 22:00). Two tiers:

  deterministic  `make check`; if INSP has published reports we do not hold,
                 `make refresh`, then every gate a release needs: `make test`,
                 `make verdict`, `make check-exports`, and `make release-check`
                 against the committed result. All pass: commit, cut the next
                 `data/<date>-r<n>`, record it in the tag register, push, and
                 comment on the pinned "Daily releases" issue.
  agent          a gate fails: open a `gate-failure` issue at once, then run
                 headless Claude Code on a `daily/<date>` branch with
                 `scripts/daily_fix_prompt.md`. The agent may read, edit, run
                 make and commit locally; it cannot push or tag. This script
                 re-runs the gates over its work, pushes the branch and opens a
                 pull request that closes the issue. Merging that PR is the
                 approval: the next run sees code ahead of the last release and
                 cuts a revision.

While a `gate-failure` issue is open, runs add a comment to it and stop: the
releases are a sequence, and a second agent on the same failure helps nobody.

Notification is GitHub's, via `.github/workflows/daily-status.yml`: an issue
this script opens under your own login does not notify you, so the workflow
@-mentions the owner from the bot account, and fails (turning the README badge
red) while any gate failure is open.

A clean run touches only the files a refresh rewrites -- the committed index
and manifest, the committed figures -- plus the CHANGELOG stub and the tag
register. Anything else in the diff stops the run as a gate failure.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
LOCK = LOGS / "daily.lock"
PROMPT = ROOT / "scripts/daily_fix_prompt.md"

#: The release gates, in order. Each is (name, command).
GATES = [
    ("test", ["make", "test"]),
    ("verdict", ["make", "verdict"]),
    ("check-exports", ["make", "check-exports"]),
]
#: Paths a clean daily refresh may change. Anything else needs a person.
REFRESH_WRITES = ("data/raw/insp_sitrep_index.tsv",
                  "data/raw/sitrep_pdfs.manifest.tsv",
                  "data/raw/PROVENANCE.tsv",
                  "figures/")
#: Changes since the last release that warrant a revision when merged.
#: The scheduling and site scripts are excluded: they change no published file.
RELEASE_RELEVANT = ("scripts/", "registers/", "data/raw/", "pyproject.toml",
                    "uv.lock", ":!scripts/daily_*", ":!scripts/launchd",
                    ":!scripts/cron_*", ":!scripts/build_site.py")
#: What the fixing agent may do. No network, no push, no tags.
AGENT_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep",
               "Bash(make:*)", "Bash(uv run:*)", "Bash(pdftotext:*)",
               "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
               "Bash(git show:*)", "Bash(git add:*)", "Bash(git commit:*)"]
AGENT_BUDGET_USD = "25"
AGENT_TIMEOUT_S = 3 * 3600

LABELS = {"gate-failure": ("b60205", "The daily update stopped on a gate"),
          "priority: high": ("d93f0b", "Needs attention today"),
          "daily-release": ("0e8a16", "The daily release log")}


class Run:
    def __init__(self, dry: bool, log: Path):
        self.dry, self.log = dry, log

    def say(self, msg: str) -> None:
        line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
        print(line, flush=True)
        with self.log.open("a") as fh:
            fh.write(line + "\n")

    def sh(self, cmd: list[str], *, check: bool = False,
           timeout: int | None = None) -> subprocess.CompletedProcess:
        self.say("$ " + " ".join(cmd))
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           timeout=timeout)
        with self.log.open("a") as fh:
            fh.write(p.stdout + p.stderr)
        if check and p.returncode:
            raise RuntimeError(f"{' '.join(cmd)} exited {p.returncode}:\n"
                               f"{tail(p.stdout + p.stderr)}")
        return p

    def remote(self, cmd: list[str]) -> str:
        """A command with effects outside this machine: skipped in a dry run."""
        if self.dry:
            self.say("(dry run, not run) " + " ".join(cmd))
            return ""
        return self.sh(cmd, check=True).stdout.strip()


def tail(text: str, n: int = 60) -> str:
    return "\n".join(text.rstrip().splitlines()[-n:])


def git(run: Run, *args: str) -> str:
    return run.sh(["git", *args], check=True).stdout.strip()


# --------------------------------------------------------------------------
# What is new, and what to call the release

def data_date() -> str:
    text = (ROOT / "data/build/streams/README.md").read_text()
    m = re.search(r"\*\*Data date (\d{4}-\d{2}-\d{2})\*\*", text)
    if not m:
        raise RuntimeError("no data date in data/build/streams/README.md")
    return m.group(1)


def last_tag(run: Run) -> str:
    rows = [ln.split("\t") for ln in
            (ROOT / "registers/released_tags.tsv").read_text().splitlines()
            if ln.startswith("data/")]
    return rows[-1][0]


def next_tag(run: Run, date: str) -> str:
    have = git(run, "tag", "-l", f"data/{date}*").split()
    revs = [int(m.group(1)) for t in have
            if (m := re.fullmatch(rf"data/{date}-r(\d+)", t))]
    if f"data/{date}" in have:          # the pre-September bare form is r1's slot
        revs.append(0)
    return f"data/{date}-r{max(revs) + 1 if revs else 0}"


def new_reports(run: Run, since: str) -> list[str]:
    """Sitrep numbers added to the committed manifest since a ref."""
    diff = git(run, "diff", since, "--", "data/raw/sitrep_pdfs.manifest.tsv")
    return sorted({m.group(1) for m in
                   re.finditer(r"^\+.*?sitrep_(\d{3})", diff, re.M)})


def window_total(stream: str, column: str, since: str) -> int:
    """Sum of a national daily stream over windows starting after `since`."""
    lines = (ROOT / f"data/build/streams/{stream}").read_text().splitlines()
    head = lines[0].split("\t")
    i, j = head.index("window_start"), head.index(column)
    return sum(int(r[j]) for r in (ln.split("\t") for ln in lines[1:])
               if r[i] >= since and r[j] != "NA")


# --------------------------------------------------------------------------
# GitHub

def ensure_labels(run: Run) -> None:
    for name, (colour, desc) in LABELS.items():
        run.remote(["gh", "label", "create", name, "--color", colour,
                    "--description", desc, "--force"])


def open_issues(run: Run, label: str) -> list[str]:
    out = run.sh(["gh", "issue", "list", "--label", label, "--state", "open",
                  "--json", "number", "--jq", ".[].number"])
    return out.stdout.split() if out.returncode == 0 else []


def release_log_issue(run: Run) -> str:
    have = open_issues(run, "daily-release")
    if have:
        return have[0]
    url = run.remote(["gh", "issue", "create", "--title", "Daily releases",
                      "--label", "daily-release", "--body",
                      "One comment per release the daily update cuts. "
                      "Failures are separate issues, labelled `gate-failure`."])
    if url:
        num = url.rsplit("/", 1)[-1]
        run.remote(["gh", "issue", "pin", num])
        return num
    return "0"


def file_failure(run: Run, step: str, output: str, reports: list[str]) -> str:
    body = (f"The daily update of {dt.date.today()} stopped at `{step}`.\n\n"
            f"New reports in this run: {', '.join(reports) or 'none'}.\n\n"
            f"```\n{tail(output, 80)}\n```\n\n"
            "A fixing agent is starting on a `daily/` branch; its pull request "
            "will reference this issue. Releases are paused until it closes.")
    url = run.remote(["gh", "issue", "create", "--title",
                      f"Daily update {dt.date.today()}: `{step}` failed",
                      "--label", "gate-failure", "--label", "priority: high",
                      "--body", body])
    return url.rsplit("/", 1)[-1] if url else "0"


# --------------------------------------------------------------------------
# The two outcomes

def gates(run: Run) -> tuple[str, str] | None:
    """Run every release gate; the first failure as (step, output), or None."""
    for name, cmd in GATES:
        p = run.sh(cmd)
        if p.returncode:
            return name, p.stdout + p.stderr
    return None


def unexpected_changes(run: Run) -> list[str]:
    changed = git(run, "status", "--porcelain").splitlines()
    paths = [ln[3:] for ln in changed]
    return [p for p in paths if not p.startswith(REFRESH_WRITES)]


def changelog_stub(run: Run, tag: str, prev: str, reports: list[str],
                   merged: list[str]) -> None:
    prev_date = re.match(r"data/(\d{4}-\d{2}-\d{2})", prev).group(1)
    date = data_date()
    cases = window_total("cases_daily_national.tsv", "cases_national", prev_date)
    deaths = window_total("deaths_daily_national.tsv", "deaths_national", prev_date)
    lines = [f"## `{tag}` — {dt.date.today()} — daily update", "",
             "Cut automatically by `scripts/daily_update.py`: every release gate "
             "passed (tests, verdict, export quotes, fresh-clone rebuild).", ""]
    if reports:
        lines += [f"**New data.** Sitreps {', '.join(reports)}, data date "
                  f"{prev_date} → {date}: {cases} confirmed cases and {deaths} "
                  "deaths nationally in windows from the previous data date.", ""]
    if merged:
        lines += ["**Fixes merged since the last release** (see each pull "
                  "request for what moved):", ""] + [f"- {m}" for m in merged] + [""]
    if not merged:
        lines += ["**Not breaking.** No code, register or schema changed.", ""]
    lines += ["---", ""]
    path = ROOT / "CHANGELOG.md"
    text = path.read_text()
    at = text.index("\n## `data/") + 1
    path.write_text(text[:at] + "\n".join(lines) + "\n" + text[at:])


def release(run: Run, branch: str, prev: str, reports: list[str],
            merged: list[str]) -> None:
    tag = next_tag(run, data_date())
    changelog_stub(run, tag, prev, reports, merged)
    git(run, "add", "-u")
    git(run, "commit", "-q", "-m",
        f"data: {tag}" + (f", sitreps {reports[0]}–{reports[-1]}" if reports else ""))
    p = run.sh(["make", "release-check"])
    if p.returncode:
        raise GateFailed("release-check", p.stdout + p.stderr)
    if run.dry:
        run.say(f"dry run: every gate passed; would tag {tag}, record it, "
                f"merge {branch} into main and push. Left on {branch}.")
        return
    git(run, "tag", "-a", tag, "-m",
        f"{tag}: automatic daily release; every gate passed. See CHANGELOG.md.")
    commit = git(run, "rev-parse", f"{tag}^{{commit}}")
    with (ROOT / "registers/released_tags.tsv").open("a") as fh:
        fh.write(f"{tag}\t{dt.date.today()}\t{commit}\n")
    git(run, "commit", "-q", "-am", f"releases: record {tag} in the tag register")
    git(run, "switch", "-q", "main")
    git(run, "merge", "-q", "--ff-only", branch)
    run.remote(["git", "push", "-q", "origin", "main", tag])
    git(run, "branch", "-q", "-d", branch)
    log = release_log_issue(run)
    run.remote(["gh", "issue", "comment", log, "--body",
                f"`{tag}` released: sitreps {', '.join(reports) or 'none new'}"
                + (f"; fixes: {'; '.join(merged)}" if merged else "") + "."])
    run.say(f"released {tag}")


class GateFailed(Exception):
    def __init__(self, step: str, output: str):
        super().__init__(step)
        self.step, self.output = step, output


def fix(run: Run, branch: str, failure: GateFailed, reports: list[str],
        no_agent: bool) -> None:
    issue = file_failure(run, failure.step, failure.output, reports)
    if no_agent:
        run.say("--no-agent: stopping after filing the issue")
        return
    verdict = run.sh(["make", "verdict"])
    pr_body = LOGS / f"daily_pr_{dt.date.today()}.md"
    prompt = PROMPT.read_text().format(
        branch=branch, new_reports=", ".join(reports) or "(none)",
        step=failure.step, issue=issue, log_tail=tail(failure.output, 80),
        verdict=tail(verdict.stdout + verdict.stderr, 60),
        pr_body=pr_body.relative_to(ROOT))
    run.say(f"starting the fixing agent on {branch}")
    try:
        agent = run.sh(["claude", "-p", prompt,
                        "--allowedTools", ",".join(AGENT_TOOLS),
                        "--permission-mode", "acceptEdits",
                        "--max-budget-usd", AGENT_BUDGET_USD,
                        "--output-format", "text"],
                       timeout=AGENT_TIMEOUT_S)
        agent_ok = agent.returncode == 0
    except subprocess.TimeoutExpired:
        agent_ok = False
    git(run, "add", "-u")                     # the fetch, if the agent left it
    if git(run, "status", "--porcelain", "--untracked-files=no"):
        git(run, "commit", "-q", "-m", f"data: fetch for {dt.date.today()}")
    after = gates(run)
    status = ("every gate passes on this branch" if after is None
              else f"still failing at `{after[0]}`")
    body = (pr_body.read_text() if pr_body.exists()
            else "The agent left no write-up; see the issue and the run log.")
    body += f"\n\n---\nRunner: {status}. Closes #{issue}."
    run.remote(["git", "push", "-q", "-u", "origin", branch])
    url = run.remote(["gh", "pr", "create", "--head", branch, "--base", "main",
                      "--title", f"Daily {dt.date.today()}: fix `{failure.step}`",
                      "--body", body])
    run.remote(["gh", "issue", "comment", issue, "--body",
                f"Agent {'finished' if agent_ok else 'stopped early'}; {status}. "
                f"Pull request: {url or '(dry run)'}"])
    git(run, "switch", "-q", "main")


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="build, gate, commit and tag locally; push, open and "
                         "comment on nothing")
    ap.add_argument("--no-agent", action="store_true",
                    help="file the issue on a failure but do not start the agent")
    args = ap.parse_args()

    LOGS.mkdir(exist_ok=True)
    run = Run(args.dry_run, LOGS / f"daily_{dt.date.today()}.log")
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 12 * 3600:
        run.say("another daily run holds the lock; stopping")
        return 0
    LOCK.write_text(str(os.getpid()))
    try:
        return update(run, args)
    finally:
        LOCK.unlink(missing_ok=True)


def update(run: Run, args) -> int:
    if git(run, "branch", "--show-current") != "main":
        raise RuntimeError("the daily run starts from main")
    if git(run, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("main has uncommitted changes; not touching it")
    if not args.dry_run:
        git(run, "pull", "-q", "--ff-only")
    ensure_labels(run)

    blocking = open_issues(run, "gate-failure")
    if blocking:
        run.say(f"gate failure #{blocking[0]} is still open; releases paused")
        run.remote(["gh", "issue", "comment", blocking[0], "--body",
                    f"Daily run {dt.date.today()}: paused while this is open."])
        return 0

    check = run.sh(["uv", "run", "python", "scripts/check_upstream.py"])
    prev = last_tag(run)
    merged = [s for s in git(run, "log", "--format=%s", f"{prev}..HEAD",
                             "--", *RELEASE_RELEVANT).splitlines()
              if not s.startswith("releases:")]
    if check.returncode == 3:
        run.say("INSP unreachable; the next run will try again")
        return 0
    if check.returncode in (0, 4) and not merged:
        run.say("current, and nothing merged since the last release")
        return 0

    branch = f"daily/{dt.date.today()}"
    git(run, "switch", "-q", "-c", branch)
    reports: list[str] = []
    try:
        if check.returncode == 2:
            raise GateFailed("check", check.stdout + check.stderr)
        steps = (["make", "refresh"] if check.returncode == 1
                 else ["make", "build", "streams", "figures", "compare", "doc"])
        p = run.sh(steps)
        reports = new_reports(run, "HEAD")
        if p.returncode:
            raise GateFailed(" ".join(steps[1:]), p.stdout + p.stderr)
        stray = unexpected_changes(run)
        if stray:
            raise GateFailed("unexpected changes",
                             "The refresh changed files it should not:\n"
                             + "\n".join(stray))
        failed = gates(run)
        if failed:
            raise GateFailed(*failed)
        release(run, branch, prev, reports, merged)
    except GateFailed as f:
        run.say(f"gate failed: {f.step}")
        fix(run, branch, f, reports, args.no_agent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
