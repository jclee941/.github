# jclee_bot - GitHub App checks runner

## OVERVIEW

First-party FastAPI extension that reuses the `jclee_bot.review_engine` app and adds App-owned Checks API
runs for PR metadata, secret scanning, workflow linting, docs policy, GitOps automation, README jobs,
CI-failure issue cleanup, and issue lifecycle events.

## STRUCTURE

```text
jclee_bot/
├── app.py                    # webhook tee, standalone checks endpoint, PR checkout/context fetch
├── dispatch.py               # maps pull_request payloads to checks
├── github_checks.py          # installation token + Checks API client
├── gitops_automation.py      # branch-to-PR and protected-flow automation
├── pr_auto_merge.py          # bot PR eligibility and auto-merge helpers
├── issue_management.py       # issue auto-label + stale-label removal on App webhooks
├── issue_maintenance.py      # App-owned stale issue sweep + issue stats
├── readme_automation.py      # App-owned README job orchestration
├── readme_runner.py          # README generation runner and sanitization checks
├── workflow_issue_automation.py, workflow_current_sweep.py, workflow_legacy_sweep.py
├── downstream_ci_inventory.py, downstream_ci_runs.py, downstream_ci_sweep.py
│                              # CI-failure issue creation/recovery/sweeps
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
| GitOps branch/PR automation | `gitops_automation.py`, `pr_auto_merge.py` |
| Issue auto-label or stale-label removal | `issue_management.py`, then `app.py` |
| Stale issue sweep or issue stats | `issue_maintenance.py`, then `app.py` |
| README automation jobs | `readme_automation.py`, `readme_jobs.py`, `readme_job_worker.py`, `readme_runner.py` |
| CI-failure issue automation | `workflow_issue_automation.py`, `workflow_current_sweep.py`, `workflow_legacy_sweep.py`, `downstream_ci_*` |
| Unit tests | `tests/unittest/test_jclee_bot_app.py`, `tests/unittest/test_jclee_bot_checks.py` |
| Mocked e2e surface | `tests/e2e/test_webhooks.py`, `tests/e2e/test_health.py` |

## CONVENTIONS

- Check names are externally visible and branch-protection-sensitive:
  `jclee-bot / pr-metadata`, `jclee-bot / secret-scan`, `jclee-bot / actionlint`.
  `jclee-bot / docs-policy` is also published by the App, but is advisory rather
  than branch-protection-required.
- Missing PR context must make required checks fail closed, not publish a skipped or misleading `success`
  conclusion. A skipped conclusion is allowed only for genuinely not-applicable cases such as actionlint
  with no workflow changes.
- Issue opened auto-labeling, stale-label removal, stale issue sweep, issue stats, and CI-failure recovery are App-owned;
  do not restore deleted downstream issue-management or CI-failure workflow callers.
- `app.py` must not break the `/api/v1/github_webhooks`, `/health`, `/ready`, or `/metrics` routes exposed by the review engine.
- External tools (`gitleaks`, `actionlint`) may map to a skipped advisory result in pure mappers, but required
  App check publishing must convert unavailable-tool skips to failure.
- Webhook handling must acknowledge promptly; blocking check work stays off the request path.
- App API endpoints must authenticate with the configured bearer token before
  queuing README, issue-command, or maintenance jobs.
- Generated README content must be sanitized before PR creation: private IPs,
  LXC identifiers, and invented repository URLs are not acceptable output.

## ANTI-PATTERNS

- Do not import `jclee_bot.app` from the review engine (`jclee_bot.review_engine`); the review engine is a stable contract surface and the App is the integration layer. Ownership points one way only.
- Do not let a failed check-report call abort other checks.
- Do not report success for a scan that did not inspect real PR content.
- Do not log installation tokens, webhook secrets, PR checkout URLs with credentials, or raw secret findings.
- Do not move GitOps, README, or CI-failure mutation logic back into downstream
  workflows. CI-failure automation is handled by the App webhook path, not a workflow caller.
