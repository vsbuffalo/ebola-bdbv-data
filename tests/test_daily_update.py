"""The daily runner's own bookkeeping, against a throwaway git repository.

Each test is pinned to the run that went wrong on 2026-10-24: a gate failure
left `daily/2026-10-24` behind, the fixing agent's pull request carried the
fetch of sitreps 160-161 into main, and the next two runs then (a) crashed on
`git switch -c` with no issue filed, and (b) released the two reports while
saying "sitreps none new" and sending no summary.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import daily_update as du  # noqa: E402


def sh(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    sh(tmp_path, "init", "-q", "-b", "main")
    sh(tmp_path, "config", "user.email", "t@example.org")
    sh(tmp_path, "config", "user.name", "t")
    manifest = tmp_path / "data/raw/sitrep_pdfs.manifest.tsv"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("file\tbytes\tsha256\nsitrep_159_2026-10-20.pdf\t1\ta\n")
    sh(tmp_path, "add", "-A")
    sh(tmp_path, "commit", "-q", "-m", "start")
    sh(tmp_path, "tag", "-a", "data/2026-10-20-r1", "-m", "r1")
    monkeypatch.setattr(du, "ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def run(tmp_path):
    return du.Run(dry=True, log=tmp_path / "run.log")


def test_reports_fetched_through_a_fix_pr_count_as_new(repo, run):
    m = repo / "data/raw/sitrep_pdfs.manifest.tsv"
    m.write_text(m.read_text() + "sitrep_160_2026-10-21.pdf\t1\tb\n"
                 "sitrep_161_2026-10-22.pdf\t1\tc\n")
    sh(repo, "commit", "-q", "-am", "data: fetch for 2026-10-24")
    assert du.new_reports(run, "HEAD") == []          # what the runner used to ask
    assert du.new_reports(run, "data/2026-10-20-r1") == ["160", "161"]


def test_a_merged_leftover_branch_is_cleared(repo, run):
    sh(repo, "branch", "daily/2026-10-24")
    du.clear_merged_branch(run, "daily/2026-10-24")
    assert sh(repo, "branch", "--list", "daily/2026-10-24") == ""


def test_an_unmerged_leftover_branch_is_kept_and_stops_the_run(repo, run):
    sh(repo, "switch", "-q", "-c", "daily/2026-10-24")
    (repo / "x").write_text("unreviewed")
    sh(repo, "add", "x")
    sh(repo, "commit", "-q", "-m", "work main does not have")
    sh(repo, "switch", "-q", "main")
    with pytest.raises(RuntimeError, match="holds commits main does not"):
        du.clear_merged_branch(run, "daily/2026-10-24")
    assert sh(repo, "branch", "--list", "daily/2026-10-24")


def test_a_crash_files_an_issue_and_exits_nonzero(monkeypatch, tmp_path):
    def boom(run, args):
        raise RuntimeError("git switch -q -c daily/2026-10-24 exited 128")
    filed = []
    monkeypatch.setattr(du, "update", boom)
    monkeypatch.setattr(du, "file_crash", lambda run, e: filed.append(str(e)))
    flagged = []
    monkeypatch.setattr(du, "flag_no_update", lambda run, r: flagged.append(r))
    monkeypatch.setattr(du, "LOGS", tmp_path)
    monkeypatch.setattr(du, "LOCK", tmp_path / "lock")
    monkeypatch.setattr(sys, "argv", ["daily_update.py", "--dry-run"])
    assert du.main() == 1
    assert filed and "exited 128" in filed[0]
    assert flagged and "crashed" in flagged[0]
    assert not (tmp_path / "lock").exists()


def test_the_fixing_agent_adds_no_coauthor_or_attribution():
    """The agent runs with `--setting-sources project,local`, so the user's own
    attribution setting is not loaded; without this one, its commits on
    daily/2026-10-22 and daily/2026-10-24 carried a Claude co-author trailer
    into main."""
    cmd = du.agent_command("x")
    settings = json.loads(Path(cmd[cmd.index("--settings") + 1]).read_text())
    assert settings["attribution"] == {"commit": "", "pr": "", "sessionUrl": False}


def test_a_notice_is_filed_once_and_a_closed_one_is_not_refiled(monkeypatch):
    output = ("CURRENT  --  ...\n"
              "NOTICE: numbering: sitrep 161 (2026-10-22) is followed by 163\n"
              "NOTICE: numbering: sitrep 170 (2026-11-01) is followed by 172\n")
    created = []

    class FakeRun:
        def say(self, msg):
            pass

        def sh(self, cmd, **kw):
            return subprocess.CompletedProcess(
                cmd, 0, "Source notice: numbering: sitrep 161 (2026-10-22) "
                        "is followed by 163\n", "")

        def remote(self, cmd):
            created.append(cmd[cmd.index("--title") + 1])
            return ""

    du.file_notices(FakeRun(), output)
    assert created == ["Source notice: numbering: sitrep 170 (2026-11-01) "
                       "is followed by 172"]


# --------------------------------------------------------------------------
# A run that ships no new report is a failure once the data is a day old.
# Pinned to 2026-10-25..28: SitRep 162-166 were published while every run
# stopped on an open gate failure, and nothing said releases had stalled.

def register(root: Path, rows: list[tuple[str, int]]) -> None:
    """Tag register rows as (tag, shipped this many days ago)."""
    today = du.dt.date.today()
    (root / "registers").mkdir(exist_ok=True)
    (root / "registers/released_tags.tsv").write_text("# header\n" + "".join(
        f"{tag}\t{today - du.dt.timedelta(days=ago)}\tabc\n" for tag, ago in rows))


class IssueRun:
    """Answers `gh issue list` with `open_`, and records every remote call."""
    def __init__(self, open_: list[str]):
        self.open_, self.calls = open_, []

    def say(self, msg):
        pass

    def sh(self, cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, "\n".join(self.open_), "")

    def remote(self, cmd):
        self.calls.append(cmd[:3])
        return ""


def test_a_revision_does_not_reset_the_age_of_the_data(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "ROOT", tmp_path)
    register(tmp_path, [("data/2026-10-20-r0", 6), ("data/2026-10-20-r1", 0)])
    date, shipped = du.data_shipped_on()
    assert date == "2026-10-20"
    assert shipped == du.dt.date.today() - du.dt.timedelta(days=6)


def test_stale_data_opens_one_issue_then_comments_on_it(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "ROOT", tmp_path)
    register(tmp_path, [("data/2026-10-23-r0", 3)])
    fresh = IssueRun([])
    du.flag_no_update(fresh, "releases paused by gate failure #14.")
    assert fresh.calls == [["gh", "issue", "create"]]
    again = IssueRun(["21"])
    du.flag_no_update(again, "releases paused by gate failure #14.")
    assert again.calls == [["gh", "issue", "comment"]]


def test_data_shipped_today_files_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "ROOT", tmp_path)
    register(tmp_path, [("data/2026-10-27-r0", 0)])
    r = IssueRun([])
    du.flag_no_update(r, "INSP has published no report we do not hold.")
    assert r.calls == []


def test_a_release_with_a_new_report_closes_the_issue(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "ROOT", tmp_path)
    register(tmp_path, [("data/2026-10-27-r0", 0)])
    r = IssueRun(["21"])
    du.flag_no_update(r, None)
    assert r.calls == [["gh", "issue", "close"]]
