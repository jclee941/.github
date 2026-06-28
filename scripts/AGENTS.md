# scripts/AGENTS.md

## OVERVIEW

Go automation tools for the canonical `config/repos.yaml` inventory: merged branch cleanup,
branch protection, rulesets, secret sync, repo review, and naming validation. The inventory currently
has 16 entries; `jclee-bot` is the source repo and `pr-agent` is excluded from rollout-style automation.

## STRUCTURE

```
scripts/
├── go.mod                               # module github.com/jclee941/jclee-bot/scripts
├── cmd/
│   ├── branch-protection/main.go        # auto-merge + branch protection rules
│   ├── branch-cleanup/main.go           # delete branches merged into managed default branches
│   ├── repo-review/main.go              # batch repo review
│   ├── rulesets-manager/main.go         # GitHub Rulesets list/apply/delete
│   ├── sync-secrets/main.go             # sync CLIPROXY_API_KEY and GH_PAT across repos
│   └── validate-naming/main.go          # naming + orphan-workflow + readme-inventory validators
├── internal/
│   └── repos/
│       └── repos.go                     # shared repo inventory and filtering logic
├── cmd/branch-protection/main_test.go   # table-driven tests (16 cases)
├── cmd/validate-naming/*_test.go        # naming/security/readme-inventory guard tests
├── repo_review.py                       # legacy Python helper
├── pr_review_runner.py                  # Python PR review invocation helper
└── generate_readme.py                   # README auto-generation helper
```

## WHERE TO LOOK

| Task | File |
|------|------|
| Delete merged stale branches | `cmd/branch-cleanup/main.go` |
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

# Merged branch cleanup
go run ./cmd/branch-cleanup --dry-run
go run ./cmd/branch-cleanup              # delete branches already merged into default branches

# GitHub Rulesets
go run ./cmd/rulesets-manager --dry-run
go run ./cmd/rulesets-manager --mode list

# Secret sync; both env vars are required and are written to each target repo
CLIPROXY_API_KEY=... GH_PAT=... go run ./cmd/sync-secrets --dry-run
CLIPROXY_API_KEY=... GH_PAT=... go run ./cmd/sync-secrets

# Naming + orphan-workflow + readme-inventory validation
go run ./cmd/validate-naming
go run ./cmd/validate-naming --fix       # auto-fix where supported

# Batch repo review
go run ./cmd/repo-review --dry-run

# Tests
go test ./...
```

## ANTI-PATTERNS

- Never run the legacy root-level binaries (`./branch-protection`, `./sync-secrets`, `./repo-review`). Use `go run ./cmd/<name>` instead.
- Never hardcode secrets or API keys in `.go` source files.
- Never run `go run` from the repo root. Always `cd scripts` first.
- Never apply `branch-protection`, `rulesets-manager`, `branch-cleanup`, `sync-secrets`, or `repo-review` to live repos before a dry-run or list pass has shown the target inventory.
