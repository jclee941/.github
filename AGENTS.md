# github-bot — PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-14
**Upstream base:** qodo-ai/pr-agent @ `d82f7d3e`

## OVERVIEW

AI-powered PR reviewer for `jclee941/*` private repos. Hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) (AGPL-3.0), rewired to use the homelab `CLIProxyAPI` at `192.168.50.114:8317` as the LLM backend, deployed on self-hosted runners with the `homelab` label.

All upstream pr-agent features are preserved: `/review`, `/improve`, `/describe`, `/ask`, `/update_changelog`, PR compression, dynamic context, multi-model fallback, slash commands.

## FORK DELTA (what changed vs upstream)

| File | Change | Reason |
|------|--------|--------|
| `pr_agent/settings/configuration.toml` | `[config] model` → `kimi-k2.6`, `fallback_models` → `["kimi-k2.5", "claude-sonnet-4-6"]` | Default model via cli_proxy/OpenAI-compatible routing |
| `.pr_agent.toml` | Prepended `[config]`, `[openai]`, `[litellm]` sections | Pin fork-level model and `api_base` to cli_proxy |
| `.github/workflows/pr-review.yml` | **NEW** | Self-hosted runner + cli_proxy env vars |
| `.github/workflows/pr-review-security.yml` | **NEW** | Deep security review (Korean, `pull_request_target`) |
| `.github/workflows/sanity.yml` | **NEW** | Fork CI gate (replaces upstream CI) |
| `scripts/deploy-to-repos.go` | **NEW** | Deploy `pr-review.yml` to `jclee941/*` repos |
| `README.md` | **REPLACED** | Fork-specific readme (upstream moved to `docs/pr-agent-upstream-README.md`) |
| `AGENTS.md` | **REPLACED** | This file |
| `NOTICE` | **NEW** | AGPL-3.0 attribution to upstream |
| `.env.example`, `.env` | **NEW** | cli_proxy env vars (`.env` is gitignored) |
| `docs/pr-agent-upstream-README.md` | **MOVED** | Preserved upstream README for reference |
| `action.yaml` | **REMOVED** | Upstream GitHub Marketplace metadata (unused by fork) |
| `Dockerfile.github_action_dockerhub` | **REMOVED** | Upstream Docker Hub image ref (unused by fork) |
| `docker/` | **REMOVED** | Multi-provider Dockerfiles — GitHub App, Lambda (unused by fork) |
| `.github/ISSUE_TEMPLATE/` | **REMOVED** | Upstream issue templates (fork uses Archon) |
| `.github/workflows/pr-agent-review.yaml` | **REMOVED** | Upstream action template |
| `.github/workflows/e2e_tests.yaml` | **REMOVED** | Upstream E2E tests (Docker-based) |
| `.github/workflows/pre-commit.yml` | **REMOVED** | Disabled upstream pre-commit |
| `.github/workflows/build-and-test.yaml` | **REMOVED** | Upstream CI |
| `.github/workflows/code_coverage.yaml` | **REMOVED** | Upstream CI |
| `.github/workflows/docs-ci.yaml` | **REMOVED** | Upstream CI |
| `tests/e2e_tests/` | **REMOVED** | Upstream E2E test suite |
| `tests/health_test/` | **REMOVED** | Upstream health check |
| `pr_compliance_checklist.yaml` | **REMOVED** | Upstream compliance artifact |
| `CONTRIBUTING.md` | **REMOVED** | Upstream contributing guide (references Discord, qodo.ai) |
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
│   ├── pr-review.yml              # FORK: self-hosted + cli_proxy
│   ├── pr-review-security.yml     # FORK: deep security review (Korean)
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
| Security review config | `.github/workflows/pr-review-security.yml` | Triggered by `security-review` label |
| CI gate | `.github/workflows/sanity.yml` | TOML parse + pytest gate |
| Slash command handling | `pr_agent/servers/github_app.py`, `github_action_runner.py` | |
| Add a git provider | `pr_agent/git_providers/` | implement base class |
| Deploy to another repo | `scripts/deploy-to-repos.go` | Automates workflow + dependabot config sync to all 12 public repos |
| Apply branch protection | `scripts/branch-protection.go` | Enables auto-merge + safe protection on default branches (12 public repos) |
| Dependabot auto-merge config | `.github/workflows/dependabot-auto-merge.yml` | Auto-approves + merges patch/minor + github-actions PRs; majors flagged for review |
| Dependabot updates schedule | `.github/dependabot.yml` | Weekly github-actions ecosystem PRs |
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
| `hycu` | private | master | ⚠️ excluded by platform | personal-account private repo on GitHub Free cannot have branch protection or `allow_auto_merge`. Revisit after upgrading to GitHub Pro. |
| `youtube` | private | master | ⚠️ excluded by platform | same as `hycu`. |
| `propose` | private | master | ⚠️ excluded by platform | same as `hycu`. |

**Scope**: 12 public jclee941 repos receive the full automation stack. The 3 private repos and the `pr-agent` fork are deliberately excluded — see Reason column.


### Per-repo automation guarantees

| Component | File | Behavior |
|-----------|------|----------|
| Auto-merge enable | repo settings | `allow_auto_merge=true`, `delete_branch_on_merge=true` |
| Branch protection | default branch | 6 required `pr-checks / *` status contexts (Size, Title, Branch Name, Description, Large Files, Sensitive Files) gate auto-merge; no force-push, no deletion, no admin enforcement |
| Dependency updates | `.github/dependabot.yml` | Weekly github-actions ecosystem PRs |
| Auto-merge policy | `.github/workflows/dependabot-auto-merge.yml` | patch + minor + github_actions → squash auto-merge after required checks pass; major → manual review comment; null update-type → manual review comment |
| PR validation | `.github/workflows/pr-checks.yml` | sanity gates before merge |
| Auto-review | `.github/workflows/pr-review.yml` | Runs on every PR opened by anyone except `dependabot[bot]` and drafts (Dependabot has its own auto-merge path). Posts review via `pr-agent` against cli_proxy. |

### Operations

```bash
# 1. Edit a workflow in .github/workflows/ or update .github/dependabot.yml
# 2. Commit + push to master
# 3. auto-deploy.yml runs deploy-to-repos.go on the self-hosted runner
#    → opens/updates PR "chore: standardize automation workflows + dependabot config"
#    in each downstream repo (force-push branch via --force-with-lease)
# 4. Each downstream PR auto-merges once its sanity check passes

# Manual deploy (local dev / CI bypass):
go run scripts/deploy-to-repos.go --dry-run                       # preview all
go run scripts/deploy-to-repos.go --repos=resume                  # canary one
go run scripts/deploy-to-repos.go                                 # apply to all 12

# Re-apply branch protection + auto-merge settings:
go run scripts/branch-protection.go --dry-run
go run scripts/branch-protection.go

# Sync CLIPROXY_API_KEY (and other shared secrets) to every public repo:
CLIPROXY_API_KEY=$(grep '^CLIPROXY_API_KEY=' .env | cut -d= -f2-) \
  go run scripts/sync-secrets.go
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
go run scripts/deploy-to-repos.go

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
- **Never** run PR review on PRs from untrusted forks using the self-hosted runner without a `pull_request_target` gate — code execution risk
- **Never** push to `main` without running at least `pytest tests/unittest/test_fix_json_escape_char.py`
- **Never** delete or rename upstream prompt TOML files (e.g. `pr_agent/settings/pr_reviewer_prompts.toml`) — they're the single source of truth for prompts

## SECURITY NOTES

- `CLIPROXY_API_KEY` is stored as GitHub repo secret AND locally in `.env` (chmod 600)
- Self-hosted runner at `.111`/`.200` must be trusted — it sees the key as env var during workflow runs
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
