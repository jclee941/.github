#!/usr/bin/env python3
"""issue_classifier_js_test.py — exercise the JS issue classifier via Node.

Why this exists
---------------
``.github/scripts/issue-classifier.cjs`` holds the deterministic, dependency-free
logic that ``.github/workflows/91_issue-classification.yml`` runs inside
``actions/github-script@v9``. The runtime is JavaScript, so the unit tests must
exercise the *same* JS rather than a re-implementation. We invoke the module's
CLI mode through ``node`` (v22 is available locally and in CI) and assert on the
JSON it prints. No npm packages or JS test framework are introduced — the repo's
existing pytest convention drives Node via ``subprocess``.

The classifier never calls the GitHub API; it only decides *what* should happen
(labels, comments, close/no-close). The workflow performs the side effects.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE = REPO_ROOT / ".github" / "scripts" / "issue-classifier.cjs"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "issue-classification"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to run the JS classifier"
)


def run_cli(*args: str) -> dict:
    """Run the classifier CLI and return parsed JSON stdout."""
    proc = subprocess.run(
        ["node", str(MODULE), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"classifier CLI exited {proc.returncode}\n"
        f"args={args}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    return json.loads(proc.stdout)


def fx(name: str) -> str:
    return str(FIXTURES / name)


def test_module_file_exists():
    assert MODULE.exists(), f"missing classifier module: {MODULE}"


def test_token_jaccard_detects_duplicate_title_body():
    out = run_cli(
        "--mode", "duplicate",
        "--issue", fx("duplicate-new.json"),
        "--candidates", fx("open-issues.json"),
    )
    assert out["matches"], "expected at least one duplicate match"
    top = out["matches"][0]
    assert top["number"] == 12, f"expected top match #12, got {top}"
    assert top["score"] >= 0.58, f"score too low: {top['score']}"
    assert out["label"] == "duplicate"
    assert out["shouldClose"] is False  # default never auto-closes duplicates


def test_low_similarity_does_not_classify_duplicate():
    out = run_cli(
        "--mode", "duplicate",
        "--issue", fx("unrelated-new.json"),
        "--candidates", fx("open-issues.json"),
    )
    assert out["matches"] == [], f"expected no matches, got {out['matches']}"
    assert out["label"] is None
    assert out["shouldClose"] is False


def test_duplicate_skips_self_and_closed_and_prs():
    # The candidate list includes the issue's own number and should never
    # match itself; closed issues and PRs must be excluded too.
    out = run_cli(
        "--mode", "duplicate",
        "--issue", fx("duplicate-new.json"),
        "--candidates", fx("open-issues.json"),
    )
    numbers = [m["number"] for m in out["matches"]]
    assert 42 not in numbers, "must not match itself"


def test_duplicate_high_confidence_close_when_enabled():
    out = run_cli(
        "--mode", "duplicate",
        "--issue", fx("duplicate-new.json"),
        "--candidates", fx("open-issues.json"),
        "--close-duplicates", "true",
        "--duplicate-close-threshold", "0.5",
    )
    assert out["label"] == "duplicate"
    assert out["shouldClose"] is True


def test_extracts_closing_keywords_from_merged_pr_body():
    out = run_cli("--mode", "resolved-pr", "--pr", fx("merged-pr.json"))
    assert sorted(out["issueNumbers"]) == [7, 9], out
    assert out["label"] == "resolved"
    assert out["shouldClose"] is True  # close_resolved_by_pr defaults true


def test_branch_issue_pattern_is_supported():
    out = run_cli("--mode", "resolved-pr", "--pr", fx("branch-only-pr.json"))
    assert out["issueNumbers"] == [42], out


def test_resolved_pr_not_closed_when_disabled():
    out = run_cli(
        "--mode", "resolved-pr",
        "--pr", fx("merged-pr.json"),
        "--close-resolved-by-pr", "false",
    )
    assert out["label"] == "resolved"
    assert out["shouldClose"] is False


def test_resolved_signal_detected_but_not_default_close():
    out = run_cli("--mode", "resolved-signal", "--issue", fx("resolved-signal-issue.json"))
    assert out["label"] == "resolved"
    assert out["shouldClose"] is False


def test_resolved_signal_closes_when_enabled():
    out = run_cli(
        "--mode", "resolved-signal",
        "--issue", fx("resolved-signal-issue.json"),
        "--close-resolved-by-signal", "true",
    )
    assert out["label"] == "resolved"
    assert out["shouldClose"] is True


def test_no_false_positive_resolved_signal():
    out = run_cli("--mode", "resolved-signal", "--issue", fx("open-signal-negative.json"))
    assert out["label"] is None, f"must not flag an unresolved issue, got {out}"
    assert out["shouldClose"] is False


def test_dry_run_never_closes():
    out = run_cli(
        "--mode", "resolved-pr",
        "--pr", fx("merged-pr.json"),
        "--close-resolved-by-pr", "true",
        "--dry-run", "true",
    )
    # In dry-run the decision is still computed but flagged as a no-op plan.
    assert out["dryRun"] is True
    assert out["label"] == "resolved"


def test_generic_exact_title_with_unrelated_body_is_not_duplicate():
    # D4: an exact but generic title ("Build failed") with unrelated bodies must
    # NOT be flagged a duplicate on title overlap alone (false-positive guard).
    out = run_cli(
        "--mode", "duplicate",
        "--issue", fx("generic-title-new.json"),
        "--candidates", fx("generic-title-candidates.json"),
    )
    assert out["matches"] == [], f"generic title must not be a duplicate, got {out['matches']}"
    assert out["label"] is None


def test_fixed_in_future_tense_is_not_resolved_signal():
    # D5: "should be fixed in a future release" / "fixed in v2?" must NOT count
    # as a resolved signal.
    out = run_cli("--mode", "resolved-signal", "--issue", fx("fixed-in-future.json"))
    assert out["label"] is None, f"future-tense 'fixed in' must not resolve, got {out}"
    assert out["shouldClose"] is False


def test_short_generic_title_with_no_body_overlap_is_not_duplicate():
    # Harden against short exact generic titles ("build failed again now") whose
    # bodies share nothing: title overlap alone must not be enough.
    import json
    import tempfile
    new = {"number": 72, "title": "build failed again now",
           "body": "unrelated alpha beta gamma delta epsilon zeta"}
    cands = [{"number": 73, "title": "build failed again now",
              "body": "completely different eta theta iota kappa lambda mu"}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as a:
        json.dump(new, a); pa = a.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as b:
        json.dump(cands, b); pb = b.name
    out = run_cli("--mode", "duplicate", "--issue", pa, "--candidates", pb)
    assert out["matches"] == [], f"short generic title w/ no body overlap must not dup: {out['matches']}"


def test_resolved_in_future_tense_is_not_resolved_signal():
    # D5 (round 2): the 'resolved in ...' future-tense/question variants must
    # NOT count as a resolved signal either.
    out = run_cli("--mode", "resolved-signal", "--issue", fx("resolved-in-future.json"))
    assert out["label"] is None, f"future-tense 'resolved in' must not resolve, got {out}"
    assert out["shouldClose"] is False


def test_concrete_resolved_in_version_is_a_signal():
    # The concrete-reference regex must still fire for a real fix reference.
    import json
    import tempfile
    payload = {"number": 91, "title": "bug", "body": "this was resolved in v2.1"}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        p = fh.name
    out = run_cli("--mode", "resolved-signal", "--issue", p)
    assert out["label"] == "resolved", out


def test_classifier_loads_via_require_in_esm_repo():
    """The workflow loads the classifier via require() inside actions/github-
    script (a CommonJS context). When the CONSUMING repo has package.json
    \"type\": \"module\", a .js module is parsed as ESM and require() fails with
    'module is not defined in ES module scope'. The classifier MUST load
    regardless of the downstream repo's module type (use .cjs)."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        # Simulate a downstream ESM repo.
        with open(os.path.join(d, "package.json"), "w") as fh:
            fh.write('{"type": "module"}')
        scripts_dir = os.path.join(d, ".github", "scripts")
        os.makedirs(scripts_dir)
        # Copy the real classifier module preserving its extension.
        dest = os.path.join(scripts_dir, MODULE.name)
        with open(MODULE) as src, open(dest, "w") as out:
            out.write(src.read())
        # A CommonJS loader (.cjs) mimics github-script's runner context.
        loader = os.path.join(d, "loader.cjs")
        with open(loader, "w") as fh:
            fh.write(
                "const path = require('path');\n"
                "const c = require(path.join(process.cwd(), "
                f"'.github/scripts/{MODULE.name}'));\n"
                "if (typeof c.classifyDuplicate !== 'function') "
                "{ throw new Error('classifyDuplicate missing'); }\n"
                "console.log('OK');\n"
            )
        proc = subprocess.run(
            ["node", "loader.cjs"], cwd=d, capture_output=True, text=True
        )
        assert proc.returncode == 0, (
            "classifier must load via require() in a type:module repo; "
            f"stderr: {proc.stderr.strip()}"
        )
        assert "OK" in proc.stdout, proc.stdout
