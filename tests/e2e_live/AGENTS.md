# tests/e2e_live — Live E2E Test Suite

## OVERVIEW

Live tests against the real `jclee941/.github` automation stack via GitHub API. Readonly inspections cover the managed fleet; controlled mutations are restricted to the private canary repo.

## STRUCTURE

```
tests/e2e_live/
├── conftest.py                  # Shared fixtures and GitHub client
├── repo_config.py               # Managed repo inventory helpers
├── github_read.py               # Read-only GitHub API helpers
├── github_mutation.py           # Mutating GitHub API helpers guarded by canary checks
├── fleet_health_helpers.py      # Fleet policy assertions
├── test_fleet_health.py         # Protected repo policy and App check contexts
├── test_app_health.py           # Bot app webhook health
├── test_security_review.py      # Static pull_request_target fork-guard checks
├── test_cliproxy_health.py      # Optional CLIProxyAPI reachability checks
├── test_private_canary.py       # Private repo canary tests
└── test_go_cli.py               # Go helper scripts validation
```

## WHERE TO LOOK

| Test file | Marker | What it checks |
|-----------|--------|----------------|
| test_fleet_health.py | readonly | Automation state across protected repos from `config/repos.yaml`, plus upstream fork exclusion checks |
| test_app_health.py | app_health | GitHub App webhook delivery logs |
| test_security_review.py | security_review | Static fork-guard checks for privileged review workflow |
| test_cliproxy_health.py | cliproxy_health | Optional CLIProxyAPI models list |
| test_private_canary.py | private_canary | Private repo mutation guard |
| test_go_cli.py | — | Go scripts return valid JSON |

## SAFETY MECHANISMS

`guard_mutation()` in `github_mutation.py` aborts any write operation outside `automation-e2e-private` (the only remaining canary). Tests that mutate repos skip if the target is not the designated canary.

## ENVIRONMENT VARIABLES

| Variable | Fallback | Purpose |
| --- | --- | --- |
| `E2E_GITHUB_TOKEN` | `GH_TOKEN` | GitHub API and `gh` CLI authentication |
| `E2E_CANARY_PRIVATE_REPO` | `jclee941/automation-e2e-private` | Private canary for mutation tests |
| `E2E_CLIPROXY_API_KEY` | `CLIPROXY_API_KEY` | Optional CLIProxyAPI connectivity checks |

## COMMANDS

```bash
pytest tests/e2e_live -v              # full suite
pytest tests/e2e_live -m readonly     # safe, no side effects
pytest tests/e2e_live -m private_canary       # mutation tests only
pytest tests/e2e_live -m "not private_canary" # exclude mutations
```
