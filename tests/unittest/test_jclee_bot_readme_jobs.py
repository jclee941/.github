from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from _pytest.monkeypatch import MonkeyPatch

from jclee_bot import readme_jobs


def test_create_or_reuse_active_job_is_atomic_for_concurrent_identical_requests(
    monkeypatch: MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("README_AUTOMATION_JOB_DIR", str(tmp_path))
    original_write_job = readme_jobs._write_job
    start = threading.Barrier(8)

    def slow_write_job(job):
        time.sleep(0.05)
        original_write_job(job)

    monkeypatch.setattr(readme_jobs, "_write_job", slow_write_job)

    def create_job():
        start.wait(timeout=2)
        return readme_jobs.create_or_reuse_active_job(
            owner="jclee941",
            repos=["propose"],
            dry_run=True,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: create_job(), range(8)))

    job_ids = {job["id"] for job, _reused in results}

    assert len(job_ids) == 1
    assert sum(1 for _job, reused in results if reused) == 7
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_create_or_reuse_active_job_expires_stale_running_match(
    monkeypatch: MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("README_AUTOMATION_JOB_DIR", str(tmp_path))
    stale_job = readme_jobs.create_job(owner="jclee941", repos=["propose"], dry_run=True)
    stale_job["status"] = "running"
    stale_job["worker_pid"] = 999_999_999
    stale_job["updated_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    readme_jobs._write_job(stale_job)

    job, reused = readme_jobs.create_or_reuse_active_job(
        owner="jclee941",
        repos=["propose"],
        dry_run=True,
    )

    expired_job = readme_jobs.get_job(str(stale_job["id"]))
    assert reused is False
    assert job["id"] != stale_job["id"]
    assert job["status"] == "queued"
    assert expired_job["status"] == "failed"
    assert "stale" in expired_job["error"]
