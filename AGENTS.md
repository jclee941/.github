# github-bot — PROJECT KNOWLEDGE BASE

**Generated:** 2026-05-10
**Commit:** `161e57ad`
**Commit:** `7bbd1698`
**Commit:** `64829b57`
**Commit:** `89f56fae`
**Commit:** `ce48a4cc`
**Branch:** `master`
**Upstream base:** qodo-ai/pr-agent @ `d82f7d3e`

## OVERVIEW

AI-powered PR reviewer for `jclee941/*` repos. Hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) (AGPL-3.0), rewired to use the homelab `CLIProxyAPI` at `<homelab-host>:8317` as the LLM backend. Workflows run on GitHub-hosted `ubuntu-latest` runners (the homelab is reached over the public internet via `https://cliproxy.jclee.me/v1`).

All upstream pr-agent features are preserved: `/review`, `/improve`, `/describe`, `/ask`, `/update_changelog`, PR compression, dynamic context, multi-model fallback, slash commands.

## FORK DELTA (what changed vs upstream)

| File | Change | Reason |
|------|--------|--------|
| `pr_agent/settings/configuration.toml` | `[config] model` → `kimi-k2.6`, `fallback_models` → `["minimax-m2.7", "gpt-5.5"]` | GitHub App default model via cli_proxy/OpenAI-compatible routing |
| `.pr_agent.toml` | Prepended `[config]`, `[openai]`, `[litellm]` sections | Pin fork-level model and `api_base` to cli_proxy |
| `.github/workflows/10_pr-review.yml` | **NEW** | ubuntu-latest runner + cli_proxy env vars |
| `.github/workflows/security/11_pr-review.yml` | **NEW** | Deep security review (Korean, `pull_request_target`, label-triggered) |
| `.github/workflows/90_sanity.yml` | **NEW** | Fork CI gate (replaces upstream CI) |
| `.github/workflows/06_codeql.yml` | **NEW** | Python SAST (security-extended + quality queries) |
| `.github/workflows/05_gitleaks.yml` | **NEW** | Secret-pattern scan on every PR/push |
| `.github/workflows/04_actionlint.yml` | **NEW** | GitHub Actions YAML semantic linter |
| `.github/workflows/35_auto-hardcode-scan.yml` | **NEW** | Weekly hardcode-pattern scan on `ubuntu-latest` (was self-hosted) |
| `.github/CODEOWNERS` | **NEW** | Auto-reviewer assignment |
| `.github/PULL_REQUEST_TEMPLATE.md` | **NEW** | Bilingual PR template (Korean + English) |
| `docs/git-workflow-gap-analysis.md` | **NEW** | Workflow automation gap analysis report |
| `.github/ISSUE_TEMPLATE/` | **NEW** | Bug / Feature / Security issue templates (replaces upstream) |
| `CONTRIBUTING.md` | **NEW** | Fork-specific contributor guide (replaces upstream) |
| `.github/release-drafter.yml` + `.github/workflows/23_release-drafter.yml` | **NEW** | Conventional-Commits-aware release draft automation |
| `.markdownlint.json` | **NEW** | Local markdownlint overrides (line_length=120, tables/code blocks exempt) |
| `.gitleaksignore` | **NEW** | Fingerprint allowlist for upstream pr-agent test fixtures |
| `scripts/go.mod` + `scripts/cmd/{branch-protection,deploy-to-repos,sync-secrets,repo-review}/main.go` | **NEW** | Module-restructured Go scripts to enable `go test`. Invoke via `(cd scripts && go run ./cmd/<name>)`. |
| `scripts/cmd/branch-protection/main_test.go` + `scripts/cmd/deploy-to-repos/main_test.go` | **NEW** | Table-driven tests for pure-logic helpers (16 test cases) |
| `scripts/cmd/deploy-to-repos/main.go` | **NEW** | Deploy `10_pr-review.yml` to `jclee941/*` repos |
| `scripts/cmd/rulesets-manager/main.go` | **NEW** | GitHub Rulesets manager — supplements branch protection with ruleset-based controls (list/apply/delete) |
| `README.md` | **REPLACED** | Fork-specific readme (upstream moved to `docs/pr-agent-upstream-README.md`) |
| `AGENTS.md` | **REPLACED** | This file |
| `NOTICE` | **NEW** | AGPL-3.0 attribution to upstream |
| `.env.example`, `.env` | **NEW** | cli_proxy env vars (`.env` is gitignored) |
| `docs/pr-agent-upstream-README.md` | **MOVED** | Preserved upstream README for reference |
| `action.yaml` | **REMOVED** | Upstream GitHub Marketplace metadata (unused by fork) |
| `Dockerfile.github_action_dockerhub` | **REMOVED** | Upstream Docker Hub image ref (unused by fork) |
| `docker/` | **REMOVED** | Multi-provider Dockerfiles — GitHub App, Lambda (unused by fork) |
<!-- ISSUE_TEMPLATE / CONTRIBUTING / SECURITY / CODE_OF_CONDUCT removed in upstream then RE-ADDED with fork-specific content (see entries above) -->
| `.github/workflows/pr-agent-review.yaml` | **REMOVED** | Upstream action template |
| `.github/workflows/e2e_tests.yaml` | **REMOVED** | Upstream E2E tests (Docker-based) |
| `.github/workflows/pre-commit.yml` | **REMOVED** | Disabled upstream pre-commit |
| `.github/workflows/build-and-test.yaml` | **REMOVED** | Upstream CI |
| `.github/workflows/code_coverage.yaml` | **REMOVED** | Upstream CI |
| `.github/workflows/docs-ci.yaml` | **REMOVED** | Upstream CI |
| `tests/e2e_tests/` | **REMOVED** | Upstream E2E test suite |
| `tests/health_test/` | **REMOVED** | Upstream health check |
| `pr_compliance_checklist.yaml` | **REMOVED** | Upstream compliance artifact |
| `SECURITY.md` | **REMOVED** | Upstream security policy (references qodo.ai) |
| `CODE_OF_CONDUCT.md` | **REMOVED** | Upstream CoC (references qodo.ai contact) |
| `CHANGELOG.md` | **REMOVED** | Upstream changelog (2023 only, no fork entries) |
| `RELEASE_NOTES.md` | **REMOVED** | Upstream release notes (v0.7–v0.11, codiumai images) |
| `codecov.yml` | **REMOVED** | Disabled coverage config (no coverage CI in fork) |
| `.pre-commit-config.yaml` | **REMOVED** | Mostly commented out, unused by fork CI |
| `docs/docs/` | **REMOVED** | Upstream mkdocs site (broken internal links) |
| `docs/mkdocs.yml` | **REMOVED** | Upstream mkdocs config |
| `docs/overrides/` | **REMOVED** | Upstream mkdocs theme overrides |
| `docs/README.md` | **REMOVED** | Upstream docs redirect |

Everything under `pr_agent/` (except `settings/configuration.toml`) is untouched upstream code.

## STRUCTURE

```text
github-bot/
├── pr_agent/                      # upstream code, do not rewrite
│   ├── agent/                     # command orchestration (/review, /improve, ...)
│   ├── algo/
│   │   └── ai_handlers/
│   │       ├── litellm_ai_handler.py   # reads OPENAI.API_BASE → litellm.api_base
│   │       └── openai_ai_handler.py
│   ├── tools/                     # individual capabilities (PRReviewer, PRDescription, ...)
│   ├── git_providers/             # github.py, gitlab.py, bitbucket.py
│   ├── servers/
│   │   ├── github_action_runner.py  # entry point for our workflow
│   │   └── github_app.py
│   └── settings/
│       ├── configuration.toml     # FORK: model defaults changed
│       ├── pr_reviewer_prompts.toml
│       └── ...                    # other prompt templates
├── .github/workflows/
│   ├── 10_pr-review.yml               # FORK: ubuntu-latest + cli_proxy (kimi-k2.6)
│   ├── security/11_pr-review.yml      # FORK: deep security review (Korean, label-gated)
│   ├── 90_sanity.yml                  # FORK: CI gate (replaces upstream CI)
│   ├── 03_pr-checks.yml               # PR validation (size, title, branch, description)
│   ├── 05_gitleaks.yml                # Secret scanning
│   ├── 06_codeql.yml                  # Python SAST
│   ├── 04_actionlint.yml              # Workflow YAML linter
│   ├── 12_dependabot-auto-merge.yml   # Auto-merge patch/minor updates
│   ├── 34_auto-deploy.yml             # Deploy workflows to downstream repos
│   └── ...                            # 47 more workflows (56 total; see .github/workflows/)
├── scripts/
│   ├── cmd/                         # Go tool entry points (8 tools)
│   │   ├── branch-protection/main.go
│   │   ├── deploy-to-repos/main.go
│   │   ├── drift-detector/main.go
│   │   ├── repo-metadata/main.go
│   │   ├── repo-review/main.go
│   │   ├── rulesets-manager/main.go
│   │   ├── sync-secrets/main.go
│   │   └── validate-naming/main.go
│   ├── internal/                    # Shared Go packages
│   └── *.py                         # Python runners (pr_review_runner, repo_review, ...)
├── github_action/
│   └── entrypoint.sh             # Docker entrypoint for GitHub Action
├── .pr_agent.toml                 # FORK: cli_proxy config + existing pr-agent overrides
├── .env.example                   # cli_proxy env vars template
├── .env                           # local secrets (gitignored)
├── NOTICE                         # AGPL-3.0 attribution
├── LICENSE                        # AGPL-3.0 (unchanged)
├── AGENTS.md                      # THIS FILE
├── README.md                      # fork-specific readme
├── config/                        # OpenCode settings (base.jsonc, providers.jsonc, lsp.jsonc)
├── templates/                     # PR/issue templates (bilingual KO/EN)
├── docs/
│   ├── review-templates/              # FORK: review templates (Korean output, bilingual PR template)
│   │   ├── code-review-template.md      # Master review format and priorities
│   │   ├── documentation-checklist.md   # Documentation review checklist
│   │   └── security-review-template.md  # Security-focused review checklist
│   └── pr-agent-upstream-README.md  # original pr-agent README
└── tests/                         # upstream pytest suite (unit tests only)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Change default model | `pr_agent/settings/configuration.toml` `[config].model` | Line 7, currently `kimi-k2.6` |
| Override model per-repo | `.pr_agent.toml` `[config].model` | Fork-level override, takes precedence |
| Change cli_proxy endpoint | `.pr_agent.toml` `[openai].api_base` | Currently `https://cliproxy.jclee.me/v1` |
| Edit review prompts | `pr_agent/settings/pr_reviewer_prompts.toml` | upstream TOML |
| Edit improve prompts | `pr_agent/settings/code_suggestions/` | |
| Workflow triggers | `.github/workflows/10_pr-review.yml` | PR events + slash commands |
| Security review config | `.github/workflows/security/11_pr-review.yml` | Triggered by `security-review` label |
| CI gate | `.github/workflows/90_sanity.yml` | TOML parse + pytest gate |
| Hardcode pattern scan | `.github/workflows/35_auto-hardcode-scan.yml` | Weekly cron + manual dispatch on `ubuntu-latest`, 15-minute timeout |
| Slash command handling | `pr_agent/servers/github_app.py`, `github_action_runner.py` | |
| Add a git provider | `pr_agent/git_providers/` | implement base class |
| Deploy to another repo | `scripts/cmd/deploy-to-repos/main.go` | Automates workflow + dependabot config sync to 11 downstream public repos (excludes `.github` source and `pr-agent` fork) |
| Apply branch protection | `scripts/cmd/branch-protection/main.go` | Enables auto-merge + safe protection on default branches of 12 public repos (includes `.github`) |
| Dependabot auto-merge config | `.github/workflows/12_dependabot-auto-merge.yml` | Auto-approves + merges patch/minor + github-actions PRs; majors flagged for review |
| Dependabot updates schedule | `.github/dependabot.yml` | Weekly `github-actions` + `pip` ecosystem PRs |
|| Upstream sync | `git fetch upstream && git merge upstream/main` | resolve conflicts in configuration.toml, .pr_agent.toml |
| Edit review templates | `docs/review-templates/` | Review output in Korean. PR/issue templates are bilingual (Korean + English) |
| View architecture diagrams | `docs/architecture.md` | Mermaid-based system & automation flow diagrams |
| View gap analysis | `docs/git-workflow-gap-analysis.md` | Workflow automation gap analysis (20 gaps, P0-P2) |
| Batch repo review | `scripts/repo_review.py`, `scripts/cmd/repo-review/main.go` | Python helper / Go CLI for repo-review-batch workflow |
| Run live E2E tests | `tests/e2e_live/` | Live GitHub API e2e tests (fleet health, canary PR lifecycle, bot review) |
| Configure documentation review | `.pr_agent.toml` `[pr_reviewer].extra_instructions` | Documentation checklist embedded in instructions |
| Run make targets | `Makefile` | `make test`, `make lint`, `make clean` |
| Edit OpenCode config | `config/` | `base.jsonc`, `providers.jsonc`, `lsp.jsonc` |
| Edit PR templates | `templates/` | Bilingual KO/EN PR/issue templates |
| View contributor guide | `CONTRIBUTING.md` | Fork scope, commit conventions, rollout phases |
| Run mocked E2E tests | `tests/e2e/` | FastAPI TestClient webhook tests |
| Configure Docker App | `docker-compose.github_app.yml` | homelab deployment compose |

## GIT FLOW AUTOMATION

### Terminology disambiguation

"Git flow" here means **GitHub PR-flow automation** (auto-merge, dependency updates, branch protection, automatic AI review on every PR). It does NOT refer to the classical Git Flow branching model (`develop` / `feature/*` / `release/*` / `hotfix/*`); that model is not in scope and not implemented across these repos.

### Repository inventory (16 jclee941 repos)

| Repo | Visibility | Default branch | Status | Reason |
|------|------------|----------------|--------|--------|
| `.github` | public | master | ✅ fully automated | source of truth |
| `account` | public | master | ✅ fully automated | |
| `blacklist` | public | master | ✅ fully automated | |
| `bug` | public | main | ✅ fully automated | |
| `hycu_fsds` | public | master | ✅ fully automated | |
| `idle-outpost` | public | main | ✅ fully automated | |
| `opencode` | public | master | ✅ fully automated | |
| `resume` | public | master | ✅ fully automated | |
| `safetywallet` | public | master | ✅ fully automated | |
| `splunk` | public | master | ✅ fully automated | |
| `terraform` | public | master | ✅ fully automated | |
| `tmux` | public | master | ✅ fully automated | |
| `pr-agent` | public (fork) | main | ⚠️ excluded by design | upstream fork; carries qodo-ai/pr-agent workflows that must not be overwritten. Sync via `git fetch upstream && git merge upstream/main`. |
| `hycu` | private | master | ✅ fully automated (GitHub Pro) | Previously limited by GitHub Free. Upgraded to Pro 2026-05-07. Now has full automation: branch protection, auto-merge, bot review. |
| `youtube` | private | master | ✅ fully automated (GitHub Pro) | Previously limited by GitHub Free. Upgraded to Pro 2026-05-07. Now has full automation: branch protection, auto-merge, bot review. |
| `propose` | private | master | ✅ fully automated (GitHub Pro) | Previously limited by GitHub Free. Upgraded to Pro 2026-05-07. Now has full automation: branch protection, auto-merge, bot review. |

**Scope**: 16 repos (12 public + 3 private + 1 source) receive the full automation stack. The 3 private repos were upgraded to GitHub Pro on 2026-05-07 and now have complete automation (auto-merge, branch protection, Dependabot, auto-review). The `pr-agent` fork is excluded by design. |

### Per-repo automation guarantees

| Component | File | Behavior |
|-----------|------|----------|
| Auto-merge enable | repo settings | `allow_auto_merge=true`, `delete_branch_on_merge=true` |
| Branch protection | default branch | **3 required contexts**: `pr-checks / Check PR Title` (Conventional Commits), `pr-checks / Check Branch Name` (standard prefixes), `Gitleaks / scan` (secret-pattern detection). 4 advisory contexts (Size, Description, Large Files, Sensitive Files) comment-only. CodeQL surfaces results via Security tab, not as a required check. No force-push, no deletion, no admin enforcement. |
| Dependency updates | `.github/dependabot.yml` | Weekly `github-actions` + `pip` ecosystem PRs (pip groups minor+patch) |
| Auto-merge policy | `.github/workflows/12_dependabot-auto-merge.yml` | patch + minor + github_actions → squash auto-merge after required checks pass; major → manual review comment; null update-type → manual review comment |
| PR validation | `.github/workflows/03_pr-checks.yml` | sanity gates before merge |
| Auto-review | `.github/workflows/10_pr-review.yml` | Runs on every PR opened by anyone except `dependabot[bot]` and drafts (Dependabot has its own auto-merge path). Posts review via `pr-agent` against cli_proxy. |
| Secret scanning | `.github/workflows/05_gitleaks.yml` | Required check on every PR/push; full-history scan on master |
| Workflow lint | `.github/workflows/04_actionlint.yml` | Validates GHA YAML semantics on workflow changes |
| Dependency Review | `.github/workflows/07_dependency-review.yml` | PR open/edit | Scans PR dependencies for known vulnerabilities (moderate+) |
| Release Notes | `.github/workflows/24_release-notes.yml` | Tag push | Auto-generates categorized release notes from conventional commits |
| Documentation sync | `.github/workflows/21_docs-sync.yml` | PR open/edit/push | Markdown lint, link check, README sync validation, API docs check |
| README generator | `.github/workflows/20_readme-gen.yml` | Weekly (Sundays) + manual | Auto-generates README.md via CLIProxyAPI (minimax-m2.7 → gpt-5.5 fallback). |
| Template sync | `.github/workflows/22_template-sync.yml` | Weekly (Sundays) + manual | Deploys standard `README.md`, `CONTRIBUTING.md`, `LICENSE` templates to downstream repos |
| Security scoring | `.github/workflows/08_scorecard.yml` | PR open/push | OpenSSF Scorecard security scoring with harden-runner |
| Semantic PR validation | `.github/workflows/09_semantic-pr.yml` | PR open/edit/synchronize | Enforces Conventional Commits format via amannn/action-semantic-pull-request |
| Runtime security | all workflows | every run | step-security/harden-runner@v2 with egress-policy: audit |
| ELK health monitoring | `.github/workflows/26_elk-health-check.yml` | Daily 06:00 UTC | Checks Elasticsearch connectivity, index health, creates issues on failure |
| ELK setup | `.github/workflows/27_elk-setup.yml` | Weekly (Sundays) + manual | Deploys index templates and ILM policies to Elasticsearch |

### Autonomous Bot Workflows

| Workflow | File | Schedule | Behavior |
|----------|------|----------|----------|
| Bot Auto-Fix | `.github/workflows/14_bot-auto-fix.yml` | PR open/edit | Auto-fixes naming violations on PRs via `validate-naming --fix` |
| Drift Detector | `.github/workflows/33_drift-detector.yml` | Daily 06:00 UTC | Detects downstream drift from source workflows; self-healing matrix with `--self_heal=true` |
| Bot Health Monitor | `.github/workflows/28_bot-health-monitor.yml` | Daily 06:00 UTC | Checks CLIProxyAPI connectivity and jclee-bot review activity; creates critical alerts |
| Org Health Report | `.github/workflows/32_org-health-report.yml` | Weekly Monday 09:00 UTC | Generates comprehensive health report: open PRs/issues, stale PRs, last commits per repo |
| Repo Health Check | `.github/workflows/31_repo-health.yml` | Weekly (Mondays 02:00 UTC) | Checks all repos for required documentation files (README.md, CONTRIBUTING.md, LICENSE); creates issues for gaps |
| Org Health Report | `.github/workflows/32_org-health-report.yml` | Weekly Monday 09:00 UTC | Generates comprehensive health report: open PRs/issues, stale PRs, last commits per repo |

### Operations

```bash
# 1. Edit a workflow in .github/workflows/, or .github/dependabot.yml,
#    or .github/CODEOWNERS, or .github/PULL_REQUEST_TEMPLATE.md, or scripts/cmd/deploy-to-repos/main.go
# 2. Commit + push to master
# 3. auto-deploy.yml runs deploy-to-repos.go (→ scripts/cmd/deploy-to-repos/main.go) on a GitHub-hosted ubuntu-latest runner
#    → opens/updates PR "chore: standardize automation workflows + dependabot config"
#    in each downstream repo (force-push branch via --force-with-lease)
# 4. Each downstream PR auto-merges once its required branch-protection contexts pass (Title + Branch [+ Gitleaks after Phase 3])

# Manual deploy (local dev / CI bypass):
(cd scripts && go run ./cmd/deploy-to-repos) --dry-run                       # preview all
(cd scripts && go run ./cmd/deploy-to-repos) --repos=resume                  # canary one
(cd scripts && go run ./cmd/deploy-to-repos)                                 # apply to all 11 downstream public repos (excludes pr-agent fork)

# Re-apply branch protection + auto-merge settings:
(cd scripts && go run ./cmd/branch-protection) --dry-run
# Apply rulesets (supplements branch protection with GitHub Rulesets):
(cd scripts && go run ./cmd/rulesets-manager) --dry-run                    # preview all
(cd scripts && go run ./cmd/rulesets-manager) --repos=resume               # canary one
(cd scripts && go run ./cmd/rulesets-manager)                              # apply to all
(cd scripts && go run ./cmd/rulesets-manager) --mode=list                  # list existing rulesets
(cd scripts && go run ./cmd/rulesets-manager) --mode=delete --dry-run      # preview deletion
(cd scripts && go run ./cmd/branch-protection)

# Sync CLIPROXY_API_KEY (and other shared secrets) to every public repo:
CLIPROXY_API_KEY=$(grep '^CLIPROXY_API_KEY=' .env | cut -d= -f2-) \
  (cd scripts && go run ./cmd/sync-secrets)
```

### Why pr-agent is handled separately

`jclee941/pr-agent` is a hard fork of `qodo-ai/pr-agent`. It carries upstream's own workflows (build-and-test.yaml, codeql.yml, release-drafter.yml, etc.) which would be overwritten by the deploy script. The fork is therefore excluded from `deploy-to-repos.go` (→ `scripts/cmd/deploy-to-repos/main.go`), but it has its own fork-local `.github/dependabot.yml` (github-actions + pip ecosystems) and `.github/workflows/12_dependabot-auto-merge.yml` that are maintained directly on a `fork/*` branch. Sync upstream via `git fetch upstream && git merge upstream/main`.

## PR REVIEW WORKFLOW BEHAVIOR

### Source Repo vs Production Path

`.github/workflows/10_pr-review.yml` in this repo is a **local development/CI tool**. It only runs on PRs opened against the `.github` repository itself.

The actual production PR review path:

1. `jclee-bot` GitHub App receives webhooks for all `jclee941/*` repos
2. App server on the homelab host (`bot.jclee.me`) runs pr-agent directly
3. Reviews are posted via the GitHub App installation token

Therefore, high skip counts in the `10_pr-review.yml` workflow are **expected and by design** — most PRs occur in downstream repos where this workflow file does not exist.

### Monitoring Bot Health

To check if the bot is actually reviewing PRs:

- Check GitHub App webhook delivery logs: `https://github.com/settings/apps/jclee-bot/advanced`
- Check container logs on the homelab host: `ssh root@<homelab-host> "docker logs github-bot-app"`
- Check PR comments by `jclee-bot[bot]` in downstream repos

## ELK INTEGRATION

| Component | Details |
|-----------|---------|
| **Elasticsearch** | `http://<homelab-elk>:9200` — homelab ELK stack |
| **Filebeat** | Ships github-bot-app container logs + Docker container logs |
| **Index** | `github-bot-logs-%{+yyyy.MM.dd}` — daily indices |
| **ILM Policy** | `github-bot-logs`: 7-day hot rollover → warm shrink → 30-day delete |
| **Config** | `filebeat.yml` — container input with Docker metadata + JSON decoding |
| **Compose** | `docker-compose.github_app.yml` — filebeat service alongside github-bot-app |

### Log Shipping Architecture

```text
GitHub App (docker container) → Docker JSON logs → Filebeat → Elasticsearch
```

### Automated Management

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `26_elk-health-check.yml` | Daily 06:00 UTC | Checks Elasticsearch connectivity and index health; creates issues on failure |
| `27_elk-setup.yml` | Weekly (Sundays) + manual | Deploys index templates and ILM policies to Elasticsearch |

### Manual Operations

```bash
# Check Filebeat status on the homelab host
ssh root@<homelab-host> "docker logs filebeat-github-bot"

# Check Elasticsearch cluster health
curl -sS http://<homelab-elk>:9200/_cluster/health?pretty

# View recent indices
curl -sS http://<homelab-elk>:9200/_cat/indices/github-bot-logs-*?v

# Query recent logs
curl -sS http://<homelab-elk>:9200/github-bot-logs-*/_search?pretty -H 'Content-Type: application/json' -d '{"size": 5, "sort": [{"@timestamp": {"order": "desc"}}]}'
```

## CLI_PROXY INTEGRATION DETAILS

| Item | Value |
|------|-------|
| **Service** | [`router-for-me/CLIProxyAPI`](https://github.com/router-for-me/CLIProxyAPI) |
| **Docker image** | `eceasy/cli-proxy-api:latest` |
| **Host** | homelab host on `pve3`, hostname `cliproxy.homelab.local` |
| **IP:port** | `<homelab-host>:8317` (primary) |
| **Additional ports** | `1455`, `8085`, `11451`, `51121`, `54545` (see `docker ps` on host) |
| **Config file** | `/opt/cli-proxy-api/config.yaml` (on the homelab host) |
| **Auth dir** | `/root/.cli-proxy-api/` (OAuth tokens for Codex, Antigravity) |
| **Auth method** | Bearer token in `Authorization` header |
| **API format** | OpenAI-compatible: `/v1/chat/completions`, `/v1/completions`, `/v1/models` |

### Available models (24 total as of 2026-05-07)

> **Current default**: GitHub App webhook uses `kimi-k2.6`; canonical fallback chain is `minimax-m2.7`, `gpt-5.5` (enforced by `90_sanity.yml`). The PR-review workflow matrix uses `[minimax-m2.7, gpt-5.5]`.
> Prefix-less Kimi/Claude/GPT/Codex/Gemini model names are routed through the configured OpenAI-compatible cli_proxy endpoint.

- **Codex (GPT)**: `openai/gpt-5.2`, `openai/gpt-5.1`, `openai/gpt-5`, `gpt-5-codex-mini`, `gpt-5.1-codex-max`, `gpt-4.1`, `gpt-4.1-mini`
- **Antigravity (Gemini)**: `gemini-3-pro-preview`, `gemini-3-flash-preview`, `gemini-2.5-flash`
- **Antigravity (Claude)**: `ag-claude-sonnet-4-5`, `ag-claude-sonnet-4-5-thinking`

Get the full list:

```bash
curl -sS http://<homelab-host>:8317/v1/models \
  -H "Authorization: Bearer $CLIPROXY_API_KEY" | jq -r '.data[].id'
```

### Retrieving the API key

```bash
ssh root@<homelab-host> \
  "python3 -c 'import yaml; print(yaml.safe_load(open(\"/opt/cli-proxy-api/config.yaml\"))[\"api-keys\"][0])'"
```

Rotate: edit `/opt/cli-proxy-api/config.yaml` on the homelab host, restart the docker container:

```bash
ssh root@<homelab-host> "docker restart cli-proxy-api"
```

## PR-AGENT WORKFLOW ENV VAR CONVENTIONS

pr-agent loads its settings via `Dynaconf(envvar_prefix=False, ...)` (see `pr_agent/config_loader.py:18`). With no prefix, **only specific env-var spellings reach the nested settings tree** — the bug-fix history is non-obvious. Memorise this table before adding any new env var to `10_pr-review.yml` or `security/11_pr-review.yml`:

| Setting key (used in pr-agent code) | Wrong env name | Correct env name | Why |
|------|----------------|------------------|-----|
| `settings.github.user_token` | `GITHUB_TOKEN` (fork-broken) | **`GITHUB__USER_TOKEN`** (double underscore) | Single-underscore creates flat key `GITHUB_TOKEN`; dynaconf nested path requires `__` |
| `settings.openai.key` | `OPENAI_KEY` (fork-broken) | **`OPENAI.KEY`** (literal dot) | Same reason. Dot syntax also works in GH Actions YAML `env:` blocks |
| `settings.openai.api_base` | — | `OPENAI.API_BASE` | Literal dot |
| `settings.config.model` | — | `CONFIG.MODEL` | Literal dot |
| `settings.config.fallback_models` | — | `CONFIG.FALLBACK_MODELS` | Literal dot |
| `settings.config.custom_model_max_tokens` | omit (forces MAX_TOKENS lookup) | **`CONFIG.CUSTOM_MODEL_MAX_TOKENS=128000`** | `kimi-k2.6` is NOT in `pr_agent/algo/__init__.py:MAX_TOKENS`; without this, prompt-trim refuses to call litellm |
| `settings.pr_reviewer.require_*` | — | `PR_REVIEWER.REQUIRE_*` | Literal dot |

**Special case — `security/11_pr-review.yml` only**: that workflow invokes `pr_agent.servers.github_action_runner` directly, which manually translates `GITHUB_TOKEN` → `settings.github.user_token` and `OPENAI_KEY` → `settings.openai.key` at `pr_agent/servers/github_action_runner.py:55-61`. Both env-var styles work there, but for consistency the fork uses the same `OPENAI.KEY` / `GITHUB__USER_TOKEN` everywhere.

**Silent-failure guard** (`pr-review.yml:141`): pr-agent's CLI catches its own exceptions in `pr_reviewer.py:184` and **returns exit code 0 even on fatal failures**. The workflow `tee`s output to `/tmp/pr-agent.log` and `grep`s for known fatal patterns (`Failed to generate prediction with any model`, `Failed to review PR`, `AuthenticationError`, etc.) — known no-op patterns (`Empty diff for PR:`, `PR has no files:`, `Review output is not published`) are subtracted to avoid false positives. The full pattern list is in the workflow's run-step.

**Phase 3 rollout completed (2026-05-03)**: Branch protection on all 12 public repos now enforces `Gitleaks / scan` as a third required status check. To re-apply after editing `branch-protection.go`, run `(cd scripts && go run ./cmd/branch-protection)` from this repo.

## COMMANDS

```bash
# ==================
# Make targets
# ==================
make install                    # python3.12 venv + pip install -e .
make test-unit                  # pytest tests/unittest -v
make test-e2e                   # pytest tests/e2e -v --tb=short
make test-live                  # pytest tests/e2e_live -v --tb=short
make lint                       # ruff check .
make clean                      # rm -rf .pytest_cache __pycache__

# ==================
# Local development
# ==================
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
PYTHONPATH=. pytest tests/unittest -v

# Local CLI review (requires .env populated)
export LITELLM_LOCAL_MODEL_COST_MAP=True  # avoid import-time network fetch in offline homelab shells
set -a; source .env; set +a
python -m pr_agent.cli --pr_url https://github.com/jclee941/<repo>/pull/<N> review

# ==================
# Test cli_proxy connectivity
# ==================
source .env
curl -sS http://<homelab-host>:8317/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CLIPROXY_API_KEY" \
  -d '{"model":"kimi-k2.6","messages":[{"role":"user","content":"ping"}],"max_tokens":10}'

# ==================
# Upstream sync
# ==================
git fetch upstream
git log upstream/main..HEAD --oneline    # see our fork-specific commits
git merge upstream/main                    # may conflict in configuration.toml, .pr_agent.toml
git push origin main

# ==================
# Deploy workflow to another jclee941 repo
# ==================
# Option 1: automated deploy script (opens PRs)
(cd scripts && go run ./cmd/deploy-to-repos)

# Option 2: manual deploy
REPO=jclee941/<target-repo>
gh -R "$REPO" secret set CLIPROXY_API_KEY --body "$(cat /home/jclee/.cache/sisyphus/cliproxy-api-key)"
# Copy .github/workflows/10_pr-review.yml to the target repo manually
```

## CONVENTIONS

- **Python**: ≥ 3.12, ruff 120-char line length, isort imports, double quotes
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`)
- **Fork-specific commits**: tag with scope `fork:` (e.g. `feat(fork): pin model to kimi-k2.6`)
- **Upstream sync commits**: `chore(upstream): merge qodo-ai/pr-agent@<sha>`
- **Secrets**: only in `.env`, `.secrets.toml`, or GitHub Actions secrets — never in TOML/YAML in git
- **Type safety**: never suppress (`as any`, `@ts-ignore`, `# type: ignore[...]` without justification)

### File Naming Conventions (`.github/`)

These conventions are enforced by `scripts/cmd/deploy-to-repos/main.go` and its tests.

| Pattern | Meaning | Example |
|---------|---------|---------|
| **kebab-case** | Default for all workflow, template, and config files | `pr-checks.yml`, `dependabot-auto-merge.yml` |
| **Underscore prefix `_`** | Local-only workflow; NEVER deployed downstream | `_stale.yml`, `_welcome.yml` |
| **`reusable-` prefix** | Callable reusable workflow | `reusable-pr-checks.yml` |
| **`security/` subdirectory** | Security-focused workflows | `security/11_pr-review.yml` |
| **No extension** | GitHub-mandated filenames | `CODEOWNERS` |
| **`.yml` preferred** | Workflow and issue template extensions | `1-bug-report.yml` (not `.yaml`) |

**Issue templates** follow the `{number}-{type}-report.yml` pattern with numeric prefix for display ordering: `1-bug-report.yml`, `2-feature-request.yml`, `3-security-vulnerability.yml` (next.js style).
`.github/ISSUE_TEMPLATE/config.yml` is exempt from numeric prefix (GitHub standard).

**Deployment branch naming**: `chore/sync-automation-workflows` (reflects full scope: workflows + dependabot + templates).

**Deployment PR title**: `chore: sync automation workflows, dependabot, and templates`.

**`templates/` directory**: Contains `CONTRIBUTING.md`, `LICENSE`, `README.md`. These are deployed to downstream repos by `.github/workflows/22_template-sync.yml` on a weekly schedule.

### Workflow Standardization Conventions

Enforced across all `.github/workflows/*.yml` (and `security/`); verified by `90_sanity.yml`, `actionlint`, and `validate-naming`.

| Aspect | Standard | Exceptions |
|--------|----------|------------|
| **Numeric prefix** | `NN_<kebab-case>.yml` two-digit prefix by pipeline stage (01-90) | reusable callers keep `reusable-`/`_`/`security/` semantics |
| **Action pinning** | First-party `actions/*` & `github/*` use semver `@vN`; third-party actions use 40-char commit SHA with `# vX.Y.Z` comment | `step-security/harden-runner@v2` is repo-wide semver (95+ uses) |
| **Runner selection** | `runs-on: ${{ github.repository_visibility == 'private' && 'self-hosted' || 'ubuntu-latest' }}` | `07_dependency-review.yml`, `08_scorecard.yml` stay `ubuntu-latest` (GitHub-hosted SARIF/dependency API); `13_pr-auto-merge.yml`, `26_elk-health-check.yml`, `27_elk-setup.yml`, `36_build-and-push-app.yml` stay `self-hosted` (homelab) |
| **Failure notification** | Use `uses: ./.github/actions/notify-on-failure` (shared composite, dedup-by-title) for `if: failure()` steps | core issue-reporting logic (e.g. `29_downstream-health-check.yml` `health-check` issues) is NOT a failure-notify step |
| **Fallback models** | Single canonical chain `["minimax-m2.7", "gpt-5.5"]` across `.pr_agent.toml`, `configuration.toml`, and every workflow `CONFIG__FALLBACK_MODELS` | GitHub App primary stays `kimi-k2.6` |
| **PR-review matrix** | `10_pr-review.yml` matrix = `[minimax-m2.7, gpt-5.5]` (Kimi excluded) | GitHub App webhook default = `kimi-k2.6` |
| **Reusable self-refs** | `18_issue-management.yml` & `21_docs-sync.yml` reference `jclee941/.github/.github/workflows/*@master` intentionally (kept in sync by `34_auto-deploy.yml`) | — |
| **Harden runner** | `step-security/harden-runner@v2` (egress-policy: audit) as first step in every job with `steps:` | reusable-workflow caller jobs (only `uses:`) are exempt |
| **POSIX** | Trailing newline at EOF; no duplicate keys; passes `actionlint` | — |

## ANTI-PATTERNS

- **Never** hardcode the cli_proxy API key in any tracked file
- **Never** commit `.env`, `.secrets.toml`, `pr_agent/settings/.secrets.toml`, or anything under `.cache/`
- **Never** edit `pr_agent/settings/configuration.toml` beyond the cli_proxy model line — it conflicts with every upstream merge
- **Never** run PR review on PRs from untrusted forks under `pull_request_target` without a head-repo guard — code execution / token-theft risk. The current guard in `.github/workflows/security/11_pr-review.yml` requires `head.repo.full_name == github.repository`.
- **Never** push to `main` without running at least `pytest tests/unittest/test_fix_json_escape_char.py`
- **Never** delete or rename upstream prompt TOML files (e.g. `pr_agent/settings/pr_reviewer_prompts.toml`) — they're the single source of truth for prompts
- **Never** run the legacy root-level binaries in `scripts/` (`./branch-protection`, `./deploy-to-repos`, `./repo-review`, `./sync-secrets`). Use `(cd scripts && go run ./cmd/<name>)` instead.

## SECURITY NOTES

- `CLIPROXY_API_KEY` is stored as GitHub repo secret AND locally in `.env` (chmod 600)
- GitHub-hosted `ubuntu-latest` runners read `CLIPROXY_API_KEY` from repo secrets; the homelab cli_proxy is reached over the public internet at `https://cliproxy.jclee.me/v1`. Treat the secret as compromised if it is ever printed to a workflow log.
- cli_proxy has no network ACL — any workstation on `<homelab-subnet>` with the key can call it
- AGPL-3.0 compliance: this is a private deployment serving only jclee941; source access is provided via this repo itself to authorized users (which is just jclee941)

## FORK ATTRIBUTION

## REVIEW TEMPLATES

> Korean-language review output for the `jclee-bot` GitHub App. PR and issue templates are bilingual (Korean + English).
Located in `docs/review-templates/` and referenced from `.pr_agent.toml`.

| Template | Purpose | Trigger |
|----------|---------|---------|
| `code-review-template.md` | Master review format, priorities, severity levels | Every `/review` |
| `documentation-checklist.md` | README, API docs, docstring, PR description checks | Embedded in `extra_instructions` |
| `security-review-template.md` | OWASP Top 10, secret scanning, SAST checks | `security-review` label |

### Template Usage Flow

```
PR opened / labeled
│
▼
GitHub App receives webhook
│
▼
pr_agent reads .pr_agent.toml
│
▼
extra_instructions loaded (compact rules from templates)
│
▼
LLM (kimi-k2.6) generates Korean review
│
▼
Review posted as PR comment (markdown tables + code blocks)
```

### Customizing Templates

1. Edit the relevant `.md` file in `docs/review-templates/`
2. Update `.pr_agent.toml` `[pr_reviewer].extra_instructions` to match (compact form)
3. Commit to `master` (default branch — GitHub App reads from here)
4. Restart container: `docker compose restart github-bot-app`

**Note**: Templates are for human reference. The bot actually uses the compact `extra_instructions` in `.pr_agent.toml`. Keep them in sync.

- **Upstream**: [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) — AGPL-3.0 © 2023-2026 CodiumAI / Qodo contributors
- **Base commit**: `d82f7d3e` (`fix: prevent dummy_key from overriding provider-specific API keys`)
- **Forked by**: `jclee941`
- **Fork date**: 2026-04-10
- **This fork**: AGPL-3.0 (inherited), see [LICENSE](LICENSE) and [NOTICE](NOTICE)

## SUB-AGENTS

| Directory | Purpose | Lines |
|-----------|---------|-------|
| `pr_agent/AGENTS.md` | Upstream code — read-only guidance | 47 |
| `scripts/AGENTS.md` | Go automation tools reference | 63 |
| `tests/e2e_live/AGENTS.md` | Live E2E test suite guide | 58 |

**Automated validation**: `scripts/cmd/validate-naming` checks cross-file invariants (deploy constants match E2E tests, auto-deploy paths cover extraFiles, CODEOWNERS coverage, kebab-case compliance). Run with `(cd scripts && go run ./cmd/validate-naming)`. Use `--fix` for auto-correction where supported.

**File naming lint**: `.ls-lint.yml` enforces directory-specific conventions via `ls-lint`. Integrated into `90_sanity.yml` CI.
pos
396#MS
