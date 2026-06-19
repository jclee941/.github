#!/usr/bin/env python3
"""issue_classification_workflow_test.py — guard 91_issue-classification.yml.

These pin the workflow-level invariants that unit tests on the JS module cannot
see, and that a prior review flagged as defects:

  * close_resolved_by_pr must default ON for non-dispatch events (the env
    expression must be gated by `github.event_name == 'workflow_dispatch'`, so an
    absent input on issues/PR/schedule events cannot coerce to 'false').
  * every `addLabels` for the non-default `resolved`/`duplicate` labels must be
    preceded by an `ensureLabel` helper (the labels may not exist in a repo).
  * the merged-PR job must NOT unconditionally skip already-closed issues (GitHub
    auto-closes Closes/Fixes/Resolves #N on merge; we still label + comment them).
  * downstream repos must load the classifier from the central jclee-bot source
    checkout, not from a local `.github/scripts` file that is not deployed.
  * issue classification must not depend on private self-hosted runner
    availability; it is lightweight GitHub API automation and should run on
    GitHub-hosted runners in every downstream repo.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WF = REPO_ROOT / ".github" / "workflows" / "91_issue-classification.yml"


def load_text() -> str:
    return WF.read_text(encoding="utf-8")


def test_workflow_parses_and_has_four_jobs():
    doc = yaml.safe_load(load_text())
    jobs = set(doc["jobs"].keys())
    assert jobs == {
        "duplicate-classification",
        "resolved-from-merged-pr",
        "resolved-from-signal",
        "resolved-sweep",
    }, jobs


def test_close_resolved_by_pr_defaults_on_for_non_dispatch():
    text = load_text()
    # The env line must gate the manual override behind workflow_dispatch so that
    # an absent input on PR/schedule/issue events resolves to 'true'.
    m = re.search(r"CLOSE_RESOLVED_BY_PR:\s*(.+)", text)
    assert m, "CLOSE_RESOLVED_BY_PR env not found"
    expr = m.group(1)
    assert "github.event_name == 'workflow_dispatch'" in expr, (
        f"close_resolved_by_pr default must be gated by workflow_dispatch: {expr}"
    )


def test_every_resolved_addlabels_has_ensurelabel():
    text = load_text()
    assert text.count("ensureLabel('resolved'") >= 3, (
        "each resolved-label addLabels site must call ensureLabel('resolved', ...)"
    )
    assert "ensureLabel('duplicate'" in text, "duplicate job must ensureLabel too"


def test_classifier_loaded_from_central_source_checkout():
    text = load_text()
    assert text.count("repository: jclee941/.github") == 4
    assert text.count("path: .jclee-bot-source") == 4
    assert "'.github/scripts/issue-classifier.cjs'" not in text
    assert text.count("'.jclee-bot-source/.github/scripts/issue-classifier.cjs'") == 4


def test_issue_classification_uses_github_hosted_runners():
    text = load_text()
    assert "github.repository_visibility == 'private' && 'self-hosted'" not in text
    assert text.count("runs-on: ubuntu-latest") == 4


def _merged_pr_job_script(text: str) -> str:
    """Return the slice of the workflow covering the resolved-from-merged-pr job."""
    start = text.index("resolved-from-merged-pr:")
    end = text.index("resolved-from-signal:")
    return text[start:end]


def test_merged_pr_does_not_skip_closed_issues_for_labeling():
    # The old defect: `if (target.state === 'closed') continue;` skipped issues
    # GitHub had already auto-closed via Closes/Fixes/Resolves #N. In the
    # merged-PR job that blanket skip must be gone; closing is guarded by
    # `plan.shouldClose && !alreadyClosed` so the label/comment still happen.
    # (The scheduled sweep job may still skip closed issues — that is cleanup,
    # not classification — so this assertion is scoped to the merged-PR job.)
    job = _merged_pr_job_script(load_text())
    assert "if (target.state === 'closed') continue;" not in job, (
        "merged-PR job must not skip already-closed issues for label/comment"
    )
    assert "plan.shouldClose && !alreadyClosed" in job, (
        "close call must be guarded by !alreadyClosed, not a blanket skip"
    )
