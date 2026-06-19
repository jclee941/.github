# .github - workflow and metadata surface

## OVERVIEW

GitHub-native automation for the source repo: workflows, local composite actions, CODEOWNERS,
Dependabot/Renovate config, issue templates, and PR template.

## STRUCTURE

```text
.github/
├── workflows/                  # numbered workflow stages, all flat
├── actions/
│   ├── notify-on-failure/       # shared issue notification action
│   ├── setup-build-cache/       # self-hosted runner cache/HOME handling
│   └── setup-python-compatible/ # GitHub-hosted vs self-hosted Python bootstrap
├── ISSUE_TEMPLATE/              # numbered issue forms
├── scripts/                     # small workflow helper scripts
├── CODEOWNERS
├── dependabot.yml
├── release-drafter.yml
└── PULL_REQUEST_TEMPLATE.md
```

## WHERE TO LOOK

| Task | File |
|------|------|
| Main CI gate | `workflows/90_sanity.yml` |
| PR review workflow for this repo | `workflows/10_pr-review.yml` |
| Deep security review | `workflows/11_security-pr-review.yml` |
| App image build/push | `workflows/36_build-and-push-app.yml` |
| Live e2e workflow | `workflows/39_e2e-live.yml` |
| App-owned README automation | `jclee_bot/readme_automation.py`, `jclee_bot/readme_runner.py` |
| App docs policy check | `jclee_bot/checks/docs_policy.py` |
| Failure issue creation | `actions/notify-on-failure/action.yml` |

## CONVENTIONS

- Workflow filenames are `NN_name.yml`, `reusable-*.yml`, or `_*.yml`; validate with
  `(cd scripts && go run ./cmd/validate-naming)`.
- Third-party actions should be pinned to immutable SHAs unless the repo explicitly allows semver.
- `step-security/harden-runner@v2` is the standard workflow hardening step.
- Self-hosted workflows are deliberate for homelab-dependent paths such as App image build, ELK setup,
  health checks, and NAS cache pruning.
- PR review workflows use literal-dot Dynaconf env keys such as `OPENAI.KEY`,
  `OPENAI.API_BASE`, `CONFIG.MODEL`, and `CONFIG.FALLBACK_MODELS`; keep
  `GITHUB__USER_TOKEN` as the token exception.

## ANTI-PATTERNS

- Do not add workflow subdirectories; GitHub ignores nested workflow files.
- Do not use org endpoints like `orgs/jclee941` for this user-owned account.
- Do not add `notify-on-failure` without a default-path checkout first.
- Do not deploy `_*.yml` local-only workflows downstream.
- Do not duplicate App check behavior with old per-repo CI workflows.
- Do not restore retired downstream README/template deploy workflows such as
  `20_readme-gen.yml`, `22_template-sync.yml`, or `34_auto-deploy.yml`; the App path owns
  cross-repo README automation.
