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
pytest tests/e2e_live -m readonly -v

# Optional checks that need CLIProxyAPI access
export E2E_CLIPROXY_API_KEY="<cliproxy key>"  # or CLIPROXY_API_KEY
pytest tests/e2e_live -m "readonly or app_health or cliproxy_health" -v
```

The fixtures call `pytest.skip()` when required environment variables are missing, so local unit-test runs remain safe
and do not fail just because live credentials are unavailable.

## Safety mechanisms

Live mutation is restricted to a dedicated canary repository only:

- `jclee941/automation-e2e-private`

Every mutation helper in `github_mutation.py` calls `guard_mutation(repo)` before creating branches, writing files, deleting
branches, or opening pull requests. The guard raises immediately unless the target repository is in
`MUTATION_ALLOWED_REPOS`.

Production repositories must remain read-only in this suite. Do not add tests that mutate any managed production repo
selected by `config/repos.yaml` with `automation.branch_protection: true`. The `github-bot` source repository is intentionally excluded
from the managed automation rollout checks.

## Required environment variables

| Variable | Fallback | Purpose |
| --- | --- | --- |
| `E2E_GITHUB_TOKEN` | `GH_TOKEN` | GitHub API and `gh` CLI authentication for live checks. |
| `E2E_CANARY_PRIVATE_REPO` | `jclee941/automation-e2e-private` | Private canary repository for allowlisted mutation tests. |
| `E2E_CLIPROXY_API_KEY` | `CLIPROXY_API_KEY` | Optional CLIProxyAPI connectivity checks. |

Never hardcode real secrets in tests, fixtures, docs, or workflow files.

## Test categories

The live suite is designed around these categories (17 tests total):

### Current live checks

1. **Repository inventory checks** (`readonly`) — verify every managed repository is reachable and report its visibility and default
   branch.
2. **Workflow deployment checks** (`readonly`) — verify required workflow inventory is empty because the jclee-bot GitHub App drives CI centrally.
3. **Required file checks** (`readonly`) — verify automation support files exist: `.github/dependabot.yml`, `.github/CODEOWNERS`, and
   `.github/PULL_REQUEST_TEMPLATE.md`.
4. **Branch protection checks** (`readonly`) — verify required status contexts are configured: `jclee-bot / pr-metadata`,
   `jclee-bot / secret-scan`, and `jclee-bot / actionlint` (App-reported Checks API contexts).
5. **Recent activity checks** (`readonly`) — inspect recent PRs and bot comments/reviews without modifying production
   repositories.
6. **Canary mutation checks** (`private_canary`) — exercise branch, file, and PR behavior only in the allowlisted private
   canary repository.
7. **Go CLI dry-run checks** (`readonly`) — verify `branch-protection` and `repo-review` Go scripts run in dry-run mode without
   errors.
8. **Security review workflow guards** (`security_review`) — static YAML analysis of `pull_request_target` fork/head-repo guards.
9. **GitHub App health checks** (`app_health`) — bot recent activity, webhook reachability, app installation, CLIProxy endpoint probes.
10. **CLIProxy health** (`cliproxy_health`) — query `/v1/models`, verify `minimax-m3` availability.

### Running by marker

```bash
# Read-only fleet health (no mutations)
pytest tests/e2e_live -m readonly -v

# Canary and privileged-workflow guard checks
pytest tests/e2e_live -m "private_canary or security_review" -v

# Infrastructure health only
pytest tests/e2e_live -m "app_health or cliproxy_health" -v

# Full suite (requires all env vars)
pytest tests/e2e_live -v
```

Keep production checks read-only. If a new helper mutates GitHub state, it must call `guard_mutation()` before making the API request.
