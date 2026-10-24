"""The daily runner's own bookkeeping, against a throwaway git repository.

Each test is pinned to the run that went wrong on 2026-10-24: a gate failure
left `daily/2026-10-24` behind, the fixing agent's pull request carried the
fetch of sitreps 160-161 into main, and the next two runs then (a) crashed on
`git switch -c` with no issue filed, and (b) released the two reports while
saying "sitreps none new" and sending no summary.
"""

from __future__ import annotations

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
    monkeypatch.setattr(du, "LOGS", tmp_path)
    monkeypatch.setattr(du, "LOCK", tmp_path / "lock")
    monkeypatch.setattr(sys, "argv", ["daily_update.py", "--dry-run"])
    assert du.main() == 1
    assert filed and "exited 128" in filed[0]
    assert not (tmp_path / "lock").exists()
