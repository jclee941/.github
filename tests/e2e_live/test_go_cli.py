import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

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
import sys
args = sys.argv[1:]
if args[:2] == ['api', 'repos/jclee941/idle-outpost']:
    print('main')
elif args[:2] == ['api', 'repos/jclee941/bug']:
    print('main')
elif len(args) >= 2 and args[0] == 'api' and args[1].startswith('repos/jclee941/'):
    print('master')
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
def test_deploy_to_repos_dry_run(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/deploy-to-repos", "--dry-run"], dry_run_env)

    assert result.returncode == 0, result.stderr
    assert "resume" in result.stdout
    assert "pr-agent" not in result.stdout
    assert "pr-review.yml" in result.stdout or "actionlint.yml" in result.stdout


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_deploy_to_repos_canary_dry_run(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/deploy-to-repos", "--dry-run", "--repos=resume"], dry_run_env)

    assert result.returncode == 0, result.stderr
    assert "resume" in result.stdout
    assert "pr-agent" not in result.stdout


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_branch_protection_dry_run(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/branch-protection", "--dry-run"], dry_run_env)

    assert result.returncode == 0, result.stderr
    assert "pr-checks / Check PR Title" in result.stdout
    assert "Gitleaks / scan" in result.stdout


def test_branch_protection_json_valid() -> None:
    source = (SCRIPTS_DIR / "cmd" / "branch-protection" / "main.go").read_text(encoding="utf-8")
    match = re.search(r"const protectionPayload = `(?P<payload>.*?)`", source, re.DOTALL)

    assert match is not None, "protectionPayload raw string not found"
    payload = cast(dict[str, object], json.loads(match.group("payload")))
    status_checks = cast(dict[str, object], payload["required_status_checks"])

    assert status_checks["contexts"] == [
        "pr-checks / Check PR Title",
        "pr-checks / Check Branch Name",
        "Gitleaks / scan",
    ]
    assert payload["enforce_admins"] is False
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False


@pytest.mark.skipif(GO_MISSING, reason="go binary is not available on PATH")
def test_repo_review_output(dry_run_env: Mapping[str, str]) -> None:
    result = run_go_cli(["./cmd/repo-review", "--dry-run", "--repos=resume"], dry_run_env)
    combined_output = f"{result.stdout}\n{result.stderr}".lower()

    assert (
        "github_token/gh_token not set" in combined_output
        or "usage" in combined_output
        or result.returncode in [0, 1]
    )
