"""SQLite persistence layer for the evolution package.

Design notes:
- For an in-memory database (``:memory:``) a single shared connection is kept,
  because each new connection to ``:memory:`` would be a *separate* database.
- For a file database a fresh connection is opened per operation, with WAL +
  ``BEGIN IMMEDIATE`` write transactions and a busy timeout so concurrent
  writers serialize instead of losing read-modify-write updates.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from scripts.evolution.models import (
    CandidateSerializer,
    FindingEventType,
    PullRequestContext,
    RecursiveRefinementNode,
    RecursiveRefinementResult,
    RefinementConfig,
    RefinementResult,
    ReviewFinding,
    Suggestion,
    SuggestionOutcome,
    WeightUpdateResult,
)

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    fingerprint_full TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    normalized_content TEXT NOT NULL,
    file_path TEXT NOT NULL DEFAULT '',
    start_line INTEGER NOT NULL DEFAULT 0,
    end_line INTEGER NOT NULL DEFAULT 0,
    first_pr_url TEXT,
    first_pr_number INTEGER,
    first_commit_sha TEXT,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_pr_url TEXT,
    last_pr_number INTEGER,
    last_commit_sha TEXT,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'open',
    closed_at TEXT,
    close_reason TEXT,
    occurrences INTEGER NOT NULL DEFAULT 1,
    CHECK (length(repo) > 0),
    CHECK (length(fingerprint) = 16),
    CHECK (length(fingerprint_full) = 64),
    CHECK (start_line >= 0),
    CHECK (end_line >= 0),
    CHECK (end_line >= start_line OR end_line = 0),
    CHECK (status IN ('open', 'closed', 'ignored'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_findings_repo_fingerprint ON findings (repo, fingerprint);
CREATE INDEX IF NOT EXISTS ix_findings_repo_status ON findings (repo, status);
CREATE INDEX IF NOT EXISTS ix_findings_repo_location ON findings (repo, file_path, start_line, end_line);
CREATE INDEX IF NOT EXISTS ix_findings_full_fingerprint ON findings (repo, fingerprint_full);

CREATE TABLE IF NOT EXISTS finding_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL,
    repo TEXT NOT NULL,
    pr_url TEXT,
    pr_number INTEGER,
    commit_sha TEXT,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE CASCADE,
    CHECK (event_type IN ('seen', 'closed', 'reopened', 'regressed', 'ignored'))
);
CREATE INDEX IF NOT EXISTS ix_finding_events_finding ON finding_events (finding_id, event_at);
CREATE INDEX IF NOT EXISTS ix_finding_events_repo_pr ON finding_events (repo, pr_number);

CREATE TABLE IF NOT EXISTS suggestion_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    suggestion_id TEXT NOT NULL,
    suggestion_fingerprint TEXT NOT NULL,
    pr_url TEXT,
    pr_number INTEGER,
    commit_sha TEXT,
    category TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    original_score REAL NOT NULL,
    adjusted_score REAL NOT NULL,
    outcome TEXT NOT NULL,
    outcome_source TEXT NOT NULL DEFAULT 'unknown',
    outcome_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    suggestion_text TEXT NOT NULL DEFAULT '',
    normalized_suggestion_text TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK (length(repo) > 0),
    CHECK (length(category) > 0),
    CHECK (original_score >= 0 AND original_score <= 10),
    CHECK (adjusted_score >= 0 AND adjusted_score <= 10),
    CHECK (outcome IN ('accepted', 'rejected', 'unknown')),
    CHECK (outcome_source IN ('author', 'reviewer', 'heuristic', 'unknown'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_suggestion_outcomes_repo_suggestion ON suggestion_outcomes (repo, suggestion_id);
CREATE INDEX IF NOT EXISTS ix_suggestion_outcomes_repo_category ON suggestion_outcomes (repo, category, outcome_at);
CREATE INDEX IF NOT EXISTS ix_suggestion_outcomes_fingerprint ON suggestion_outcomes (repo, suggestion_fingerprint);

CREATE TABLE IF NOT EXISTS evolution_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    category TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    weight REAL NOT NULL DEFAULT 1.0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    unknown_count INTEGER NOT NULL DEFAULT 0,
    total_updates INTEGER NOT NULL DEFAULT 0,
    last_outcome TEXT,
    last_updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    explanation TEXT NOT NULL DEFAULT 'initial weight',
    CHECK (length(repo) > 0),
    CHECK (length(category) > 0),
    CHECK (weight >= 0.5 AND weight <= 1.5),
    CHECK (accepted_count >= 0),
    CHECK (rejected_count >= 0),
    CHECK (unknown_count >= 0),
    CHECK (total_updates >= 0),
    CHECK (last_outcome IS NULL OR last_outcome IN ('accepted', 'rejected', 'unknown'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_evolution_weights_scope ON evolution_weights (repo, category, label);

CREATE TABLE IF NOT EXISTS refinement_runs (
id INTEGER PRIMARY KEY AUTOINCREMENT,
run_id TEXT NOT NULL UNIQUE,
repo TEXT,
pr_url TEXT,
started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
finished_at TEXT,
initial_quality REAL,
final_quality REAL,
stop_reason TEXT,
max_iterations INTEGER NOT NULL,
threshold REAL NOT NULL,
    min_delta REAL NOT NULL,
    parent_run_id TEXT,
    node_path TEXT NOT NULL DEFAULT '',
    depth INTEGER NOT NULL DEFAULT 0,
    aggregate_quality REAL,
    total_iterations INTEGER,
    max_observed_depth INTEGER,
    is_recursive_root INTEGER NOT NULL DEFAULT 0,
CHECK (max_iterations >= 1),
CHECK (threshold >= 0 AND threshold <= 1),
    CHECK (min_delta >= 0),
    CHECK (depth >= 0),
    CHECK (is_recursive_root IN (0, 1))
);
CREATE INDEX IF NOT EXISTS ix_refinement_runs_parent ON refinement_runs (parent_run_id);

CREATE TABLE IF NOT EXISTS refinement_iterations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    candidate_hash TEXT NOT NULL,
    candidate_text TEXT NOT NULL,
    quality REAL NOT NULL,
    critique_text TEXT NOT NULL DEFAULT '',
    accepted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES refinement_runs(run_id) ON DELETE CASCADE,
    UNIQUE (run_id, iteration),
    CHECK (iteration >= 0),
    CHECK (quality >= 0 AND quality <= 1),
    CHECK (accepted IN (0, 1))
);
CREATE INDEX IF NOT EXISTS ix_refinement_iterations_run ON refinement_iterations (run_id, iteration);
"""


class EvolutionStore:
    def __init__(self, db_path: str | Path, *, timeout_seconds: float = 5.0) -> None:
        self.db_path = str(db_path)
        self.timeout_seconds = timeout_seconds
        self._is_memory = self.db_path == ":memory:" or self.db_path.startswith("file::memory:")
        self._shared: sqlite3.Connection | None = None

    # -- connection management ------------------------------------------------
    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.timeout_seconds, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = %d" % int(self.timeout_seconds * 1000))
        if not self._is_memory:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def connect(self) -> sqlite3.Connection:
        """Return a usable connection.

        For ``:memory:`` a single shared connection is reused for the lifetime
        of the store; for file DBs a fresh connection is returned each call.
        """
        if self._is_memory:
            if self._shared is None:
                self._shared = self._new_connection()
            return self._shared
        return self._new_connection()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection inside a ``BEGIN IMMEDIATE`` write transaction."""
        conn = self.connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            if not self._is_memory:
                conn.close()

    _V2_REFINEMENT_RUN_COLUMNS = (
        ("parent_run_id", "TEXT"),
        ("node_path", "TEXT NOT NULL DEFAULT ''"),
        ("depth", "INTEGER NOT NULL DEFAULT 0"),
        ("aggregate_quality", "REAL"),
        ("total_iterations", "INTEGER"),
        ("max_observed_depth", "INTEGER"),
        ("is_recursive_root", "INTEGER NOT NULL DEFAULT 0"),
    )

    def initialize(self) -> None:
        conn = self.connect()
        # Migrate legacy tables FIRST so v2 DDL (e.g. the parent_run_id index in
        # _SCHEMA) can reference columns added by ALTER on a pre-v2 database.
        self._migrate(conn)
        conn.executescript(_SCHEMA)
        row = conn.execute("SELECT 1 FROM schema_version WHERE version = ?", (SCHEMA_VERSION,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        if not self._is_memory:
            conn.commit()
            conn.close()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Idempotently bring a pre-v2 database up to the current schema.

        Pre-v2 ``refinement_runs`` tables predate the recursive-tree columns;
        ``CREATE TABLE IF NOT EXISTS`` will not add them, so we ALTER them in.
        Guarded by ``PRAGMA table_info`` so re-running is a no-op.
        """
        existing = {
            r["name"] for r in conn.execute("PRAGMA table_info(refinement_runs)").fetchall()
        }
        if not existing:
            return  # table not present yet (executescript creates it fresh)
        for name, definition in self._V2_REFINEMENT_RUN_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE refinement_runs ADD COLUMN {name} {definition}")

    # -- findings -------------------------------------------------------------
    def upsert_finding_seen(self, ctx: PullRequestContext, finding: ReviewFinding, identity) -> int:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id, occurrences FROM findings WHERE repo = ? AND fingerprint = ?",
                (ctx.repo, identity.fingerprint),
            ).fetchone()
            if row is None:
                cur = conn.execute(
                    """
                    INSERT INTO findings (
                        repo, fingerprint, fingerprint_full, category, severity, title,
                        content, normalized_content, file_path, start_line, end_line,
                        first_pr_url, first_pr_number, first_commit_sha,
                        last_pr_url, last_pr_number, last_commit_sha, status, occurrences
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 1)
                    """,
                    (
                        ctx.repo, identity.fingerprint, identity.fingerprint_full,
                        finding.category, finding.severity, finding.title,
                        str(finding.content), identity.normalized_content,
                        finding.file_path or "", finding.start_line or 0, finding.end_line or 0,
                        ctx.pr_url, ctx.pr_number, ctx.commit_sha,
                        ctx.pr_url, ctx.pr_number, ctx.commit_sha,
                    ),
                )
                return int(cur.lastrowid or 0)
            conn.execute(
                """
                UPDATE findings
                SET occurrences = occurrences + 1,
                    last_pr_url = ?, last_pr_number = ?, last_commit_sha = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (ctx.pr_url, ctx.pr_number, ctx.commit_sha, row["id"]),
            )
            return int(row["id"])

    def get_finding_by_fingerprint(self, repo: str, fingerprint: str) -> Mapping[str, object] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM findings WHERE repo = ? AND fingerprint = ?",
                (repo, fingerprint),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            if not self._is_memory:
                conn.close()

    def close_finding(
        self, repo: str, fingerprint: str, *, reason: str, ctx: PullRequestContext | None = None
    ) -> bool:
        with self.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE findings
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP, close_reason = ?
                WHERE repo = ? AND fingerprint = ? AND status != 'closed'
                """,
                (reason, repo, fingerprint),
            )
            if cur.rowcount == 0:
                return False
            row = conn.execute(
                "SELECT id FROM findings WHERE repo = ? AND fingerprint = ?", (repo, fingerprint)
            ).fetchone()
            if row is not None:
                self._insert_event(conn, int(row["id"]), ctx or PullRequestContext(repo),
                                    FindingEventType.CLOSED, {"reason": reason})
            return True

    def reopen_finding(self, finding_id: int, ctx: PullRequestContext, finding: ReviewFinding) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE findings
                SET status = 'open', closed_at = NULL, close_reason = NULL,
                    occurrences = occurrences + 1,
                    last_pr_url = ?, last_pr_number = ?, last_commit_sha = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (ctx.pr_url, ctx.pr_number, ctx.commit_sha, finding_id),
            )

    def reopen_finding_with_event(
        self,
        finding_id: int,
        ctx: PullRequestContext,
        finding: ReviewFinding,
        event_type: FindingEventType,
        details: Mapping[str, object] | None = None,
    ) -> None:
        """Atomically reopen a closed finding AND record its event (D7)."""
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE findings
                SET status = 'open', closed_at = NULL, close_reason = NULL,
                    occurrences = occurrences + 1,
                    last_pr_url = ?, last_pr_number = ?, last_commit_sha = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (ctx.pr_url, ctx.pr_number, ctx.commit_sha, finding_id),
            )
            self._insert_event(conn, finding_id, ctx, event_type, details)

    def record_finding_event(
        self,
        finding_id: int,
        ctx: PullRequestContext,
        event_type: FindingEventType,
        details: Mapping[str, object] | None = None,
    ) -> None:
        with self.transaction() as conn:
            self._insert_event(conn, finding_id, ctx, event_type, details)

    @staticmethod
    def _insert_event(
        conn: sqlite3.Connection,
        finding_id: int,
        ctx: PullRequestContext,
        event_type: FindingEventType,
        details: Mapping[str, object] | None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO finding_events (finding_id, repo, pr_url, pr_number, commit_sha, event_type, details_json)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                finding_id, ctx.repo, ctx.pr_url, ctx.pr_number, ctx.commit_sha,
                str(event_type), json.dumps(dict(details or {}), sort_keys=True),
            ),
        )

    # -- suggestion outcomes --------------------------------------------------
    def record_suggestion_outcome(
        self,
        ctx: PullRequestContext,
        suggestion: Suggestion,
        adjusted_score: float,
        outcome: SuggestionOutcome,
        *,
        suggestion_fingerprint: str = "",
        normalized_text: str = "",
        outcome_source: str = "unknown",
    ) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO suggestion_outcomes (
                    repo, suggestion_id, suggestion_fingerprint, pr_url, pr_number, commit_sha,
                    category, label, original_score, adjusted_score, outcome, outcome_source,
                    suggestion_text, normalized_suggestion_text, metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(repo, suggestion_id) DO UPDATE SET
                    adjusted_score = excluded.adjusted_score,
                    outcome = excluded.outcome,
                    outcome_source = excluded.outcome_source,
                    outcome_at = CURRENT_TIMESTAMP
                """,
                (
                    ctx.repo, suggestion.suggestion_id, suggestion_fingerprint,
                    ctx.pr_url, ctx.pr_number, ctx.commit_sha,
                    suggestion.category, suggestion.label, float(suggestion.score), float(adjusted_score),
                    str(outcome), outcome_source,
                    suggestion.text, normalized_text, json.dumps(dict(suggestion.metadata), sort_keys=True),
                ),
            )
            if cur.lastrowid:
                return int(cur.lastrowid or 0)
            row = conn.execute(
                "SELECT id FROM suggestion_outcomes WHERE repo = ? AND suggestion_id = ?",
                (ctx.repo, suggestion.suggestion_id),
            ).fetchone()
            return int(row["id"])

    def get_suggestion_outcome(self, repo: str, suggestion_id: str) -> Mapping[str, object] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM suggestion_outcomes WHERE repo = ? AND suggestion_id = ?",
                (repo, suggestion_id),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            if not self._is_memory:
                conn.close()

    # -- weights --------------------------------------------------------------
    def get_weight(self, repo: str, category: str, label: str = "") -> Mapping[str, object] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM evolution_weights WHERE repo = ? AND category = ? AND label = ?",
                (repo, category, label),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            if not self._is_memory:
                conn.close()

    def upsert_weight(self, result: WeightUpdateResult, outcome: SuggestionOutcome) -> None:
        acc = 1 if outcome == SuggestionOutcome.ACCEPTED else 0
        rej = 1 if outcome == SuggestionOutcome.REJECTED else 0
        unk = 1 if outcome == SuggestionOutcome.UNKNOWN else 0
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO evolution_weights (
                    repo, category, label, weight, accepted_count, rejected_count,
                    unknown_count, total_updates, last_outcome, last_updated_at, explanation
                ) VALUES (?,?,?,?,?,?,?,1,?,CURRENT_TIMESTAMP,?)
                ON CONFLICT(repo, category, label) DO UPDATE SET
                    weight = excluded.weight,
                    accepted_count = evolution_weights.accepted_count + ?,
                    rejected_count = evolution_weights.rejected_count + ?,
                    unknown_count = evolution_weights.unknown_count + ?,
                    total_updates = evolution_weights.total_updates + 1,
                    last_outcome = excluded.last_outcome,
                    last_updated_at = CURRENT_TIMESTAMP,
                    explanation = excluded.explanation
                """,
                (
                    result.repo, result.category, result.label, result.new_weight,
                    acc, rej, unk, str(outcome), result.explanation,
                    acc, rej, unk,
                ),
            )

    def apply_outcome(
        self,
        ctx: PullRequestContext,
        suggestion: Suggestion,
        adjusted_score: float,
        outcome: SuggestionOutcome,
        category: str,
        label: str,
        next_weight_fn,
        *,
        suggestion_fingerprint: str = "",
        normalized_text: str = "",
        outcome_source: str = "unknown",
        default_weight: float = 1.0,
    ) -> dict[str, object]:
        """Atomically record a suggestion outcome AND evolve its bucket weight (D7).

        The ENTIRE read-modify-write (existing-outcome check, current-weight read,
        next-weight computation, outcome insert, weight upsert) happens inside a
        single ``BEGIN IMMEDIATE`` transaction, so concurrent writers serialize and
        cannot double-count or compute from a stale weight.

        ``next_weight_fn(old_weight, outcome) -> (new_weight, explanation)`` is the
        caller's pure weight rule, invoked while holding the write lock.

        Returns a dict: {status, old_weight, new_weight, accepted_count,
        rejected_count, unknown_count, explanation, conflict_existing}.
        ``status`` is one of 'applied', 'idempotent', 'conflict'.
        """
        acc = 1 if outcome == SuggestionOutcome.ACCEPTED else 0
        rej = 1 if outcome == SuggestionOutcome.REJECTED else 0
        unk = 1 if outcome == SuggestionOutcome.UNKNOWN else 0
        with self.transaction() as conn:
            # 1) Existing-outcome check INSIDE the lock (idempotency + conflict).
            existing = conn.execute(
                "SELECT outcome FROM suggestion_outcomes WHERE repo = ? AND suggestion_id = ?",
                (ctx.repo, suggestion.suggestion_id),
            ).fetchone()
            weight_row = conn.execute(
                "SELECT weight, accepted_count, rejected_count, unknown_count "
                "FROM evolution_weights WHERE repo = ? AND category = ? AND label = ?",
                (ctx.repo, category, label),
            ).fetchone()
            cur_weight = float(weight_row["weight"]) if weight_row is not None else default_weight
            cur_acc = int(weight_row["accepted_count"]) if weight_row is not None else 0
            cur_rej = int(weight_row["rejected_count"]) if weight_row is not None else 0
            cur_unk = int(weight_row["unknown_count"]) if weight_row is not None else 0

            if existing is not None:
                if existing["outcome"] != str(outcome):
                    return {
                        "status": "conflict",
                        "conflict_existing": existing["outcome"],
                        "old_weight": cur_weight,
                        "new_weight": cur_weight,
                        "accepted_count": cur_acc,
                        "rejected_count": cur_rej,
                        "unknown_count": cur_unk,
                        "explanation": "conflicting outcome",
                    }
                # idempotent replay: no write, no count/weight change.
                return {
                    "status": "idempotent",
                    "conflict_existing": None,
                    "old_weight": cur_weight,
                    "new_weight": cur_weight,
                    "accepted_count": cur_acc,
                    "rejected_count": cur_rej,
                    "unknown_count": cur_unk,
                    "explanation": "idempotent replay: no change",
                }

            # 2) Compute next weight from the LOCKED current state.
            new_weight, explanation = next_weight_fn(cur_weight, outcome)

            # 3) Insert the outcome (no conflict possible: we hold the lock and
            # confirmed no existing row).
            conn.execute(
                """
                INSERT INTO suggestion_outcomes (
                    repo, suggestion_id, suggestion_fingerprint, pr_url, pr_number, commit_sha,
                    category, label, original_score, adjusted_score, outcome, outcome_source,
                    suggestion_text, normalized_suggestion_text, metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ctx.repo, suggestion.suggestion_id, suggestion_fingerprint,
                    ctx.pr_url, ctx.pr_number, ctx.commit_sha,
                    suggestion.category, suggestion.label, float(suggestion.score), float(adjusted_score),
                    str(outcome), outcome_source,
                    suggestion.text, normalized_text, json.dumps(dict(suggestion.metadata), sort_keys=True),
                ),
            )
            # 4) Upsert the weight from the locked current state.
            conn.execute(
                """
                INSERT INTO evolution_weights (
                    repo, category, label, weight, accepted_count, rejected_count,
                    unknown_count, total_updates, last_outcome, last_updated_at, explanation
                ) VALUES (?,?,?,?,?,?,?,1,?,CURRENT_TIMESTAMP,?)
                ON CONFLICT(repo, category, label) DO UPDATE SET
                    weight = excluded.weight,
                    accepted_count = evolution_weights.accepted_count + ?,
                    rejected_count = evolution_weights.rejected_count + ?,
                    unknown_count = evolution_weights.unknown_count + ?,
                    total_updates = evolution_weights.total_updates + 1,
                    last_outcome = excluded.last_outcome,
                    last_updated_at = CURRENT_TIMESTAMP,
                    explanation = excluded.explanation
                """,
                (
                    ctx.repo, category, label, new_weight,
                    acc, rej, unk, str(outcome), explanation,
                    acc, rej, unk,
                ),
            )
            return {
                "status": "applied",
                "conflict_existing": None,
                "old_weight": cur_weight,
                "new_weight": new_weight,
                "accepted_count": cur_acc + acc,
                "rejected_count": cur_rej + rej,
                "unknown_count": cur_unk + unk,
                "explanation": explanation,
            }

    # -- refinement -----------------------------------------------------------
    def record_refinement_run(
        self,
        run_id: str,
        result: RefinementResult,
        config: RefinementConfig,
        *,
        repo: str | None = None,
        pr_url: str | None = None,
        parent_run_id: str | None = None,
        node_path: str = "",
        depth: int = 0,
        is_recursive_root: bool = False,
        aggregate_quality: float | None = None,
        total_iterations: int | None = None,
        max_observed_depth: int | None = None,
        candidate_serializer: CandidateSerializer | None = None,
    ) -> None:
        with self.transaction() as conn:
            self._insert_refinement_run(
                conn, run_id, result, config,
                repo=repo, pr_url=pr_url, parent_run_id=parent_run_id,
                node_path=node_path, depth=depth, is_recursive_root=is_recursive_root,
                aggregate_quality=aggregate_quality, total_iterations=total_iterations,
                max_observed_depth=max_observed_depth, candidate_serializer=candidate_serializer,
            )

    def record_recursive_refinement_run(
        self,
        run_id: str,
        result: "RecursiveRefinementResult",
        config: RefinementConfig,
        *,
        repo: str | None = None,
        pr_url: str | None = None,
        candidate_serializer: CandidateSerializer | None = None,
    ) -> None:
        """Persist a recursive refinement tree as nested ``refinement_runs`` rows.

        The root node uses ``run_id``; each descendant uses a deterministic
        ``{run_id}:{dotted-path}`` id (e.g. ``run:0``, ``run:1.0``). Aggregate
        tree metrics are stored on the root row.
        """
        with self.transaction() as conn:
            self._insert_node(
                conn, run_id, result.tree, config,
                repo=repo, pr_url=pr_url, parent_run_id=None,
                is_root=True, candidate_serializer=candidate_serializer,
                root_run_id=run_id,
                aggregate_quality=result.tree.aggregate_quality,
                total_iterations=result.total_iterations,
                max_observed_depth=result.max_observed_depth,
            )

    def _insert_node(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        node: "RecursiveRefinementNode",
        config: RefinementConfig,
        *,
        repo: str | None,
        pr_url: str | None,
        parent_run_id: str | None,
        is_root: bool,
        candidate_serializer: CandidateSerializer | None,
        root_run_id: str,
        aggregate_quality: float | None = None,
        total_iterations: int | None = None,
        max_observed_depth: int | None = None,
    ) -> None:
        node_path = ".".join(str(i) for i in node.path)
        self._insert_refinement_run(
            conn, run_id, node.refinement, config,
            repo=repo, pr_url=pr_url, parent_run_id=parent_run_id,
            node_path=node_path, depth=node.depth, is_recursive_root=is_root,
            aggregate_quality=aggregate_quality if is_root else node.aggregate_quality,
            total_iterations=total_iterations,
            max_observed_depth=max_observed_depth,
            candidate_serializer=candidate_serializer,
        )
        # Persist the internal node's pre-decompose flat refinement as a separate
        # phase row so the recorded iteration history is complete (matches
        # RecursiveRefinementResult.total_iterations).
        if node.pre_refinement is not None:
            self._insert_refinement_run(
                conn, f"{run_id}#pre", node.pre_refinement, config,
                repo=repo, pr_url=pr_url, parent_run_id=run_id,
                node_path=f"{node_path}#pre", depth=node.depth, is_recursive_root=False,
                aggregate_quality=node.pre_refinement.final_quality,
                total_iterations=None, max_observed_depth=None,
                candidate_serializer=candidate_serializer,
            )
        for child in node.children:
            child_path = ".".join(str(i) for i in child.path)
            child_run_id = f"{root_run_id}:{child_path}"
            self._insert_node(
                conn, child_run_id, child, config,
                repo=repo, pr_url=pr_url, parent_run_id=run_id,
                is_root=False, candidate_serializer=candidate_serializer,
                root_run_id=root_run_id,
            )

    @staticmethod
    def _insert_refinement_run(
        conn: sqlite3.Connection,
        run_id: str,
        result: RefinementResult,
        config: RefinementConfig,
        *,
        repo: str | None,
        pr_url: str | None,
        parent_run_id: str | None,
        node_path: str,
        depth: int,
        is_recursive_root: bool,
        aggregate_quality: float | None,
        total_iterations: int | None,
        max_observed_depth: int | None,
        candidate_serializer: CandidateSerializer | None,
    ) -> None:
        serialize = candidate_serializer or (lambda c: c if isinstance(c, str) else str(c))
        initial_quality = result.iterations[0].critique.quality if result.iterations else None
        conn.execute(
            """
            INSERT INTO refinement_runs (
                run_id, repo, pr_url, finished_at, initial_quality, final_quality,
                stop_reason, max_iterations, threshold, min_delta,
                parent_run_id, node_path, depth, aggregate_quality,
                total_iterations, max_observed_depth, is_recursive_root
            ) VALUES (?,?,?,CURRENT_TIMESTAMP,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id, repo, pr_url, initial_quality, result.final_quality,
                str(result.stop_reason), config.max_iterations,
                config.quality_threshold, config.min_delta,
                parent_run_id, node_path, depth, aggregate_quality,
                total_iterations, max_observed_depth, 1 if is_recursive_root else 0,
            ),
        )
        for it in result.iterations:
            conn.execute(
                """
                INSERT INTO refinement_iterations (
                    run_id, iteration, candidate_hash, candidate_text, quality, critique_text, accepted
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    run_id, it.iteration, it.candidate_hash, serialize(it.candidate),
                    it.critique.quality, it.critique.message, 1 if it.accepted else 0,
                ),
            )

    @staticmethod
    def new_run_id() -> str:
        return uuid.uuid4().hex
