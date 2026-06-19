from __future__ import annotations

import argparse
import os
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


def main() -> int:
    args = _parser().parse_args()
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
        readme_jobs.mark_failed(args.job_id, sanitize_error(exc, secrets=[private_key]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
