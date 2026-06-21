from __future__ import annotations

from typing import Any

from jclee_bot import issue_management


class TestCreateIssueBranch:
    def test_uses_inferred_string_labels_for_branch_type(self) -> None:
        # Given
        labels = ["bug", "enhancement", "tests"]

        # When
        branch = issue_management.issue_branch_name(
            issue_number=7,
            title="Bug: crash in coverage workflow",
            labels=labels,
        )

        # Then
        assert branch == "fix/issue-7-bug-crash-in-coverage-workflow"

    def test_creates_issue_branch_from_master_and_comments(self, monkeypatch) -> None:
        # Given
        requests: list[tuple[str, str, dict[str, Any] | None]] = []

        class FakeResponse:
            def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
                self.status_code = status_code
                self._payload = payload or {}

            def json(self) -> dict[str, Any]:
                return self._payload

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    raise AssertionError(f"unexpected HTTP status {self.status_code}")

        def fake_get(url: str, **kwargs: Any) -> FakeResponse:
            requests.append(("GET", url, None))
            if url.endswith("/git/ref/heads/fix/issue-7-bug-crash-in-coverage-workflow"):
                return FakeResponse(404)
            if url.endswith("/git/ref/heads/master"):
                return FakeResponse(200, {"object": {"sha": "abc123"}})
            raise AssertionError(f"unexpected GET {url}")

        def fake_post(url: str, **kwargs: Any) -> FakeResponse:
            requests.append(("POST", url, kwargs.get("json")))
            return FakeResponse(201)

        monkeypatch.setattr(issue_management.requests, "get", fake_get)
        monkeypatch.setattr(issue_management.requests, "post", fake_post)

        # When
        branch = issue_management.create_issue_branch(
            token="tok",
            repo_full_name="jclee941/propose",
            issue_number=7,
            title="Bug: crash in coverage workflow",
            labels=[{"name": "bug"}],
        )

        # Then
        assert branch == "fix/issue-7-bug-crash-in-coverage-workflow"
        assert requests == [
            (
                "GET",
                "https://api.github.com/repos/jclee941/propose/git/ref/heads/fix/issue-7-bug-crash-in-coverage-workflow",
                None,
            ),
            (
                "GET",
                "https://api.github.com/repos/jclee941/propose/git/ref/heads/master",
                None,
            ),
            (
                "POST",
                "https://api.github.com/repos/jclee941/propose/git/refs",
                {
                    "ref": "refs/heads/fix/issue-7-bug-crash-in-coverage-workflow",
                    "sha": "abc123",
                },
            ),
            (
                "POST",
                "https://api.github.com/repos/jclee941/propose/issues/7/comments",
                {
                    "body": "Branch `fix/issue-7-bug-crash-in-coverage-workflow` created. "
                    "Push commits to that branch and a draft PR will open automatically."
                },
            ),
        ]

    def test_skips_branch_creation_when_branch_already_exists(self, monkeypatch) -> None:
        # Given
        posts: list[str] = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                raise AssertionError("existing branch should not be treated as an error")

        monkeypatch.setattr(issue_management.requests, "get", lambda *args, **kwargs: FakeResponse())
        monkeypatch.setattr(
            issue_management.requests,
            "post",
            lambda url, **kwargs: posts.append(url),
        )

        # When
        branch = issue_management.create_issue_branch(
            token="tok",
            repo_full_name="jclee941/propose",
            issue_number=7,
            title="Bug: crash in coverage workflow",
            labels=[{"name": "bug"}],
        )

        # Then
        assert branch is None
        assert posts == []
