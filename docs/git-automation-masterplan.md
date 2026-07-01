# Git Automation Masterplan

> Status: current implementation plan for the App-owned git automation surface.

## Operating Model

`jclee-bot` uses the GitHub App path as the production source of truth. The
fleet automation does not redeploy per-repository PR-review workflows as the
primary rollout mechanism.

- Managed repositories come from `config/repos.yaml`.
- Branch protection and rulesets require App-owned checks:
  - `jclee-bot / pr-metadata`
  - `jclee-bot / secret-scan`
  - `jclee-bot / actionlint`
- Protected managed repositories target the default branch recorded by the
  inventory and repo policy helpers.
- Mutating rollout commands must support dry-run evidence before they write to
  GitHub.

## Automation Map

| Surface | Source | Operator proof |
| --- | --- | --- |
| Branch-to-PR GitOps | `jclee_bot/gitops_automation.py` | Unit tests in `tests/unittest/test_jclee_bot_gitops_automation.py` |
| Bot PR auto-merge | `jclee_bot/pr_auto_merge.py` | App event unit coverage and live PR check state |
| Merged branch cleanup | `scripts/cmd/branch-cleanup` | `(cd scripts && go run ./cmd/branch-cleanup --dry-run)` |
| Repository standardization | `jclee_bot/repo_standardization_endpoint.py` | App endpoint `/api/v1/repo_standardization`; App runtime health and endpoint tests |
| Branch protection diagnostics | `scripts/cmd/branch-protection` | `(cd scripts && go run ./cmd/branch-protection --dry-run)` |
| Rulesets diagnostics | `scripts/cmd/rulesets-manager` | `(cd scripts && go run ./cmd/rulesets-manager --dry-run)` |
| Repo review batch | `scripts/cmd/repo-review` | `(cd scripts && go run ./cmd/repo-review --normalize-repos)` |
| CI failure issue lifecycle | `jclee_bot/workflow_issue_automation.py` and `jclee_bot/workflow_current_sweep.py` | Unit tests in `tests/unittest/test_jclee_bot_workflow_issue_*.py` |
| README automation | `jclee_bot/readme_automation.py` and `jclee_bot/readme_runner.py` | README tests plus live App job evidence |

## Implementation Waves

1. Keep the inventory canonical.
   - Read managed repo names from `config/repos.yaml`.
   - Do not hardcode repository counts or default branches in docs, workflows,
     or tests.
   - Normalize explicit repo lists before using them in mutation-capable tools.

2. Keep policy rollout observable before mutation.
   - Production branch protection and Rulesets rollout must stay App-owned
     through `/api/v1/repo_standardization`.
   - `branch-cleanup`, `branch-protection`, and `rulesets-manager` must retain
     dry-run coverage as diagnostics and compatibility checks.
   - Required check contexts must remain aligned between branch protection,
     rulesets, tests, and docs.
   - Broad workflow mutations stay behind explicit workflow dispatch inputs and
     dry-run defaults.

3. Keep issue cleanup conservative.
   - Current CI-failure issues close only after a matching successful run for
     the same workflow file, default branch, and SHA.
   - Issues are kept when the workflow name cannot be resolved.
   - Issues are deferred while an active run for the same SHA is still queued or
     running.

4. Keep live verification cheap and read-only by default.
   - Local unit tests cover parser and policy payload behavior.
   - `tests/e2e_live/test_go_cli.py` smokes the local diagnostic Go CLIs without
     GitHub credentials by injecting a fake `gh` binary where possible.
   - Live fleet checks are limited to readonly health and branch-protection
     assertions unless a mutation test is explicitly requested.

## Verification Matrix

Use this sequence when changing git automation:

```bash
(cd scripts && go test ./cmd/branch-cleanup ./cmd/branch-protection ./cmd/rulesets-manager ./cmd/repo-review)
pytest tests/unittest/test_jclee_bot_gitops_automation.py \
  tests/unittest/test_jclee_bot_repo_standardization.py \
  tests/unittest/test_repo_standardization_workflow.py \
  tests/unittest/test_jclee_bot_workflow_issue_automation.py \
  tests/unittest/test_jclee_bot_workflow_issue_current_sweep.py \
  tests/unittest/test_jclee_bot_workflow_issue_event_recovery.py
pytest tests/e2e_live/test_go_cli.py -v
pytest tests/e2e_live/test_fleet_health.py -v -k branch_protection
(cd scripts && go run ./cmd/branch-cleanup --dry-run)
(cd scripts && go run ./cmd/branch-protection --dry-run)
(cd scripts && go run ./cmd/rulesets-manager --dry-run)
(cd scripts && go run ./cmd/repo-review --normalize-repos)
gh issue list --repo jclee941/jclee-bot --state open --json number --jq 'length'
gh pr list --repo jclee941/jclee-bot --state open --json number --jq 'length'
```

For production proof, call the deployed App standardization endpoint with
`dry_run=true` and confirm the response summary is not failed. The retired
repository-standardization workflow must not be restored; the App owns this
automation surface directly.

## Current Guardrail

The weakest verified policy surfaces were the boundaries between the App-owned
standardization endpoint and the older Go diagnostics. The App endpoint owns
repository standardization directly, while the Go CLI smoke suite keeps the
local diagnostic tools from drifting.

The riskiest runtime surface is current CI-failure issue cleanup. It must stay
biased toward preserving or deferring issues when workflow identity or run state
is ambiguous.
