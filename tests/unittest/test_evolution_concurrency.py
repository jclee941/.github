"""Concurrency stress verification of scripts/evolution/ (검증 고도화).

Proves the SQLite atomicity guarantees hold under GENUINE contention, with both
in-process threads and true multi-process writers against a shared file DB:

  C1 thread/process: N distinct accepted outcomes in the SAME bucket serialize to
     the exact additive total (no lost update).
  C4 thread/process: K identical (suggestion_id, outcome) replays are idempotent
     under contention (count stays 1, single weight step, no error).
  CONFLICT: two workers race accept vs reject on the same suggestion_id -> exactly
     one wins, one is rejected/idempotent; never a torn/double write.
  C3 thread: many workers re-ingest the SAME previously-closed finding at once ->
     final state is a coherent reopened row (TOCTOU-aware assertions).

All tests use a real temp FILE database (``:memory:`` keeps a single shared
connection and would NOT exercise multi-connection contention). Each worker opens
its OWN EvolutionStore/EvolutionScorer (fresh sqlite connection).
"""

from __future__ import annotations

import multiprocessing
import sqlite3
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any

import pytest

from scripts.evolution.errors import DuplicateOutcomeError
from scripts.evolution.fingerprint import finding_identity
from scripts.evolution.models import (
    PullRequestContext,
    ReviewFinding,
    Suggestion,
    SuggestionOutcome,
)
from scripts.evolution.regression import RegressionDetector
from scripts.evolution.scoring import EvolutionScorer
from scripts.evolution.storage import EvolutionStore

REPO = "jclee941/repo"
TIMEOUT = 30.0


def _ctx(pr: int = 1) -> PullRequestContext:
    return PullRequestContext(REPO, f"pr/{pr}", pr)


def _suggestion(sid: str, score: float = 5.0) -> Suggestion:
    return Suggestion(sid, "performance", "perf", f"suggestion {sid}", score, "f.py", 1, 2)


def _weight_row(db_path: str) -> dict[str, Any]:
    store = EvolutionStore(db_path, timeout_seconds=TIMEOUT)
    row = store.get_weight(REPO, "performance", "perf")
    assert row is not None, "expected an evolution_weights row to exist"
    return dict(row)


def _count(db_path: str, sql: str, params=()) -> int:
    conn = sqlite3.connect(db_path, timeout=TIMEOUT)
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Top-level process workers (must be picklable under 'spawn')
# --------------------------------------------------------------------------- #
def proc_record_outcome(db_path: str, sid: str, outcome: str, pr: int, start_event=None) -> str:
    # Wait on the shared start gate so all workers write simultaneously (forces
    # genuine cross-process contention instead of relying on scheduler luck).
    if start_event is not None:
        start_event.wait(timeout=TIMEOUT)
    store = EvolutionStore(db_path, timeout_seconds=TIMEOUT)
    scorer = EvolutionScorer(store)
    try:
        scorer.record_outcome(PullRequestContext(REPO, f"pr/{pr}", pr), _suggestion(sid),
                              SuggestionOutcome(outcome))
        return "ok"
    except DuplicateOutcomeError:
        return "duplicate"


# --------------------------------------------------------------------------- #
# C1 / C4 — thread contention
# --------------------------------------------------------------------------- #
class TestThreadContention:
    def test_distinct_accepts_same_bucket_serialize(self, tmp_path):
        db = str(tmp_path / "ev.sqlite")
        EvolutionStore(db, timeout_seconds=TIMEOUT).initialize()
        n = 8
        barrier = threading.Barrier(n)

        def worker(i: int) -> None:
            barrier.wait()  # force real overlap
            scorer = EvolutionScorer(EvolutionStore(db, timeout_seconds=TIMEOUT))
            scorer.record_outcome(_ctx(i), _suggestion(f"s{i}"), SuggestionOutcome.ACCEPTED)

        with ThreadPoolExecutor(max_workers=n) as ex:
            list(ex.map(worker, range(n)))

        row = _weight_row(db)
        assert row["accepted_count"] == n
        assert row["rejected_count"] == 0
        assert row["unknown_count"] == 0
        assert row["total_updates"] == n
        assert row["weight"] == pytest.approx(round(1.0 + 0.05 * n, 4))  # 1.4, no clamp
        assert _count(db, "SELECT count(*) FROM suggestion_outcomes WHERE repo=?", (REPO,)) == n

    def test_same_outcome_same_suggestion_idempotent(self, tmp_path):
        db = str(tmp_path / "ev.sqlite")
        EvolutionStore(db, timeout_seconds=TIMEOUT).initialize()
        k = 8
        barrier = threading.Barrier(k)
        errors: list[Exception] = []

        def worker(_i: int) -> None:
            barrier.wait()
            scorer = EvolutionScorer(EvolutionStore(db, timeout_seconds=TIMEOUT))
            try:
                scorer.record_outcome(_ctx(), _suggestion("same"), SuggestionOutcome.ACCEPTED)
            except Exception as e:  # pragma: no cover - captured for assertion
                errors.append(e)

        with ThreadPoolExecutor(max_workers=k) as ex:
            list(ex.map(worker, range(k)))

        assert errors == []  # same outcome is idempotent, never DuplicateOutcomeError
        row = _weight_row(db)
        assert row["accepted_count"] == 1
        assert row["rejected_count"] == 0
        assert row["unknown_count"] == 0
        assert row["total_updates"] == 1
        assert row["weight"] == pytest.approx(1.05)
        assert _count(db, "SELECT count(*) FROM suggestion_outcomes WHERE repo=?", (REPO,)) == 1

    def test_conflicting_outcome_exactly_one_wins(self, tmp_path):
        db = str(tmp_path / "ev.sqlite")
        EvolutionStore(db, timeout_seconds=TIMEOUT).initialize()
        barrier = threading.Barrier(2)
        results: list[str] = []
        lock = threading.Lock()

        def worker(outcome: SuggestionOutcome) -> None:
            barrier.wait()
            scorer = EvolutionScorer(EvolutionStore(db, timeout_seconds=TIMEOUT))
            try:
                scorer.record_outcome(_ctx(), _suggestion("same"), outcome)
                res = "ok"
            except DuplicateOutcomeError:
                res = "duplicate"
            with lock:
                results.append(res)

        with ThreadPoolExecutor(max_workers=2) as ex:
            list(ex.map(worker, [SuggestionOutcome.ACCEPTED, SuggestionOutcome.REJECTED]))

        # exactly one stored outcome, exactly one update; the loser is 'duplicate'
        assert _count(db, "SELECT count(*) FROM suggestion_outcomes WHERE repo=?", (REPO,)) == 1
        row = _weight_row(db)
        assert row["total_updates"] == 1
        assert row["accepted_count"] + row["rejected_count"] == 1
        assert row["unknown_count"] == 0
        outcome_row = sqlite3.connect(db).execute(
            "SELECT outcome FROM suggestion_outcomes WHERE repo=? AND suggestion_id=?", (REPO, "same")
        ).fetchone()
        assert outcome_row is not None
        assert outcome_row[0] in {"accepted", "rejected"}
        if outcome_row[0] == "accepted":
            assert row["weight"] == pytest.approx(1.05)
            assert row["accepted_count"] == 1
        else:
            assert row["weight"] == pytest.approx(0.95)
            assert row["rejected_count"] == 1
        assert sorted(results) == ["duplicate", "ok"]


# --------------------------------------------------------------------------- #
# C1 / C4 — process contention (true parallel writers)
# --------------------------------------------------------------------------- #
class TestProcessContention:
    def test_distinct_accepts_same_bucket_serialize(self, tmp_path):
        db = str(tmp_path / "ev.sqlite")
        EvolutionStore(db, timeout_seconds=TIMEOUT).initialize()
        n = 8
        ctx = multiprocessing.get_context("spawn")
        with ctx.Manager() as manager:
            start = manager.Event()
            with ProcessPoolExecutor(max_workers=n, mp_context=ctx) as ex:
                futures = [
                    ex.submit(proc_record_outcome, db, f"s{i}", "accepted", i, start)
                    for i in range(n)
                ]
                start.set()  # release all workers at once -> genuine contention
                results = [f.result(timeout=60) for f in futures]

        assert all(r == "ok" for r in results)
        row = _weight_row(db)
        assert row["accepted_count"] == n
        assert row["total_updates"] == n
        assert row["weight"] == pytest.approx(round(1.0 + 0.05 * n, 4))
        assert _count(db, "SELECT count(*) FROM suggestion_outcomes WHERE repo=?", (REPO,)) == n

    def test_same_outcome_idempotent_across_processes(self, tmp_path):
        db = str(tmp_path / "ev.sqlite")
        EvolutionStore(db, timeout_seconds=TIMEOUT).initialize()
        k = 8
        ctx = multiprocessing.get_context("spawn")
        with ctx.Manager() as manager:
            start = manager.Event()
            with ProcessPoolExecutor(max_workers=k, mp_context=ctx) as ex:
                futures = [
                    ex.submit(proc_record_outcome, db, "same", "accepted", i, start)
                    for i in range(k)
                ]
                start.set()  # release all workers at once -> genuine contention
                results = [f.result(timeout=60) for f in futures]

        assert all(r == "ok" for r in results)  # same outcome idempotent, no conflict
        row = _weight_row(db)
        assert row["accepted_count"] == 1
        assert row["total_updates"] == 1
        assert row["weight"] == pytest.approx(1.05)
        assert _count(db, "SELECT count(*) FROM suggestion_outcomes WHERE repo=?", (REPO,)) == 1


# --------------------------------------------------------------------------- #
# C3 — regression reopen under concurrency (TOCTOU-aware)
# --------------------------------------------------------------------------- #
class TestRegressionConcurrency:
    def test_concurrent_reingest_of_closed_finding(self, tmp_path):
        db = str(tmp_path / "ev.sqlite")
        store0 = EvolutionStore(db, timeout_seconds=TIMEOUT)
        store0.initialize()
        finding = ReviewFinding("security", "critical", "t", "vuln content", "api/x.py", 10, 14)
        ident = finding_identity(REPO, finding)

        # establish + close
        RegressionDetector(store0).ingest_findings(_ctx(1), [finding])
        RegressionDetector(store0).mark_closed(REPO, ident.fingerprint, reason="fixed")

        n = 8
        barrier = threading.Barrier(n)
        regression_flags: list[bool] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker(i: int) -> None:
            barrier.wait()
            det = RegressionDetector(EvolutionStore(db, timeout_seconds=TIMEOUT))
            try:
                matches = det.ingest_findings(_ctx(100 + i), [finding])
                with lock:
                    regression_flags.append(matches[0].is_regression)
            except Exception as e:  # pragma: no cover
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=n) as ex:
            list(ex.map(worker, range(n)))

        assert errors == []
        row = store0.get_finding_by_fingerprint(REPO, ident.fingerprint)
        assert row is not None
        # final state is a coherent reopened row
        assert row["status"] == "open"
        assert row["closed_at"] is None
        # original ingest (occurrences=1) + N reopen/touch increments
        assert row["occurrences"] == 1 + n
        # at least one worker observed the closed->open transition; never more than N.
        regressed_events = _count(
            db, "SELECT count(*) FROM finding_events WHERE event_type='regressed'"
        )
        assert 1 <= regressed_events <= n
        assert 1 <= sum(regression_flags) <= n
