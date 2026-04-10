# github-bot — PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-10
**Upstream base:** qodo-ai/pr-agent @ `d82f7d3e`

## OVERVIEW

AI-powered PR reviewer for `jclee941/*` private repos. Hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) (AGPL-3.0), rewired to use the homelab `CLIProxyAPI` at `192.168.50.114:8317` as the LLM backend, deployed on self-hosted runners with the `homelab` label.

All upstream pr-agent features are preserved: `/review`, `/improve`, `/describe`, `/ask`, `/update_changelog`, PR compression, dynamic context, multi-model fallback, slash commands.

## FORK DELTA (what changed vs upstream)

| File | Change | Reason |
|------|--------|--------|
| `pr_agent/settings/configuration.toml` | `[config] model` → `openai/gpt-5.2`, `fallback_models` → `["claude-sonnet-4-6"]` | Default model via cli_proxy instead of direct OpenAI |
| `.pr_agent.toml` | Prepended `[config]` and `[openai]` sections | Pin fork-level model and `api_base` to cli_proxy |
| `.github/workflows/pr-review.yml` | **NEW** | Self-hosted runner + cli_proxy env vars |
| `README.md` | **REPLACED** | Fork-specific readme (upstream moved to `docs/pr-agent-upstream-README.md`) |
| `AGENTS.md` | **REPLACED** | This file |
| `NOTICE` | **NEW** | AGPL-3.0 attribution to upstream |
| `.env.example`, `.env` | **NEW** | cli_proxy env vars (`.env` is gitignored) |
| `docs/pr-agent-upstream-README.md` | **MOVED** | Preserved upstream README for reference |

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
│   ├── pr-agent-review.yaml       # upstream template (kept for reference)
│   ├── build-and-test.yaml        # upstream CI
│   └── ...
├── .pr_agent.toml                 # FORK: cli_proxy config + existing pr-agent overrides
├── .env.example                   # cli_proxy env vars template
├── .env                           # local secrets (gitignored)
├── NOTICE                         # AGPL-3.0 attribution
├── LICENSE                        # AGPL-3.0 (unchanged)
├── AGENTS.md                      # THIS FILE
├── README.md                      # fork-specific readme
├── docs/
│   ├── pr-agent-upstream-README.md  # original pr-agent README
│   └── docs/                      # mkdocs site (upstream)
└── tests/                         # upstream pytest suite
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Change default model | `pr_agent/settings/configuration.toml` `[config].model` | Line 7, currently `openai/gpt-5.2` |
| Override model per-repo | `.pr_agent.toml` `[config].model` | Fork-level override, takes precedence |
| Change cli_proxy endpoint | `.pr_agent.toml` `[openai].api_base` | Currently `http://192.168.50.114:8317/v1` |
| Edit review prompts | `pr_agent/settings/pr_reviewer_prompts.toml` | upstream TOML |
| Edit improve prompts | `pr_agent/settings/code_suggestions/` | |
| Workflow triggers | `.github/workflows/pr-review.yml` | PR events + slash commands |
| Slash command handling | `pr_agent/servers/github_app.py`, `github_action_runner.py` | |
| Add a git provider | `pr_agent/git_providers/` | implement base class |
| Upstream sync | `git fetch upstream && git merge upstream/main` | resolve conflicts in configuration.toml, .pr_agent.toml |

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
set -a; source .env; set +a
python -m pr_agent.cli --pr_url https://github.com/jclee941/<repo>/pull/<N> review

# ==================
# Test cli_proxy connectivity
# ==================
source .env
curl -sS http://192.168.50.114:8317/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CLIPROXY_API_KEY" \
  -d '{"model":"openai/gpt-5.2","messages":[{"role":"user","content":"ping"}],"max_tokens":10}'

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
REPO=jclee941/<target-repo>
gh -R "$REPO" secret set CLIPROXY_API_KEY --body "$(cat /home/jclee/.cache/sisyphus/cliproxy-api-key)"
# Copy .github/workflows/pr-review.yml to the target repo manually or via a script
```

## CONVENTIONS

- **Python**: ≥ 3.12, ruff 120-char line length, isort imports, double quotes
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`)
- **Fork-specific commits**: tag with scope `fork:` (e.g. `feat(fork): pin model to openai/gpt-5.2`)
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

- **Upstream**: [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) — AGPL-3.0 © 2023-2026 CodiumAI / Qodo contributors
- **Base commit**: `d82f7d3e` (`fix: prevent dummy_key from overriding provider-specific API keys`)
- **Forked by**: `jclee941`
- **Fork date**: 2026-04-10
- **This fork**: AGPL-3.0 (inherited), see [LICENSE](LICENSE) and [NOTICE](NOTICE)
