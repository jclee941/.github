#!/usr/bin/env python3
"""
Retroactively scan and redact secrets exposed in GitHub Issues and Pull
Requests across all non-archived repositories owned by the authenticated user
(or an explicit ``--owner``).

What it does:
1. Lists repositories under ``--owner`` (default: gh-authenticated user)
2. For each repo, iterates over every Issue and PR (open + closed)
3. Inspects:
   - issue body
   - issue comments
   - PR body
   - PR issue comments
   - PR review comments (inline)
   - PR review summaries
4. Applies ``pr_agent.algo.secret_masking.mask_text`` to detect secrets.
5. If anything would change AND ``--apply`` was passed, calls the GitHub API to
   PATCH the comment/issue/PR body with the redacted version.
6. Otherwise runs in dry-run mode (default) and writes a report.

Authentication: uses ``gh auth token`` from the GitHub CLI.

Usage::

    python scripts/redact_exposed_secrets.py                    # dry-run, current user
    python scripts/redact_exposed_secrets.py --owner jclee941   # dry-run
    python scripts/redact_exposed_secrets.py --owner jclee941 --apply
    python scripts/redact_exposed_secrets.py --owner jclee941 --repo blacklist --apply
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import requests

# Make pr_agent importable regardless of where this script is launched from.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pr_agent.algo.secret_masking import REDACTION, mask_text  # noqa: E402

GITHUB_API = "https://api.github.com"


def _gh_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], check=True, capture_output=True, text=True
        )
        return out.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise SystemExit(
            "No GITHUB_TOKEN/GH_TOKEN env var and `gh auth token` failed. "
            "Run `gh auth login` first."
        ) from e


@dataclass
class Finding:
    repo: str
    kind: str  # issue|issue_comment|pr|pr_comment|pr_review_comment|pr_review
    number: int
    item_id: int  # comment_id (or issue/PR number when editing the body)
    url: str
    original_excerpt: str
    redacted_excerpt: str


@dataclass
class Stats:
    repos_scanned: int = 0
    items_scanned: int = 0
    findings: list[Finding] = field(default_factory=list)
    edits_applied: int = 0
    edits_failed: int = 0


class GitHub:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "pr-agent-secret-redactor/1.0",
            }
        )

    def _request(self, method: str, url: str, **kw) -> requests.Response:
        # Tolerate secondary rate limits.
        for attempt in range(5):
            r = self.s.request(method, url, **kw)
            if r.status_code == 403 and "rate limit" in r.text.lower():
                reset = int(r.headers.get("X-RateLimit-Reset", "0"))
                sleep_for = max(5, reset - int(time.time()) + 1)
                print(f"  rate-limited, sleeping {sleep_for}s ...", file=sys.stderr)
                time.sleep(sleep_for)
                continue
            return r
        return r

    def paginate(self, url: str, params: dict | None = None) -> Iterable[dict]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        while url:
            r = self._request("GET", url, params=params)
            if r.status_code >= 400:
                raise RuntimeError(f"GET {url} -> {r.status_code} {r.text[:200]}")
            for item in r.json():
                yield item
            link = r.headers.get("Link", "")
            url = None
            params = None
            for part in link.split(","):
                seg = part.strip()
                if seg.endswith('rel="next"'):
                    url = seg.split(";")[0].strip().lstrip("<").rstrip(">")
                    break

    def list_repos(self, owner: str) -> list[dict]:
        # /users/{owner}/repos lists all public+private (if token authorized).
        return list(
            self.paginate(
                f"{GITHUB_API}/users/{owner}/repos",
                params={"type": "owner", "sort": "updated"},
            )
        )

    def list_issues(self, owner: str, repo: str) -> list[dict]:
        # Note: the "issues" endpoint includes PRs by default; filter via has "pull_request" key.
        return list(
            self.paginate(
                f"{GITHUB_API}/repos/{owner}/{repo}/issues",
                params={"state": "all"},
            )
        )

    def list_issue_comments(self, owner: str, repo: str, number: int) -> list[dict]:
        return list(
            self.paginate(
                f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}/comments"
            )
        )

    def list_pr_review_comments(self, owner: str, repo: str, number: int) -> list[dict]:
        return list(
            self.paginate(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/comments"
            )
        )

    def list_pr_reviews(self, owner: str, repo: str, number: int) -> list[dict]:
        return list(
            self.paginate(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/reviews"
            )
        )

    # Edit endpoints
    def patch_issue(self, owner: str, repo: str, number: int, body: str) -> bool:
        r = self._request(
            "PATCH",
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}",
            json={"body": body},
        )
        return r.status_code < 300

    def patch_pull(self, owner: str, repo: str, number: int, body: str) -> bool:
        r = self._request(
            "PATCH",
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}",
            json={"body": body},
        )
        return r.status_code < 300

    def patch_issue_comment(self, owner: str, repo: str, comment_id: int, body: str) -> bool:
        r = self._request(
            "PATCH",
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{comment_id}",
            json={"body": body},
        )
        return r.status_code < 300

    def patch_pr_review_comment(self, owner: str, repo: str, comment_id: int, body: str) -> bool:
        r = self._request(
            "PATCH",
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/comments/{comment_id}",
            json={"body": body},
        )
        return r.status_code < 300

    def patch_pr_review(self, owner: str, repo: str, number: int, review_id: int, body: str) -> bool:
        r = self._request(
            "PUT",
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/reviews/{review_id}",
            json={"body": body},
        )
        return r.status_code < 300


def _excerpt(text: str, max_len: int = 120) -> str:
    if text is None:
        return ""
    s = text.replace("\n", " ")
    return (s[: max_len - 1] + "…") if len(s) > max_len else s


def scan_body(
    gh: GitHub,
    owner: str,
    repo: str,
    *,
    kind: str,
    number: int,
    item_id: int,
    url: str,
    body: str,
    stats: Stats,
    apply: bool,
) -> None:
    stats.items_scanned += 1
    if not body or not isinstance(body, str):
        return
    redacted = mask_text(body)
    if redacted == body:
        return  # No secret detected.
    # Find the FIRST diff window for the report excerpt.
    f = Finding(
        repo=f"{owner}/{repo}",
        kind=kind,
        number=number,
        item_id=item_id,
        url=url,
        original_excerpt=_excerpt(_diff_excerpt(body, redacted)[0]),
        redacted_excerpt=_excerpt(_diff_excerpt(body, redacted)[1]),
    )
    stats.findings.append(f)
    print(
        f"  [HIT] {kind:18s} #{number:<5d} {url} :: {f.original_excerpt}",
        flush=True,
    )
    if not apply:
        return
    ok = _apply_edit(gh, owner, repo, kind, number, item_id, redacted)
    if ok:
        stats.edits_applied += 1
        print(f"        -> redacted on GitHub", flush=True)
    else:
        stats.edits_failed += 1
        print(f"        -> EDIT FAILED", flush=True)


def _apply_edit(
    gh: GitHub,
    owner: str,
    repo: str,
    kind: str,
    number: int,
    item_id: int,
    redacted: str,
) -> bool:
    if kind == "issue":
        return gh.patch_issue(owner, repo, number, redacted)
    if kind == "pr":
        return gh.patch_pull(owner, repo, number, redacted)
    if kind in ("issue_comment", "pr_comment"):
        return gh.patch_issue_comment(owner, repo, item_id, redacted)
    if kind == "pr_review_comment":
        return gh.patch_pr_review_comment(owner, repo, item_id, redacted)
    if kind == "pr_review":
        return gh.patch_pr_review(owner, repo, number, item_id, redacted)
    return False


def _diff_excerpt(orig: str, redacted: str) -> tuple[str, str]:
    """Return a short (orig, redacted) snippet around the first divergence."""
    idx = 0
    while idx < min(len(orig), len(redacted)) and orig[idx] == redacted[idx]:
        idx += 1
    start = max(0, idx - 40)
    return orig[start : idx + 80], redacted[start : idx + 80]


def scan_repo(gh: GitHub, owner: str, repo: str, stats: Stats, apply: bool) -> None:
    print(f"==> {owner}/{repo}", flush=True)
    try:
        items = gh.list_issues(owner, repo)
    except Exception as e:
        print(f"  ! failed to list issues: {e}", file=sys.stderr)
        return

    for it in items:
        number = it["number"]
        is_pr = "pull_request" in it
        kind = "pr" if is_pr else "issue"
        # 1. Body
        scan_body(
            gh,
            owner,
            repo,
            kind=kind,
            number=number,
            item_id=number,
            url=it["html_url"],
            body=it.get("body") or "",
            stats=stats,
            apply=apply,
        )
        # 2. Issue/PR conversation comments (PRs use the same endpoint).
        try:
            for c in gh.list_issue_comments(owner, repo, number):
                scan_body(
                    gh,
                    owner,
                    repo,
                    kind=("pr_comment" if is_pr else "issue_comment"),
                    number=number,
                    item_id=c["id"],
                    url=c["html_url"],
                    body=c.get("body") or "",
                    stats=stats,
                    apply=apply,
                )
        except Exception as e:
            print(f"  ! failed to list comments for #{number}: {e}", file=sys.stderr)

        if not is_pr:
            continue
        # 3. PR inline review comments
        try:
            for c in gh.list_pr_review_comments(owner, repo, number):
                scan_body(
                    gh,
                    owner,
                    repo,
                    kind="pr_review_comment",
                    number=number,
                    item_id=c["id"],
                    url=c["html_url"],
                    body=c.get("body") or "",
                    stats=stats,
                    apply=apply,
                )
        except Exception as e:
            print(f"  ! failed to list review comments for #{number}: {e}", file=sys.stderr)
        # 4. PR review summaries
        try:
            for rv in gh.list_pr_reviews(owner, repo, number):
                if not rv.get("body"):
                    continue
                scan_body(
                    gh,
                    owner,
                    repo,
                    kind="pr_review",
                    number=number,
                    item_id=rv["id"],
                    url=rv.get("html_url") or it["html_url"],
                    body=rv.get("body") or "",
                    stats=stats,
                    apply=apply,
                )
        except Exception as e:
            print(f"  ! failed to list reviews for #{number}: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--owner", default=None,
                    help="GitHub owner/user to scan (default: gh-authenticated user)")
    ap.add_argument("--repo", action="append", default=None,
                    help="Limit to specific repo name(s). Repeatable.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually PATCH bodies/comments. Default is dry-run.")
    ap.add_argument("--report", default="redaction_report.json",
                    help="Write findings as JSON to this path.")
    args = ap.parse_args()

    token = _gh_token()
    gh = GitHub(token)

    owner = args.owner
    if not owner:
        r = gh._request("GET", f"{GITHUB_API}/user")
        owner = r.json()["login"]

    print(f"Owner: {owner}")
    print(f"Mode:  {'APPLY (will edit)' if args.apply else 'DRY-RUN (read-only)'}")

    if args.repo:
        repos = [{"name": n, "archived": False, "fork": False} for n in args.repo]
    else:
        repos = gh.list_repos(owner)

    stats = Stats()
    for r in repos:
        if r.get("archived"):
            continue
        stats.repos_scanned += 1
        scan_repo(gh, owner, r["name"], stats, args.apply)

    # Report
    print("\n=================== SUMMARY ===================")
    print(f"Repos scanned:   {stats.repos_scanned}")
    print(f"Items scanned:   {stats.items_scanned}")
    print(f"Findings:        {len(stats.findings)}")
    if args.apply:
        print(f"Edits applied:   {stats.edits_applied}")
        print(f"Edits failed:    {stats.edits_failed}")
    if stats.findings:
        report_path = Path(args.report).resolve()
        report_path.write_text(
            json.dumps(
                {
                    "owner": owner,
                    "mode": "apply" if args.apply else "dry_run",
                    "repos_scanned": stats.repos_scanned,
                    "items_scanned": stats.items_scanned,
                    "edits_applied": stats.edits_applied,
                    "edits_failed": stats.edits_failed,
                    "findings": [
                        {
                            "repo": f.repo,
                            "kind": f.kind,
                            "number": f.number,
                            "item_id": f.item_id,
                            "url": f.url,
                            "original_excerpt": f.original_excerpt,
                            "redacted_excerpt": f.redacted_excerpt,
                        }
                        for f in stats.findings
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print(f"Report written:  {report_path}")
    return 0 if stats.edits_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
