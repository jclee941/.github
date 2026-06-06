"""Tests for scripts/evolution/storage.py (EvolutionStore)."""

from __future__ import annotations

import sqlite3

import pytest

from scripts.evolution.fingerprint import finding_identity
from scripts.evolution.models import (
    FindingEventType,
    PullRequestContext,
    ReviewFinding,
    Suggestion,
    SuggestionOutcome,
    WeightUpdateResult,
)
from scripts.evolution.storage import EvolutionStore


@pytest.fixture
def store() -> EvolutionStore:
    s = EvolutionStore(":memory:")
    s.initialize()
    return s


def _finding(content="c", category="bug", file="f.py", start=1, end=2) -> ReviewFinding:
    return ReviewFinding(category, "high", "t", content, file, start, end)


class TestInitialize:
    def test_creates_all_tables(self, store):
        conn = store.connect()
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in rows}
        assert {
            "schema_version",
            "findings",
            "finding_events",
            "suggestion_outcomes",
            "evolution_weights",
            "refinement_runs",
            "refinement_iterations",
        } <= names

    def test_idempotent(self, store):
        store.initialize()
        store.initialize()  # must not raise
        conn = store.connect()
        version = conn.execute("SELECT max(version) FROM schema_version").fetchone()[0]
        assert version == 2

    def test_foreign_keys_enabled(self, store):
        conn = store.connect()
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


class TestFindingsCrud:
    def test_insert_and_fetch_finding(self, store):
        ctx = PullRequestContext("repo", "url", 1)
        f = _finding()
        ident = finding_identity("repo", f)
        fid = store.upsert_finding_seen(ctx, f, ident)
        assert fid > 0
        row = store.get_finding_by_fingerprint("repo", ident.fingerprint)
        assert row is not None
        assert row["status"] == "open"
        assert row["occurrences"] == 1
        assert row["fingerprint_full"] == ident.fingerprint_full

    def test_upsert_same_finding_increments_occurrences(self, store):
        ctx = PullRequestContext("repo", "url", 1)
        f = _finding()
        ident = finding_identity("repo", f)
        fid1 = store.upsert_finding_seen(ctx, f, ident)
        fid2 = store.upsert_finding_seen(PullRequestContext("repo", "url2", 2), f, ident)
        assert fid1 == fid2
        row = store.get_finding_by_fingerprint("repo", ident.fingerprint)
        assert row["occurrences"] == 2
        assert row["last_pr_number"] == 2

    def test_close_finding(self, store):
        ctx = PullRequestContext("repo", "url", 1)
        f = _finding()
        ident = finding_identity("repo", f)
        store.upsert_finding_seen(ctx, f, ident)
        ok = store.close_finding("repo", ident.fingerprint, reason="resolved")
        assert ok is True
        row = store.get_finding_by_fingerprint("repo", ident.fingerprint)
        assert row["status"] == "closed"
        assert row["close_reason"] == "resolved"
        assert row["closed_at"] is not None

    def test_close_unknown_finding_returns_false(self, store):
        assert store.close_finding("repo", "deadbeefdeadbeef", reason="x") is False

    def test_reopen_finding(self, store):
        ctx = PullRequestContext("repo", "url", 1)
        f = _finding()
        ident = finding_identity("repo", f)
        fid = store.upsert_finding_seen(ctx, f, ident)
        store.close_finding("repo", ident.fingerprint, reason="resolved")
        store.reopen_finding(fid, PullRequestContext("repo", "url3", 3), f)
        row = store.get_finding_by_fingerprint("repo", ident.fingerprint)
        assert row["status"] == "open"
        assert row["occurrences"] == 2
        assert row["closed_at"] is None

    def test_record_event(self, store):
        ctx = PullRequestContext("repo", "url", 1)
        f = _finding()
        ident = finding_identity("repo", f)
        fid = store.upsert_finding_seen(ctx, f, ident)
        store.record_finding_event(fid, ctx, FindingEventType.REGRESSED, {"k": "v"})
        conn = store.connect()
        events = conn.execute(
            "SELECT event_type, details_json FROM finding_events WHERE finding_id=?",
            (fid,),
        ).fetchall()
        types = {e[0] for e in events}
        assert "regressed" in types


class TestConstraints:
    def test_invalid_status_rejected(self, store):
        conn = store.connect()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO findings (repo, fingerprint, fingerprint_full, category, severity, content, normalized_content, status) "
                "VALUES ('r','0123456789abcdef',?,?,?,?,?,'bogus')",
                ("a" * 64, "bug", "high", "c", "c"),
            )

    def test_short_fingerprint_must_be_16(self, store):
        conn = store.connect()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO findings (repo, fingerprint, fingerprint_full, category, severity, content, normalized_content) "
                "VALUES ('r','tooshort',?,?,?,?,?)",
                ("a" * 64, "bug", "high", "c", "c"),
            )

    def test_weight_out_of_bounds_rejected(self, store):
        conn = store.connect()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO evolution_weights (repo, category, weight) VALUES ('r','bug', 99.0)"
            )


class TestSuggestionOutcomes:
    def test_record_and_read_outcome(self, store):
        ctx = PullRequestContext("repo", "url", 1)
        sugg = Suggestion("sid-1", "performance", "perf", "use a set", 7.0, "f.py", 1, 2)
        rid = store.record_suggestion_outcome(
            ctx, sugg, adjusted_score=7.35, outcome=SuggestionOutcome.ACCEPTED, outcome_source="author"
        )
        assert rid > 0
        conn = store.connect()
        row = conn.execute(
            "SELECT outcome, adjusted_score, category FROM suggestion_outcomes WHERE id=?", (rid,)
        ).fetchone()
        assert row[0] == "accepted"
        assert abs(row[1] - 7.35) < 1e-9


class TestWeights:
    def test_get_missing_weight_returns_none(self, store):
        assert store.get_weight("repo", "bug") is None

    def test_upsert_and_get_weight(self, store):
        result = WeightUpdateResult("repo", "bug", "", 1.0, 1.05, 1, 0, 0, "accepted: +0.05")
        store.upsert_weight(result, SuggestionOutcome.ACCEPTED)
        row = store.get_weight("repo", "bug")
        assert row is not None
        assert abs(row["weight"] - 1.05) < 1e-9
        assert row["accepted_count"] == 1
        # second accept accumulates counts
        result2 = WeightUpdateResult("repo", "bug", "", 1.05, 1.10, 2, 0, 0, "accepted: +0.05")
        store.upsert_weight(result2, SuggestionOutcome.ACCEPTED)
        row = store.get_weight("repo", "bug")
        assert row["accepted_count"] == 2
        assert abs(row["weight"] - 1.10) < 1e-9


class TestConcurrencyTransaction:
    def test_transaction_serializes_increment(self, tmp_path):
        # Two stores on the same file; BEGIN IMMEDIATE + busy_timeout must not
        # lose updates to occurrences.
        db = tmp_path / "ev.sqlite"
        s1 = EvolutionStore(str(db), timeout_seconds=5.0)
        s1.initialize()
        s2 = EvolutionStore(str(db), timeout_seconds=5.0)
        ctx = PullRequestContext("repo", "url", 1)
        f = _finding()
        ident = finding_identity("repo", f)
        s1.upsert_finding_seen(ctx, f, ident)
        s2.upsert_finding_seen(PullRequestContext("repo", "url2", 2), f, ident)
        s1.upsert_finding_seen(PullRequestContext("repo", "url3", 3), f, ident)
        row = s1.get_finding_by_fingerprint("repo", ident.fingerprint)
        assert row["occurrences"] == 3


class TestSchemaV2Migration:
    def test_recursive_columns_present(self, store):
        conn = store.connect()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(refinement_runs)").fetchall()}
        assert {
            "parent_run_id", "node_path", "depth",
            "aggregate_quality", "total_iterations",
            "max_observed_depth", "is_recursive_root",
        } <= cols

    def test_migrates_v1_database_additively(self, tmp_path):
        # Build a v1-shaped refinement_runs table, then initialize() must add the
        # recursive columns without dropping the existing row.
        import sqlite3
        db = tmp_path / "v1.sqlite"
        raw = sqlite3.connect(str(db))
        raw.executescript(
            """
            CREATE TABLE schema_version (version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO schema_version (version) VALUES (1);
            CREATE TABLE refinement_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                repo TEXT, pr_url TEXT,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT, initial_quality REAL, final_quality REAL,
                stop_reason TEXT, max_iterations INTEGER NOT NULL,
                threshold REAL NOT NULL, min_delta REAL NOT NULL);
            INSERT INTO refinement_runs (run_id, max_iterations, threshold, min_delta)
                VALUES ('legacy-1', 5, 0.9, 0.01);
            """
        )
        raw.commit()
        raw.close()

        store = EvolutionStore(str(db))
        store.initialize()  # must migrate, not crash
        conn = store.connect()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(refinement_runs)").fetchall()}
        assert "parent_run_id" in cols and "node_path" in cols and "depth" in cols
        row = conn.execute("SELECT run_id, node_path, depth FROM refinement_runs WHERE run_id='legacy-1'").fetchone()
        assert row is not None
        assert row["node_path"] == ""  # default backfilled
        assert row["depth"] == 0
        version = conn.execute("SELECT max(version) FROM schema_version").fetchone()[0]
        assert version == 2


class TestRecursivePersistence:
    def test_records_nested_recursive_runs(self, store):
        from scripts.evolution.models import Critique, RefinementConfig, RefinementPart
        from scripts.evolution.refinement import RecursiveRefiner

        required = ("intro", "usage")

        def critic(c):
            have = sum(1 for kw in required if kw in c.lower())
            return Critique(have / len(required), "q")

        def gen(c, cr, i):
            for kw in required:
                if kw not in c.lower():
                    return c + "\n" + kw
            return c

        def decompose(c):
            import re
            parts = []
            for block in re.split(r"(?m)^(?=# )", c):
                block = block.strip("\n")
                if block:
                    parts.append(RefinementPart(value=block, key=block.splitlines()[0]))
            return parts

        def recompose(original, refined):
            return "\n\n".join(rp.node.final_candidate for rp in refined)

        refiner = RecursiveRefiner()
        result = refiner.refine_recursive(
            "# Intro\n\nTODO\n\n# Usage\n\nTODO",
            critic, gen, decompose, recompose,
            RefinementConfig(quality_threshold=1.0, max_iterations=5),
            max_depth=1,
        )
        store.record_recursive_refinement_run("rec-1", result, RefinementConfig())

        conn = store.connect()
        runs = conn.execute(
            "SELECT run_id, parent_run_id, node_path, depth, is_recursive_root "
            "FROM refinement_runs ORDER BY node_path"
        ).fetchall()
        run_ids = {r["run_id"] for r in runs}
        # root + 2 children persisted
        assert "rec-1" in run_ids
        roots = [r for r in runs if r["is_recursive_root"] == 1]
        assert len(roots) == 1
        assert roots[0]["run_id"] == "rec-1"
        assert roots[0]["parent_run_id"] is None
        assert roots[0]["node_path"] == ""
        # Tree children exclude the '#pre' phase rows (those record the
        # pre-decompose flat refinement, not a tree child).
        children = [
            r for r in runs
            if r["parent_run_id"] == "rec-1" and not r["run_id"].endswith("#pre")
        ]
        assert len(children) == 2
        # Persisted iteration rows must equal the result's total_iterations,
        # i.e. BOTH the pre-decompose and post-recompose phases of every
        # internal node are recorded (no lost refinement history).
        iters = conn.execute("SELECT count(*) FROM refinement_iterations").fetchone()[0]
        assert iters == result.total_iterations
        assert iters > 0

    def test_plain_record_refinement_run_still_works(self, store):
        from scripts.evolution.models import Critique, RefinementConfig
        from scripts.evolution.refinement import SelfRefinementLoop

        result = SelfRefinementLoop().refine(
            "ab", lambda c: Critique(min(1.0, len(c) / 6.0), "q"),
            lambda c, cr, i: c + "cd", RefinementConfig(quality_threshold=0.9, max_iterations=10),
        )
        store.record_refinement_run("plain-1", result, RefinementConfig())
        conn = store.connect()
        row = conn.execute(
            "SELECT node_path, depth, is_recursive_root FROM refinement_runs WHERE run_id='plain-1'"
        ).fetchone()
        assert row is not None
        assert row["node_path"] == ""
        assert row["depth"] == 0
        assert row["is_recursive_root"] == 0
