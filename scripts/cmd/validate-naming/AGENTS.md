# validate-naming - cross-file automation invariants

## OVERVIEW

Go validator for workflow names, issue-template names, required App check contexts, workflow security patterns, README automation-surface claims, and managed-repo inventory derivation. This command is part of the `90_sanity.yml` gate.

## WHERE TO LOOK

| Task | File |
|------|------|
| Validation registry | `main.go` |
| Shared path discovery | `paths.go` |
| Workflow naming and inventory | `workflow_jobs.go`, `workflow_inventory_test.go` |
| Workflow security and dispatch input guards | `workflow_security.go`, `workflow_security_test.go` |
| Active workflow mutation policy | `active_workflow_guards.go`, `active_workflow_mutation_test.go` |
| README/App automation surface | `readme_workflow_inventory.go`, `readme_workflow_inventory_test.go` |
| Required App checks in docs | `current_required_checks_docs.go`, `current_required_checks_docs_test.go` |
| Go inventory derivation | `go_managed_inventory.go`, `go_managed_inventory_test.go` |

## CONVENTIONS

- Run from the scripts module: `(cd scripts && go run ./cmd/validate-naming)`.
- Add each new invariant to the `validations` slice in `main.go` and cover it with table-driven tests.
- The canonical managed repo list comes from `config/repos.yaml`; validators should reject hardcoded managed-repo inventories in workflows or Go commands.
- Required branch-protection contexts are exactly `jclee-bot / pr-metadata`, `jclee-bot / secret-scan`, and `jclee-bot / actionlint`.
- README checks should enforce the App automation surface, not resurrect a row-by-row workflow inventory.

## ANTI-PATTERNS

- Do not make validators depend on network access, `gh`, live repo state, or generated files outside the worktree.
- Do not add broad text rewrites to `--fix` unless the transformation is deterministic and covered by tests.
- Do not silence a validation by weakening the expected policy; update the source policy only when the App/GitOps operating model really changes.
