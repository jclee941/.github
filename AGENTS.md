# github-bot — PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-14
**Upstream base:** qodo-ai/pr-agent @ `d82f7d3e`

## OVERVIEW

AI-powered PR reviewer for `jclee941/*` private repos. Hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) (AGPL-3.0), rewired to use the homelab `CLIProxyAPI` at `192.168.50.114:8317` as the LLM backend. Workflows run on GitHub-hosted `ubuntu-latest` runners (the homelab is reached over the public internet via `https://cliproxy.jclee.me/v1`).

All upstream pr-agent features are preserved: `/review`, `/improve`, `/describe`, `/ask`, `/update_changelog`, PR compression, dynamic context, multi-model fallback, slash commands.

## FORK DELTA (what changed vs upstream)

| File | Change | Reason |
|------|--------|--------|
| `pr_agent/settings/configuration.toml` | `[config] model` → `kimi-k2.6`, `fallback_models` → `["kimi-k2.5", "claude-sonnet-4-6"]` | Default model via cli_proxy/OpenAI-compatible routing |
| `.pr_agent.toml` | Prepended `[config]`, `[openai]`, `[litellm]` sections | Pin fork-level model and `api_base` to cli_proxy |
| `.github/workflows/pr-review.yml` | **NEW** | ubuntu-latest runner + cli_proxy env vars |
| `.github/workflows/security/pr-review.yml` | **NEW** | Deep security review (Korean, `pull_request_target`, label-triggered) |
| `.github/workflows/sanity.yml` | **NEW** | Fork CI gate (replaces upstream CI) |
| `.github/workflows/codeql.yml` | **NEW** | Python SAST (security-extended + quality queries) |
| `.github/workflows/gitleaks.yml` | **NEW** | Secret-pattern scan on every PR/push |
| `.github/workflows/actionlint.yml` | **NEW** | GitHub Actions YAML semantic linter |
| `.github/workflows/auto-hardcode-scan.yml` | **NEW** | Weekly hardcode-pattern scan on `ubuntu-latest` (was self-hosted) |
| `.github/CODEOWNERS` | **NEW** | Auto-reviewer assignment |
| `.github/PULL_REQUEST_TEMPLATE.md` | **NEW** | Standard PR template (Korean) |
| `docs/git-workflow-gap-analysis.md` | **NEW** | Workflow automation gap analysis report |
| `.github/ISSUE_TEMPLATE/` | **NEW** | Bug / Feature / Security issue templates (replaces upstream) |
| `CONTRIBUTING.md` | **NEW** | Fork-specific contributor guide (replaces upstream) |
| `.github/release-drafter.yml` + `.github/workflows/release-drafter.yml` | **NEW** | Conventional-Commits-aware release draft automation |
| `.markdownlint.json` | **NEW** | Local markdownlint overrides (line_length=120, tables/code blocks exempt) |
| `.gitleaksignore` | **NEW** | Fingerprint allowlist for upstream pr-agent test fixtures |
| `scripts/go.mod` + `scripts/cmd/{branch-protection,deploy-to-repos,sync-secrets}/main.go` | **NEW** | Module-restructured Go scripts to enable `go test`. Invoke via `(cd scripts && go run ./cmd/<name>)`. |
| `scripts/cmd/branch-protection/main_test.go` + `scripts/cmd/deploy-to-repos/main_test.go` | **NEW** | Table-driven tests for pure-logic helpers (16 test cases) |
| `scripts/cmd/deploy-to-repos/main.go` | **NEW** | Deploy `pr-review.yml` to `jclee941/*` repos |
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
│   ├── pr-review.yml              # FORK: ubuntu-latest + cli_proxy (kimi-k2.6)
│   ├── security/pr-review.yml     # FORK: deep security review (Korean, label-gated)
│   └── sanity.yml                 # FORK: CI gate (replaces upstream CI)
├── scripts/
│   └── deploy-to-repos.go        # FORK: deploy workflow to jclee941/* repos
├── github_action/
│   └── entrypoint.sh             # Docker entrypoint for GitHub Action
├── .pr_agent.toml                 # FORK: cli_proxy config + existing pr-agent overrides
├── .env.example                   # cli_proxy env vars template
├── .env                           # local secrets (gitignored)
├── NOTICE                         # AGPL-3.0 attribution
├── LICENSE                        # AGPL-3.0 (unchanged)
├── AGENTS.md                      # THIS FILE
├── README.md                      # fork-specific readme
├── docs/
│   ├── review-templates/              # FORK: review templates (Korean)
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
| Workflow triggers | `.github/workflows/pr-review.yml` | PR events + slash commands |
| Security review config | `.github/workflows/security/pr-review.yml` | Triggered by `security-review` label |
| CI gate | `.github/workflows/sanity.yml` | TOML parse + pytest gate |
| Hardcode pattern scan | `.github/workflows/auto-hardcode-scan.yml` | Weekly cron + manual dispatch on `ubuntu-latest`, 15-minute timeout |
| Slash command handling | `pr_agent/servers/github_app.py`, `github_action_runner.py` | |
| Add a git provider | `pr_agent/git_providers/` | implement base class |
| Deploy to another repo | `scripts/cmd/deploy-to-repos/main.go` | Automates workflow + dependabot config sync to 11 downstream public repos (excludes `.github` source) |
| Apply branch protection | `scripts/cmd/branch-protection/main.go` | Enables auto-merge + safe protection on default branches of 12 public repos (includes `.github`) |
| Dependabot auto-merge config | `.github/workflows/dependabot-auto-merge.yml` | Auto-approves + merges patch/minor + github-actions PRs; majors flagged for review |
| Dependabot updates schedule | `.github/dependabot.yml` | Weekly `github-actions` + `pip` ecosystem PRs |
|| Upstream sync | `git fetch upstream && git merge upstream/main` | resolve conflicts in configuration.toml, .pr_agent.toml |
|| Edit review templates | `docs/review-templates/` | Korean-language review templates (code, docs, security) |
|| Configure documentation review | `.pr_agent.toml` `[pr_reviewer].extra_instructions` | Documentation checklist embedded in instructions |

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
| `hycu` | private | master | 🟡 partial (Dependabot only) | personal-account private repo on GitHub Free — has `.github/dependabot.yml` + `.github/workflows/dependabot-auto-merge.yml`, but `allow_auto_merge` and required-checks branch protection require GitHub Pro. Dependabot PRs auto-approve but await manual merge. |
| `youtube` | private | master | 🟡 partial (Dependabot only) | same as `hycu`. Dependabot covers github-actions, npm, pip, gomod, docker. |
| `propose` | private | master | 🟡 partial (Dependabot only) | same as `hycu`. Dependabot covers github-actions, npm. |

**Scope**: 12 public repos receive the full automation stack (auto-merge, branch protection, Dependabot, auto-review). The 3 private repos receive the platform-independent subset (Dependabot config + auto-merge approval workflow); branch protection and auto-merge button require GitHub Pro. The `pr-agent` fork has its own fork-local Dependabot setup.


### Per-repo automation guarantees

| Component | File | Behavior |
|-----------|------|----------|
| Auto-merge enable | repo settings | `allow_auto_merge=true`, `delete_branch_on_merge=true` |
| Branch protection | default branch | **3 required contexts**: `pr-checks / Check PR Title` (Conventional Commits), `pr-checks / Check Branch Name` (standard prefixes), `Gitleaks / scan` (secret-pattern detection). 4 advisory contexts (Size, Description, Large Files, Sensitive Files) comment-only. CodeQL surfaces results via Security tab, not as a required check. No force-push, no deletion, no admin enforcement. |
| Dependency updates | `.github/dependabot.yml` | Weekly `github-actions` + `pip` ecosystem PRs (pip groups minor+patch) |
| Auto-merge policy | `.github/workflows/dependabot-auto-merge.yml` | patch + minor + github_actions → squash auto-merge after required checks pass; major → manual review comment; null update-type → manual review comment |
| PR validation | `.github/workflows/pr-checks.yml` | sanity gates before merge |
| Auto-review | `.github/workflows/pr-review.yml` | Runs on every PR opened by anyone except `dependabot[bot]` and drafts (Dependabot has its own auto-merge path). Posts review via `pr-agent` against cli_proxy. |
| Static analysis | `.github/workflows/codeql.yml` | Python SAST on PR + weekly schedule (security-extended + security-and-quality queries) |
| Secret scanning | `.github/workflows/gitleaks.yml` | Required check on every PR/push; full-history scan on master |
| Workflow lint | `.github/workflows/actionlint.yml` | Validates GHA YAML semantics on workflow changes |

### Operations

```bash
# 1. Edit a workflow in .github/workflows/, or .github/dependabot.yml,
#    or .github/CODEOWNERS, or .github/PULL_REQUEST_TEMPLATE.md, or scripts/cmd/deploy-to-repos/main.go
# 2. Commit + push to master
# 3. auto-deploy.yml runs deploy-to-repos.go on a GitHub-hosted ubuntu-latest runner
#    → opens/updates PR "chore: standardize automation workflows + dependabot config"
#    in each downstream repo (force-push branch via --force-with-lease)
# 4. Each downstream PR auto-merges once its required branch-protection contexts pass (Title + Branch [+ Gitleaks after Phase 3])

# Manual deploy (local dev / CI bypass):
(cd scripts && go run ./cmd/deploy-to-repos) --dry-run                       # preview all
(cd scripts && go run ./cmd/deploy-to-repos) --repos=resume                  # canary one
(cd scripts && go run ./cmd/deploy-to-repos)                                 # apply to all 11 downstream

# Re-apply branch protection + auto-merge settings:
(cd scripts && go run ./cmd/branch-protection) --dry-run
(cd scripts && go run ./cmd/branch-protection)

# Sync CLIPROXY_API_KEY (and other shared secrets) to every public repo:
CLIPROXY_API_KEY=$(grep '^CLIPROXY_API_KEY=' .env | cut -d= -f2-) \
  (cd scripts && go run ./cmd/sync-secrets)
```

### Why pr-agent is handled separately

`jclee941/pr-agent` is a hard fork of `qodo-ai/pr-agent`. It carries upstream's own workflows (build-and-test.yaml, codeql.yml, release-drafter.yml, etc.) which would be overwritten by the deploy script. The fork is therefore excluded from `deploy-to-repos.go`, but it has its own fork-local `.github/dependabot.yml` (github-actions + pip ecosystems) and `.github/workflows/dependabot-auto-merge.yml` that are maintained directly on a `fork/*` branch. Sync upstream via `git fetch upstream && git merge upstream/main`.

## CLI_PROXY INTEGRATION DETAILS

| Item | Value |
|------|-------|
| **Service** | [`router-for-me/CLIProxyAPI`](https://github.com/router-for-me/CLIProxyAPI) |
| **Docker image** | `eceasy/cli-proxy-api:latest` |
| **Host** | LXC 100 on `pve3`, hostname `cliproxy.homelab.local` |
| **IP:port** | `192.168.50.114:8317` (primary) |
| **Additional ports** | `1455`, `8085`, `11451`, `51121`, `54545` (see `docker ps` on host) |
| **Config file** | `/opt/cli-proxy-api/config.yaml` (on LXC 100) |
| **Auth dir** | `/root/.cli-proxy-api/` (OAuth tokens for Codex, Antigravity) |
| **Auth method** | Bearer token in `Authorization` header |
| **API format** | OpenAI-compatible: `/v1/chat/completions`, `/v1/completions`, `/v1/models` |

### Available models (24 total as of 2026-04-10)

> **Current default**: `kimi-k2.6` with fallbacks `kimi-k2.5`, `claude-sonnet-4-6`.
> Prefix-less Kimi/Claude/GPT/Codex/Gemini model names are routed through the configured OpenAI-compatible cli_proxy endpoint.

- **Codex (GPT)**: `openai/gpt-5.2`, `openai/gpt-5.1`, `openai/gpt-5`, `gpt-5-codex-mini`, `gpt-5.1-codex-max`, `gpt-4.1`, `gpt-4.1-mini`
- **Antigravity (Gemini)**: `gemini-3-pro-preview`, `gemini-3-flash-preview`, `gemini-2.5-flash`
- **Antigravity (Claude)**: `claude-sonnet-4-6`, `ag-claude-sonnet-4-5`, `ag-claude-sonnet-4-5-thinking`

Get the full list:
```bash
curl -sS http://192.168.50.114:8317/v1/models \
  -H "Authorization: Bearer $CLIPROXY_API_KEY" | jq -r '.data[].id'
```

### Retrieving the API key

```bash
ssh root@192.168.50.114 \
  "python3 -c 'import yaml; print(yaml.safe_load(open(\"/opt/cli-proxy-api/config.yaml\"))[\"api-keys\"][0])'"
```

Rotate: edit `/opt/cli-proxy-api/config.yaml` on LXC 100, restart the docker container:
```bash
ssh root@192.168.50.114 "docker restart cli-proxy-api"
```

## PR-AGENT WORKFLOW ENV VAR CONVENTIONS

pr-agent loads its settings via `Dynaconf(envvar_prefix=False, ...)` (see `pr_agent/config_loader.py:18`). With no prefix, **only specific env-var spellings reach the nested settings tree** — the bug-fix history is non-obvious. Memorise this table before adding any new env var to `pr-review.yml` or `security/pr-review.yml`:

| Setting key (used in pr-agent code) | Wrong env name | Correct env name | Why |
|------|----------------|------------------|-----|
| `settings.github.user_token` | `GITHUB_TOKEN` (fork-broken) | **`GITHUB__USER_TOKEN`** (double underscore) | Single-underscore creates flat key `GITHUB_TOKEN`; dynaconf nested path requires `__` |
| `settings.openai.key` | `OPENAI_KEY` (fork-broken) | **`OPENAI.KEY`** (literal dot) | Same reason. Dot syntax also works in GH Actions YAML `env:` blocks |
| `settings.openai.api_base` | — | `OPENAI.API_BASE` | Literal dot |
| `settings.config.model` | — | `CONFIG.MODEL` | Literal dot |
| `settings.config.fallback_models` | — | `CONFIG.FALLBACK_MODELS` | Literal dot |
| `settings.config.custom_model_max_tokens` | omit (forces MAX_TOKENS lookup) | **`CONFIG.CUSTOM_MODEL_MAX_TOKENS=128000`** | `kimi-k2.6` is NOT in `pr_agent/algo/__init__.py:MAX_TOKENS`; without this, prompt-trim refuses to call litellm |
| `settings.pr_reviewer.require_*` | — | `PR_REVIEWER.REQUIRE_*` | Literal dot |

**Special case — `security/pr-review.yml` only**: that workflow invokes `pr_agent.servers.github_action_runner` directly, which manually translates `GITHUB_TOKEN` → `settings.github.user_token` and `OPENAI_KEY` → `settings.openai.key` at `pr_agent/servers/github_action_runner.py:55-61`. Both env-var styles work there, but for consistency the fork uses the same `OPENAI.KEY` / `GITHUB__USER_TOKEN` everywhere.

**Silent-failure guard** (`pr-review.yml:141`): pr-agent's CLI catches its own exceptions in `pr_reviewer.py:184` and **returns exit code 0 even on fatal failures**. The workflow `tee`s output to `/tmp/pr-agent.log` and `grep`s for known fatal patterns (`Failed to generate prediction with any model`, `Failed to review PR`, `AuthenticationError`, etc.) — known no-op patterns (`Empty diff for PR:`, `PR has no files:`, `Review output is not published`) are subtracted to avoid false positives. The full pattern list is in the workflow's run-step.

**Phase 3 rollout completed (2026-05-03)**: Branch protection on all 12 public repos now enforces `Gitleaks / scan` as a third required status check. To re-apply after editing `branch-protection.go`, run `(cd scripts && go run ./cmd/branch-protection)` from this repo.


## COMMANDS

```bash
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
curl -sS http://192.168.50.114:8317/v1/chat/completions \
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
# Copy .github/workflows/pr-review.yml to the target repo manually
```

## CONVENTIONS

- **Python**: ≥ 3.12, ruff 120-char line length, isort imports, double quotes
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`)
- **Fork-specific commits**: tag with scope `fork:` (e.g. `feat(fork): pin model to kimi-k2.6`)
- **Upstream sync commits**: `chore(upstream): merge qodo-ai/pr-agent@<sha>`
- **Secrets**: only in `.env`, `.secrets.toml`, or GitHub Actions secrets — never in TOML/YAML in git
- **Type safety**: never suppress (`as any`, `@ts-ignore`, `# type: ignore[...]` without justification)

## ANTI-PATTERNS

- **Never** hardcode the cli_proxy API key in any tracked file
- **Never** commit `.env`, `.secrets.toml`, `pr_agent/settings/.secrets.toml`, or anything under `.cache/`
- **Never** edit `pr_agent/settings/configuration.toml` beyond the cli_proxy model line — it conflicts with every upstream merge
- **Never** run PR review on PRs from untrusted forks under `pull_request_target` without a head-repo guard — code execution / token-theft risk. The current guard in `.github/workflows/security/pr-review.yml` requires `head.repo.full_name == github.repository`.
- **Never** push to `main` without running at least `pytest tests/unittest/test_fix_json_escape_char.py`
- **Never** delete or rename upstream prompt TOML files (e.g. `pr_agent/settings/pr_reviewer_prompts.toml`) — they're the single source of truth for prompts

## SECURITY NOTES

- `CLIPROXY_API_KEY` is stored as GitHub repo secret AND locally in `.env` (chmod 600)
- GitHub-hosted `ubuntu-latest` runners read `CLIPROXY_API_KEY` from repo secrets; the homelab cli_proxy is reached over the public internet at `https://cliproxy.jclee.me/v1`. Treat the secret as compromised if it is ever printed to a workflow log.
- cli_proxy has no network ACL — any workstation on `192.168.50.0/24` with the key can call it
- AGPL-3.0 compliance: this is a private deployment serving only jclee941; source access is provided via this repo itself to authorized users (which is just jclee941)

## FORK ATTRIBUTION

## REVIEW TEMPLATES

> Korean-language review templates for the `jclee-bot` GitHub App.
Located in `docs/review-templates/` and referenced from `.pr_agent.toml`.

| Template | Purpose | Trigger |
|----------|---------|---------|
| `code-review-template.md` | Master review format, priorities, severity levels | Every `/review` |
| `documentation-checklist.md` | README, API docs, docstring, PR description checks | Embedded in `extra_instructions` |
| `security-review-template.md` | OWASP Top 10, secret scanning, SAST checks | `security-review` label or `/agentic_review --security` |

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
