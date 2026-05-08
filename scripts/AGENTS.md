# scripts/AGENTS.md

## OVERVIEW

Go automation tools for managing 16 jclee941 repos. Branch protection, workflow deploy, secret sync, repo review.

## STRUCTURE

```
scripts/
├── go.mod                               # module github.com/jclee941/dotgithub-scripts
├── cmd/
│   ├── branch-protection/main.go        # auto-merge + branch protection rules
│   ├── deploy-to-repos/main.go          # push workflows to downstream repos
│   ├── repo-review/main.go              # batch repo review
│   └── sync-secrets/main.go             # sync CLIPROXY_API_KEY across repos
├── internal/
│   └── repos/
│       └── repos.go                     # shared repo inventory and filtering logic
├── cmd/deploy-to-repos/main_test.go
├── cmd/branch-protection/main_test.go
├── repo_review.py                       # legacy Python helper
├── pr_review_runner.py                  # Python PR review invocation helper
├── generate_readme.py                   # README auto-generation helper
└── branch-protection, deploy-to-repos,  # legacy binaries (do not use)
    repo-review, sync-secrets
```

## WHERE TO LOOK

| Task | File |
|------|------|
| Deploy workflows to downstream repos | `cmd/deploy-to-repos/main.go` |
| Apply branch protection + auto-merge | `cmd/branch-protection/main.go` |
| Sync shared secrets across repos | `cmd/sync-secrets/main.go` |
| Batch repository review | `cmd/repo-review/main.go` |

## COMMANDS

```bash
cd scripts

# Deploy workflows
go run ./cmd/deploy-to-repos --dry-run              # preview all
go run ./cmd/deploy-to-repos --repos=resume         # canary one repo
go run ./cmd/deploy-to-repos                        # all 11 downstream public repos

# Branch protection
go run ./cmd/branch-protection --dry-run
go run ./cmd/branch-protection                      # apply to all 12 public repos

# Secret sync
CLIPROXY_API_KEY=... go run ./cmd/sync-secrets

# Tests
go test ./...
```

## ANTI-PATTERNS

- Never run the legacy root-level binaries (`./branch-protection`, `./sync-secrets`, `./repo-review`). Use `go run ./cmd/<name>` instead.
- Never hardcode secrets or API keys in `.go` source files.
- Never run `go run` from the repo root. Always `cd scripts` first.
