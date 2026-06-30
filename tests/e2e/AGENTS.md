# tests/e2e - mocked FastAPI and webhook tests

## OVERVIEW

Mocked integration tests for the local FastAPI/webhook surface. These drive
`jclee_bot.app` through `TestClient` while patching the review-engine GitHub
provider, so they are broader than unit tests but must remain offline.

## WHERE TO LOOK

| Task | File | Notes |
|------|------|-------|
| Shared fixtures and provider patching | `conftest.py` | Sets Dynaconf env keys and mocks Git provider calls |
| Health/ready/metrics routes | `test_health.py` | Exercises `/health`, `/ready`, `/metrics`, `/` |
| GitHub webhook accept path | `test_webhooks.py` | PR, issue_comment, bot-user, marketplace payloads |
| App implementation | `../../jclee_bot/app.py` | Imported by the `test_client` fixture |
| Unit-level check detail | `../unittest/` | Use for focused branch/check behavior |
| Live GitHub behavior | `../e2e_live/` | Use only when real API state is required |

## COMMANDS

```bash
make test-e2e
.venv/bin/python -m pytest tests/e2e -q
```

## CONVENTIONS

- Patch `get_git_provider_with_context` at every import path used by the app/review-engine server, as `conftest.py` does.
- Keep Dynaconf-style env keys literal, for example `OPENAI.KEY`, `OPENAI.API_BASE`, and `GITHUB.WEBHOOK_SECRET`.
- Assert request acceptance and route shape here; detailed check logic belongs in `tests/unittest/`.
- Keep payloads representative but minimal. Avoid copying live GitHub responses wholesale.

## ANTI-PATTERNS

- Do not require `GH_TOKEN`, `E2E_GITHUB_TOKEN`, CLIProxyAPI, or network access.
- Do not create branches, PRs, labels, issues, or other GitHub state here.
- Do not bypass webhook/auth behavior by changing production defaults; patch env/config in fixtures.
