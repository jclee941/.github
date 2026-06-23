from __future__ import annotations

import fcntl
import json
import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

ACTIVE_STATUSES: Final = frozenset({"queued", "running"})
ACTIVE_JOB_STALE_AFTER: Final = timedelta(hours=6)


class InvalidReadmeJobId(ValueError):
    pass


def _job_dir() -> Path:
    path = Path(os.environ.get("README_AUTOMATION_JOB_DIR", "/tmp/jclee-bot-readme-jobs"))
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _job_path(job_id: str) -> Path:
    if not job_id or any(ch not in "0123456789abcdef-" for ch in job_id):
        raise InvalidReadmeJobId("invalid job id")
    return _job_dir() / f"{job_id}.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def _active_job_lock() -> Iterator[None]:
    lock_path = _job_dir() / ".active-job.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_job(job: dict[str, Any]) -> None:
    path = _job_path(str(job["id"]))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(job, tmp, ensure_ascii=False)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
    path.chmod(0o600)


def create_job(*, owner: str, repos: list[str] | None, dry_run: bool) -> dict[str, Any]:
    job = {
        "id": str(uuid.uuid4()),
        "status": "queued",
        "owner": owner,
        "repos": repos,
        "dry_run": dry_run,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _write_job(job)
    return job


def create_or_reuse_active_job(*, owner: str, repos: list[str] | None, dry_run: bool) -> tuple[dict[str, Any], bool]:
    with _active_job_lock():
        now = datetime.now(UTC)
        for path in sorted(_job_dir().glob("*.json")):
            job = json.loads(path.read_text(encoding="utf-8"))
            if (
                job.get("status") in ACTIVE_STATUSES
                and job.get("owner") == owner
                and job.get("repos") == repos
                and job.get("dry_run") is dry_run
            ):
                updated_at_raw = job.get("updated_at")
                job_is_stale = True
                if isinstance(updated_at_raw, str):
                    try:
                        updated_at = datetime.fromisoformat(updated_at_raw)
                    except ValueError:
                        job_is_stale = True
                    else:
                        if updated_at.tzinfo is None:
                            updated_at = updated_at.replace(tzinfo=UTC)
                        job_is_stale = now - updated_at > ACTIVE_JOB_STALE_AFTER
                if job_is_stale:
                    job["status"] = "failed"
                    job["error"] = "stale README automation job expired before completion"
                    job["updated_at"] = _now()
                    _write_job(job)
                    continue
                return job, True
        return create_job(owner=owner, repos=repos, dry_run=dry_run), False


def mark_running(job_id: str) -> None:
    job = get_job(job_id)
    job["status"] = "running"
    job["updated_at"] = _now()
    _write_job(job)


def mark_spawned(job_id: str, *, pid: int) -> None:
    job = get_job(job_id)
    job["worker_pid"] = pid
    job["updated_at"] = _now()
    _write_job(job)


def mark_progress(job_id: str, repository_result: dict[str, Any]) -> None:
    job = get_job(job_id)
    result = job.setdefault("result", {"dry_run": job.get("dry_run", False), "repositories": []})
    repositories = result.setdefault("repositories", [])
    repositories.append(repository_result)
    job["status"] = "running"
    job["progress"] = {
        "repository_count": len(repositories),
        "error_count": sum(1 for item in repositories if item.get("error")),
    }
    job["updated_at"] = _now()
    _write_job(job)


def mark_finished(job_id: str, result: dict[str, Any]) -> None:
    job = get_job(job_id)
    job["status"] = "completed"
    job["result"] = result
    repositories = result.get("repositories", [])
    if isinstance(repositories, list):
        job["progress"] = {
            "repository_count": len(repositories),
            "error_count": sum(1 for item in repositories if isinstance(item, dict) and item.get("error")),
        }
    job["updated_at"] = _now()
    _write_job(job)


def mark_failed(job_id: str, error: str) -> None:
    job = get_job(job_id)
    job["status"] = "failed"
    job["error"] = error
    job["updated_at"] = _now()
    _write_job(job)


def get_job(job_id: str) -> dict[str, Any]:
    path = _job_path(job_id)
    if not path.exists():
        raise FileNotFoundError(job_id)
    return json.loads(path.read_text(encoding="utf-8"))
