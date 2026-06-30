# tests/unittest - mocked Python unit suite

## OVERVIEW

Large mocked Python suite covering the first-party App layer, absorbed review engine behavior,
README automation, issue/workflow automation, providers, and `scripts/evolution`.

## WHERE TO LOOK

| Task | File pattern |
|------|--------------|
| App routes, webhook tee, health, metrics | `test_jclee_bot_app*.py`, `test_jclee_bot_native_health.py` |
| App checks and reporting | `test_jclee_bot_checks.py`, `test_jclee_bot_app_checks_reporting.py` |
| GitOps and auto-merge | `test_jclee_bot_gitops_automation.py`, `test_jclee_bot_app_gitops.py`, `test_jclee_bot_pr_auto_merge.py` |
| Issue automation | `test_jclee_bot_issue_*.py`, `test_jclee_bot_pr_maintenance.py` |
| README automation | `test_jclee_bot_readme_*.py`, `test_generate_readme*.py` |
| CI-failure issue automation | `test_jclee_bot_workflow_issue_*.py`, `test_jclee_bot_workflow_legacy_sweep.py` |
| Evolution engine | `test_evolution_*.py` |
| Review-engine providers/tools | `test_github_provider_*.py`, `test_gitlab_provider.py`, `test_bitbucket_provider.py`, `test_pr_*.py` |
| Runtime/config safety | `test_python_runtime_policy.py`, `test_litellm_*.py`, `test_secret_*.py`, `test_config_loader_secrets.py` |

## COMMANDS

```bash
make test-unit
.venv/bin/python -m pytest tests/unittest/test_jclee_bot_checks.py -v
.venv/bin/python -m pytest tests/unittest/test_evolution_facade.py -v
```

## CONVENTIONS

- Keep these tests offline and deterministic: mock GitHub, CLIProxyAPI, subprocesses, filesystem mutation, and provider clients unless the parent test policy explicitly routes the case to `tests/e2e_live/`.
- Match the file family of the behavior under change instead of adding broad catch-all tests.
- Use temporary directories for README/evolution/storage tests; do not write durable state under the repo root except test-owned temp paths.
- Existing Ruff ignores allow long inherited assertions here, but new tests should still favor readable fixtures over oversized inline payloads.
- `scripts/evolution` tests should preserve JSON-in/out boundaries and avoid direct network or LLM calls.

## ANTI-PATTERNS

- Do not require `GH_TOKEN`, `E2E_GITHUB_TOKEN`, CLIProxyAPI availability, or homelab services for unit tests.
- Do not assert on raw secrets, installation tokens, or credentialed URLs.
- Do not bypass App auth checks by changing production defaults; patch config/env in the test.
