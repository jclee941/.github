# jclee_bot/checks - App-owned Checks API modules

## OVERVIEW

Pure check implementations for App-published GitHub Check Runs. `jclee_bot.app`
collects PR context and `jclee_bot.dispatch` calls these modules; this directory
does not own installation-token lookup, checkout, or Check Run publication.

## WHERE TO LOOK

| Task | File | Notes |
|------|------|-------|
| Shared result contract | `__init__.py` | `CheckResult`, valid conclusions, module re-exports |
| PR title, size, sensitive paths | `pr_metadata.py` | Required branch-protection context |
| Secret scanning | `secret_scan.py` | Maps `gitleaks` JSON into a check result |
| Workflow linting | `actionlint_check.py` | Runs only for changed `.github/workflows/**` files |
| Documentation freshness/private IP policy | `docs_policy.py` | Advisory check, not required by branch protection |
| Dispatcher wiring | `../dispatch.py` | Adds/removes checks from the App check set |
| Publishing semantics | `../app.py`, `../github_checks.py` | Converts required-tool skips to failure when needed |
| Tests | `../../tests/unittest/test_jclee_bot_checks.py` | Mapper and pure-check behavior |

## CHECK NAMES

| Module | Check name | Protection |
|--------|------------|------------|
| `pr_metadata.py` | `jclee-bot / pr-metadata` | Required |
| `secret_scan.py` | `jclee-bot / secret-scan` | Required |
| `actionlint_check.py` | `jclee-bot / actionlint` | Required |
| `docs_policy.py` | `jclee-bot / docs-policy` | Advisory |

## CONVENTIONS

- Keep check modules pure where possible: input data in, `CheckResult` out.
- Use only `success`, `failure`, or `neutral`; GitHub API publishing is handled outside this directory.
- A missing local binary may map to `neutral` inside a pure mapper, but required App checks must fail closed before branch protection sees them.
- Keep summaries safe for public PR output: no installation tokens, webhook secrets, credentialed URLs, or raw secret values.
- If a new required check is added here, update `dispatch.py`, branch-protection/rulesets Go payloads, docs, and tests together.

## ANTI-PATTERNS

- Do not call GitHub APIs or mutate repo state from a check module.
- Do not report `success` when the check did not inspect real PR content.
- Do not expand sensitive-file exemptions without a specific bot-owned branch case.
- Do not make `docs-policy` branch-protection-required without updating the Go rollout tools and docs.
