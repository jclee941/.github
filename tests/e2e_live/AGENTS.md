# tests/e2e_live — Live E2E Test Suite

## OVERVIEW

30 live tests against the real jclee941/.github automation stack via GitHub API. Readonly inspections and controlled mutations on canary repos.

## STRUCTURE

```
tests/e2e_live/
├── conftest.py                  # Shared fixtures, GitHub client, guard_mutation()
├── test_fleet_health.py         # Repo automation state checks
├── test_canary_pr.py            # Canary PR open/close lifecycle
├── test_bot_review.py           # jclee-bot review smoke test
├── test_security_review.py      # Security review label path
├── test_mergeability.py         # Branch protection + merge rules
├── test_deploy_path.py          # Workflow deploy propagation
├── test_app_health.py           # Bot app webhook health
├── test_cliproxy_health.py      # CLIProxy API reachability
├── test_private_canary.py       # Private repo canary tests
└── test_go_cli.py               # Go helper scripts validation
```

## WHERE TO LOOK

| Test file | Marker | What it checks |
|-----------|--------|----------------|
| test_fleet_health.py | readonly | Automation state across all 16 repos |
| test_canary_pr.py | canary | PR open, edit, close on automation-e2e-public |
| test_bot_review.py | bot_review | jclee-bot posts a review comment |
| test_security_review.py | security_review | Security label triggers deep review |
| test_mergeability.py | mergeability | Required checks block/allow merge |
| test_deploy_path.py | deploy_path | Workflow files propagate downstream |
| test_app_health.py | app_health | GitHub App webhook delivery logs |
| test_cliproxy_health.py | cliproxy_health | CLIProxy API models list |
| test_private_canary.py | private_canary | Private repo mutation guard |
| test_go_cli.py | — | Go scripts return valid JSON |

## SAFETY MECHANISMS

`guard_mutation()` in `conftest.py` aborts any write operation outside `automation-e2e-public` and `automation-e2e-private`. Tests that mutate repos skip if the target is not a designated canary.

## COMMANDS

```bash
pytest tests/e2e_live -v              # full suite
pytest tests/e2e_live -m readonly     # safe, no side effects
pytest tests/e2e_live -m canary       # mutation tests only
pytest tests/e2e_live -m "not canary" # exclude mutations
```
