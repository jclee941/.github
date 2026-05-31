# pr-agent Fork for jclee941 | jclee941용 pr-agent 포크

> 개인 homelab CLIProxyAPI 백엔드를 사용하는 AI 기반 PR 리뷰어 및 자동화 봇
> AI-powered PR reviewer and automation bot backed by a homelab CLIProxyAPI

[![Project Version](https://img.shields.io/badge/version-0.3.1-blue.svg)](https://github.com/qodo-ai/pr-agent)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/upstream-qodo--ai/pr--agent-red.svg)](https://github.com/qodo-ai/pr-agent)
![Model](https://img.shields.io/badge/model-kimi--k2.6-purple.svg)

---

## Table of Contents | 목차

- [Overview | 개요](#overview--개요)
- [Features | 기능](#features--기능)
- [Architecture | 아키텍처](#architecture--아키텍처)
- [Automation Inventory | 자동화 인벤토리](#automation-inventory--자동화-인벤토리)
- [Quick Start | 빠른 시작](#quick-start--빠른-시작)
- [Local Development | 로컬 개발](#local-development--로컬-개발)
- [Commands Reference | 명령어 참조](#commands-reference--명령어-참조)
- [Contribution | 기여](#contribution--기여)

---

## Overview | 개요

This repository is a hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent), customized for `jclee941/*` repositories. It uses a homelab-hosted CLIProxyAPI (`192.168.50.114:8317`) as the primary LLM backend, accessible externally via `https://cliproxy.jclee.me/v1`.

이 저장소는 `jclee941/*` 저장소를 위해 커스터마이징된 [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)의 하드 포크입니다. 개인 homelab에 호스팅된 CLIProxyAPI (`192.168.50.114:8317`)를 주요 LLM 백엔드로 사용하며, 외부에서는 `https://cliproxy.jclee.me/v1`를 통해 접근합니다.

### Key Models | 주요 모델

| Model | Role | Endpoint |
|-------|------|----------|
| `kimi-k2.6` | Primary | CLIProxyAPI |
| `minimax-m2.7` | Fallback | CLIProxyAPI CLI |
| `gpt-5.5` | Fallback | CLIProxyAPI CLI |

### Multi-Provider Support | 멀티 프로바이더 지원

- GitHub (Actions + App)
- GitLab
- Bitbucket
- Azure DevOps
- Gitea
- AWS CodeCommit

---

## Features | 기능

### AI-Powered PR Commands | AI 기반 PR 명령어

| Command | Description | 설명 |
|---------|-------------|------|
| `/review` | Comprehensive PR review with security, performance, and style checks | 보안, 성능, 스타일 체크가 포함된 종합 PR 리뷰 |
| `/improve` | Suggest code improvements | 코드 개선 제안 |
| `/describe` | Generate PR description from diff | diff에서 PR 설명 생성 |
| `/ask` | Answer questions about the codebase | 코드베이스 관련 질문 답변 |
| `/update_changelog` | Automatic changelog updates | 자동 changelog 업데이트 |

### Workflow Automation | 워크플로우 자동화

| Category | Workflows | 설명 |
|----------|-----------|------|
| **PR Lifecycle** | 45 workflows | PR checks, auto-merge, stale bot, review assignment |
| **Issue Management** | 5 workflows | Issue creation, labeling, lifecycle management |
| **Security** | 8 workflows | CodeQL, Gitleaks, dependency review, security PR review |
| **Release Management** | 5 workflows | Release drafter, notes, publishing |
| **Health & Monitoring** | 6 workflows | ELK health, bot health, downstream checks |
| **Repository Maintenance** | 3 workflows | Drift detection, auto-deploy, repo health |

### Go Automation Tools | Go 자동화 도구

| Tool | Purpose | 용도 |
|------|---------|------|
| `branch-protection` | Manage branch protection rules | 브랜치 보호 규칙 관리 |
| `deploy-to-repos` | Deploy workflows to repositories | 저장소에 워크플로우 배포 |
| `drift-detector` | Detect infrastructure drift | 인프라 드리프트 탐지 |
| `repo-metadata` | Manage repository metadata | 저장소 메타데이터 관리 |
| `repo-review` | Review repository configuration | 저장소 구성 검토 |
| `rulesets-manager` | Manage GitHub Rulesets | GitHub Rulesets 관리 |
| `sync-secrets` | Synchronize secrets across repos | 저장소 간 시크릿 동기화 |
| `validate-naming` | Validate naming conventions | 명명 규칙 검증 |

---

## Architecture | 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions Runner                     │
│                    (ubuntu-latest)                           │
├─────────────────────────────────────────────────────────────┤
│  pr-agent (Python 3.12+)                                     │
│  ├── CLI: pr-agent                                           │
│  ├── GitHub App                                              │
│  └── Docker Container                                        │
├─────────────────────────────────────────────────────────────┤
│                    External Network                          │
│                    (cliproxy.jclee.me)                       │
├─────────────────────────────────────────────────────────────┤
│              CLIProxyAPI (Homelab)                           │
│              (192.168.50.114:8317)                          │
├─────────────────────────────────────────────────────────────┤
│  LLM Backends                                                │
│  ├── kimi-k2.6 (Primary)                                    │
│  ├── minimax-m2.7 (Fallback)                                │
│  └── gpt-5.5 (Fallback)                                    │
└─────────────────────────────────────────────────────────────┘
```

### Component Overview | 컴포넌트 개요

```
/
├── .github/workflows/          # 56 GitHub Actions workflows
├── _bot-scripts/               # Bot deployment scripts
│   └── scripts/                # Go automation tools source
├── pr_agent/                   # Python package
├── config/                     # Configuration files
├── docs/                       # Documentation
├── tests/                      # Test suites
│   ├── unittest/               # Unit tests
│   ├── e2e/                   # End-to-end tests
│   └── e2e_live/              # Live environment tests
└── tools/                      # Compiled Go binaries
```

---

## Automation Inventory | 자동화 인벤토리

### GitHub Actions Workflows | GitHub Actions 워크플로우 (56개)

#### PR Lifecycle | PR 라이프사이클 (13개)

| # | Workflow | Trigger | Description |
|---|----------|---------|-------------|
| 01 | `branch-to-pr.yml` | push | Branch to PR conversion |
| 03 | `pr-checks.yml` | pull_request | PR validation checks |
| 09 | `semantic-pr.yml` | pull_request | Semantic PR format validation |
| 10 | `pr-review.yml` | pull_request | AI PR review (primary) |
| 13 | `pr-auto-merge.yml` | pull_request | Auto-merge on conditions |
| 14 | `bot-auto-fix.yml` | pull_request | Bot-triggered auto-fix |
| 15 | `merged-pr-cleanup.yml` | push | Cleanup after PR merge |
| 44 | `reusable-pr-checks.yml` | workflow_call | Reusable PR checks |
| 81 | `auto-merge.yml` | pull_request | Auto-merge workflow |
| 85 | `pr-normalize.yml` | pull_request | PR normalization |
| 86 | `pr-review-security.yml` | pull_request | Security-focused PR review |
| 87 | `pr-size.yml` | pull_request | PR size labeling |
| 90 | `sanity.yml` | pull_request | Sanity checks gate |

#### Security & Scanning | 보안 및 스캔 (11개)

| # | Workflow | Trigger | Description |
|---|----------|---------|-------------|
| 04 | `actionlint.yml` | push, pull_request | GitHub Actions YAML linting |
| 05 | `gitleaks.yml` | push, pull_request | Secret pattern scanning |
| 06 | `codeql.yml` | push | CodeQL analysis (SAST) |
| 07 | `dependency-review.yml` | pull_request | Dependency vulnerability review |
| 08 | `scorecard.yml` | push | Security scorecard |
| 35 | `auto-hardcode-scan.yml` | schedule | Weekly hardcode pattern scan |
| 45 | `reusable-gitleaks.yml` | workflow_call | Reusable gitleaks scan |
| security/11 | `pr-review.yml` | pull_request | Deep security review (Korean) |
| 60 | `ci-auto-heal.yml` | workflow_run | CI failure auto-heal |
| 82 | `issue-label.yml` | issues | Issue labeling automation |
| 89 | `welcome.yml` | pull_request | Welcome message for contributors |

#### Issue Management | 이슈 관리 (8개)

| # | Workflow | Trigger | Description |
|---|----------|---------|-------------|
| 16 | `stale-repo-identifier.yml` | schedule | Identify stale repositories |
| 17 | `pr-stale-bot.yml` | schedule | Mark stale PRs |
| 18 | `issue-management.yml` | issues | Issue management automation |
| 19 | `issue-backfill.yml` | workflow_dispatch | Backfill issues |
| 43 | `reusable-issue-management.yml` | workflow_call | Reusable issue management |
| 82 | `issue-label.yml` | issues | Issue labeling |
| 83 | `issue-lifecycle.yml` | issues | Issue lifecycle management |
| 84 | `labeler.yml` | pull_request | Auto-labeler |

#### Release & Deployment | 배포 및 릴리스 (6개)

| # | Workflow | Trigger | Description |
|---|----------|---------|-------------|
| 23 | `release-drafter.yml` | push | Draft releases |
| 24 | `release-notes.yml` | release | Generate release notes |
| 25 | `release-publish.yml` | release | Publish releases |
| 34 | `auto-deploy.yml` | push | Auto-deployment |
| 36 | `build-and-push-app.yml` | push | Build and push app |
| 41 | `reusable-ci.yml` | workflow_call | Reusable CI pipeline |

#### Documentation | 문서화 (5개)

| # | Workflow | Trigger | Description |
|---|----------|---------|-------------|
| 20 | `readme-gen.yml` | push, pull_request | README generation |
| 21 | `docs-sync.yml` | push | Documentation sync |
| 22 | `template-sync.yml` | push | Template synchronization |
| 42 | `reusable-docs-sync.yml` | workflow_call | Reusable docs sync |

#### Health & Monitoring | 헬스 및 모니터링 (7개)

| # | Workflow | Trigger | Description |
|---|----------|---------|-------------|
| 26 | `elk-health-check.yml` | schedule | ELK stack health check |
| 27 | `elk-setup.yml` | workflow_dispatch | ELK setup |
| 28 | `bot-health-monitor.yml` | schedule | Bot health monitoring |
| 29 | `downstream-health-check.yml` | schedule | Downstream service health |
| 30 | `runtime-health-check.yml` | schedule | Runtime health check |
| 31 | `repo-health.yml` | schedule | Repository health report |
| 32 | `org-health-report.yml` | schedule | Organization health report |

#### Repository Maintenance | 저장소 유지보수 (6개)

| # | Workflow | Trigger | Description |
|---|----------|---------|-------------|
| 02 | `issue-to-branch.yml` | issues | Issue to branch creation |
| 33 | `drift-detector.yml` | schedule | Drift detection |
| 37 | `ci-failure-issues.yml` | workflow_run | Create issues for CI failures |
| 38 | `e2e.yml` | schedule | End-to-end tests |
| 39 | `e2e-live.yml` | workflow_dispatch | Live E2E tests |
| 40 | `repo-review-batch.yml` | workflow_dispatch | Batch repository review |

### Go Automation Tools | Go 자동화 도구 (8개)

All tools are located in `scripts/cmd/` and invoked via `go run ./cmd/<tool-name>`.

| Tool | Location | Purpose |
|------|----------|---------|
| `branch-protection` | `scripts/cmd/branch-protection/` | Manage GitHub branch protection rules |
| `deploy-to-repos` | `scripts/cmd/deploy-to-repos/` | Deploy `pr-review.yml` to `jclee941/*` repos |
| `drift-detector` | `scripts/cmd/drift-detector/` | Detect infrastructure configuration drift |
| `repo-metadata` | `scripts/cmd/repo-metadata/` | Manage repository metadata |
| `repo-review` | `scripts/cmd/repo-review/` | Review repository configuration |
| `rulesets-manager` | `scripts/cmd/rulesets-manager/` | Manage GitHub Rulesets (list/apply/delete) |
| `sync-secrets` | `scripts/cmd/sync-secrets/` | Synchronize secrets across repositories |
| `validate-naming` | `scripts/cmd/validate-naming/` | Validate repository naming conventions |

---

## Quick Start | 빠른 시작

### Prerequisites |前提条件

- Python 3.12+
- Go 1.21+
- Docker (optional, for containerized deployment)
- CLIProxyAPI endpoint access

### Installation | 설치

```bash
# Clone the repository
git clone https://github.com/qodo-ai/pr-agent.git
cd pr-agent

# Install Python dependencies
make install

# Verify installation
pr-agent --help
```

### Configuration | 설정

1. Copy `.env.example` to `.env`:

   ```bash
   cp .env.example .env
   ```

2. Configure the following environment variables in `.env`:

   ```bash
   # CLIProxyAPI Configuration
   CLI_PROXY_API_KEY=your_api_key_here
   CLI_PROXY_API_BASE=https://cliproxy.jclee.me/v1
   CLI_PROXY_MODEL=kimi-k2.6
   CLI_PROXY_FALLBACK_MODELS=minimax-m2.7,gpt-5.5
   
   # GitHub Configuration (if using GitHub App)
   GITHUB_APP_ID=your_app_id
   GITHUB_APP_PRIVATE_KEY=your_private_key
   ```

3. For repository-specific configuration, create `.pr_agent.toml`:

   ```toml
   [config]
   model = "kimi-k2.6"
   fallback_models = ["minimax-m2.7", "gpt-5.5"]

   [openai]
   api_key = "${CLI_PROXY_API_KEY}"
   api_base = "${CLI_PROXY_API_BASE}"

   [litellm]
   drop_params = true
   ```

### Running Locally | 로컬 실행

```bash
# Run PR review locally
pr-agent review --pr_url https://github.com/owner/repo/pull/123

# Run describe
pr-agent describe --pr_url https://github.com/owner/repo/pull/123

# Run ask
pr-agent ask "What does this PR do?" --pr_url https://github.com/owner/repo/pull/123
```

---

## Local Development | 로컬 개발

### Development Environment Setup | 개발 환경 설정

```bash
# Create virtual environment
python3.12 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -e .
pip install -r requirements-dev.txt
```

### Testing | 테스트

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run end-to-end tests
make test-e2e

# Run live environment tests
make test-live

# Run with coverage
pytest --cov=pr_agent --cov-report=html
```

### Linting | 린팅

```bash
# Run linter
make lint

# Auto-fix issues (where applicable)
ruff check --fix .
```

### Clean | 정리

```bash
# Clean cache and artifacts
make clean
```

---

## Commands Reference | 명령어 참조

### Makefile Commands | Makefile 명령어

| Command | Description | 설명 |
|---------|-------------|------|
| `make install` | Install dependencies | 의존성 설치 |
| `make test` | Run all tests | 모든 테스트 실행 |
| `make test-unit` | Run unit tests only | 유닛 테스트만 실행 |
| `make test-e2e` | Run E2E tests | E2E 테스트 실행 |
| `make test-live` | Run live tests | 라이브 테스트 실행 |
| `make lint` | Run linter | 린터 실행 |
| `make clean` | Clean cache files | 캐시 파일 정리 |

### pr-agent CLI Commands | pr-agent CLI 명령어

```bash
# PR Review
pr-agent review --pr_url https://github.com/owner/repo/pull/123

# PR Description
pr-agent describe --pr_url https://github.com/owner/repo/pull/123

# Suggest Improvements
pr-agent improve --pr_url https://github.com/owner/repo/pull/123

# Ask Questions
pr-agent ask "What does this PR do?" --pr_url https://github.com/owner/repo/pull/123

# Update Changelog
pr-agent update_changelog --pr_url https://github.com/owner/repo/pull/123
```

### Go Tools Commands | Go 도구 명령어

```bash
# Navigate to scripts directory
cd scripts

# Branch Protection
go run ./cmd/branch-protection

# Deploy to Repositories
go run ./cmd/deploy-to-repos

# Drift Detection
go run ./cmd/drift-detector

# Repository Review
go run ./cmd/repo-review

# Rulesets Manager
go run ./cmd/rulesets-manager

# Sync Secrets
go run ./cmd/sync-secrets

# Validate Naming
go run ./cmd/validate-naming
```

---

## Contribution | 기여

### Contributing Guidelines | 기여 가이드라인

We welcome contributions! Please see the following documents:

- [CONTRIBUTING.md](./CONTRIBUTING.md) - Contribution guidelines
- [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) - Code of conduct
- [SECURITY.md](./SECURITY.md) - Security policy

### Fork-Specific Notes | 포크 특정 참고 사항

This is a **hard fork** of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent). When contributing:

1. **Maintain AGPL-3.0 license compatibility**
2. **Preserve upstream functionality** unless explicitly removing for fork-specific needs
3. **Document fork-specific changes** in the [AGENTS.md](./AGENTS.md)
4. **Test against CLIProxyAPI** before submitting changes
5. **Follow the bilingual documentation standard** (Korean + English)

### Workflow Development | 워크플로우 개발

When adding new GitHub Actions workflows:

1. Place workflow files in `.github/workflows/`
2. For reusable workflows, use `workflow_call` trigger
3. Security-sensitive workflows should be in `security/` subdirectory
4. Follow naming convention: `{priority}_{workflow-name}.yml`
5. Include appropriate triggers (push, pull_request, schedule, etc.)

### Go Tool Development | Go 도구 개발

When adding new Go automation tools:

1. Create under `scripts/cmd/<tool-name>/`
2. Implement `main.go` with CLI argument parsing
3. Add table-driven tests in `main_test.go`
4. Update this README's automation inventory
5. Update [AGENTS.md](./AGENTS.md) with new tool information

### Documentation Standards | 문서화 표준

- All user-facing documentation must be **bilingual** (Korean + English)
- Use Markdown with 120 character line length
- Tables and code blocks are exempt from line length limits
- Include both Korean and English sections with clear headers

---

## License | 라이선스

This project is licensed under the **AGPL-3.0** license. See [LICENSE](./LICENSE) for details.

This is a derivative work of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent). See [NOTICE](./NOTICE) for attribution.

---

## External Links | 외부 링크

- **Upstream Project:** [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)
- **CLIProxyAPI (External):** [cliproxy.jclee.me](https://cliproxy.jclee.me)
- **Bot Status Page:** [bot.jclee.me](https://bot.jclee.me)

---

## Support | 지원

- **Documentation:** [docs/](docs/)
- **Upstream README:** [docs/pr-agent-upstream-README.md](docs/pr-agent-upstream-README.md)
- **Architecture:** [docs/architecture.md](docs/architecture.md)
- **Workflow Analysis:** [docs/git-workflow-gap-analysis.md](docs/git-workflow-gap-analysis.md)

---

*Generated by pr-agent | pr-agent로 생성됨*
*Version: 0.3.1*
