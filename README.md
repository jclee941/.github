# pr-agent Fork for jclee941 | jclee941용 pr-agent 포크

> 개인 homelab CLIProxyAPI 백엔드를 사용하는 AI 기반 PR 리뷰어 및 자동화 봇
> AI-powered PR reviewer and automation bot backed by a homelab CLIProxyAPI

[![Project Version](https://img.shields.io/badge/version-0.3.1-blue.svg)](https://github.com/qodo-ai/pr-agent)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/upstream-qodo--ai/pr--agent-red.svg)](https://github.com/qodo-ai/pr-agent)
![Model](https://img.shields.io/badge/model-kimi--k2.6-purple.svg)
![Providers](https://img.shields.io/badge/providers-6-blueviolet.svg)

---

## Table of Contents | 목차

- [Overview | 개요](#overview--개요)
- [Features | 기능](#features--기능)
- [Architecture | 아키텍처](#architecture--아키텍처)
- [Automation Inventory | 자동화 인벤토리](#automation-inventory--자동화-인벤토리)
  - [GitHub Workflows (56 total) | GitHub 워크플로우 (56개)](#github-workflows-56-total--github-워크플로우-56개)
  - [Go Automation Tools (8 total) | Go 자동화 도구 (8개)](#go-automation-tools-8-total--go-자동화-도구-8개)
- [Quick Start | 빠른 시작](#quick-start--빠른-시작)
- [Local Development | 로컬 개발](#local-development--로컬-개발)
- [Commands Reference | 명령어 참조](#commands-reference--명령어-참조)
- [Contribution | 기여](#contribution--기여)

---

## Overview | 개요

This repository is a hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent), customized for `jclee941/*` repositories. It uses a homelab-hosted CLIProxyAPI (`<homelab-host>:8317`) as the primary LLM backend, accessible externally via `https://cliproxy.jclee.me/v1`.

이 저장소는 `jclee941/*` 저장소를 위해 커스터마이징된 [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)의 하드 포크입니다. 개인 homelab에 호스팅된 CLIProxyAPI (`<homelab-host>:8317`)를 주요 LLM 백엔드로 사용하며, 외부에서는 `https://cliproxy.jclee.me/v1`를 통해 접근합니다.

### Key Models | 주요 모델

| Model | Role | Endpoint |
|-------|------|----------|
| `kimi-k2.6` | Primary | CLIProxyAPI |
| `minimax-m2.7` | Fallback #1 | CLIProxyAPI |
| `gpt-5.5` | Fallback #2 | CLIProxyAPI |

### Why This Fork? | 왜 이 포크인가?

- **Personal LLM Gateway**: Uses a self-hosted CLIProxyAPI deployment for cost-effective, customizable AI inference
- **Repository-Specific Automation**: Workflows tailored for `jclee941/*` repositories
- **Security-First**: Additional security review workflows and secret scanning
- **Multi-Model Fallback**: Automatic fallback to ensure reliability

---

## Features | 기능

### AI-Powered Code Review

- `/review` - Comprehensive PR review with security, performance, and style checks
- `/improve` - Automatic code improvement suggestions
- `/describe` - PR description generation from diff
- `/ask` - Natural language questions about code
- `/update_changelog` - Automatic changelog updates

### Automation Workflows

- **Branch Management**: Automatic branch-to-PR conversion, issue-to-branch workflows
- **PR Lifecycle**: Auto-merge, stale bot, size checks, label management
- **Security**: Gitleaks secret scanning, CodeQL analysis, dependency review, scorecard
- **Release Management**: Release drafter, auto-publishing, changelog generation
- **Health Monitoring**: ELK stack health checks, runtime health monitoring, repo health reports
- **CI/CD**: Auto-deploy, build-and-push, CI failure tracking, e2e testing

### Developer Tools

- **Go Automation**: 8 standalone tools for repository management
- **Docker Support**: GitHub Action and GitHub App deployment configurations
- **Testing Infrastructure**: Unit, e2e, and live test suites

---

## Architecture | 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        GitHub Repositories                       │
│                      (jclee941/* repositories)                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Workflows (56)                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │
│  │ PR Checks    │ │ Issue Mgmt   │ │ Security     │              │
│  │ Auto-Merge   │ │ Stale Bot    │ │ Gitleaks     │              │
│  │ Release      │ │ Health       │ │ CodeQL       │              │
│  └──────────────┘ └──────────────┘ └──────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     pr-agent (Python 3.12+)                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  CLI: pr-agent                                           │   │
│  │  Modules: github_provider, gitlab_provider, azure_devops │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLIProxyAPI (Homelab)                         │
│              https://cliproxy.jclee.me/v1                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │
│  │ kimi-k2.6    │ │minimax-m2.7  │ │   gpt-5.5    │              │
│  │  (primary)   │ │  (fallback)  │ │  (fallback)  │              │
│  └──────────────┘ └──────────────┘ └──────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### Component Overview

| Component | Technology | Purpose |
|-----------|------------|---------|
| LLM Backend | CLIProxyAPI | Homelab-hosted inference proxy |
| Bot Framework | pr-agent | PR review and automation |
| Workflows | GitHub Actions | CI/CD and automation pipelines |
| Go Tools | Go 1.23+ | Repository management utilities |
| Container | Docker | Deployment packaging |

---

## Automation Inventory | 자동화 인벤토리

### GitHub Workflows (56 total) | GitHub 워크플로우 (56개)

#### Branch & Issue Management | 브랜치 및 이슈 관리

| # | Workflow File | Purpose |
|---|---------------|---------|
| 01 | `01_branch-to-pr.yml` | Convert branch to PR automatically |
| 02 | `02_issue-to-branch.yml` | Create branch from issue |
| 18 | `18_issue-management.yml` | Issue lifecycle management |
| 19 | `19_issue-backfill.yml` | Backfill missing issues |
| 82 | `82_issue-label.yml` | Auto-label issues |
| 83 | `83_issue-lifecycle.yml` | Issue lifecycle automation |
| 84 | `84_labeler.yml` | Label management |

#### PR Automation | PR 자동화

| # | Workflow File | Purpose |
|---|---------------|---------|
| 03 | `03_pr-checks.yml` | PR validation checks |
| 09 | `09_semantic-pr.yml` | Semantic PR validation |
| 10 | `10_pr-review.yml` | AI-powered PR review |
| 12 | `12_dependabot-auto-merge.yml` | Auto-merge Dependabot PRs |
| 13 | `13_pr-auto-merge.yml` | Auto-merge eligible PRs |
| 14 | `14_bot-auto-fix.yml` | Auto-fix from bot suggestions |
| 15 | `15_merged-pr-cleanup.yml` | Cleanup after PR merge |
| 17 | `17_pr-stale-bot.yml` | Mark stale PRs |
| 81 | `81_auto-merge.yml` | Generic auto-merge |
| 85 | `85_pr-normalize.yml` | Normalize PR format |
| 86 | `86_pr-review-security.yml` | Security-focused PR review |
| 87 | `87_pr-size.yml` | PR size validation |
| 88 | `88_stale.yml` | Stale detection |
| 89 | `89_welcome.yml` | Welcome messages |
| 90 | `90_sanity.yml` | Sanity checks |
| security/11 | `security/11_pr-review.yml` | Deep security review |

#### Security & Scanning | 보안 및 스캐닝

| # | Workflow File | Purpose |
|---|---------------|---------|
| 04 | `04_actionlint.yml` | GitHub Actions YAML linting |
| 05 | `05_gitleaks.yml` | Secret scanning |
| 06 | `06_codeql.yml` | CodeQL static analysis |
| 07 | `07_dependency-review.yml` | Dependency vulnerability review |
| 08 | `08_scorecard.yml` | OpenSSF scorecard |
| 35 | `35_auto-hardcode-scan.yml` | Hardcoded secret scanning |

#### Release Management | 릴리스 관리

| # | Workflow File | Purpose |
|---|---------------|---------|
| 22 | `22_template-sync.yml` | Template synchronization |
| 23 | `23_release-drafter.yml` | Release draft generation |
| 24 | `24_release-notes.yml` | Release notes generation |
| 25 | `25_release-publish.yml` | Release publishing |

#### Health & Monitoring | 상태 및 모니터링

| # | Workflow File | Purpose |
|---|---------------|---------|
| 26 | `26_elk-health-check.yml` | ELK stack health |
| 27 | `27_elk-setup.yml` | ELK setup automation |
| 28 | `28_bot-health-monitor.yml` | Bot health monitoring |
| 29 | `29_downstream-health-check.yml` | Downstream repo health |
| 30 | `30_runtime-health-check.yml` | Runtime health check |
| 31 | `31_repo-health.yml` | Repository health |
| 32 | `32_org-health-report.yml` | Organization health report |
| 33 | `33_drift-detector.yml` | Configuration drift detection |

#### CI/CD & Deployment | CI/CD 및 배포

| # | Workflow File | Purpose |
|---|---------------|---------|
| 34 | `34_auto-deploy.yml` | Automatic deployment |
| 36 | `36_build-and-push-app.yml` | Build and push container images |
| 37 | `37_ci-failure-issues.yml` | Create issues for CI failures |
| 38 | `38_e2e.yml` | End-to-end tests |
| 39 | `39_e2e-live.yml` | Live e2e tests |
| 41 | `41_reusable-ci.yml` | Reusable CI template |
| 60 | `60_ci-auto-heal.yml` | Auto-heal CI failures |

#### Documentation | 문서화

| # | Workflow File | Purpose |
|---|---------------|---------|
| 20 | `20_readme-gen.yml` | README generation |
| 21 | `21_docs-sync.yml` | Documentation sync |

#### Batch Operations | 일괄 작업

| # | Workflow File | Purpose |
|---|---------------|---------|
| 40 | `40_repo-review-batch.yml` | Batch repository review |

#### Reusable Workflows | 재사용 가능한 워크플로우

| # | Workflow File | Purpose |
|---|---------------|---------|
| 41 | `41_reusable-ci.yml` | Reusable CI workflow |
| 42 | `42_reusable-docs-sync.yml` | Reusable docs sync |
| 43 | `43_reusable-issue-management.yml` | Reusable issue management |
| 44 | `44_reusable-pr-checks.yml` | Reusable PR checks |
| 45 | `45_reusable-gitleaks.yml` | Reusable gitleaks scan |

#### Utility | 유틸리티

| # | Workflow File | Purpose |
|---|---------------|---------|
| 16 | `16_stale-repo-identifier.yml` | Identify stale repositories |

---

### Go Automation Tools (8 total) | Go 자동화 도구 (8개)

These tools are located in `scripts/cmd/` and can be invoked via `go run ./cmd/<tool-name>`.

| Tool | Purpose | Key Features |
|------|---------|---------------|
| `branch-protection` | Manage branch protection rules | List, apply, delete protection rules |
| `deploy-to-repos` | Deploy workflows to repositories | Batch deploy `10_pr-review.yml` to `jclee941/*` repos |
| `drift-detector` | Detect configuration drift | Monitor infrastructure-as-code changes |
| `repo-metadata` | Extract repository metadata | Gather repo stats, languages, contributors |
| `repo-review` | Batch repository review | Review multiple repos systematically |
| `rulesets-manager` | Manage GitHub Rulesets | Supplement branch protection with ruleset-based controls |
| `sync-secrets` | Synchronize secrets | Cross-repo secret management |
| `validate-naming` | Validate naming conventions | Enforce naming standards across repos |

#### Invoking Go Tools

```bash
# From the scripts directory
cd scripts

# Run a specific tool
go run ./cmd/branch-protection

# Run with arguments
go run ./cmd/deploy-to-repos --repo=example-repo --workflow=10_pr-review.yml

# Run tests
go test ./cmd/branch-protection/...
go test ./cmd/deploy-to-repos/...
```

---

## Quick Start | 빠른 시작

### Prerequisites | 사전 요구사항

- Python 3.12+
- Go 1.23+ (for automation tools)
- Docker (for containerized deployment)
- CLIProxyAPI endpoint access

### Installation | 설치

```bash
# Clone the repository
git clone https://github.com/qodo-ai/pr-agent.git
cd pr-agent

# Install Python dependencies
make install

# Or manually
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install --upgrade pip
pip install -e .
```

### Configuration | 설정

1. Copy `.env.example` to `.env`:

   ```bash
   cp .env.example .env
   ```

2. Configure your CLIProxyAPI credentials in `.env`:

   ```env
   CLI_PROXY_API_KEY=your-api-key
   CLI_PROXY_API_BASE=https://cliproxy.jclee.me/v1
   ```

3. Set the model configuration in `.pr_agent.toml`:

   ```toml
   [config]
   model = "kimi-k2.6"
   fallback_models = ["minimax-m2.7", "gpt-5.5"]

   [openai]
   api_key = "${CLI_PROXY_API_KEY}"
   base_url = "${CLI_PROXY_API_BASE}"

   [litellm]
   api_key = "${CLI_PROXY_API_KEY}"
   ```

### Running the Bot | 봇 실행

```bash
# Run pr-agent CLI
pr-agent --help

# Run a specific command
pr-agent review --pr_url https://github.com/owner/repo/pull/123

# Use the GitHub App
# Install from GitHub Marketplace and authorize on your repositories
```

### Docker Deployment | Docker 배포

```bash
# GitHub Action Runner
docker build -f Dockerfile.github_action -t pr-agent:action .

# GitHub App
docker build -f Dockerfile.github_app -t pr-agent:app .

# Run container
docker run -e CLI_PROXY_API_KEY=your-key pr-agent:action
```

---

## Local Development | 로컬 개발

### Development Setup | 개발 환경 설정

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
pip install -r requirements-dev.txt

# Install Go dependencies
cd scripts
go mod download
```

### Running Tests | 테스트 실행

```bash
# All tests
make test

# Unit tests only
make test-unit

# E2E tests
make test-e2e

# Live tests (requires real credentials)
make test-live

# Specific test file
python -m pytest tests/unittest/test_github_provider_issue_creation.py -v
```

### Linting | 린팅

```bash
# Run all linters
make lint

# Run ruff
python -m ruff check .
python -m ruff check --fix .
```

### Code Quality | 코드 품질

```bash
# Format code (isort)
python -m ruff check --select I001 --fix .

# Run security checks
python -m bandit -r pr_agent/
```

### Go Development | Go 개발

```bash
cd scripts

# Format
go fmt ./...

# Vet
go vet ./...

# Build all tools
go build ./cmd/...

# Test specific tool
go test ./cmd/branch-protection/...

# Run tool
go run ./cmd/repo-review/main.go --help
```

---

## Commands Reference | 명령어 참조

### Make Commands | Make 명령어

| Command | Description |
|---------|-------------|
| `make install` | Install dependencies and setup virtual environment |
| `make test` | Run all tests (unit, e2e, live) |
| `make test-unit` | Run unit tests only |
| `make test-e2e` | Run end-to-end tests |
| `make test-live` | Run live tests against real services |
| `make lint` | Run linting checks |
| `make clean` | Clean up cache and pycache |

### pr-agent CLI Commands | pr-agent CLI 명령어

```bash
# PR Review
pr-agent review --pr_url https://github.com/owner/repo/pull/123

# Improve Code
pr-agent improve --pr_url https://github.com/owner/repo/pull/123

# Describe PR
pr-agent describe --pr_url https://github.com/owner/repo/pull/123

# Ask Question
pr-agent ask --pr_url https://github.com/owner/repo/pull/123 --question "Why is this function needed?"

# Update Changelog
pr-agent update_changelog --pr_url https://github.com/owner/repo/pull/123

# Server Mode
pr-agent server --port 8317
```

### Go Tools Commands | Go 도구 명령어

| Tool | Command | Description |
|------|---------|-------------|
| branch-protection | `go run ./cmd/branch-protection --org qodo-ai --repo pr-agent` | List branch protection rules |
| deploy-to-repos | `go run ./cmd/deploy-to-repos --target jclee941/* --workflow 10_pr-review.yml` | Deploy workflow to repos |
| drift-detector | `go run ./cmd/drift-detector --config .github/` | Detect configuration drift |
| repo-metadata | `go run ./cmd/repo-metadata --repo qodo-ai/pr-agent` | Extract repo metadata |
| repo-review | `go run ./cmd/repo-review --batch repos.yaml` | Batch review repos |
| rulesets-manager | `go run ./cmd/rulesets-manager --org qodo-ai --rule-id 123` | Manage rulesets |
| sync-secrets | `go run ./cmd/sync-secrets --source prod --target staging` | Sync secrets |
| validate-naming | `go run ./cmd/validate-naming --pattern "feat/*"` | Validate branch naming |

---

## Project Structure | 프로젝트 구조

```
pr-agent/
├── .github/
│   ├── workflows/          # 56 GitHub workflow files
│   ├── CODEOWNERS
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
├── _bot-scripts/           # Bot automation scripts
│   ├── scripts/
│   │   ├── check_private_ips.py
│   │   ├── pr_review_runner.py
│   │   ├── redact_exposed_secrets.py
│   │   └── repo_review.py
│   └── ... (mirrors root structure)
├── scripts/
│   ├── cmd/                # Go automation tools (8 tools)
│   │   ├── branch-protection/
│   │   ├── deploy-to-repos/
│   │   ├── drift-detector/
│   │   ├── repo-metadata/
│   │   ├── repo-review/
│   │   ├── rulesets-manager/
│   │   ├── sync-secrets/
│   │   └── validate-naming/
│   └── go.mod
├── pr_agent/               # Main Python package
│   ├── github_provider.py
│   ├── gitlab_provider.py
│   ├── azure_devops_provider.py
│   └── ... (core bot logic)
├── tests/
│   ├── unittest/           # Unit tests
│   ├── e2e/                # End-to-end tests
│   └── e2e_live/           # Live tests
├── docs/                   # Documentation
│   ├── architecture.md
│   ├── automation-enhancement-brainstorm.md
│   └── review-templates/
├── config/
│   └── repos.yaml          # Repository configuration
├── pyproject.toml
├── requirements.txt
├── Dockerfile.github_action
├── Dockerfile.github_app
└── docker-compose.github_app.yml
```

---

## Contribution | 기여

### Contributing Guidelines | 기여 지침

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our development workflow and contribution process.

### Development Workflow | 개발 워크플로

1. **Fork** the repository
2. **Clone** your fork:

   ```bash
   git clone https://github.com/your-username/pr-agent.git
   cd pr-agent
   ```

3. **Create a branch** for your changes:

   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Make your changes** and commit:

   ```bash
   git commit -m "feat: add your feature description"
   ```

5. **Push** to your fork:

   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request** with a clear description

### Code Style | 코드 스타일

- Python: Follow `ruff` linting rules (line-length: 120)
- Go: Follow standard Go conventions (`go fmt`, `go vet`)
- YAML: Use `actionlint` for GitHub Actions

### Testing | 테스트

- All new features must include tests
- Ensure all tests pass before submitting PR
- Run `make test-unit` to verify unit tests
- Run `make lint` to verify code quality

### Security | 보안

- Never commit secrets or API keys
- Use `.env.example` for environment variable templates
- Run security scans (`05_gitleaks.yml`, `06_codeql.yml`) before merging

### Documentation | 문서화

- Update README.md for user-facing changes
- Add inline comments for complex logic
- Update docs/ for architectural changes

---

## License | 라이선스

This project is licensed under the **AGPL-3.0** License - see [LICENSE](LICENSE) for details.

This is a derivative work of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent). See [NOTICE](NOTICE) for attribution requirements.

---

## Acknowledgments |Acknowledgments

- **Upstream**: [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) - The original pr-agent project
- **LLM Provider**: CLIProxyAPI - Homelab-hosted inference proxy
- **Documentation**: Built with intelligence from pr-agent tools

---

## Links | 링크

- **Upstream Repository**: [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)
- **CLIProxyAPI Documentation**: [cliproxy.jclee.me](https://cliproxy.jclee.me)
- **Bot Status**: [bot.jclee.me](https://bot.jclee.me)

---

*Generated by pr-agent on behalf of jclee941*
