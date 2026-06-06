"""Tests for scripts/evolution/facade.py (EvolutionEngine) and cli.py."""

from __future__ import annotations

import json

import pytest

from scripts.evolution.facade import EvolutionEngine
from scripts.evolution.models import (
    Critique,
    PullRequestContext,
    RefinementConfig,
    ReviewFinding,
    Suggestion,
    SuggestionOutcome,
)
from scripts.evolution.storage import EvolutionStore


@pytest.fixture
def engine() -> EvolutionEngine:
    store = EvolutionStore(":memory:")
    store.initialize()
    return EvolutionEngine(store)


class TestEngineOrchestration:
    def test_process_then_regression(self, engine):
        ctx = PullRequestContext("repo", "pr/1", 1)
        f = ReviewFinding("bug", "high", "t", "leak", "a.py", 5, 9)
        m1 = engine.process_review_findings(ctx, [f])
        assert m1[0].is_regression is False
        engine.regression.mark_closed("repo", m1[0].fingerprint, reason="fixed")
        m2 = engine.process_review_findings(PullRequestContext("repo", "pr/2", 2), [f])
        assert m2[0].is_regression is True

    def test_adjust_and_record(self, engine):
        ctx = PullRequestContext("repo", "pr/1", 1)
        s = Suggestion("s1", "perf", "perf", "use set", 8.0, "a.py", 1, 2)
        engine.record_suggestion_outcomes(ctx, [(s, SuggestionOutcome.ACCEPTED)])
        out = engine.adjust_code_suggestions("repo", [Suggestion("s2", "perf", "perf", "use dict", 8.0, "a.py", 3, 4)])
        assert out[0].weight > 1.0

    def test_refine_output(self, engine):
        r = engine.refine_output(
            "ab",
            lambda c: Critique(min(1.0, len(c) / 6.0), "q"),
            lambda c, cr, i: c + "cd",
            RefinementConfig(quality_threshold=0.9, max_iterations=10),
        )
        assert r.final_quality >= 0.9

    def test_refine_output_persists_when_requested(self, engine):
        engine.refine_output(
            "ab",
            lambda c: Critique(min(1.0, len(c) / 6.0), "q"),
            lambda c, cr, i: c + "cd",
            RefinementConfig(quality_threshold=0.9, max_iterations=10),
            persist=True,
            repo="repo",
            pr_url="pr/1",
        )
        conn = engine.store.connect()
        runs = conn.execute("SELECT count(*) FROM refinement_runs").fetchone()[0]
        assert runs == 1


class TestCli:
    def test_init_db_and_ingest_and_adjust(self, tmp_path, capsys):
        from scripts.evolution import cli

        db = tmp_path / "ev.sqlite"

        rc = cli.main(["init-db", "--db", str(db)])
        assert rc == 0
        assert db.exists()
        capsys.readouterr()  # drain init-db output

        findings = tmp_path / "findings.json"
        findings.write_text(json.dumps([
            {"category": "security", "severity": "critical", "title": "t",
             "content": "vuln", "file_path": "a.py", "start_line": 1, "end_line": 2}
        ]))
        rc = cli.main([
            "ingest-findings", "--db", str(db), "--repo", "jclee941/x",
            "--pr-url", "pr/1", "--pr-number", "1", "--input", str(findings),
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["count"] == 1
        assert out["regressions"] == 0

        suggestions = tmp_path / "suggestions.json"
        suggestions.write_text(json.dumps([
            {"suggestion_id": "s1", "category": "perf", "label": "perf",
             "text": "use set", "score": 8.0, "file_path": "a.py", "start_line": 1, "end_line": 2}
        ]))
        out_file = tmp_path / "adjusted.json"
        rc = cli.main([
            "adjust-suggestions", "--db", str(db), "--repo", "jclee941/x",
            "--input", str(suggestions), "--output", str(out_file), "--threshold", "0.0",
        ])
        assert rc == 0
        adjusted = json.loads(out_file.read_text())
        assert adjusted[0]["adjusted_score"] == 8.0
        assert adjusted[0]["weight"] == 1.0

    def test_ingest_findings_accepts_upstream_file_key(self, tmp_path, capsys):
        # D2 at CLI boundary: upstream pr_reviewer findings carry "file", not
        # "file_path". The CLI must honor it so fingerprints match.
        import hashlib

        from scripts.evolution import cli

        db = tmp_path / "ev.sqlite"
        cli.main(["init-db", "--db", str(db)])
        capsys.readouterr()

        findings = tmp_path / "f.json"
        findings.write_text(json.dumps([
            {"category": "security", "severity": "critical", "title": "t",
             "content": "vuln X", "file": "src/db.py", "start_line": 10, "end_line": 15}
        ]))
        rc = cli.main([
            "ingest-findings", "--db", str(db), "--repo", "jclee941/x",
             "--pr-url", "pr/1", "--pr-number", "1", "--input", str(findings),
        ])
        assert rc == 0
        # Verify the stored fingerprint matches the upstream marker for file=src/db.py
        ch = hashlib.sha256(b"vuln X").hexdigest()[:8]
        marker = f"jclee941/x|src/db.py|10|15|security|{ch}"
        fp = hashlib.sha256(marker.encode()).hexdigest()[:16]
        from scripts.evolution.storage import EvolutionStore
        row = EvolutionStore(str(db)).get_finding_by_fingerprint("jclee941/x", fp)
        assert row is not None, "fingerprint did not match upstream marker (file key ignored)"
        assert row["file_path"] == "src/db.py"

    def test_ingest_review_uses_adapter(self, tmp_path, capsys):
        # D1: ingest raw pr_reviewer review_data via the adapter.
        from scripts.evolution import cli

        db = tmp_path / "ev.sqlite"
        cli.main(["init-db", "--db", str(db)])
        capsys.readouterr()

        review = tmp_path / "review.json"
        review.write_text(json.dumps({
            "review": {
                "security_concerns": "SQL injection in query builder",
                "key_issues_to_review": [
                    {"issue_header": "Crash", "issue_content": "crashes on empty input",
                     "relevant_file": "a.py", "start_line": 3, "end_line": 4}
                ],
            }
        }))
        rc = cli.main([
            "ingest-review", "--db", str(db), "--repo", "jclee941/x",
            "--pr-url", "pr/2", "--pr-number", "2", "--input", str(review),
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["count"] == 2  # one security_concerns + one bug
        assert out["regressions"] == 0

    def test_mark_closed_then_regression(self, tmp_path, capsys):
        # D3/D4: CLI can mark a finding closed, enabling regression detection.
        from scripts.evolution import cli

        db = tmp_path / "ev.sqlite"
        cli.main(["init-db", "--db", str(db)])
        capsys.readouterr()
        findings = tmp_path / "f.json"
        findings.write_text(json.dumps([
            {"category": "bug", "severity": "high", "title": "t", "content": "npe",
             "file": "x.py", "start_line": 1, "end_line": 2}
        ]))
        cli.main(["ingest-findings", "--db", str(db), "--repo", "r", "--pr-number", "1", "--input", str(findings)])
        out = json.loads(capsys.readouterr().out)
        # CLI surfaces the fingerprint so the user can close it
        fp = out["fingerprints"][0]

        rc = cli.main(["mark-closed", "--db", str(db), "--repo", "r", "--fingerprint", fp, "--reason", "fixed"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["closed"] is True

        cli.main(["ingest-findings", "--db", str(db), "--repo", "r", "--pr-number", "5", "--input", str(findings)])
        out = json.loads(capsys.readouterr().out)
        assert out["regressions"] == 1

    def test_record_outcome_evolves_weight(self, tmp_path, capsys):
        # D3: CLI can record accept/reject outcomes that evolve the weight.
        from scripts.evolution import cli

        db = tmp_path / "ev.sqlite"
        cli.main(["init-db", "--db", str(db)])
        capsys.readouterr()
        sugg = tmp_path / "s.json"
        sugg.write_text(json.dumps([
            {"suggestion_id": "s1", "category": "perf", "label": "perf",
             "text": "use set", "score": 8.0, "file_path": "a.py", "start_line": 1, "end_line": 2}
        ]))
        rc = cli.main([
            "record-outcome", "--db", str(db), "--repo", "r", "--pr-number", "1",
            "--outcome", "accepted", "--input", str(sugg),
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["results"][0]["new_weight"] > 1.0

    def test_refine_command_runs(self, tmp_path, capsys):
        # D4: CLI exposes the self-refinement loop with a built-in deterministic
        # section-coverage critic (no LLM needed).
        from scripts.evolution import cli

        db = tmp_path / "ev.sqlite"
        cli.main(["init-db", "--db", str(db)])
        capsys.readouterr()
        draft = tmp_path / "draft.txt"
        draft.write_text("## Summary\ninitial")
        rc = cli.main([
            "refine", "--db", str(db),
            "--input", str(draft),
            "--require-section", "## Summary",
            "--require-section", "## Changes",
            "--require-section", "## Testing",
            "--max-iterations", "6",
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["final_quality"] == 1.0
        assert "## Testing" in out["final_candidate"]

    def test_adjust_suggestions_accepts_raw_improve_output(self, tmp_path, capsys):
        # D1/D3: CLI can consume RAW pr_code_suggestions output via --raw, using
        # the adapter (no pre-transformation, no suggestion_id required).
        from scripts.evolution import cli

        db = tmp_path / "ev.sqlite"
        cli.main(["init-db", "--db", str(db)])
        capsys.readouterr()
        improve = tmp_path / "improve.json"
        improve.write_text(json.dumps({
            "code_suggestions": [
                {"relevant_file": "a.py", "label": "performance",
                 "one_sentence_summary": "use a set", "relevant_lines_start": 10,
                 "relevant_lines_end": 12, "score": 8}
            ]
        }))
        out_file = tmp_path / "adj.json"
        rc = cli.main([
            "adjust-suggestions", "--db", str(db), "--repo", "r",
            "--input", str(improve), "--raw", "--output", str(out_file), "--threshold", "0.0",
        ])
        assert rc == 0
        adjusted = json.loads(out_file.read_text())
        assert adjusted[0]["category"] == "performance"
        assert adjusted[0]["adjusted_score"] == 8.0

    def test_record_outcome_accepts_raw_improve_output(self, tmp_path, capsys):
        # D1/D3: record-outcome can consume raw pr_code_suggestions via --raw.
        from scripts.evolution import cli

        db = tmp_path / "ev.sqlite"
        cli.main(["init-db", "--db", str(db)])
        capsys.readouterr()
        improve = tmp_path / "improve.json"
        improve.write_text(json.dumps({
            "code_suggestions": [
                {"relevant_file": "a.py", "label": "performance",
                 "one_sentence_summary": "use a set", "relevant_lines_start": 1,
                 "relevant_lines_end": 2, "score": 7}
            ]
        }))
        rc = cli.main([
            "record-outcome", "--db", str(db), "--repo", "r", "--pr-number", "1",
            "--outcome", "accepted", "--input", str(improve), "--raw",
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["results"][0]["new_weight"] > 1.0

    def test_suggestion_from_dict_accepts_upstream_keys(self):
        # D2 for suggestions: cli._suggestion_from_dict must read relevant_file /
        # relevant_lines_start/end (upstream) as well as file_path/start_line/end_line.
        from scripts.evolution import cli

        s = cli._suggestion_from_dict({
            "suggestion_id": "s1", "category": "perf", "label": "perf",
            "text": "t", "score": 5.0,
            "relevant_file": "core/x.py", "relevant_lines_start": 3, "relevant_lines_end": 7,
        })
        assert s.file_path == "core/x.py"
        assert s.start_line == 3
        assert s.end_line == 7

    def test_cli_unknown_command_returns_nonzero(self):
        from scripts.evolution import cli
        with pytest.raises(SystemExit):
            cli.main(["bogus-command"])

    def test_refine_recursive_command_runs_and_persists(self, tmp_path, capsys):
        # Recursive refinement CLI: decompose a markdown doc into sections,
        # refine each (deterministic section-coverage critic), recompose, persist
        # the nested run tree. No LLM.
        from scripts.evolution import cli

        db = tmp_path / "ev.sqlite"
        cli.main(["init-db", "--db", str(db)])
        capsys.readouterr()
        draft = tmp_path / "draft.md"
        draft.write_text("# Intro\n\nplaceholder\n\n# Usage\n\nplaceholder")
        out_file = tmp_path / "rec.json"
        rc = cli.main([
            "refine-recursive", "--db", str(db),
            "--input", str(draft), "--output", str(out_file),
            "--run-id", "qa-rec-1",
            "--require-section", "## Summary",
            "--require-section", "## Details",
            "--max-depth", "1", "--max-iterations", "5",
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert "final_candidate" in out
        assert "tree" in out
        assert "total_iterations" in out
        assert out["max_observed_depth"] <= 1
        assert len(out["tree"]["children"]) == 2
        # persisted: root + children rows present
        from scripts.evolution.storage import EvolutionStore
        conn = EvolutionStore(str(db)).connect()
        rows = conn.execute(
            "SELECT run_id, parent_run_id, is_recursive_root FROM refinement_runs"
        ).fetchall()
        run_ids = {r["run_id"] for r in rows}
        assert "qa-rec-1" in run_ids
        assert any(r["parent_run_id"] == "qa-rec-1" for r in rows)
        assert any(r["is_recursive_root"] == 1 for r in rows)
