# jclee_bot - GitHub App checks runner

## OVERVIEW

Fork-owned FastAPI extension that reuses the upstream `pr_agent` app and adds App-owned Checks API
runs for PR metadata, secret scanning, workflow linting, docs policy, and issue lifecycle events.

## STRUCTURE

```text
jclee_bot/
├── app.py                    # webhook tee, standalone checks endpoint, PR checkout/context fetch
├── dispatch.py               # maps pull_request payloads to checks
├── github_checks.py          # installation token + Checks API client
├── issue_management.py       # issue auto-label + stale-label removal on App webhooks
└── checks/
    ├── pr_metadata.py        # title, size, sensitive-file policy
    ├── secret_scan.py        # gitleaks result mapping + invocation
    ├── actionlint_check.py   # workflow lint result mapping + invocation
    └── docs_policy.py        # markdown private-IP and docs freshness policy
```

## WHERE TO LOOK

| Task | File |
|------|------|
| Add or change a check | `checks/`, then `dispatch.py` |
| Webhook signature / tee behavior | `app.py` |
| GitHub installation token and check-run API | `github_checks.py` |
| Issue auto-label or stale-label removal | `issue_management.py`, then `app.py` |
| Unit tests | `tests/unittest/test_jclee_bot_app.py`, `tests/unittest/test_jclee_bot_checks.py` |
| Mocked e2e surface | `tests/e2e/test_webhooks.py`, `tests/e2e/test_health.py` |

## CONVENTIONS

- Check names are externally visible and branch-protection-sensitive:
  `jclee-bot / pr-metadata`, `jclee-bot / secret-scan`, `jclee-bot / actionlint`.
- Missing PR context must produce `neutral`, not misleading `success`, for checks that need changed files or checkout.
- Issue opened auto-labeling and stale-label removal are App-owned; do not restore downstream
  `18_issue-management.yml` or `43_reusable-issue-management.yml`.
- `app.py` must not break upstream `/api/v1/github_webhooks`, `/health`, `/ready`, or `/metrics` routes.
- External tools (`gitleaks`, `actionlint`) degrade to neutral when unavailable; unit-test the pure result mappers.
- Webhook handling must acknowledge promptly; blocking check work stays off the request path.

## ANTI-PATTERNS

- Do not import this package from upstream `pr_agent/`; ownership points one way only.
- Do not let a failed check-report call abort other checks.
- Do not report success for a scan that did not inspect real PR content.
- Do not log installation tokens, webhook secrets, PR checkout URLs with credentials, or raw secret findings.
