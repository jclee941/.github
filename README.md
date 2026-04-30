# github-bot

> Private AI-powered PR reviewer for `jclee941/*` repos. Hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent), backed by the homelab **CLIProxyAPI** at `192.168.50.114:8317`.

[![Fork of pr-agent](https://img.shields.io/badge/fork-qodo--ai%2Fpr--agent-blue)](https://github.com/qodo-ai/pr-agent)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](LICENSE)
[![Deployment: GitHub App](https://img.shields.io/badge/deployment-GitHub%20App-green)](#architecture)

---

## What is this?

A hard fork of PR-Agent wired to run entirely inside the jclee941 homelab as a **GitHub App**:

- **LLM backend**: [`router-for-me/CLIProxyAPI`](https://github.com/router-for-me/CLIProxyAPI) on LXC 100 (`192.168.50.114:8317`), wrapping Claude Code CLI / Codex CLI / Gemini CLI as an OpenAI-compatible API
- **Deployment**: GitHub App `jclee-bot` (ID: 3540327) running on LXC 100 via Cloudflare Tunnel
- **Default model**: `kimi-k2.6` (via cli_proxy), fallback `kimi-k2.5`, `claude-sonnet-4-6`
- **Scope**: Private — for `jclee941/*` repositories only
- **Webhook**: `https://bot.jclee.me/api/v1/github_webhooks`

No data leaves the homelab LAN. PR reviews go straight from GitHub webhook → Cloudflare Tunnel → LXC 100 → internal cli_proxy → back to GitHub.

## Features (inherited from pr-agent)

| Command | Purpose |
|---------|---------|
| `/review` | Full PR review (security, performance, architecture, tests) |
| `/improve` | Inline code improvement suggestions |
| `/describe` | Auto-generate PR title + description + changes walkthrough |
| `/ask <question>` | Ask about the diff |
| `/update_changelog` | Append changelog entry |
| `/help` | List all commands |

**Core abilities**: PR compression (handles large diffs), dynamic context, incremental update, self-reflection, multi-model fallback.

See [docs/pr-agent-upstream-README.md](docs/pr-agent-upstream-README.md) for the full feature reference from upstream.

## Documentation Review

Every PR review automatically checks for documentation completeness:

- **README.md** — new features, API changes, config options require updates
- **API docs** — endpoint changes need spec updates
- **Code comments** — complex logic requires inline explanations
- **PR description** — clarity and completeness of the change rationale
- **Config examples** — `.env`/`.toml` changes need documentation

The bot suggests specific documentation updates in review comments when gaps are detected.

## Review Templates

Structured Korean-language review templates live in [`docs/review-templates/`](docs/review-templates/):

| Template | File | Purpose |
|----------|------|---------|
| Code Review | [`code-review-template.md`](docs/review-templates/code-review-template.md) | Master format, priorities, severity levels |
| Documentation | [`documentation-checklist.md`](docs/review-templates/documentation-checklist.md) | README, API docs, docstring checks |
| Security | [`security-review-template.md`](docs/review-templates/security-review-template.md) | OWASP Top 10, secret scanning, SAST |

These templates define the review standards used by `jclee-bot`. Modify the templates and update `.pr_agent.toml` `extra_instructions` to change review behavior.

## Architecture

```
  PR event on jclee941/<repo>
            │
            ▼
  GitHub App: jclee-bot
  Webhook URL: https://bot.jclee.me/api/v1/github_webhooks
            │
            ▼
  Cloudflare Tunnel (bot.jclee.me)
            │
            ▼
  github-bot-app container (LXC 100, localhost:3001)
            │
            ▼
  litellm.completion(model="kimi-k2.6",
                     api_base="http://localhost:8317/v1")
            │
            ▼
  CLIProxyAPI  (docker container on LXC 100)
            │
            ▼
  Claude Code CLI / Codex CLI / Gemini CLI
            │
            ▼
  Review posted back to PR via GitHub REST API
```

## Quick start

The GitHub App `jclee-bot` is already installed on all `jclee941/*` repositories. No per-repo setup is required.

### 1. Open a PR

Create a pull request in any `jclee941/*` repository. The bot will automatically review it if configured to do so.

### 2. Use slash commands

Comment on any PR with:

```text
/review
/describe
/improve
/ask What does this PR change?
```

The bot will respond via the GitHub App installation.

## Local development

```bash
git clone https://github.com/jclee941/github-bot
cd github-bot

# Env setup
cp .env.example .env
# .env is already populated if you ran the setup script; otherwise fill CLIPROXY_API_KEY

# Python setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .

# Run a review locally
set -a; source .env; set +a
python -m pr_agent.cli --pr_url https://github.com/jclee941/<repo>/pull/<N> review
```

## Fork lineage

- **Upstream**: [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) (AGPL-3.0)
- **Base commit**: [`d82f7d3e`](https://github.com/qodo-ai/pr-agent/commit/d82f7d3e) (2026-04-10)
- **Attribution**: [NOTICE](NOTICE)

### Sync with upstream

```bash
git fetch upstream
git merge upstream/main
# Expected conflict areas:
#   - pr_agent/settings/configuration.toml  (our cli_proxy model override)
#   - .pr_agent.toml                         (our [openai].api_base override)
git push origin main
```

## License

[AGPL-3.0](LICENSE) (inherited). Per AGPL-3.0 §13: if you modify and deploy this as a network service, you must offer source access to users interacting with it. This is a private bot running only on the homelab, so compliance is trivial — this repo + its fork graph is the source.

## See also

- [AGENTS.md](AGENTS.md) — project knowledge base for AI agents and new contributors
- [docs/pr-agent-upstream-README.md](docs/pr-agent-upstream-README.md) — original pr-agent README
- [NOTICE](NOTICE) — AGPL-3.0 attribution
- Upstream CLIProxyAPI: [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)
