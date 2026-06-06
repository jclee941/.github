"""Tests for scripts/evolution/regression.py (RegressionDetector)."""

from __future__ import annotations

import pytest

from scripts.evolution.errors import FingerprintCollisionError, ValidationError
from scripts.evolution.fingerprint import finding_identity
from scripts.evolution.models import FindingStatus, PullRequestContext, ReviewFinding
from scripts.evolution.regression import RegressionDetector
from scripts.evolution.storage import EvolutionStore


@pytest.fixture
def detector() -> RegressionDetector:
    store = EvolutionStore(":memory:")
    store.initialize()
    return RegressionDetector(store)


def _f(content="bug here", category="bug", file="f.py", start=1, end=2) -> ReviewFinding:
    return ReviewFinding(category, "high", "title", content, file, start, end)


def _ctx(pr=1) -> PullRequestContext:
    return PullRequestContext("jclee941/repo", f"url/{pr}", pr)


class TestIngestNewAndCarryover:
    def test_new_finding_is_not_regression(self, detector):
        matches = detector.ingest_findings(_ctx(1), [_f()])
        assert len(matches) == 1
        assert matches[0].is_regression is False
        assert matches[0].previous_status == FindingStatus.OPEN
        assert "new finding" in matches[0].reason

    def test_repeated_open_finding_not_regression(self, detector):
        f = _f()
        detector.ingest_findings(_ctx(1), [f])
        matches = detector.ingest_findings(_ctx(2), [f])
        assert matches[0].is_regression is False
        # occurrences accumulate
        row = detector.store.get_finding_by_fingerprint("jclee941/repo", finding_identity("jclee941/repo", f).fingerprint)
        assert row["occurrences"] == 2

    def test_multiple_findings_processed_independently(self, detector):
        f1 = _f(content="bug one", file="a.py")
        f2 = _f(content="bug two", file="b.py")
        matches = detector.ingest_findings(_ctx(1), [f1, f2])
        assert len(matches) == 2
        assert all(m.is_regression is False for m in matches)


class TestRegression:
    def test_closed_finding_reappears_is_regression(self, detector):
        f = _f()
        detector.ingest_findings(_ctx(1), [f])
        ident = finding_identity("jclee941/repo", f)
        detector.mark_closed("jclee941/repo", ident.fingerprint, reason="fixed")
        # Reappears in a later PR
        matches = detector.ingest_findings(_ctx(5), [f])
        assert len(matches) == 1
        assert matches[0].is_regression is True
        assert "previously closed" in matches[0].reason.lower()
        # status flipped back to open
        row = detector.store.get_finding_by_fingerprint("jclee941/repo", ident.fingerprint)
        assert row["status"] == "open"
        assert row["closed_at"] is None
        # a 'regressed' event was recorded
        conn = detector.store.connect()
        types = {r[0] for r in conn.execute(
            "SELECT event_type FROM finding_events WHERE finding_id=?", (row["id"],)
        ).fetchall()}
        assert "regressed" in types

    def test_ignored_finding_reappears_is_not_regression(self, detector):
        f = _f()
        detector.ingest_findings(_ctx(1), [f])
        ident = finding_identity("jclee941/repo", f)
        detector.ignore("jclee941/repo", ident.fingerprint, reason="false positive")
        matches = detector.ingest_findings(_ctx(2), [f])
        assert matches[0].is_regression is False
        row = detector.store.get_finding_by_fingerprint("jclee941/repo", ident.fingerprint)
        assert row["status"] == "ignored"


class TestMarkClosed:
    def test_mark_closed_unknown_returns_false(self, detector):
        assert detector.mark_closed("jclee941/repo", "ffffffffffffffff", reason="x") is False

    def test_mark_closed_known_returns_true(self, detector):
        f = _f()
        detector.ingest_findings(_ctx(1), [f])
        ident = finding_identity("jclee941/repo", f)
        assert detector.mark_closed("jclee941/repo", ident.fingerprint, reason="fixed") is True


class TestValidationAndCollision:
    def test_missing_repo_raises(self, detector):
        with pytest.raises(ValidationError):
            detector.ingest_findings(PullRequestContext("  "), [_f()])

    def test_end_before_start_raises(self, detector):
        with pytest.raises(ValidationError):
            detector.ingest_findings(_ctx(1), [_f(start=10, end=5)])

    def test_collision_raises(self, detector, monkeypatch):
        # First ingest establishes a row.
        f = _f()
        detector.ingest_findings(_ctx(1), [f])
        ident = finding_identity("jclee941/repo", f)

        # Force a second, different finding to produce the SAME short fingerprint
        # but a DIFFERENT full fingerprint, simulating a collision.
        import scripts.evolution.regression as regmod
        from scripts.evolution.models import FindingIdentity

        def fake_identity(repo, finding):
            return FindingIdentity(
                fingerprint=ident.fingerprint,           # same short
                fingerprint_full="0" * 64,               # different full
                marker_input="forced-collision",
                normalized_content="x",
            )

        monkeypatch.setattr(regmod, "finding_identity", fake_identity)
        with pytest.raises(FingerprintCollisionError):
            detector.ingest_findings(_ctx(2), [_f(content="totally different")])

    def test_duplicate_findings_in_one_input_dedupe(self, detector):
        f = _f()
        matches = detector.ingest_findings(_ctx(1), [f, f])
        # Two identical findings in one PR must not create two rows.
        ident = finding_identity("jclee941/repo", f)
        row = detector.store.get_finding_by_fingerprint("jclee941/repo", ident.fingerprint)
        assert row["occurrences"] == 1
        # but both inputs are reported
        assert len(matches) == 2
