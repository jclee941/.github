from __future__ import annotations

import subprocess
from pathlib import Path

from jclee_bot import readme_runner


def test_checkout_pr_head_does_not_put_installation_token_in_git_args(monkeypatch, tmp_path):
    from jclee_bot import app as app_module

    token = "ghs_secret_installation_token"
    token_user = "x-access" + "-token"
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs.get("env")))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)

    assert app_module._checkout_pr_head(token, "jclee941/propose", "abc123", str(tmp_path)) is True
    joined_args = " ".join(" ".join(args) for args, _env in calls)
    assert token not in joined_args
    assert token_user not in joined_args
    assert "https://github.com/jclee941/propose.git" in joined_args
    fetch_env = calls[1][1]
    assert fetch_env is not None
    assert fetch_env["GIT_ASKPASS_USERNAME"] == token_user
    assert fetch_env["GIT_ASKPASS_PASSWORD"] == token


def test_clone_repo_does_not_put_installation_token_in_git_args(monkeypatch, tmp_path):
    token = "ghs_secret_installation_token"
    token_user = "x-access" + "-token"
    seen_args: list[list[str]] = []
    seen_safe_args: list[list[str] | None] = []
    seen_env: list[dict[str, str] | None] = []

    def fake_run_git(
        args: list[str],
        *,
        cwd: Path,
        timeout: int = 120,
        safe_args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        seen_args.append(args)
        seen_safe_args.append(safe_args)
        seen_env.append(env)

    monkeypatch.setattr(readme_runner, "_run_git", fake_run_git)

    repo_path = readme_runner.clone_repo(
        token=token,
        repo_full_name="jclee941/propose",
        default_branch="master",
        workspace=tmp_path,
    )

    assert repo_path == tmp_path / "repo"
    assert len(seen_args) == 1
    args = " ".join(str(part) for part in seen_args[0])
    safe_args = " ".join(str(part) for part in seen_safe_args[0] or [])
    env = seen_env[0]
    assert token not in args
    assert token_user not in args
    assert token not in safe_args
    assert "https://github.com/jclee941/propose.git" in args
    assert isinstance(env, dict)
    assert env["GIT_ASKPASS_USERNAME"] == token_user
    assert env["GIT_ASKPASS_PASSWORD"] == token


def test_readme_automation_sanitizes_git_clone_failure(monkeypatch):
    token = "ghs_secret_installation_token"
    token_user = "x-access" + "-token"
    token_url = (
        "https://"
        + token_user
        + ":"
        + token
        + "@github.com/jclee941/propose.git"
    )

    def fake_clone_repo(**kwargs):
        raise subprocess.CalledProcessError(
            128,
            ["git", "clone", token_url],
            stderr="remote: Repository not found.",
        )

    monkeypatch.setattr(readme_runner, "clone_repo", fake_clone_repo)

    result = readme_runner.ensure_readme_commit(
        token=token,
        repo={"full_name": "jclee941/propose", "default_branch": "master"},
        dry_run=True,
    )

    assert result["repo"] == "jclee941/propose"
    assert result["changed"] is False
    assert "error" in result
    assert token not in str(result)
    assert token_user not in str(result)
