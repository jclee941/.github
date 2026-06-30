from __future__ import annotations

import requests
from _pytest.monkeypatch import MonkeyPatch

from jclee_bot import github_retry, repository_metadata
from jclee_bot.json_boundary import JsonObject
from jclee_bot.repo_standardization_github import apply_branch_protection, upsert_ruleset


def response_with_json(*, status_code: int, body: bytes = b"{}") -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    object.__setattr__(response, "_content", body)
    return response


def test_metadata_github_get_retries_retryable_status(monkeypatch: MonkeyPatch) -> None:
    get_calls = 0
    sleep_calls = 0

    def fake_sleep_before_retry() -> None:
        nonlocal sleep_calls
        sleep_calls += 1

    def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> requests.Response:
        nonlocal get_calls
        assert url.endswith("/repos/jclee941/tmux")
        assert headers["Authorization"] == "Bearer tok"
        assert timeout == 30
        get_calls += 1
        if get_calls == 1:
            return response_with_json(status_code=502, body=b'{"message":"bad gateway"}')
        return response_with_json(status_code=200, body=b'{"description":"Tmux","homepage":""}')

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(github_retry, "sleep_before_retry", fake_sleep_before_retry)

    result = repository_metadata.github_get(token="tok", path="/repos/jclee941/tmux")

    assert result == {"description": "Tmux", "homepage": ""}
    assert get_calls == 2
    assert sleep_calls == 1


def test_branch_protection_retries_transient_github_patch_failure(monkeypatch: MonkeyPatch) -> None:
    patch_calls = 0
    put_calls = 0
    sleep_calls = 0

    def fake_sleep_before_retry() -> None:
        nonlocal sleep_calls
        sleep_calls += 1

    def fake_patch(url: str, *, headers: dict[str, str], json: JsonObject, timeout: int) -> requests.Response:
        nonlocal patch_calls
        assert url.endswith("/repos/jclee941/tmux")
        assert headers["Authorization"] == "token token"
        assert json["allow_auto_merge"] is True
        assert timeout == 30
        patch_calls += 1
        if patch_calls == 1:
            raise requests.ConnectionError("api.github.com refused connection")
        return response_with_json(status_code=200)

    def fake_put(url: str, *, headers: dict[str, str], json: JsonObject, timeout: int) -> requests.Response:
        nonlocal put_calls
        assert url.endswith("/repos/jclee941/tmux/branches/master/protection")
        assert headers["Authorization"] == "token token"
        assert "required_status_checks" in json
        assert timeout == 30
        put_calls += 1
        return response_with_json(status_code=200, body=b"")

    monkeypatch.setattr(requests, "patch", fake_patch)
    monkeypatch.setattr(requests, "put", fake_put)
    monkeypatch.setattr(github_retry, "sleep_before_retry", fake_sleep_before_retry)

    action = apply_branch_protection(token="token", full_repo="jclee941/tmux", dry_run=False)

    assert action.action == "applied"
    assert patch_calls == 2
    assert put_calls == 1
    assert sleep_calls == 1


def test_rulesets_retries_retryable_github_status(monkeypatch: MonkeyPatch) -> None:
    get_calls = 0
    sleep_calls = 0

    def fake_sleep_before_retry() -> None:
        nonlocal sleep_calls
        sleep_calls += 1

    def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> requests.Response:
        nonlocal get_calls
        assert url.endswith("/repos/jclee941/tmux/rulesets")
        assert headers["Authorization"] == "token token"
        assert timeout == 30
        get_calls += 1
        if get_calls == 1:
            return response_with_json(status_code=502, body=b'{"message":"bad gateway"}')
        return response_with_json(status_code=200, body=b'[{"id":42,"name":"Default Branch Protection"}]')

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(github_retry, "sleep_before_retry", fake_sleep_before_retry)

    action = upsert_ruleset(token="token", full_repo="jclee941/tmux", dry_run=True)

    assert action.action == "would_apply"
    assert action.detail == "update existing ruleset"
    assert get_calls == 2
    assert sleep_calls == 1


def test_ruleset_create_rechecks_after_ambiguous_post_failure(monkeypatch: MonkeyPatch) -> None:
    get_calls = 0
    post_calls = 0

    def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> requests.Response:
        nonlocal get_calls
        assert url.endswith("/repos/jclee941/tmux/rulesets")
        assert headers["Authorization"] == "token token"
        assert timeout == 30
        get_calls += 1
        if get_calls == 1:
            return response_with_json(status_code=200, body=b"[]")
        return response_with_json(status_code=200, body=b'[{"id":42,"name":"Default Branch Protection"}]')

    def fake_post(url: str, *, headers: dict[str, str], json: JsonObject, timeout: int) -> requests.Response:
        nonlocal post_calls
        assert url.endswith("/repos/jclee941/tmux/rulesets")
        assert headers["Authorization"] == "token token"
        assert json["name"] == "Default Branch Protection"
        assert timeout == 30
        post_calls += 1
        raise requests.Timeout("ruleset create response timed out after apply")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)

    action = upsert_ruleset(token="token", full_repo="jclee941/tmux", dry_run=False)

    assert action.action == "applied"
    assert get_calls == 2
    assert post_calls == 1
