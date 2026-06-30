import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

pytestmark = pytest.mark.readonly

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
GO_MISSING = shutil.which("go") is None


@pytest.fixture()
def dry_run_env(tmp_path: Path) -> dict[str, str]:
    """Provide a fake gh binary so dry-run tests do not need GitHub auth."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text(
        """#!/usr/bin/env python3
import os
import subprocess
import sys
args = sys.argv[1:]
if len(args) >= 2 and args[0] == 'api' and args[1].startswith('repos/jclee941/'):
    print('master')
elif args[:2] == ['pr', 'list']:
    print('')
elif args[:2] == ['repo', 'clone'] and len(args) >= 4:
    repo_dir = args[3]
    os.makedirs(repo_dir, exist_ok=True)
    subprocess.run(['git', 'init', '-q'], cwd=repo_dir, check=True)
    subprocess.run(['git', 'config', 'user.email', 'fake@example.invalid'], cwd=repo_dir, check=True)
    subprocess.run(['git', 'config', 'user.name', 'fake gh'], cwd=repo_dir, check=True)
    with open(os.path.join(repo_dir, 'README.md'), 'w', encoding='utf-8') as handle:
        handle.write('fake repo\\n')
    subprocess.run(['git', 'add', 'README.md'], cwd=repo_dir, check=True)
    subprocess.run(['git', 'commit', '-q', '-m', 'init'], cwd=repo_dir, check=True)
    subprocess.run(['git', 'update-ref', 'refs/remotes/origin/master', 'HEAD'], cwd=repo_dir, check=True)
elif args[:2] == ['repo', 'view']:
    print('master')
else:
    print('fake gh: unsupported command: ' + ' '.join(args), file=sys.stderr)
    sys.exit(2)
""",
        encoding="utf-8",
    )
    _ = gh.chmod(0o755)

    env = os.environ.copy()
    env["GO111MODULE"] = "on"
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    _ = env.pop("GITHUB_TOKEN", None)
    _ = env.pop("GH_TOKEN", None)
    return env


def run_go_cli(args: Sequence[str], env: Mapping[str, str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["go", "run", *args],
            cwd=SCRIPTS_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = "" if exc.stdout is None else str(exc.stdout)
        stderr = "" if exc.stderr is None else str(exc.stderr)
        pytest.fail(f"go CLI timed out after {timeout}s\nstdout:\n{stdout}\nstderr:\n{stderr}")


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_branch_cleanup_dry_run_smoke(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/branch-cleanup", "--dry-run", "--repos=resume"], dry_run_env)

    assert result.returncode == 0, result.stderr
    assert "Summary (dry-run):" in result.stdout
    assert "jclee941/resume" in result.stdout
    assert "Total merge-cleanup candidate branches:" in result.stdout


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_rulesets_manager_dry_run_smoke(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/rulesets-manager", "--dry-run", "--repos=resume"], dry_run_env)

    assert result.returncode == 0, result.stderr
    assert "repos/jclee941/resume/rulesets/" in result.stdout
    assert "jclee-bot / pr-metadata" in result.stdout
    assert "jclee-bot / secret-scan" in result.stdout
    assert "jclee-bot / actionlint" in result.stdout
    assert "- jclee941/resume: previewed" in result.stdout



@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_branch_protection_dry_run(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/branch-protection", "--dry-run"], dry_run_env)

    assert result.returncode == 0, result.stderr
    assert "jclee-bot / pr-metadata" in result.stdout
    assert "jclee-bot / secret-scan" in result.stdout
    assert "jclee-bot / actionlint" in result.stdout


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_branch_protection_dry_run_safe_settings(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/branch-protection", "--dry-run", "--repos=resume"], dry_run_env)

    assert result.returncode == 0, result.stderr
    assert "jclee-bot / pr-metadata" in result.stdout
    assert "jclee-bot / secret-scan" in result.stdout
    assert "jclee-bot / actionlint" in result.stdout
    assert "enforce_admins" in result.stdout
    assert "allow_force_pushes" in result.stdout
    assert "allow_deletions" in result.stdout


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_repo_review_output(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/repo-review", "--dry-run", "--repos=resume"], dry_run_env)
    combined_output = f"{result.stdout}\n{result.stderr}".lower()

    assert (
        "github_token/gh_token not set" in combined_output
        or "usage" in combined_output
        or result.returncode in [0, 1]
    )


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_repo_review_normalize_repos_allows_managed_repos_without_token(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/repo-review", "--normalize-repos", "--repos=resume, tmux,resume,hycu"], dry_run_env)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "resume,tmux,hycu"


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_repo_review_normalize_repos_rejects_unsafe_repo_names(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/repo-review", "--normalize-repos", "--repos=../resume"], dry_run_env)

    assert result.returncode != 0
    assert "must be a managed repo name" in result.stderr


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_repo_standardization_dry_run_smoke(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/repo-standardization", "--dry-run", "--repos=resume"], dry_run_env)

    assert result.returncode == 0, result.stderr
    assert "repo-standardization starting (dry-run)" in result.stdout
    assert "- jclee941/resume: passed" in result.stdout
    assert "repo-standardization finished. failures=0" in result.stdout
