from jclee_bot.checks import CheckResult
from jclee_bot.context_guards import neutralize_on_missing_context


def test_required_pr_metadata_fails_when_changed_files_unavailable():
    results = neutralize_on_missing_context(
        [
            CheckResult(
                name="jclee-bot / pr-metadata",
                conclusion="success",
                title="PR metadata OK",
                summary="No sensitive files.",
            )
        ],
        files_ok=False,
        checkout_ok=True,
    )

    assert results[0].conclusion == "failure"
    assert "changed-files API unavailable" in results[0].summary


def test_required_secret_scan_fails_when_checkout_unavailable():
    results = neutralize_on_missing_context(
        [
            CheckResult(
                name="jclee-bot / secret-scan",
                conclusion="success",
                title="no secrets detected",
                summary="gitleaks found no secrets.",
            )
        ],
        files_ok=True,
        checkout_ok=False,
    )

    assert results[0].conclusion == "failure"
    assert "PR checkout unavailable" in results[0].summary


def test_required_tool_skip_fails_closed():
    results = neutralize_on_missing_context(
        [
            CheckResult(
                name="jclee-bot / secret-scan",
                conclusion="neutral",
                title="secret scan skipped",
                summary="gitleaks was not available.",
            ),
            CheckResult(
                name="jclee-bot / actionlint",
                conclusion="neutral",
                title="actionlint not run",
                summary="actionlint was unavailable.",
            ),
        ],
        files_ok=True,
        checkout_ok=True,
    )

    assert [result.conclusion for result in results] == ["failure", "failure"]
    assert "required check skipped" in results[0].summary
    assert "required check skipped" in results[1].summary


def test_actionlint_no_workflow_changes_remains_neutral_when_checkout_unavailable():
    results = neutralize_on_missing_context(
        [
            CheckResult(
                name="jclee-bot / actionlint",
                conclusion="neutral",
                title="no workflow changes",
                summary="No workflow files changed; actionlint not needed.",
            )
        ],
        files_ok=True,
        checkout_ok=False,
    )

    assert results[0].conclusion == "neutral"
    assert results[0].title == "no workflow changes"


def test_actionlint_no_workflow_changes_fails_when_changed_files_unavailable():
    results = neutralize_on_missing_context(
        [
            CheckResult(
                name="jclee-bot / actionlint",
                conclusion="neutral",
                title="no workflow changes",
                summary="No workflow files changed; actionlint not needed.",
            )
        ],
        files_ok=False,
        checkout_ok=True,
    )

    assert results[0].conclusion == "failure"
    assert "changed-files API unavailable" in results[0].summary
