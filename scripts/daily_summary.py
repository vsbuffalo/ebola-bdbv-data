"""A modeller's summary of each new situation report, written by an agent and
checked by this script.

    python scripts/daily_summary.py --tag data/2026-10-20-r0 158 159          # write it
    python scripts/daily_summary.py --tag data/2026-10-20-r0 158 159 --send   # and email it

Run by `scripts/daily_update.py` after a release with new reports. Three steps:

  digest   `sitrep_digest.py` sorts each report's sentences into new, updated
           and returning against the reports before it (deterministic).
  agent    headless Claude Code with `scripts/daily_summary_prompt.md`, in the
           same sandbox as the fixing agent and with fewer tools: it can read
           files and nothing else -- no shell, no edits, no network. Its
           answer is its output.
  check    every «quote» in the summary is looked up in the report's own text;
           one that is not there word for word is marked unverified in what is
           sent. This is the guard against an invented quotation, and it is
           mechanical, not a second opinion.

The summary lands in `data/build/summaries/<tag>.md`. `--send` emails it from
the account whose app password is in the login keychain under service
`ebola-bdbv-mail` (the keychain item's account name is the sender address) to
`$DAILY_MAIL_TO`, or else to this checkout's `git config ebola.mailto`, which
keeps the address out of the repository. The password is read after the agent has finished and never
enters its environment.
"""

from __future__ import annotations

import argparse
import os
import re
import smtplib
import subprocess
import sys
import unicodedata
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitrep_digest import OUT, digest, pdf_of, pdftext  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "scripts/daily_summary_prompt.md"
MAIL_SERVICE = "ebola-bdbv-mail"
BUDGET_USD = "5"
TIMEOUT_S = 1800
FOOTER = ("Written by Claude (Anthropic) from the INSP situation report text, "
          "unreviewed. Quotes are checked mechanically against the report; "
          "{checked}.")


def agent_command(prompt: str) -> list[str]:
    """Read-only: the fixing agent's sandbox settings, and only file reading."""
    return ["claude", "-p", prompt,
            "--setting-sources", "project,local",
            "--settings", str(ROOT / "scripts/daily_agent_settings.json"),
            "--strict-mcp-config",
            "--tools", "Read,Glob,Grep",
            "--allowedTools", "Read,Glob,Grep",
            "--max-budget-usd", BUDGET_USD,
            "--output-format", "text"]


def agent_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items()
            if k not in ("GH_TOKEN", "GITHUB_TOKEN")}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).replace("’", "'").replace("‘", "'")
    s = s.replace("-\n", "")
    return re.sub(r"\s+", " ", s).strip()


def check_quotes(summary: str, sources: list[str]) -> tuple[str, int, int]:
    """Mark every «quote» not found verbatim (up to whitespace) in a source."""
    hay = [norm(t) for t in sources]
    total = bad = 0

    def mark(m: re.Match) -> str:
        nonlocal total, bad
        q = norm(m.group(1))
        total += 1
        if any(q in h for h in hay):
            return m.group(0)
        bad += 1
        return m.group(0) + " **[quote not found in the report]**"

    return re.sub(r"«\s*(.+?)\s*»", mark, summary, flags=re.S), total, bad


def write(tag: str, reports: list[int]) -> Path:
    for n in reports:
        digest(n)
    prompt = (PROMPT.read_text()
              .replace("{tag}", tag)
              .replace("{reports}", ", ".join(f"{n:03d}" for n in reports)))
    p = subprocess.run(agent_command(prompt), cwd=ROOT, capture_output=True,
                       text=True, timeout=TIMEOUT_S, env=agent_env())
    if p.returncode or "Headline:" not in p.stdout:
        raise RuntimeError(f"summary agent exited {p.returncode}:\n"
                           f"{(p.stdout + p.stderr)[-3000:]}")
    body = p.stdout[p.stdout.index("Headline:"):].strip()
    sources = []
    for n in reports:
        sources += [pdftext(pdf_of(n), layout=False),
                    (OUT / f"sitrep_{n:03d}" / "text.txt").read_text()]
    body, total, bad = check_quotes(body, sources)
    checked = (f"all {total} found in the report" if not bad
               else f"{bad} of {total} not found, marked in the text")
    out = OUT / f"{tag.replace('/', '_')}.md"
    out.write_text(f"{body}\n\n---\n\n*{FOOTER.format(checked=checked)}*\n")
    return out


def keychain_login() -> tuple[str, str]:
    item = subprocess.run(["security", "find-generic-password", "-s", MAIL_SERVICE],
                          capture_output=True, text=True)
    m = re.search(r'"acct"<blob>="([^"]+)"', item.stdout)
    pw = subprocess.run(["security", "find-generic-password", "-s", MAIL_SERVICE, "-w"],
                        capture_output=True, text=True)
    if item.returncode or pw.returncode or not m:
        raise RuntimeError(f"no keychain item for service {MAIL_SERVICE}")
    return m.group(1), pw.stdout.strip()


def html_of(markdown: str) -> str | None:
    """Markdown to HTML with Quarto's bundled pandoc; plain text only without it."""
    p = subprocess.run(["quarto", "pandoc", "-f", "markdown", "-t", "html"],
                       input=markdown, capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def send(subject: str, markdown: str) -> None:
    to = os.environ.get("DAILY_MAIL_TO") or subprocess.run(
        ["git", "config", "--get", "ebola.mailto"], cwd=ROOT,
        capture_output=True, text=True).stdout.strip()
    if not to:
        raise RuntimeError("no recipient: set DAILY_MAIL_TO or git config ebola.mailto")
    sender, password = keychain_login()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(markdown)
    if (html := html_of(markdown)) is not None:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(sender, password)
        s.send_message(msg)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--send", action="store_true")
    ap.add_argument("reports", type=int, nargs="+")
    args = ap.parse_args()
    try:
        out = write(args.tag, args.reports)
    except Exception as e:                          # tell the reader, then fail
        if args.send:
            send(f"[ebola-bdbv] {args.tag}: summary failed",
                 f"The release `{args.tag}` shipped, but its summary could not "
                 f"be written.\n\n```\n{e}\n```\n")
        raise
    text = out.read_text()
    headline = text.splitlines()[0].removeprefix("Headline:").strip()
    print(out.relative_to(ROOT))
    if args.send:
        send(f"[ebola-bdbv] {args.tag}: {headline}", text)
        print("sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
