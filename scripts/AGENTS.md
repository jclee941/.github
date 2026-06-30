# scripts/AGENTS.md

## OVERVIEW

Go automation tools for the canonical `config/repos.yaml` inventory: merged branch cleanup,
branch-protection diagnostics, rulesets diagnostics, secret sync, repo review, naming validation,
README generation helpers, and a file-based suggestion/regression feedback engine. `jclee-bot`
is the source repo; production repository standardization is owned by the App endpoint, not by
workflow-side Go execution.

## STRUCTURE

```
scripts/
├── go.mod                               # module github.com/jclee941/jclee-bot/scripts
├── cmd/
│   ├── branch-protection/main.go        # branch protection dry-run diagnostics
│   ├── branch-cleanup/main.go           # delete branches merged into managed default branches
│   ├── repo-standardization/main.go     # legacy downstream documentation diagnostics
│   ├── repo-review/main.go              # batch repo review
│   ├── rulesets-manager/main.go         # GitHub Rulesets list/dry-run diagnostics
│   ├── sync-secrets/main.go             # sync CLIPROXY_API_KEY and GH_PAT across repos
│   └── validate-naming/main.go          # naming + orphan-workflow + readme-inventory validators
├── internal/
│   └── repos/
│       └── repos.go                     # shared repo inventory and filtering logic
├── cmd/branch-protection/main_test.go   # table-driven tests (16 cases)
├── cmd/validate-naming/*_test.go        # naming/security/readme-inventory guard tests
├── repo_review.py                       # legacy Python helper
├── pr_review_runner.py                  # Python PR review invocation helper
├── generate_readme.py                   # README auto-generation helper
└── evolution/                           # JSON-in/out feedback engine with SQLite storage
```

## WHERE TO LOOK

| Task | File |
|------|------|
| Delete merged stale branches | `cmd/branch-cleanup/main.go` |
| Inspect branch protection payloads | `cmd/branch-protection/main.go` |
| Inspect GitHub Rulesets payloads | `cmd/rulesets-manager/main.go` |
| Sync shared secrets across repos | `cmd/sync-secrets/main.go` |
| Validate downstream doc standardization | `cmd/repo-standardization/main.go` |
| Batch repository review | `cmd/repo-review/main.go` |
| Enforce naming conventions | `cmd/validate-naming/main.go` |
| README generation prompts/helpers | `generate_readme.py`, `generate_readme_prompts.py` |
| Suggestion/regression feedback engine | `evolution/cli.py`, `evolution/facade.py`, `evolution/storage.py` |
| CI gate for naming/inventory | `cmd/validate-naming/main.go`, `.github/workflows/90_sanity.yml` |

## COMMANDS

```bash
cd scripts
go test ./...
go run ./cmd/branch-protection --dry-run
go run ./cmd/branch-cleanup --dry-run
go run ./cmd/branch-cleanup              # delete branches already merged into default branches
go run ./cmd/rulesets-manager --dry-run
go run ./cmd/rulesets-manager --mode list
go run ./cmd/repo-standardization --dry-run
CLIPROXY_API_KEY=... GH_PAT=... go run ./cmd/sync-secrets --dry-run
go run ./cmd/validate-naming
go run ./cmd/validate-naming --fix       # auto-fix where supported
go run ./cmd/repo-review --dry-run
cd ..
.venv/bin/python -m scripts.evolution.cli init-db --db .cache/evolution.sqlite
```

## CONVENTIONS

- `scripts/evolution/` is intentionally file-based JSON in/out so it can be tested without GitHub or LLM access.
- `scripts/evolution/storage.py` owns the SQLite schema and migration behavior; keep schema changes deterministic and covered by focused tests.
- Python helper modules under `scripts/` are repo-local utilities; `pyproject.toml` only packages `jclee_bot*`, so do not rely on them as installed package entry points.
- `validate-naming` is part of the source-repo sanity gate; keep its README/workflow inventory expectations aligned with `.github/workflows/` and `README.md`.

## ANTI-PATTERNS

- Never run the legacy root-level binaries (`./branch-protection`, `./sync-secrets`, `./repo-review`). Use `go run ./cmd/<name>` instead.
- Never add workflow-side `go run ./cmd/branch-protection`, `go run ./cmd/rulesets-manager`, or `go run ./cmd/repo-standardization` as the production rollout path. Use the App endpoint `/api/v1/repo_standardization`.
- Never hardcode secrets or API keys in `.go` source files.
- Never run `go run` from the repo root. Always `cd scripts` first.
- Never apply `branch-protection`, `rulesets-manager`, `branch-cleanup`, `sync-secrets`, or `repo-review` to live repos before a dry-run or list pass has shown the target inventory.
- Never feed `scripts/evolution` live GitHub or LLM calls directly; adapt external outputs to JSON and pass them through the CLI or facade.
