"""Command-line interface for the evolution package.

File-based JSON in/out so it stays testable without GitHub or LLM access:

    python -m scripts.evolution.cli init-db --db .cache/evolution.sqlite
    python -m scripts.evolution.cli ingest-findings --db ... --repo R --input findings.json
    python -m scripts.evolution.cli adjust-suggestions --db ... --repo R --input s.json --output out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence, SupportsFloat, SupportsInt, cast

from scripts.evolution.adapters import (
    findings_from_review_data,
    suggestions_from_improve_data,
)
from scripts.evolution.facade import EvolutionEngine
from scripts.evolution.models import (
    PullRequestContext,
    ReviewFinding,
    Suggestion,
    SuggestionOutcome,
)
from scripts.evolution.storage import EvolutionStore


def _load_json(path: str) -> list[dict[str, object]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON array in {path}, got {type(data).__name__}")
    return data


def _load_suggestions(repo: str, path: str, raw: bool):
    """Load suggestions from JSON.

    raw=True  -> raw pr_code_suggestions output ({"code_suggestions": [...]} or a
                 plain list of upstream suggestion dicts) via the adapter (D1/D3).
    raw=False -> pre-transformed suggestion dicts (suggestion_id/category/score).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw:
        return suggestions_from_improve_data(repo, data)
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON array in {path}, got {type(data).__name__}")
    return [_suggestion_from_dict(d) for d in data]


def _as_str(value: object, default: str = "") -> str:
    return default if value is None else str(value)


def _as_int(value: object, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(cast("SupportsInt | str", value))


def _as_float(value: object) -> float:
    return float(cast("SupportsFloat | str", value))


def _required(d: dict[str, object], field: str) -> object:
    """Return d[field], raising a friendly ValueError when it is missing.

    The CLI ingests externally supplied JSON, so a missing required field must
    surface as a meaningful error rather than a bare KeyError traceback.
    """
    if field not in d:
        raise ValueError(f"missing required field: {field}")
    return d[field]


def _finding_from_dict(d: dict[str, object]) -> ReviewFinding:
    return ReviewFinding(
        category=_as_str(_required(d, "category")),
        severity=_as_str(d.get("severity"), "unknown"),
        title=_as_str(d.get("title")),
        content=_as_str(d.get("content")),
        file_path=_as_str(d.get("file", d.get("file_path"))),
        start_line=_as_int(d.get("start_line")),
        end_line=_as_int(d.get("end_line")),
    )


def _suggestion_from_dict(d: dict[str, object]) -> Suggestion:
    metadata = d.get("metadata") or {}
    return Suggestion(
        suggestion_id=_as_str(_required(d, "suggestion_id")),
        category=_as_str(_required(d, "category")),
        label=_as_str(d.get("label")),
        text=_as_str(d.get("text")),
        score=_as_float(_required(d, "score")),
        file_path=_as_str(d.get("relevant_file", d.get("file", d.get("file_path")))),
        start_line=_as_int(d.get("relevant_lines_start", d.get("start_line"))),
        end_line=_as_int(d.get("relevant_lines_end", d.get("end_line"))),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _cmd_init_db(args: argparse.Namespace) -> int:
    store = EvolutionStore(args.db)
    store.initialize()
    print(json.dumps({"status": "ok", "db": args.db}))
    return 0


def _cmd_ingest_findings(args: argparse.Namespace) -> int:
    store = EvolutionStore(args.db)
    store.initialize()
    engine = EvolutionEngine(store)
    raw = _load_json(args.input)
    findings = [_finding_from_dict(d) for d in raw]
    ctx = PullRequestContext(args.repo, args.pr_url, args.pr_number, args.commit_sha)
    matches = engine.process_review_findings(ctx, findings)
    regressions = [
        {"fingerprint": m.fingerprint, "reason": m.reason, "first_pr_number": m.first_pr_number}
        for m in matches
        if m.is_regression
    ]
    print(json.dumps({
        "count": len(matches),
        "regressions": len(regressions),
        "details": regressions,
        "fingerprints": [m.fingerprint for m in matches],
    }))
    return 0


def _cmd_adjust_suggestions(args: argparse.Namespace) -> int:
    store = EvolutionStore(args.db)
    store.initialize()
    engine = EvolutionEngine(store)
    suggestions = _load_suggestions(args.repo, args.input, args.raw)
    adjusted = engine.adjust_code_suggestions(args.repo, suggestions, filter_threshold=args.threshold)
    payload = [
        {
            "suggestion_id": a.suggestion.suggestion_id,
            "category": a.suggestion.category,
            "label": a.suggestion.label,
            "original_score": a.suggestion.score,
            "weight": a.weight,
            "adjusted_score": a.adjusted_score,
            "filtered": a.filtered,
            "explanation": a.explanation,
        }
        for a in adjusted
    ]
    text = json.dumps(payload, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(json.dumps({"status": "ok", "written": args.output, "count": len(payload)}))
    else:
        print(text)
    return 0

def _cmd_ingest_review(args: argparse.Namespace) -> int:
    store = EvolutionStore(args.db)
    store.initialize()
    engine = EvolutionEngine(store)
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    findings = findings_from_review_data(raw)
    ctx = PullRequestContext(args.repo, args.pr_url, args.pr_number, args.commit_sha)
    matches = engine.process_review_findings(ctx, findings)
    regressions = [
        {"fingerprint": m.fingerprint, "reason": m.reason, "first_pr_number": m.first_pr_number}
        for m in matches
        if m.is_regression
    ]
    print(json.dumps({
        "count": len(matches),
        "regressions": len(regressions),
        "details": regressions,
        "fingerprints": [m.fingerprint for m in matches],
    }))
    return 0


def _cmd_mark_closed(args: argparse.Namespace) -> int:
    store = EvolutionStore(args.db)
    store.initialize()
    engine = EvolutionEngine(store)
    closed = engine.regression.mark_closed(args.repo, args.fingerprint, reason=args.reason)
    print(json.dumps({"closed": closed, "fingerprint": args.fingerprint}))
    return 0


def _cmd_record_outcome(args: argparse.Namespace) -> int:
    store = EvolutionStore(args.db)
    store.initialize()
    engine = EvolutionEngine(store)
    outcome = SuggestionOutcome(args.outcome)
    ctx = PullRequestContext(args.repo, args.pr_url, args.pr_number, args.commit_sha)
    suggestions = _load_suggestions(args.repo, args.input, args.raw)
    pairs = [(s, outcome) for s in suggestions]
    results = engine.record_suggestion_outcomes(ctx, pairs, outcome_source=args.source)
    payload = [
        {
            "category": r.category,
            "label": r.label,
            "old_weight": r.old_weight,
            "new_weight": r.new_weight,
            "explanation": r.explanation,
        }
        for r in results
    ]
    print(json.dumps({"count": len(payload), "results": payload}))
    return 0


def _section_coverage_critic(required: list[str]) -> "object":
    """Deterministic critic: quality = fraction of required sections present."""
    from scripts.evolution.models import Critique

    def _critic(candidate: str) -> Critique:
        if not required:
            return Critique(1.0, "no required sections")
        have = sum(1 for s in required if s in candidate)
        q = have / len(required)
        return Critique(q, f"{have}/{len(required)} required sections present")

    return _critic


def _section_generator(required: list[str]) -> "object":
    """Deterministic generator: append the first missing required section."""
    def _gen(candidate: str, critique: object, iteration: int) -> str:
        for s in required:
            if s not in candidate:
                return candidate + "\n" + s + "\n..."
        return candidate

    return _gen


def _cmd_refine(args: argparse.Namespace) -> int:
    from scripts.evolution.models import RefinementConfig

    store = EvolutionStore(args.db)
    store.initialize()
    engine = EvolutionEngine(store)
    initial = Path(args.input).read_text(encoding="utf-8")
    required = list(args.require_section or [])
    critic = _section_coverage_critic(required)
    generator = _section_generator(required)
    config = RefinementConfig(
        max_iterations=args.max_iterations,
        quality_threshold=args.threshold,
    )
    result = engine.refine_output(
        initial, critic, generator, config,
        persist=True, repo=args.repo, pr_url=args.pr_url,
    )
    payload = {
        "stop_reason": str(result.stop_reason),
        "final_quality": result.final_quality,
        "iterations": len(result.iterations),
        "final_candidate": result.final_candidate,
    }
    if args.output:
        Path(args.output).write_text(result.final_candidate, encoding="utf-8")
        payload["written"] = args.output
    print(json.dumps(payload))
    return 0


def _split_markdown_sections(required: list[str]):
    """Decompose a markdown doc into one part per top-level ('# ') section."""
    import re

    from scripts.evolution.models import RefinementPart

    def _decompose(doc: str):
        parts = []
        for block in re.split(r"(?m)^(?=# )", doc):
            block = block.strip("\n")
            if block:
                head = block.splitlines()[0]
                parts.append(RefinementPart(value=block, key=head))
        return parts

    return _decompose


def _join_markdown_sections(original: str, refined) -> str:
    if not refined:
        return original
    return "\n\n".join(rp.node.final_candidate for rp in refined)


def _node_to_dict(node) -> dict:
    return {
        "path": list(node.path),
        "depth": node.depth,
        "final_candidate": node.final_candidate,
        "stop_reason": str(node.refinement.stop_reason),
        "quality": node.refinement.final_quality,
        "aggregate_quality": node.aggregate_quality,
        "max_depth_reached": node.max_depth_reached,
        "children": [_node_to_dict(c) for c in node.children],
    }


def _cmd_refine_recursive(args: argparse.Namespace) -> int:
    from scripts.evolution.models import RefinementConfig

    store = EvolutionStore(args.db)
    store.initialize()
    engine = EvolutionEngine(store)
    initial = Path(args.input).read_text(encoding="utf-8")
    required = list(args.require_section or [])
    critic = _section_coverage_critic(required)
    generator = _section_generator(required)
    decompose = _split_markdown_sections(required)
    config = RefinementConfig(
        max_iterations=args.max_iterations,
        quality_threshold=args.threshold,
    )
    result = engine.refine_recursive(
        initial, critic, generator, decompose, _join_markdown_sections, config,
        max_depth=args.max_depth, max_workers=args.max_workers,
        persist=True, run_id=args.run_id, repo=args.repo, pr_url=args.pr_url,
    )
    payload = {
        "final_candidate": result.final_candidate,
        "final_quality": result.final_quality,
        "total_iterations": result.total_iterations,
        "max_observed_depth": result.max_observed_depth,
        "tree": _node_to_dict(result.tree),
    }
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["written"] = args.output
    print(json.dumps(payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.evolution.cli",
        description="Recursive regression & evolution engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="create the SQLite schema")
    p_init.add_argument("--db", required=True)
    p_init.set_defaults(func=_cmd_init_db)

    p_ing = sub.add_parser("ingest-findings", help="persist findings and report regressions")
    p_ing.add_argument("--db", required=True)
    p_ing.add_argument("--repo", required=True)
    p_ing.add_argument("--pr-url", dest="pr_url", default=None)
    p_ing.add_argument("--pr-number", dest="pr_number", type=int, default=None)
    p_ing.add_argument("--commit-sha", dest="commit_sha", default=None)
    p_ing.add_argument("--input", required=True)
    p_ing.set_defaults(func=_cmd_ingest_findings)

    p_adj = sub.add_parser("adjust-suggestions", help="apply evolved weights to suggestions")
    p_adj.add_argument("--db", required=True)
    p_adj.add_argument("--repo", required=True)
    p_adj.add_argument("--input", required=True)
    p_adj.add_argument("--output", default=None)
    p_adj.add_argument("--threshold", type=float, default=0.0)
    p_adj.add_argument("--raw", action="store_true", help="input is raw pr_code_suggestions output")
    p_adj.set_defaults(func=_cmd_adjust_suggestions)

    p_rev = sub.add_parser("ingest-review", help="ingest raw pr_reviewer review_data via the adapter")
    p_rev.add_argument("--db", required=True)
    p_rev.add_argument("--repo", required=True)
    p_rev.add_argument("--pr-url", dest="pr_url", default=None)
    p_rev.add_argument("--pr-number", dest="pr_number", type=int, default=None)
    p_rev.add_argument("--commit-sha", dest="commit_sha", default=None)
    p_rev.add_argument("--input", required=True)
    p_rev.set_defaults(func=_cmd_ingest_review)

    p_close = sub.add_parser("mark-closed", help="mark a finding closed (enables regression detection)")
    p_close.add_argument("--db", required=True)
    p_close.add_argument("--repo", required=True)
    p_close.add_argument("--fingerprint", required=True)
    p_close.add_argument("--reason", default="resolved")
    p_close.set_defaults(func=_cmd_mark_closed)

    p_out = sub.add_parser("record-outcome", help="record accept/reject outcomes and evolve weights")
    p_out.add_argument("--db", required=True)
    p_out.add_argument("--repo", required=True)
    p_out.add_argument("--pr-url", dest="pr_url", default=None)
    p_out.add_argument("--pr-number", dest="pr_number", type=int, default=None)
    p_out.add_argument("--commit-sha", dest="commit_sha", default=None)
    p_out.add_argument("--outcome", required=True, choices=["accepted", "rejected", "unknown"])
    p_out.add_argument("--source", default="author")
    p_out.add_argument("--input", required=True)
    p_out.add_argument("--raw", action="store_true", help="input is raw pr_code_suggestions output")
    p_out.set_defaults(func=_cmd_record_outcome)

    p_ref = sub.add_parser("refine", help="run the recursive self-refinement loop (section-coverage critic)")
    p_ref.add_argument("--db", required=True)
    p_ref.add_argument("--repo", default=None)
    p_ref.add_argument("--pr-url", dest="pr_url", default=None)
    p_ref.add_argument("--input", required=True)
    p_ref.add_argument("--output", default=None)
    p_ref.add_argument("--require-section", dest="require_section", action="append", default=[])
    p_ref.add_argument("--max-iterations", dest="max_iterations", type=int, default=5)
    p_ref.add_argument("--threshold", type=float, default=1.0)
    p_ref.set_defaults(func=_cmd_refine)

    p_rec = sub.add_parser(
        "refine-recursive",
        help="recursively refine a markdown doc by section (section-coverage critic)",
    )
    p_rec.add_argument("--db", required=True)
    p_rec.add_argument("--repo", default=None)
    p_rec.add_argument("--pr-url", dest="pr_url", default=None)
    p_rec.add_argument("--input", required=True)
    p_rec.add_argument("--output", default=None)
    p_rec.add_argument("--run-id", dest="run_id", default=None)
    p_rec.add_argument("--require-section", dest="require_section", action="append", default=[])
    p_rec.add_argument("--max-iterations", dest="max_iterations", type=int, default=5)
    p_rec.add_argument("--max-depth", dest="max_depth", type=int, default=1)
    p_rec.add_argument("--max-workers", dest="max_workers", type=int, default=1,
                       help="parallel sibling refinement workers (>1 needs thread-safe callables)")
    p_rec.add_argument("--threshold", type=float, default=1.0)
    p_rec.set_defaults(func=_cmd_refine_recursive)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
