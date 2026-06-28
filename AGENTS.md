# jclee-bot - PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-28
**Commit:** `f0eb10bb`
**Branch:** `master`
**Upstream provenance:** originally derived from `qodo-ai/pr-agent` (de-forked; see `docs/defork-provenance.md` and `NOTICE`)

## OVERVIEW

Source-of-truth automation repo for `jclee941/*` PR flow. It combines the `jclee_bot` GitHub App checks runner, GitOps/issue/README automation, the absorbed review engine (`jclee_bot.review_engine`, originally derived from `qodo-ai/pr-agent`), Go/Python automation scripts, GitHub Actions workflows, and downstream community-file templates.

Production review/check behavior uses a GitHub App-centered operating model: the homelab GitHub
App posts Checks API runs, reviews, issue maintenance, README automation, and CI-failure cleanup;
per-repo workflow deployment is no longer the primary rollout path.

## STRUCTURE

```text
jclee-bot/
├── .github/               # workflows, local actions, templates, CODEOWNERS
├── jclee_bot/             # first-party GitHub App checks runner + review engine
│   ├── app.py, dispatch.py, github_checks.py  # FastAPI app + Checks API client
│   ├── checks/            # pr-metadata, secret-scan, actionlint, docs-policy
│   ├── gitops_automation.py, pr_auto_merge.py     # branch-to-PR and bot PR auto-merge
│   ├── issue_management.py, issue_maintenance.py  # App-owned issue automation
│   ├── readme_automation.py, readme_runner.py     # App-owned README jobs
│   └── review_engine/     # AI review engine (originally derived from qodo-ai/pr-agent)
├── scripts/               # Go CLIs + Python helpers for repo automation
├── tests/                 # unit, mocked e2e, and live GitHub e2e tests
├── docs/                  # architecture, review templates, operational notes
├── templates/             # downstream community-file sources
├── config/repos.yaml      # canonical managed-repo inventory
├── pyproject.toml         # Python package/lint/test config
└── docker-compose.github_app.yml

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| App-owned PR checks | `jclee_bot/` | Posts `pr-metadata`, `secret-scan`, `actionlint`, and `docs-policy` via Checks API; branch protection requires the first three |
| GitOps and bot PR flow | `jclee_bot/gitops_automation.py`, `jclee_bot/pr_auto_merge.py` | Branch-to-PR, App-owned bot PR auto-merge, protected `master` flow |
| Workflow and reusable-action policy | `.github/` | Numeric workflow stages, local actions, issue/PR templates |
| Default/fallback model config | `.pr_agent.toml`, `jclee_bot/review_engine/settings/configuration.toml` | Per-repo overrides go in `.pr_agent.toml`; engine-wide defaults live in the engine's `settings/` |
| Managed repo inventory | `config/repos.yaml` | Canonical source for managed repos and per-repo automation flags |
| Branch cleanup / protection / rulesets | `scripts/cmd/branch-cleanup`, `scripts/cmd/branch-protection`, `scripts/cmd/rulesets-manager` | Run from `scripts/`; use `--dry-run` before mutations |
| Naming and workflow invariants | `scripts/cmd/validate-naming` | Enforces workflow/template/README inventory rules |
| README automation | `jclee_bot/readme_automation.py`, `jclee_bot/readme_runner.py` | Uses `scripts/generate_readme.py` helpers; redacts private IPs and rejects invented repo links |
| Review prompt templates | `docs/review-templates/`, `.pr_agent.toml` | Review output is Korean; PR/issue templates are bilingual; prompts live in `jclee_bot/review_engine/settings/` |
| Tests | `tests/` | Unit and mocked e2e tests inherit `tests/AGENTS.md`; live GitHub tests add `tests/e2e_live/AGENTS.md` |
| Live GitHub tests | `tests/e2e_live/` | Has its own mutation guard instructions |
| Docs and review templates | `docs/` | Architecture, provenance, GitOps notes, and review-template guidance |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `jclee_bot.review_engine.cli.run` | function | `jclee_bot/review_engine/cli.py` | Local `pr-agent` CLI entry (console script) |
| `jclee_bot.review_engine.servers.github_action_runner.run_action` | function | `jclee_bot/review_engine/servers/github_action_runner.py` | GitHub Action runner |
| `jclee_bot.app._run_checks_for_payload` | function | `jclee_bot/app.py` | Fetches PR context, runs checks, reports Check Runs |
| `jclee_bot.app._tee_pull_request_to_checks` | middleware | `jclee_bot/app.py` | Tees the review-engine webhook into App checks and App-owned automation |
| `jclee_bot.dispatch.run_checks` | function | `jclee_bot/dispatch.py` | Dispatches `pr-metadata`, `secret-scan`, `actionlint`, `docs-policy` |
| `jclee_bot.gitops_automation.handle_create_event` | function | `jclee_bot/gitops_automation.py` | Opens App-owned PRs for eligible branch create events |
| `jclee_bot.gitops_automation.handle_pull_request_auto_merge` | function | `jclee_bot/gitops_automation.py` | Enables auto-merge for eligible PR/review events |
| `scripts/cmd/validate-naming.main` | Go CLI | `scripts/cmd/validate-naming/main.go` | Workflow/name/inventory validator |
| `scripts/cmd/branch-cleanup.main` | Go CLI | `scripts/cmd/branch-cleanup/main.go` | Deletes merged remote branches when not in dry-run |
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
- README architecture diagrams must use sanitized placeholders such as `<homelab-host>` and `<homelab-elk>`; never restore raw private infrastructure addresses.
- Conventional commit subjects are the observed repo style; common scopes include `ci`, `app`, `docs`, `review`, `workflow`.

## ANTI-PATTERNS

- Do not rewrite the review engine's `algo/`, `tools/`, or `git_providers/` modules without a deliberate plan; prefer narrow prompt/config changes in `.pr_agent.toml` or `jclee_bot/review_engine/settings/`.
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
(cd scripts && go run ./cmd/branch-cleanup --dry-run)
(cd scripts && go run ./cmd/branch-protection --dry-run)
(cd scripts && go run ./cmd/rulesets-manager --dry-run)
```

## NOTES

- The live App path is `jclee_bot.app:app`, reusing the review engine's FastAPI app and adding Checks API behavior.
- Branch protection requires App check contexts from `jclee-bot`; keep script payloads, docs, and README inventory aligned.
- `tests/e2e_live` can touch real GitHub resources; follow its nested `AGENTS.md` before running mutation tests.
