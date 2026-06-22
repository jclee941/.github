# github-bot - PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-19
**Commit:** `afbfc27f`
**Branch:** `master`
**Upstream base:** qodo-ai/pr-agent fork

## OVERVIEW

Source-of-truth automation repo for `jclee941/*` PR flow. It combines an upstream `qodo-ai/pr-agent`
fork, a fork-owned `jclee_bot` GitHub App checks runner, Go/Python automation scripts, GitHub
Actions workflows, and downstream community-file templates.

Production review/check behavior uses a GitHub App-centered operating model: the homelab GitHub
App posts Checks API runs and reviews; per-repo workflow deployment is no longer the primary
rollout path.

## STRUCTURE

```text
github-bot/
├── .github/               # workflows, local actions, templates, CODEOWNERS
├── jclee_bot/             # fork-owned GitHub App checks runner
├── pr_agent/              # upstream fork; edit config only unless explicitly syncing upstream
├── scripts/               # Go CLIs + Python helpers for repo automation
├── tests/                 # unit, mocked e2e, and live GitHub e2e tests
├── docs/                  # architecture, review templates, operational notes
├── templates/             # downstream community-file sources
├── config/repos.yaml      # canonical managed-repo inventory
├── pyproject.toml         # Python package/lint/test config
└── docker-compose.github_app.yml
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| App-owned PR checks | `jclee_bot/` | Posts `pr-metadata`, `secret-scan`, `actionlint` via Checks API |
| Workflow and reusable-action policy | `.github/` | Numeric workflow stages, local actions, issue/PR templates |
| Default/fallback model config | `.pr_agent.toml`, `pr_agent/settings/configuration.toml` | Keep fork overrides out of upstream code when possible |
| Managed repo inventory | `config/repos.yaml` | Canonical source for managed repos and per-repo automation flags |
| Branch protection / rulesets | `scripts/cmd/branch-protection`, `scripts/cmd/rulesets-manager` | Run from `scripts/` |
| Naming and workflow invariants | `scripts/cmd/validate-naming` | Enforces workflow/template/README inventory rules |
| README automation | `jclee_bot/readme_automation.py`, `jclee_bot/readme_runner.py` | Uses `scripts/generate_readme.py` helpers; redacts private IPs and rejects invented repo links |
| Review prompt templates | `docs/review-templates/`, `.pr_agent.toml` | Review output is Korean; PR/issue templates are bilingual |
| Live GitHub tests | `tests/e2e_live/` | Has its own mutation guard instructions |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `pr_agent.cli.run` | function | `pr_agent/cli.py` | Local `pr-agent` CLI entry |
| `pr_agent.servers.github_action_runner.run_action` | function | `pr_agent/servers/github_action_runner.py` | GitHub Action runner |
| `jclee_bot.app._run_checks_for_payload` | function | `jclee_bot/app.py` | Fetches PR context, runs checks, reports Check Runs |
| `jclee_bot.app._tee_pull_request_to_checks` | middleware | `jclee_bot/app.py` | Tees upstream review webhook into App checks |
| `jclee_bot.dispatch.run_checks` | function | `jclee_bot/dispatch.py` | Dispatches `pr-metadata`, `secret-scan`, `actionlint` |
| `scripts/cmd/validate-naming.main` | Go CLI | `scripts/cmd/validate-naming/main.go` | Workflow/name/inventory validator |
| `scripts/cmd/branch-protection.main` | Go CLI | `scripts/cmd/branch-protection/main.go` | Branch protection and auto-merge rollout |
| `scripts/cmd/rulesets-manager.main` | Go CLI | `scripts/cmd/rulesets-manager/main.go` | GitHub Rulesets rollout |

## CONVENTIONS

- Python target is 3.12; use the repo `Makefile` targets for local install/test/lint.
- pr-agent workflow env vars use literal-dot Dynaconf spelling in Actions, such as
  `OPENAI.KEY`, `OPENAI.API_BASE`, `CONFIG.MODEL`, and `CONFIG.FALLBACK_MODELS`.
  Keep `GITHUB__USER_TOKEN` as the GitHub token exception.
- `config/repos.yaml` is the canonical repo list; do not duplicate repo counts or default branches by hand.
- Workflow files stay flat in `.github/workflows/` and follow numeric stage names such as `10_pr-review.yml`.
- `templates/` contains downstream community files only; App checks are shipped through the App image.
- Conventional commit subjects are the observed repo style; fork-specific changes commonly use scopes like `ci`, `app`, `fork`, `docs`.

## ANTI-PATTERNS

- Do not rewrite upstream `pr_agent/`; prefer `.pr_agent.toml`, workflow env, or fork-owned wrappers.
- Do not restore removed per-repo workflow deployment or old upstream Docker/action metadata.
- Do not hardcode secrets, bearer tokens, private keys, internal IPs, or homelab host details in committed docs/code.
- Do not run `pull_request_target` review paths against untrusted fork code without the existing guard pattern.
- Do not run Go CLIs from the repo root; use `(cd scripts && go run ./cmd/<name>)`.
- Do not treat skipped source-repo PR-review workflow runs as production bot failures; downstream reviews happen through the App.

## COMMANDS

```bash
make install
make test-unit
make test-e2e
make test-live
make lint

(cd scripts && go test ./...)
(cd scripts && go run ./cmd/validate-naming)
(cd scripts && go run ./cmd/branch-protection --dry-run)
(cd scripts && go run ./cmd/rulesets-manager --dry-run)
```

## NOTES

- The live App path is `jclee_bot.app:app`, reusing the upstream FastAPI app and adding Checks API behavior.
- Branch protection requires App check contexts from `jclee-bot`; keep script payloads, docs, and README inventory aligned.
- `tests/e2e_live` can touch real GitHub resources; follow its nested `AGENTS.md` before running mutation tests.
