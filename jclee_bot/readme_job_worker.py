from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from functools import partial

from jclee_bot import readme_jobs
from jclee_bot.readme_runner import run_app_readme_automation, sanitize_error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a jclee-bot README automation job.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repo", action="append", default=[])
    return parser


def _job_id_from_args(args: Sequence[str]) -> str | None:
    for index, value in enumerate(args):
        if value.startswith("--job-id="):
            return value.removeprefix("--job-id=")
        if value == "--job-id" and index + 1 < len(args):
            return args[index + 1]
    return None


def _secrets_to_sanitize(private_key: str) -> list[str]:
    names = [
        "GITHUB_PRIVATE_KEY",
        "CLIPROXY_API_KEY",
        "CLIPROXY_MANAGEMENT_KEY",
        "ISSUE_MAINTENANCE_TOKEN",
        "README_AUTOMATION_TOKEN",
    ]
    return [value for value in [private_key, *(os.environ.get(name, "") for name in names)] if value]


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _parser().parse_args(raw_args)
    except SystemExit:
        job_id = _job_id_from_args(raw_args)
        if job_id:
            try:
                readme_jobs.mark_failed(job_id, "invalid README automation worker arguments")
            except (FileNotFoundError, ValueError):
                pass
        return 2
    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        readme_jobs.mark_failed(args.job_id, "github app credentials unavailable")
        return 1

    try:
        readme_jobs.mark_running(args.job_id)
        result = run_app_readme_automation(
            app_id=app_id,
            private_key=private_key,
            owner=args.owner,
            dry_run=args.dry_run,
            repo_names=set(args.repo) if args.repo else None,
            progress=partial(readme_jobs.mark_progress, args.job_id),
        )
        readme_jobs.mark_finished(args.job_id, result)
    except Exception as exc:  # noqa: BLE001 - worker must persist failure status
        readme_jobs.mark_failed(args.job_id, sanitize_error(exc, secrets=_secrets_to_sanitize(private_key)))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
