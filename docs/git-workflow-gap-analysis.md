# Git Workflow Gap Analysis

> Status: superseded summary. The old per-repository workflow rollout analysis is historical and should not be used as current implementation guidance.

## Current Operating Model

Production Git flow automation follows the GitHub App-centered operating model:

- `jclee-bot` posts Checks API runs for PR metadata, secret scanning, and workflow linting.
- Branch protection and rulesets require the App-owned contexts.
- Protected managed repositories target `master`.
- The `github-bot` source repository itself is excluded from protected fleet rollout and keeps its own default branch.
- `config/repos.yaml` is the canonical inventory for scripts and workflow loops.

## Current Required Contexts

- `jclee-bot / pr-metadata`
- `jclee-bot / secret-scan`
- `jclee-bot / actionlint`

Historical workflow context names must not be reintroduced as required merge gates.

## Remaining Gap Classes

| Class | Current guard |
| --- | --- |
| Hardcoded repo inventory | `repoinventory` helpers and `validate-naming` checks |
| Stale required check names | `currentRequiredChecksDocs` and branch-protection/ruleset tests |
| Unsafe broad mutation workflows | active workflow guard tests |
| Dry-run bypasses | active workflow guard tests |
| Workflow inventory drift | README automation and `validate-naming` |

## Verification

Use the current verification commands instead of replaying historical rollout steps:

```bash
(cd scripts && go test ./...)
(cd scripts && go run ./cmd/validate-naming)
(cd scripts && go run ./cmd/branch-protection --dry-run)
(cd scripts && go run ./cmd/rulesets-manager --dry-run)
```
