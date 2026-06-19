# pr-agent Fork for jclee941 | jclee941용 pr-agent 포크

> AI-powered PR reviewer and GitHub automation platform for `jclee941/*` repositories, backed by a homelab CLIProxyAPI deployment.
> homelab CLIProxyAPI 배포를 기반으로 `jclee941/*` 저장소를 자동화하는 AI PR 리뷰어 및 GitHub 자동화 플랫폼입니다.

[![Version](https://img.shields.io/badge/version-0.3.1-blue.svg)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.12%2B-green.svg)](pyproject.toml)
[![License](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/upstream-qodo--ai%2Fpr--agent-red.svg)](https://github.com/qodo-ai/pr-agent)
[![CLIProxy](https://img.shields.io/badge/LLM%20Gateway-CLIProxyAPI-purple.svg)](https://cliproxy.jclee.me/v1)
[![Workflows](https://img.shields.io/badge/workflows-35-yellowgreen.svg)](#github-workflows-35-total--github-워크플로우-35개)
[![Go Tools](https://img.shields.io/badge/go--tools-5-blue.svg)](#go-automation-tools-5-total--go-자동화-도구-5개)

---

## Table of Contents | 목차

- [Overview | 개요](#overview--개요)
- [Features | 기능](#features--기능)
- [Architecture | 아키텍처](#architecture--아키텍처)
- [Automation Inventory | 자동화 인벤토리](#automation-inventory--자동화-인벤토리)
  - [GitHub Workflows 35 total | GitHub 워크플로우 35개](#github-workflows-35-total--github-워크플로우-35개)
  - [Go Automation Tools 5 total | Go 자동화 도구 5개](#go-automation-tools-5-total--go-자동화-도구-5개)
- [Repository Structure | 저장소 구조](#repository-structure--저장소-구조)
- [Quick Start | 빠른 시작](#quick-start--빠른-시작)
- [Local Development | 로컬 개발](#local-development--로컬-개발)
- [Commands Reference | 명령어 참조](#commands-reference--명령어-참조)
- [Contribution Guide | 기여 가이드](#contribution-guide--기여-가이드)

---

## Overview | 개요

This repository is a private hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent), customized for the `jclee941/*` repository ecosystem. It preserves the upstream PR-Agent capabilities while adding repository-wide GitHub automation, security checks, release workflows, issue lifecycle management, and infrastructure automation.

**Key differentiators from upstream:**

| Aspect | Upstream (qodo-ai/pr-agent) | This Fork (jclee941) |
|--------|----------------------------|----------------------|
| LLM Backend | Configurable | CLIProxyAPI at `https://cliproxy.jclee.me/v1` |
| Default Model | `gpt-4` | `gpt-5.5` via CLIProxy routing |
| Fallback Models | Varies | `["minimax-m3"]` |
| Security Scanning | Basic | Deep security review workflow (`11_security-pr-review.yml`) |
| Workflow Coverage | Core PR tools | 35 workflows + 5 Go automation tools |
| Runner Environment | GitHub-hosted | GitHub-hosted (`ubuntu-latest`) + homelab API gateway |

All AI inference is routed through the homelab CLIProxyAPI deployment, enabling cost-effective LLM inference with model fallback and routing capabilities.

---

## Features | 기능

### AI-Powered Code Review

- **PR Review** (`10_pr-review.yml`): Automatic PR analysis with inline comments
- **Security Review** (`11_security-pr-review.yml`): Deep security-focused PR analysis
- **PR Improvement** (`/improve`): AI-suggested code improvements
- **PR Description** (`/describe`): Automatic PR changelog generation

### Security & Compliance

- **Secret Scanning**: Replaced by the jclee-bot Checks-API runner (`jclee-bot / secret-scan`) which runs gitleaks inside the App image; branch protection now requires that App context instead of a per-repo workflow.
- **CodeQL Analysis**: Handled by GitHub-native CodeQL default setup.
- **Dependency Review**: Handled by Dependabot's native vulnerability reporting.
- **Hardcode Pattern Scan** (`35_auto-hardcode-scan.yml`): Weekly scan for hardcoded credentials

### Issue Lifecycle Automation

- **Issue Management** (`18_issue-management.yml`, `43_reusable-issue-management.yml`): Automated issue handling
- **Issue Backfill** (`19_issue-backfill.yml`): Sync issues across repositories
- **Issue Classification** (`91_issue-classification.yml`): AI-powered issue categorization
- **Label Management** (`18_issue-management.yml`, `91_issue-classification.yml`): Automated labeling
- **Stale Management** (`16_stale-repo-identifier.yml`, `17_pr-stale-bot.yml`): Identify and close stale content

### Pull Request Automation

- **PR Metadata** (`jclee-bot / pr-metadata`): App-reported check covering title convention, PR size, and sensitive files. Replaces the old `03_pr-checks`, `44_reusable-pr-checks`, and `09_semantic-pr` workflows.
- **Auto Merge** (`13_pr-auto-merge.yml`): Automatic PR merging
- **Auto Fix** (`14_bot-auto-fix.yml`): Bot-initiated automatic fixes

### Release Engineering

- **Release Drafter** (`23_release-drafter.yml`): Automated release note drafting
- **Release Notes** (`24_release-notes.yml`): Structured release documentation
- **Release Publish** (`25_release-publish.yml`): Release publication workflow

### Documentation

- **README Generation** (`20_readme-gen.yml`): Automatic README updates
- **Docs Policy** (`jclee-bot / docs-policy`): App-reported documentation hygiene check for Markdown private IP leaks and docs freshness warnings

### Infrastructure & Health Monitoring

- **ELK Health Check** (`26_elk-health-check.yml`): Elasticsearch/ELK stack monitoring
- **ELK Setup** (`27_elk-setup.yml`): ELK infrastructure provisioning
- **Bot Health Monitor** (`28_bot-health-monitor.yml`): Bot service health tracking
- **Downstream Health Check** (`29_downstream-health-check.yml`): Dependency health monitoring
- **Runtime Health Check** (`30_runtime-health-check.yml`): Runtime environment validation
- **Repo Health** (`31_repo-health.yml`): Repository health metrics
- **Org Health Report** (`32_org-health-report.yml`): Organization-level health dashboard

### CI/CD & Automation Tools

- **Build and Push App** (`36_build-and-push-app.yml`): Container image build/push
- **CI Failure Issues** (`37_ci-failure-issues.yml`): Automatic issue creation on CI failure
- **E2E Testing** (`38_e2e.yml`, `39_e2e-live.yml`): End-to-end test suites
- **CI Auto Heal** (`60_ci-auto-heal.yml`): Automatic CI failure remediation
- **actionlint** (`jclee-bot / actionlint`): App-reported workflow YAML validation (replaces the deleted `04_actionlint.yml`)

### Repository Operations

- **Repo Review Batch** (`40_repo-review-batch.yml`): Batch repository review
- **Branch to PR** (`01_branch-to-pr.yml`): Branch-to-PR conversion automation
- **Issue to Branch** (`02_issue-to-branch.yml`): Issue-driven branch creation
- **Merged PR Cleanup** (`15_merged-pr-cleanup.yml`): Post-merge cleanup
- **Dependabot Auto Merge** (`12_dependabot-auto-merge.yml`): Automated dependency updates
- **Sanity Check** (`90_sanity.yml`): Fork CI gate

---

## Architecture | 아키텍처

```mermaid
flow TB
    subgraph "GitHub Repository jclee941/github-bot"
        subgraph "Workflows ubuntu-latest"
            W10["10_pr-review.yml<br/>PR Review"]
            W90["90_sanity.yml<br/>Sanity"]
            WSec["11_security-pr-review.yml<br/>Security Review"]
        end

        subgraph "jclee-bot GitHub App (homelab)"
            AppChecks["Checks API<br/>jclee-bot / pr-metadata<br/>jclee-bot / secret-scan<br/>jclee-bot / actionlint"]
        end
        subgraph "Go Automation Tools"
            G1["branch-protection"]
            G2["repo-review"]
            G3["rulesets-manager"]
            G4["sync-secrets"]
            G5["validate-naming"]
        end
        subgraph "pr_agent Python Package"
            P1["pr_agent.cli:run"]
            P2["AI Review Engine"]
            P3["Tool Handlers"]
        end
    end

    subgraph "GitHub Actions Runner"
        Runner["ubuntu-latest Runner"]
    end

    subgraph "Homelab CLIProxyAPI"
        Proxy["CLIProxyAPI Gateway<br/>&lt;homelab-host&gt;:8317"]
        
        subgraph "Model Routing"
            M1["minimax-m3"]
            M2["kimi-k2.6"]
            M3["gpt-5.5"]
        end

        Proxy --> M1
        Proxy --> M2
        Proxy --> M3
    end

    subgraph "External Services"
        GH["GitHub API"]
        ELK["ELK Stack<br/>&lt;homelab-elk&gt;"]
        Filebeat["Filebeat"]
    end

    W10 --> |"cli_proxy env vars"| Proxy
    WSec --> |"cli_proxy env vars"| Proxy
    P1 --> |"api_base: https://cliproxy.jclee.me/v1"| Proxy

    Runner --> |"Filebeat logging"| Filebeat
    Filebeat --> |"logs"| ELK

    GH --> |"webhook events"| W10
    GH --> |"webhook events"| WSec
```

**Data Flow:**

1. **PR Event Trigger**: GitHub webhook triggers `10_pr-review.yml` on `pull_request` events
2. **LLM Inference**: Workflow exports `CLIPROXY_API_KEY` and routes to CLIProxyAPI at `https://cliproxy.jclee.me/v1`
3. **Model Routing**: The PR-review workflow runs `gpt-5.5`; the GitHub App webhook default is `gpt-5.5` with fallback chain `[minimax-m3]`
4. **Security Scanning**: The jclee-bot GitHub App posts `jclee-bot / secret-scan`, `jclee-bot / pr-metadata`, and `jclee-bot / actionlint` check runs; `11_security-pr-review.yml` runs label-gated deep security review in parallel.
5. **Logging**: Filebeat ships workflow logs to ELK stack at `<homelab-elk>` for monitoring

---

## Automation Inventory | 자동화 인벤토리

### GitHub Workflows 35 total | GitHub 워크플로우 35개

#### PR/Branch Automation (3)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `01_branch-to-pr.yml` | push, manual | Convert feature branches to PRs automatically |
| `02_issue-to-branch.yml` | issues, manual | Create branches from issue assignments |
| `15_merged-pr-cleanup.yml` | pull_request, manual | Clean up branches after PR merge |

#### PR Quality & Security (0) — moved to the jclee-bot GitHub App

Branch protection on managed repos now requires the two App contexts (`pr-metadata`, `secret-scan`).

#### PR Review & Improvement (2)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `10_pr-review.yml` | pull_request | AI-powered PR review via CLIProxyAPI |
| `14_bot-auto-fix.yml` | pull_request | Bot-initiated automatic code fixes |

Conventional-commit title enforcement and PR size / sensitive-file checks were folded into the App-reported `jclee-bot / pr-metadata` context (the old `09_semantic-pr.yml` is deleted).

#### Merge Automation (3)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `12_dependabot-auto-merge.yml` | pull_request | Auto-merge Dependabot updates |
| `13_pr-auto-merge.yml` | pull_request_review, pull_request, manual | Automatic PR merging on approval |
| `60_ci-auto-heal.yml` | workflow_run, check_suite, repository_dispatch, manual | Auto-heal CI failures |

#### Issue Management (3)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `18_issue-management.yml` | issues, issue_comment, manual | Automated issue handling |
| `19_issue-backfill.yml` | workflow_run, manual | Sync issues across repositories |
| `91_issue-classification.yml` | issues, issue_comment, pull_request, manual | AI-powered issue categorization |

#### Stale & Cleanup (2)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `16_stale-repo-identifier.yml` | push, workflow_run, manual | Identify repositories with stale content |
| `17_pr-stale-bot.yml` | pull_request, workflow_run, manual | Mark and close stale PRs |

#### Documentation (1)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `20_readme-gen.yml` | push, manual | Automatic README regeneration |

Downstream documentation checks moved to the App-reported `jclee-bot / docs-policy` context; no downstream documentation workflow is deployed.

#### Release Engineering (3)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `23_release-drafter.yml` | push, pull_request, manual | Automated release note drafting |
| `24_release-notes.yml` | push, manual | Structured release documentation |
| `25_release-publish.yml` | push, manual | Release publication workflow |

#### Health Monitoring (6)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `26_elk-health-check.yml` | deployment_status, workflow_run, repository_dispatch, manual | Elasticsearch/ELK stack monitoring |
| `27_elk-setup.yml` | push, deployment, repository_dispatch, manual | ELK infrastructure provisioning |
| `28_bot-health-monitor.yml` | deployment_status, workflow_run, repository_dispatch, manual | Bot service health tracking |
| `29_downstream-health-check.yml` | workflow_run, repository_dispatch, manual | Dependency health monitoring |
| `30_runtime-health-check.yml` | deployment_status, workflow_run, repository_dispatch, manual | Runtime environment validation |
| `32_org-health-report.yml` | pull_request, workflow_run, manual | Organization-level health dashboard |

#### Infrastructure & Deployment (6)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `35_auto-hardcode-scan.yml` | push, pull_request, workflow_run, manual | Hardcoded credential scan |
| `36_build-and-push-app.yml` | push, manual | Container image build and push |
| `37_ci-failure-issues.yml` | workflow_run, repository_dispatch, manual | Auto-create issues on CI failure |
| `40_repo-review-batch.yml` | manual | Batch repository review |
| `41_pages-deploy.yml` | push, manual | GitHub Pages docs site deployment |
| `46_nas-cache-prune.yml` | workflow_run, manual | Prune the NFS-backed build cache on the self-hosted runner |

#### Testing (2)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `38_e2e.yml` | push, pull_request | End-to-end test suite |
| `39_e2e-live.yml` | workflow_run, repository_dispatch, manual | Live environment E2E testing |

#### Repository Health (1)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `31_repo-health.yml` | push, workflow_run, manual | Repository health metrics collection |

#### Security (1)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `11_security-pr-review.yml` | pull_request_target | Deep security review (Korean, `pull_request_target`) |

#### Reusable Workflows (1)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `43_reusable-issue-management.yml` | workflow_call, manual | Shared issue management |

The deleted `44_reusable-pr-checks.yml` and `45_reusable-gitleaks.yml` were the only callers of the now-removed per-repo `03_pr-checks` and `05_gitleaks` callers; with those gone, the reusables have no callers in this repo.

#### Fork CI Gate (1)

| Workflow File | Trigger | Description |
|---------------|---------|-------------|
| `90_sanity.yml` | push, pull_request | Fork CI gate replacing upstream CI |

---

### Go Automation Tools 5 total | Go 자동화 도구 5개

All tools are invoked via `(cd scripts && go run ./cmd/<tool-name>)`.

| Tool | Entry Point | Purpose |
|------|-------------|---------|
| `branch-protection` | `scripts/cmd/branch-protection/main.go` | Manage branch protection rules across repositories |
| `repo-review` | `scripts/cmd/repo-review/main.go` | Batch repository review and reporting |
| `rulesets-manager` | `scripts/cmd/rulesets-manager/main.go` | GitHub Rulesets management (list/apply/delete) |
| `sync-secrets` | `scripts/cmd/sync-secrets/main.go` | Synchronize secrets across repositories |
| `validate-naming` | `scripts/cmd/validate-naming/main.go` | Enforce naming conventions for branches/releases |

---

## Repository Structure | 저장소 구조

```
github-bot/
├── .github/
│   ├── workflows/              # GitHub Actions workflows (37 files)
│   │   ├── 01_branch-to-pr.yml
│   │   ├── 02_issue-to-branch.yml
│   │   ├── 10_pr-review.yml
│   │   ├── 12_dependabot-auto-merge.yml
│   │   ├── 13_pr-auto-merge.yml
│   │   ├── 14_bot-auto-fix.yml
│   │   ├── 15_merged-pr-cleanup.yml
│   │   ├── 16_stale-repo-identifier.yml
│   │   ├── 17_pr-stale-bot.yml
│   │   ├── 18_issue-management.yml
│   │   ├── 19_issue-backfill.yml
│   │   ├── 20_readme-gen.yml
│   │   ├── 23_release-drafter.yml
│   │   ├── 24_release-notes.yml
│   │   ├── 25_release-publish.yml
│   │   ├── 26_elk-health-check.yml
│   │   ├── 27_elk-setup.yml
│   │   ├── 28_bot-health-monitor.yml
│   │   ├── 29_downstream-health-check.yml
│   │   ├── 30_runtime-health-check.yml
│   │   ├── 31_repo-health.yml
│   │   ├── 32_org-health-report.yml
│   │   ├── 35_auto-hardcode-scan.yml
│   │   ├── 36_build-and-push-app.yml
│   │   ├── 37_ci-failure-issues.yml
│   │   ├── 38_e2e.yml
│   │   ├── 39_e2e-live.yml
│   │   ├── 40_repo-review-batch.yml
│   │   ├── 41_pages-deploy.yml
│   │   ├── 43_reusable-issue-management.yml
│   │   ├── 46_nas-cache-prune.yml
│   │   ├── 60_ci-auto-heal.yml
│   │   ├── 90_sanity.yml
│   │   ├── 91_issue-classification.yml
│   │   └── security/
│   └── PULL_REQUEST_TEMPLATE.md
│   └── CODEOWNERS
│   └── release-drafter.yml
│   └── ISSUE_TEMPLATE/
├── docs/
│   ├── architecture.md
│   ├── automation-enhancement-brainstorm.md
│   ├── git-workflow-gap-analysis.md
│   ├── github-profile-enhancement-brainstorm.md
│   ├── pr-agent-upstream-README.md
│   └── review-templates/
│       ├── code-review-template.md
│       ├── documentation-checklist.md
│       └── security-review-template.md
├── scripts/
│   ├── go.mod
│   ├── cmd/
│   │   ├── branch-protection/
│   │   │   ├── main.go
│   │   │   └── main_test.go
│   │   ├── repo-review/
│   │   │   ├── main.go
│   │   │   └── main_test.go
│   │   ├── rulesets-manager/
│   │   │   └── main.go
│   │   ├── sync-secrets/
│   │   │   └── main.go
│   │   └── validate-naming/
│   │       ├── main.go
│   │       └── main_test.go
│   ├── internal/
│   └── ...
├── tests/
│   ├── unittest/             # Unit tests
│   └── e2e/                  # End-to-end tests
│   └── e2e_live/             # Live environment tests
├── config/
│   └── repos.yaml            # Repository configuration
├── filebeat.yml              # Filebeat configuration for ELK
├── docker-compose.github_app.yml
├── docker-compose.github_app.yml.lxc
├── Dockerfile.github_action
├── Dockerfile.github_app
├── Makefile
├── pyproject.toml
├── setup.py
├── requirements.txt
├── requirements-dev.txt
└── _bot-scripts/             # CI transient checkout path
```

---

## Quick Start | 빠른 시작

### Prerequisites

- Python 3.12+
- GitHub account with access to `jclee941/*` repositories
- CLIProxyAPI access (configured via environment variables)

### Installation

```bash
# Clone the repository
git clone https://github.com/jclee941/.github
cd github-bot

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -e .
```

### Configuration

Create a `.env` file with your CLIProxyAPI credentials:

```bash
# .env (gitignored)
CLIPROXY_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://cliproxy.jclee.me/v1
```

### Running Locally

```bash
# Run PR review locally
pr-agent --pr_url https://github.com/jclee941/.github/pull/123 review

# Run specific tool
pr-agent --pr_url https://github.com/jclee941/.github/pull/123 describe
```

---

## Local Development | 로컬 개발

### Development Environment Setup

```bash
# Install all dependencies (including dev)
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install the package in editable mode
pip install -e .
```

### Running Tests

```bash
# All tests (unit + e2e + live)
make test

# Unit tests only
make test-unit

# End-to-end tests
make test-e2e

# Live environment tests
make test-live
```

### Linting

```bash
make lint
```

### Clean

```bash
make clean
```

---

## Commands Reference | 명령어 참조

### Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Create virtual environment and install package |
| `make test` | Run all tests (unit, e2e, live) |
| `make test-unit` | Run unit tests only |
| `make test-e2e` | Run end-to-end tests |
| `make test-live` | Run live environment tests |
| `make lint` | Run ruff linter |
| `make clean` | Remove cache and temporary files |

### Go Automation Tools

```bash
# Navigate to scripts directory
cd scripts

# Branch protection management
go run ./cmd/branch-protection

# GitHub Rulesets management (list/apply/delete)
go run ./cmd/rulesets-manager

# Synchronize secrets across repositories
go run ./cmd/sync-secrets

# Validate workflow/issue-template naming
go run ./cmd/validate-naming

# Batch repository review and reporting
go run ./cmd/repo-review

# Run all tests for Go tools
go test ./...
# Batch repository review
go run ./cmd/repo-review

# Manage GitHub Rulesets
go run ./cmd/rulesets-manager

# Synchronize secrets
go run ./cmd/sync-secrets

# Validate naming conventions
go run ./cmd/validate-naming

# Run all tests for Go tools
go test ./...
```

### pr-agent CLI

```bash
# PR Review
pr-agent --pr_url https://github.com/jclee941/.github/pull/123 review

# PR Description
pr-agent --pr_url https://github.com/jclee941/.github/pull/123 describe

# PR Improve
pr-agent --pr_url https://github.com/jclee941/.github/pull/123 improve

# Ask Question
pr-agent --pr_url https://github.com/jclee941/.github/pull/123 ask --question "What does this PR do?"

# Update Changelog
pr-agent --pr_url https://github.com/jclee941/.github/pull/123 update_changelog
```

---

## Contribution Guide | 기여 가이드

### Fork-Specific Guidelines

This is a hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent). When contributing:

1. **Preserve Upstream Functionality**: All upstream pr-agent features must remain functional
2. **Fork Delta Documentation**: Document any changes from upstream in `AGENTS.md`
3. **CLIProxy Integration**: New AI features should route through CLIProxyAPI
4. **Workflow Naming**: Use numeric prefixes (e.g., `10_`, `20_`) for workflow files
5. **Go Tool Structure**: Place new tools under `scripts/cmd/<tool-name>/`

### Branch Strategy

- `master`: Stable release branch
- `upstream/master`: Tracking upstream qodo-ai/pr-agent
- Feature branches: `feat/<feature-name>`

### Pull Request Process

1. Create a feature branch from `master`
2. Ensure `90_sanity.yml` passes
3. Run `make lint` and `make test-unit`
4. Update `AGENTS.md` if adding fork-specific changes
5. Request review from maintainers

### Adding Workflows

1. Use numeric prefix (e.g., `50_new-workflow.yml`)
2. Add to appropriate category in this README
3. Document trigger, description, and purpose
4. Ensure reusable workflows follow `reusable-*.yml` naming

### Adding Go Tools

1. Create `scripts/cmd/<tool-name>/main.go`
2. Add `main_test.go` with table-driven tests
3. Update Go module if adding dependencies
4. Document in `AGENTS.md` and this README

### License

This project is AGPL-3.0 licensed. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for details. Upstream attribution to [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) is preserved.

---

## Links | 링크

- **Upstream**: [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)
- **CLIProxy Gateway**: [cliproxy.jclee.me](https://cliproxy.jclee.me/v1)
- **Bot Status**: [bot.jclee.me](https://bot.jclee.me)
- **Documentation**: [docs/](docs/)
- **Upstream README**: [docs/pr-agent-upstream-README.md](docs/pr-agent-upstream-README.md)
