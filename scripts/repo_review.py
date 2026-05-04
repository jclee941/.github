#!/usr/bin/env python3
"""Whole-repo review entrypoint using pr-agent's LocalGitProvider.

Runs pr-agent's PRReviewer against a local clone of a target repository
where the head commit is the default branch HEAD and the base is either
the root commit (for tiny repos) or HEAD~N (for larger repos).

Output: writes a review.md inside the repo path; the orchestrator (the
Go CLI in scripts/cmd/repo-review) reads it and files it as a GitHub
issue on the target repo.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: str | None = None) -> str:
    """Run a command, return stdout, raise on failure."""
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def prepare_review_branch(repo_path: str, since_commits: int) -> tuple[str, str, int]:
    """Create a local 'repo-review-base' branch at the appropriate base SHA.

    Returns (base_sha, base_branch_name, total_commits).
    """
    total = int(run(["git", "rev-list", "--count", "HEAD"], cwd=repo_path))
    if total <= since_commits:
        # Use root commit for tiny repos.
        base_sha = run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=repo_path).split("\n")[-1].strip()
    else:
        base_sha = run(["git", "rev-parse", f"HEAD~{since_commits}"], cwd=repo_path)

    base_branch = "repo-review-base"
    # Replace existing branch if it exists.
    subprocess.run(
        ["git", "branch", "-D", base_branch],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    run(["git", "branch", base_branch, base_sha], cwd=repo_path)
    return base_sha, base_branch, total


def diff_size_bytes(repo_path: str, base_branch: str) -> int:
    """Return total chars of the diff between base_branch..HEAD."""
    proc = subprocess.run(
        ["git", "diff", f"{base_branch}..HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return len(proc.stdout)


def configure_pr_agent(model: str, response_language: str, review_path: str) -> None:
    """Apply runtime overrides for pr-agent."""
    from pr_agent.config_loader import get_settings

    s = get_settings()
    s.set("CONFIG.git_provider", "local")
    s.set("CONFIG.publish_output", True)
    s.set("CONFIG.model", model)
    s.set("CONFIG.fallback_models", ["kimi-k2.5", "claude-sonnet-4-6"])
    s.set("CONFIG.response_language", response_language)
    s.set("CONFIG.ai_timeout", 180)
    s.set("CONFIG.custom_model_max_tokens", 128000)
    s.set("LOCAL.review_path", review_path)
    s.set("PR_REVIEWER.inline_code_comments", False)
    s.set("PR_REVIEWER.persistent_comment", False)
    s.set("PR_REVIEWER.publish_output_no_suggestions", False)
    s.set("PR_REVIEWER.require_score_review", True)
    s.set("PR_REVIEWER.require_tests_review", True)
    s.set("PR_REVIEWER.require_security_review", True)
    s.set("PR_REVIEWER.num_max_findings", 10)
    s.set(
        "PR_REVIEWER.extra_instructions",
        (
            "이 리뷰는 전체 레포지토리 스냅샷 리뷰입니다. 다음 관점에서 체계적으로 점검:\n"
            "1. 보안: secrets/credentials 노출, SQL injection, XSS, 인증/인가\n"
            "2. 정확성: 논리 오류, 경쟁 조건, edge case 미처리\n"
            "3. 유지보수성: 코드 중복, 과도한 복잡성, 테스트 부재\n"
            "4. 의존성: outdated/취약 패키지, 사용하지 않는 deps\n"
            "5. 운영성: 로깅, 모니터링, 에러 처리, 설정 관리\n"
            "각 발견사항에 심각도([CRITICAL]/[WARNING]/[INFO])와 파일:라인을 명시."
        ),
    )


async def run_review(target_branch: str) -> None:
    """Invoke pr-agent's review tool against the local repo."""
    from pr_agent.tools.pr_reviewer import PRReviewer

    # The LocalGitProvider derives the repo from cwd / git_provider config.
    # PRReviewer interprets pr_url as the local target branch when provider is 'local'.
    reviewer = PRReviewer(target_branch)
    await reviewer.run()


def main() -> int:
    parser = argparse.ArgumentParser(description="Whole-repo review using pr-agent + LocalGitProvider")
    parser.add_argument("--repo-path", required=True, help="Absolute path to the cloned repo")
    parser.add_argument("--review-path", required=True, help="Absolute path to write review.md")
    parser.add_argument(
        "--since-commits", type=int, default=50, help="Commits back from HEAD to use as base (root if smaller)"
    )
    parser.add_argument("--diff-size-limit", type=int, default=100_000, help="Skip if diff exceeds this many chars")
    parser.add_argument("--model", default="kimi-k2.6")
    parser.add_argument("--response-language", default="ko")
    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    if not (repo_path / ".git").exists():
        print(f"::error::not a git repo: {repo_path}", file=sys.stderr)
        return 2

    review_path = Path(args.review_path).resolve()
    review_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: prepare review base branch
    try:
        base_sha, base_branch, total = prepare_review_branch(str(repo_path), args.since_commits)
    except subprocess.CalledProcessError as e:
        print(f"::error::failed to prepare base branch: {e.stderr}", file=sys.stderr)
        return 3
    print(f"prepared base: {base_branch}={base_sha[:12]} total_commits={total} since={args.since_commits}")

    # Step 2: diff size guard
    size = diff_size_bytes(str(repo_path), base_branch)
    print(f"diff size: {size} chars")
    if size > args.diff_size_limit:
        # Write a stub review noting the skip rather than failing the whole batch.
        review_path.write_text(
            f"## Bot Review: skipped (oversized diff)\n\n"
            f"- diff size: {size} chars (limit {args.diff_size_limit})\n"
            f"- base: {base_sha[:12]}\n"
            f"- total commits: {total}\n\n"
            f"Increase `--diff-size-limit` or reduce `--since-commits` to review this repo.\n"
        )
        return 0
    if size == 0:
        review_path.write_text(
            f"## Bot Review: skipped (empty diff)\n\n"
            f"- base: {base_sha[:12]}\n"
            f"- total commits: {total}\n\n"
            f"No changes between base and HEAD; nothing to review.\n"
        )
        return 0

    # Step 3: chdir + configure + run
    os.chdir(repo_path)
    # pr-agent's config_loader caches the repo root; re-import after chdir.
    if "pr_agent.config_loader" in sys.modules:
        # Force re-resolution of repository root.
        for mod_name in list(sys.modules):
            if mod_name.startswith("pr_agent"):
                del sys.modules[mod_name]

    configure_pr_agent(args.model, args.response_language, str(review_path))

    try:
        asyncio.run(run_review(base_branch))
    except Exception as e:
        print(f"::error::review failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 4

    if not review_path.exists() or review_path.stat().st_size == 0:
        print(f"::error::review.md is empty after review run", file=sys.stderr)
        return 5

    # Prepend metadata so the issue body has clear provenance.
    body = review_path.read_text()
    head_sha = run(["git", "rev-parse", "HEAD"], cwd=str(repo_path))
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo_path))
    meta = (
        f"## Bot Review Metadata\n\n"
        f"- **Default branch:** {branch}\n"
        f"- **HEAD commit:** {head_sha}\n"
        f"- **Base:** {base_sha} ({total} total commits, scope={args.since_commits})\n"
        f"- **Diff size:** {size} chars\n"
        f"- **Model:** {args.model}\n"
        f"- **Workflow:** repo-review-batch.yml\n\n"
        f"---\n\n"
    )
    review_path.write_text(meta + body)
    print(f"review written: {review_path} ({review_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
