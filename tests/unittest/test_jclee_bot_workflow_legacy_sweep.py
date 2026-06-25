from __future__ import annotations

from _pytest.monkeypatch import MonkeyPatch

from jclee_bot import workflow_current_sweep, workflow_issue_automation, workflow_legacy_sweep


def _install_no_current_sweep(monkeypatch: MonkeyPatch) -> None:
    def no_current_sweep(
        *,
        token: str,
        repo_full_name: str,
        default_branch: str,
        dry_run: bool,
        close_issue: workflow_current_sweep.CloseIssue,
    ) -> list[str]:
        del token, repo_full_name, default_branch, dry_run, close_issue
        return []

    monkeypatch.setattr(workflow_current_sweep, "sweep_current_failure_issues", no_current_sweep)


def _install_no_pr_review_issues(monkeypatch: MonkeyPatch) -> None:
    def no_open_issues(
        *, token: str, repo_full_name: str, labels: str | None = None
    ) -> list[dict[str, workflow_legacy_sweep.JsonValue]]:
        del token, repo_full_name, labels
        return []

    monkeypatch.setattr(workflow_legacy_sweep, "_open_issues", no_open_issues)


def test_legacy_sweep_closes_release_drafter_notify_issue_after_latest_master_success(
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    closed: list[tuple[int, str]] = []

    def release_drafter_issue_numbers(
        *, token: str, repo_full_name: str, title_substring: str
    ) -> list[int]:
        del token, repo_full_name
        if title_substring == "[ci-fail] Release Drafter @":
            return [738]
        return []

    def release_drafter_success(
        *, token: str, repo_full_name: str, workflow_file: str, default_branch: str, completed_only: bool
    ) -> tuple[str, str]:
        del token, repo_full_name, default_branch
        if workflow_file == "23_release-drafter.yml" and completed_only:
            return ("completed", "success")
        return ("none", "none")

    def no_in_flight_run(*, token: str, repo_full_name: str, workflow_file: str, default_branch: str) -> bool:
        del token, repo_full_name, workflow_file, default_branch
        return False

    def fake_close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
        del token, repo_full_name
        closed.append((issue_number, body))

    monkeypatch.setattr(workflow_legacy_sweep, "_issue_numbers_with_title", release_drafter_issue_numbers)
    monkeypatch.setattr(workflow_legacy_sweep, "_newest_run_in_flight", no_in_flight_run)
    monkeypatch.setattr(workflow_legacy_sweep, "_workflow_run_status", release_drafter_success)
    monkeypatch.setattr(workflow_issue_automation, "_close", fake_close)
    _install_no_current_sweep(monkeypatch)
    _install_no_pr_review_issues(monkeypatch)

    # When
    actions = workflow_issue_automation.sweep_legacy_failure_issues(
        token="tok",
        repo_full_name="jclee941/.github",
        default_branch="master",
        dry_run=False,
    )

    # Then
    assert actions == ["close-legacy:738:23_release-drafter.yml"]
    assert closed == [
        (
            738,
            "23_release-drafter.yml latest run on master concluded success.\n\n_jclee-bot에의해자동화됨._",
        )
    ]


def test_legacy_sweep_closes_old_sanity_current_issue_after_latest_master_success(
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    closed: list[tuple[int, str]] = []

    def sanity_issue_numbers(*, token: str, repo_full_name: str, title_substring: str) -> list[int]:
        del token, repo_full_name
        if title_substring == "[ci] Sanity failed at":
            return [710]
        return []

    def sanity_success(
        *, token: str, repo_full_name: str, workflow_file: str, default_branch: str, completed_only: bool
    ) -> tuple[str, str]:
        del token, repo_full_name, default_branch
        if workflow_file == "90_sanity.yml" and completed_only:
            return ("completed", "success")
        return ("none", "none")

    def no_in_flight_run(*, token: str, repo_full_name: str, workflow_file: str, default_branch: str) -> bool:
        del token, repo_full_name, workflow_file, default_branch
        return False

    def fake_close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
        del token, repo_full_name
        closed.append((issue_number, body))

    monkeypatch.setattr(workflow_legacy_sweep, "_issue_numbers_with_title", sanity_issue_numbers)
    monkeypatch.setattr(workflow_legacy_sweep, "_workflow_run_status", sanity_success)
    monkeypatch.setattr(workflow_legacy_sweep, "_newest_run_in_flight", no_in_flight_run)
    monkeypatch.setattr(workflow_issue_automation, "_close", fake_close)
    _install_no_current_sweep(monkeypatch)
    _install_no_pr_review_issues(monkeypatch)

    # When
    actions = workflow_issue_automation.sweep_legacy_failure_issues(
        token="tok",
        repo_full_name="jclee941/.github",
        default_branch="master",
        dry_run=False,
    )

    # Then
    assert actions == ["close-legacy:710:90_sanity.yml"]
    assert closed == [
        (
            710,
            "90_sanity.yml latest run on master concluded success.\n\n_jclee-bot에의해자동화됨._",
        )
    ]


def test_legacy_sweep_closes_pr_review_failure_issue_when_pr_is_closed(
    monkeypatch: MonkeyPatch,
) -> None:
    # Given
    closed: list[tuple[int, str]] = []

    def open_ci_issues(
        *, token: str, repo_full_name: str, labels: str | None = None
    ) -> list[dict[str, workflow_legacy_sweep.JsonValue]]:
        del token, repo_full_name, labels
        return [{"number": 723, "title": "PR Review failed for PR #721"}]

    def pr_is_closed(*, token: str, repo_full_name: str, pr_number: int) -> str:
        del token, repo_full_name
        assert pr_number == 721
        return "closed"

    def no_legacy_issues(*, token: str, repo_full_name: str, title_substring: str) -> list[int]:
        del token, repo_full_name, title_substring
        return []

    def no_in_flight_run(*, token: str, repo_full_name: str, workflow_file: str, default_branch: str) -> bool:
        del token, repo_full_name, workflow_file, default_branch
        return False

    def fake_close(*, token: str, repo_full_name: str, issue_number: int, body: str) -> None:
        del token, repo_full_name
        closed.append((issue_number, body))

    monkeypatch.setattr(workflow_legacy_sweep, "_open_issues", open_ci_issues)
    monkeypatch.setattr(workflow_legacy_sweep, "_pull_request_state", pr_is_closed)
    monkeypatch.setattr(workflow_legacy_sweep, "_issue_numbers_with_title", no_legacy_issues)
    monkeypatch.setattr(workflow_legacy_sweep, "_newest_run_in_flight", no_in_flight_run)
    monkeypatch.setattr(workflow_issue_automation, "_close", fake_close)
    _install_no_current_sweep(monkeypatch)

    # When
    actions = workflow_issue_automation.sweep_legacy_failure_issues(
        token="tok",
        repo_full_name="jclee941/.github",
        default_branch="master",
        dry_run=False,
    )

    # Then
    assert actions == ["close-pr-review:723:721"]
    assert closed == [
        (
            723,
            "PR #721 is closed; closing legacy PR review failure issue.\n\n_jclee-bot에의해자동화됨._",
        )
    ]
