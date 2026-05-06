# Live E2E Test Suite

`tests/e2e_live` contains pytest fixtures and helpers for validating the real `jclee941/.github` automation stack
against GitHub. These tests are intentionally separate from mocked `tests/e2e` tests because they call the live
GitHub API, inspect real workflow runs, and may use dedicated canary repositories for mutation scenarios.

## How to run

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .

# Read-only live checks
export E2E_GITHUB_TOKEN="<github token>"  # or GH_TOKEN
pytest tests/e2e_live -v

# Optional checks that need CLIProxyAPI access
export E2E_CLIPROXY_API_KEY="<cliproxy key>"  # or CLIPROXY_API_KEY
pytest tests/e2e_live -v
```

The fixtures call `pytest.skip()` when required environment variables are missing, so local unit-test runs remain safe
and do not fail just because live credentials are unavailable.

## Safety mechanisms

Live mutation is restricted to dedicated canary repositories only:

- `jclee941/automation-e2e-public`
- `jclee941/automation-e2e-private`

Every mutation helper in `conftest.py` calls `guard_mutation(repo)` before creating branches, writing files, deleting
branches, or opening pull requests. The guard raises immediately unless the target repository is in
`MUTATION_ALLOWED_REPOS`.

Production repositories must remain read-only in this suite. Do not add tests that mutate any managed production repo,
including `.github`, `account`, `blacklist`, `bug`, `hycu_fsds`, `idle-outpost`, `opencode`, `resume`, `safetywallet`,
`splunk`, `terraform`, `tmux`, `hycu`, `youtube`, or `propose`. The `pr-agent` fork is intentionally excluded from the
managed automation rollout checks.

## Required environment variables

| Variable | Fallback | Purpose |
| --- | --- | --- |
| `E2E_GITHUB_TOKEN` | `GH_TOKEN` | GitHub API and `gh` CLI authentication for live checks. |
| `E2E_CANARY_PUBLIC_REPO` | `jclee941/automation-e2e-public` | Public canary repository for allowlisted mutation tests. |
| `E2E_CANARY_PRIVATE_REPO` | `jclee941/automation-e2e-private` | Private canary repository for allowlisted mutation tests. |
| `E2E_CLIPROXY_API_KEY` | `CLIPROXY_API_KEY` | Optional CLIProxyAPI connectivity checks. |

Never hardcode real secrets in tests, fixtures, docs, or workflow files.

## Test categories

The live suite is designed around these categories:

1. **Repository inventory checks** — verify every managed repository is reachable and report its visibility and default
   branch.
2. **Workflow deployment checks** — verify required workflows exist, including `pr-review.yml`, `pr-checks.yml`,
   `gitleaks.yml`, and `actionlint.yml`.
3. **Required file checks** — verify automation support files exist: `.github/dependabot.yml`, `.github/CODEOWNERS`, and
   `.github/PULL_REQUEST_TEMPLATE.md`.
4. **Branch protection checks** — verify required status contexts are configured: `pr-checks / Check PR Title`,
   `pr-checks / Check Branch Name`, and `Gitleaks / scan`.
5. **Recent activity checks** — inspect recent PRs, workflow conclusions, and bot comments without modifying production
   repositories.
6. **Canary mutation checks** — exercise branch, file, PR, and workflow behavior only in the allowlisted public/private
   canary repositories.

Keep production checks read-only. If a new helper mutates GitHub state, it must call `guard_mutation()` before making the
API request.
