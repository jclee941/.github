# scripts/AGENTS.md

## OVERVIEW

Go automation tools for the canonical `config/repos.yaml` inventory: branch protection, rulesets,
secret sync, repo review, naming validation. The inventory currently has 16 entries, with `.github`
as the source repo and `pr-agent` excluded from rollout-style automation.

## STRUCTURE

```
scripts/
├── go.mod                               # module github.com/jclee941/.github/scripts
├── cmd/
│   ├── branch-protection/main.go        # auto-merge + branch protection rules
│   ├── repo-review/main.go              # batch repo review
│   ├── rulesets-manager/main.go         # GitHub Rulesets list/apply/delete
│   ├── sync-secrets/main.go             # sync CLIPROXY_API_KEY across repos
│   └── validate-naming/main.go          # naming + orphan-workflow + readme-inventory validators
├── internal/
│   └── repos/
│       └── repos.go                     # shared repo inventory and filtering logic
├── cmd/branch-protection/main_test.go   # table-driven tests (16 cases)
├── cmd/validate-naming/main_test.go     # table-driven tests for naming/orphan/readme-inventory
├── repo_review.py                       # legacy Python helper
├── pr_review_runner.py                  # Python PR review invocation helper
└── generate_readme.py                   # README auto-generation helper
```

## WHERE TO LOOK

| Task | File |
|------|------|
| Apply branch protection + auto-merge | `cmd/branch-protection/main.go` |
| Manage GitHub Rulesets (list/apply/delete) | `cmd/rulesets-manager/main.go` |
| Sync shared secrets across repos | `cmd/sync-secrets/main.go` |
| Batch repository review | `cmd/repo-review/main.go` |
| Enforce naming conventions | `cmd/validate-naming/main.go` |

## COMMANDS

```bash
cd scripts

# Branch protection
go run ./cmd/branch-protection --dry-run
go run ./cmd/branch-protection           # apply to eligible repos from config/repos.yaml

# GitHub Rulesets
go run ./cmd/rulesets-manager --dry-run

# Secret sync
CLIPROXY_API_KEY=... go run ./cmd/sync-secrets

# Naming + orphan-workflow + readme-inventory validation
go run ./cmd/validate-naming
go run ./cmd/validate-naming --fix       # auto-fix where supported

# Tests
go test ./...
```

## ANTI-PATTERNS

- Never run the legacy root-level binaries (`./branch-protection`, `./sync-secrets`, `./repo-review`). Use `go run ./cmd/<name>` instead.
- Never hardcode secrets or API keys in `.go` source files.
- Never run `go run` from the repo root. Always `cd scripts` first.
