# pr-agent Fork for jclee941

> 개인 homelab CLIProxyAPI 백엔드를 사용하는 AI 기반 PR 리뷰어 및 자동화 봇

![Project Version](https://img.shields.io/badge/version-0.3.1-blue.svg)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/upstream-qodo--ai/pr--agent-red.svg)](https://github.com/qodo-ai/pr-agent)
![Model](https://img.shields.io/badge/model-kimi--k2.6-purple.svg)

---

## Overview | 개요

This repository is a hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent), customized for `jclee941/*` repositories. It uses the homelab-hosted CLIProxyAPI (`192.168.50.114:8317`) as the primary LLM backend, accessible externally via `https://cliproxy.jclee.me/v1`.

이 저장소는 `jclee941/*` 저장소를 위해 커스터마이징된 [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)의 하드 포크입니다. 개인 homelab에 호스팅된 CLIProxyAPI (`192.168.50.114:8317`)를 주요 LLM 백엔드로 사용하며, 외부에서는 `https://cliproxy.jclee.me/v1`를 통해 접근합니다.

### Key Features | 주요 기능

- **Primary Model:** `kimi-k2.6` (via CLIProxyAPI)
- **Fallback Models:** `minimax-m2.7`, `gpt-5.5` (via CLIProxyAPI CLI fallback)
- **56 GitHub Actions Workflows** for comprehensive automation
- **8 Go Automation Tools** for repository management
- **Multi-provider Support:** GitHub, GitLab, Bitbucket, Azure DevOps, Gitea, CodeCommit

---

## Features | 기능

### AI-Powered PR Review

- `/review` - Comprehensive PR review with security, performance, and style checks
- `/improve` - Suggest code improvements
- `/describe` - Generate PR description from diff
- `/ask` - Answer questions about the codebase
- `/update_changelog` - Automatic changelog updates

### Workflow Automation | 워크플로우 자동화

| Category | Workflows |
|----------|-----------|
| PR Lifecycle | PR checks, auto-merge, stale bot, review assignment |
| Issue Management | Issue creation, labeling, lifecycle management |
| Security | CodeQL, Gitleaks, dependency review, security PR review |
| Release Management | Release drafter, publish, changelog generation |
| Repository Health | Health monitoring, drift detection, downstream checks |
| Documentation | Auto-docs sync, README generation, template sync |

### Supported Providers | 지원 프로바이더

- GitHub (primary)
- GitLab
- Bitbucket
- Azure DevOps
- Gitea
- AWS CodeCommit

---

## Architecture | 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    GitHub Actions                        │
│                  (ubuntu-latest runners)                  │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  pr-agent (v0.3.1)                       │
│              Python 3.12+ / FastAPI                      │
└──────────┬────────────────────────────┬──────────────────┘
           │                            │
           ▼                            ▼
┌──────────────────────┐    ┌─────────────────────────────┐
│   CLIProxyAPI        │    │   Go Automation Tools       │
│  (Homelab Backend)   │    │  - branch-protection        │
│  kimi-k2.6           │    │  - repo-review              │
│  minimax-m2.7        │    │  - sync-secrets             │
│  gpt-5.5             │    │  - deploy-to-repos          │
│  (fallback)          │    │  - rulesets-manager         │
└──────────────────────┘    │  - drift-detector           │
    ▲                       │  - repo-metadata            │
    │                       │  - validate-naming          │
    │                       └─────────────────────────────┘
    │
┌────┴─────────────────────────────────────────────────────┐
│              CLIProxyAPI at 192.168.50.114:8317         │
│         (External: https://cliproxy.jclee.me/v1)          │
└──────────────────────────────────────────────────────────┘
```

### Upstream Reference

For upstream pr-agent documentation, see [docs/pr-agent-upstream-README.md](docs/pr-agent-upstream-README.md).

---

## Automation Inventory | 자동화 인벤토리

### GitHub Actions Workflows (56 total) | 깃헙 액션 워크플로우

#### Pull Request Workflows | PR 워크플로우

| # | Workflow File | Description |
|---|---------------|-------------|
| 01 | `01_branch-to-pr.yml` | Convert branch to PR |
| 02 | `02_issue-to-branch.yml` | Create branch from issue |
| 03 | `03_pr-checks.yml` | PR validation checks |
| 09 | `09_semantic-pr.yml` | Semantic PR validation |
| 10 | `10_pr-review.yml` | AI PR review |
| 11 | `security/11_pr-review.yml` | Security-focused PR review |
| 13 | `13_pr-auto-merge.yml` | Auto-merge PRs |
| 14 | `14_bot-auto-fix.yml` | Bot auto-fix automation |
| 15 | `15_merged-pr-cleanup.yml` | Post-merge cleanup |
| 17 | `17_pr-stale-bot.yml` | Mark stale PRs |
| 81 | `81_auto-merge.yml` | Generic auto-merge |
| 85 | `85_pr-normalize.yml` | PR normalization |
| 86 | `86_pr-review-security.yml` | Additional security review |
| 87 | `87_pr-size.yml` | PR size tracking |

#### Issue Workflows | 이슈 워크플로우

| # | Workflow File | Description |
|---|---------------|-------------|
| 16 | `16_stale-repo-identifier.yml` | Identify stale repos |
| 18 | `18_issue-management.yml` | Issue management |
| 19 | `19_issue-backfill.yml` | Issue backfill |
| 82 | `82_issue-label.yml` | Issue labeling |
| 83 | `83_issue-lifecycle.yml` | Issue lifecycle management |
| 88 | `88_stale.yml` | Generic stale management |

#### Security Workflows | 보안 워크플로우

| # | Workflow File | Description |
|---|---------------|-------------|
| 04 | `04_actionlint.yml` | GitHub Actions YAML linting |
| 05 | `05_gitleaks.yml` | Secret detection |
| 06 | `06_codeql.yml` | CodeQL analysis |
| 07 | `07_dependency-review.yml` | Dependency review |
| 08 | `08_scorecard.yml` | Security scorecard |
| 11 | `11_pr-review.yml` (security/) | Deep security review |

#### Release Workflows | 릴리스 워크플로우

| # | Workflow File | Description |
|---|---------------|-------------|
| 22 | `22_template-sync.yml` | Template synchronization |
| 23 | `23_release-drafter.yml` | Release draft generation |
| 24 | `24_release-notes.yml` | Release notes generation |
| 25 | `25_release-publish.yml` | Release publishing |

#### Health & Monitoring | 헬스 및 모니터링

| # | Workflow File | Description |
|---|---------------|-------------|
| 26 | `26_elk-health-check.yml` | ELK stack health |
| 27 | `27_elk-setup.yml` | ELK setup |
| 28 | `28_bot-health-monitor.yml` | Bot health monitoring |
| 29 | `29_downstream-health-check.yml` | Downstream repo health |
| 30 | `30_runtime-health-check.yml` | Runtime health checks |
| 31 | `31_repo-health.yml` | Repository health |
| 32 | `32_org-health-report.yml` | Organization health report |

#### Automation & Maintenance | 자동화 및 유지보수

| # | Workflow File | Description |
|---|---------------|-------------|
| 12 | `12_dependabot-auto-merge.yml` | Dependabot auto-merge |
| 33 | `33_drift-detector.yml` | Configuration drift detection |
| 34 | `34_auto-deploy.yml` | Auto-deployment |
| 35 | `35_auto-hardcode-scan.yml` | Hardcode pattern scanning |
| 36 | `36_build-and-push-app.yml` | Build and push app |
| 37 | `37_ci-failure-issues.yml` | CI failure issue creation |
| 38 | `38_e2e.yml` | End-to-end tests |
| 39 | `39_e2e-live.yml` | Live E2E tests |
| 40 | `40_repo-review-batch.yml` | Batch repo review |
| 41 | `41_reusable-ci.yml` | Reusable CI template |
| 42 | `42_reusable-docs-sync.yml` | Reusable docs sync |
| 43 | `43_reusable-issue-management.yml` | Reusable issue management |
| 44 | `44_reusable-pr-checks.yml` | Reusable PR checks |
| 45 | `45_reusable-gitleaks.yml` | Reusable Gitleaks |
| 60 | `60_ci-auto-heal.yml` | CI auto-healing |
| 84 | `84_labeler.yml` | PR/Issue labeler |
| 89 | `89_welcome.yml` | Welcome new contributors |
| 90 | `90_sanity.yml` | Sanity checks |

### Go Automation Tools (8 total) | Go 자동화 도구

| Tool | Description | Path |
|------|-------------|------|
| `branch-protection` | Manage branch protection rules | `scripts/cmd/branch-protection/` |
| `deploy-to-repos` | Deploy PR review workflow to repos | `scripts/cmd/deploy-to-repos/` |
| `drift-detector` | Detect configuration drift | `scripts/cmd/drift-detector/` |
| `repo-metadata` | Manage repository metadata | `scripts/cmd/repo-metadata/` |
| `repo-review` | Review repository configuration | `scripts/cmd/repo-review/` |
| `rulesets-manager` | Manage GitHub Rulesets | `scripts/cmd/rulesets-manager/` |
| `sync-secrets` | Synchronize secrets across repos | `scripts/cmd/sync-secrets/` |
| `validate-naming` | Validate naming conventions | `scripts/cmd/validate-naming/` |

---

## Quick Start | 빠른 시작

### Prerequisites | 전제 조건

- Python 3.12+
- GitHub token with appropriate permissions
- Access to CLIProxyAPI (`https://cliproxy.jclee.me`)

### Installation | 설치

```bash
# Clone repository
git clone https://github.com/jclee941/.github
cd pr-agent

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your settings
```

### Configuration | 설정

Create a `.env` file or set environment variables:

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_API_BASE="https://cliproxy.jclee.me/v1"
export GITHUB_TOKEN="your-github-token"
```

Or create `.pr_agent.toml`:

```toml
[config]
model = "kimi-k2.6"
fallback_models = ["minimax-m2.7", "gpt-5.5"]

[openai]
api_key = "your-api-key"
api_base = "https://cliproxy.jclee.me/v1"

[litellm]
fallback_models = ["minimax-m2.7", "gpt-5.5"]
```

### Running the Bot | 봇 실행

```bash
# Interactive mode
pr-agent

# With specific command
pr-agent review --pr_url https://github.com/owner/repo/pull/123

# Run as GitHub App
python -m pr_agent.app
```

---

## Local Development | 로컬 개발

### Development Setup | 개발 환경 설정

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Install Go dependencies (for Go tools)
cd scripts
go mod download
```

### Running Tests | 테스트 실행

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run E2E tests
make test-e2e

# Run live tests
make test-live

# Lint code
make lint
```

### Go Tools Development | Go 도구 개발

```bash
# Navigate to scripts directory
cd scripts

# Run a specific tool
go run ./cmd/branch-protection
go run ./cmd/repo-review
go run ./cmd/deploy-to-repos

# Run tests for Go tools
go test ./...
```

### Project Structure | 프로젝트 구조

```
.
├── pr_agent/           # Main Python package
│   ├── agents/         # AI agents
│   ├── cli/            # CLI interface
│   ├── modules/        # Core modules
│   └── tools/          # Tool implementations
├── scripts/            # Go automation tools
│   └── cmd/            # Tool commands
│       ├── branch-protection/
│       ├── deploy-to-repos/
│       ├── drift-detector/
│       ├── repo-metadata/
│       ├── repo-review/
│       ├── rulesets-manager/
│       ├── sync-secrets/
│       └── validate-naming/
├── .github/            # GitHub configuration
│   ├── workflows/      # GitHub Actions workflows (56)
│   └── ISSUE_TEMPLATE/ # Issue templates
├── docs/               # Documentation
├── tests/              # Test suites
│   ├── unittest/       # Unit tests
│   └── e2e/            # End-to-end tests
└── config/             # Configuration files
```

---

## Commands Reference | 명령어 참고

### Python CLI | Python CLI

```bash
# PR Review
pr-agent review --pr_url https://github.com/owner/repo/pull/123

# PR Improve
pr-agent improve --pr_url https://github.com/owner/repo/pull/123

# PR Describe
pr-agent describe --pr_url https://github.com/owner/repo/pull/123

# Ask Question
pr-agent ask --question "How does X work?" --pr_url https://github.com/owner/repo/pull/123

# Update Changelog
pr-agent update_changelog --pr_url https://github.com/owner/repo/pull/123

# Run as server
pr-agent serve --port 8080
```

### Make Commands | Make 명령어

```bash
make install        # Install package and dependencies
make test           # Run all tests (unit + e2e + live)
make test-unit      # Run unit tests only
make test-e2e       # Run E2
