from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

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
