<think>
The user wants me to generate a comprehensive README.md for this repository. The repository appears to be a GitHub bot project (pr-agent fork) with extensive automation. Let me analyze all the provided information and create a comprehensive bilingual README in Korean and English.

Key information:

- Project: pr-agent fork for jclee941 repositories
- AI-powered PR reviewer
- Uses CLIProxyAPI at 192.168.50.114:8317 as LLM backend
- 56 workflow files
- 8 Go automation tools
- Hard fork of qodo-ai/pr-agent

Let me create a comprehensive README with:

1. Title
2. Badges
3. Overview (bilingual)
4. Features
5. Architecture
6. Automation Inventory (workflows + tools)
7. Quick Start
8. Local Development
9. Commands Reference
10. Contributing Guide

I need to be specific about workflow names and tool names.
</think>

# pr-agent (fork for jclee941)

# pr-agent (jclee941 포크)

---

## badges

```markdown
[![Project Version](https://img.shields.io/badge/version-0.3.1-blue.svg)](https://github.com/jclee941/github-bot)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/upstream-qodo--ai/pr--agent-red.svg)](https://github.com/qodo-ai/pr-agent)
```

[![Project Version](https://img.shields.io/badge/version-0.3.1-blue.svg)](https://github.com/jclee941/github-bot)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/upstream-qodo--ai/pr--agent-red.svg)](https://github.com/qodo-ai/pr-agent)

---

## Overview / 개요

### English

`pr-agent` is a private AI-powered pull request reviewer and automation bot for `jclee941/*` repositories. It is a hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) (AGPL-3.0), rewired to use a homelab [CLIProxyAPI](https://github.com/jclee941/CLIProxyAPI) deployment (`192.168.50.114:8317`) as the primary LLM backend. All workflows run on GitHub-hosted `ubuntu-latest` runners and reach the homelab LLM via the public internet through `https://cliproxy.jclee.me/v1`.

All upstream pr-agent features are preserved: `/review`, `/improve`, `/describe`, `/ask`, `/update_changelog`, PR compression, dynamic context, multi-model fallback, and slash commands.

### 한국어

`pr-agent`는 `jclee941/*` 레포지터리를 위한 개인용 AI 기반 풀 리퀘스트 리뷰어 및 자동화 봇입니다. [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)의 하드 포크(AGPL-3.0)로, 주 LLM 백엔드로 홈랩 [CLIProxyAPI](https://github.com/jclee941/CLIProxyAPI) 배포판(`192.168.50.114:8317`)을 사용하도록 재연결되었습니다. 모든 워크플로우는 GitHub 호스팅 `ubuntu-latest` 러너에서 실행되며, `https://cliproxy.jclee.me/v1`을 통해 공개 인터넷으로 홈랩 LLM에 접속합니다.

`/review`, `/improve`, `/describe`, `/ask`, `/update_changelog`, PR 압축, 동적 컨텍스트, 다중 모델 폴백, 슬래시 명령 등 상류(upstream) pr-agent의 모든 기능이 유지됩니다.

---

## Features / 기능

### English

| Feature | Description |
|---------|-------------|
| **AI Code Review** | Automated PR review via `/review` command with Korean and English support |
| **Auto Improvement** | `/improve` generates code suggestions and refactoring hints |
| **PR Description** | `/describe` auto-generates PR titles and descriptions |
| **Question Answering** | `/ask` answers questions about code context |
| **Changelog Updates** | `/update_changelog` tracks version history |
| **Security Review** | Dedicated security review workflow with `pull_request_target` trigger |
| **Secret Scanning** | Gitleaks integration for exposed secret detection |
| **Multi-Model Fallback** | Primary: `kimi-k2.6` → Fallback: `minimax-m2.7` → `gpt-5.5` |
| **Multi-Provider Support** | GitHub, GitLab, Bitbucket, Azure DevOps, Gitea, CodeCommit |
| **CI/CD Automation** | Auto-merge, stale bot, issue management, drift detection |

### 한국어

| 기능 | 설명 |
|------|------|
| **AI 코드 리뷰** | 한국어/영어 지원 `/review` 명령을 통한 자동 PR 리뷰 |
| **자동 개선** | `/improve`가 코드 제안 및 리팩토링 힌트 생성 |
| **PR 설명** | `/describe`가 PR 제목과 설명 자동 생성 |
| **질문 답변** | `/ask`가 코드 컨텍스트에 대한 질문 답변 |
| **체인지로그 업데이트** | `/update_changelog`로 버전 히스토리 추적 |
| **보안 리뷰** | `pull_request_target` 트리거를 사용하는 전용 보안 리뷰 워크플로우 |
| **시크릿 스캐닝** | 노출된 시크릿 감지를 위한 Gitleaks 통합 |
| **다중 모델 폴백** | Primary: `kimi-k2.6` → Fallback: `minimax-m2.7` → `gpt-5.5` |
| **다중 프로바이더 지원** | GitHub, GitLab, Bitbucket, Azure DevOps, Gitea, CodeCommit |
| **CI/CD 자동화** | 자동 병합, 스톨 봇, 이슈 관리, 드리프트 감지 |

---

## Architecture / 아키텍처

### English

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub-Hosted Runners                        │
│                      (ubuntu-latest)                            │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐       │
│  │   Workflows  │   │  Python App  │   │  Go Tools    │       │
│  │   (56 YAML)  │   │  (pr-agent)  │   │  (8 binaries)│       │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘       │
│         │                  │                  │                │
│         └──────────────────┼──────────────────┘                │
│                            │                                    │
│                     ┌──────▼──────┐                            │
│                     │  CLIProxy   │                            │
│                     │  API Client │                            │
│                     └──────┬──────┘                            │
└────────────────────────────┼────────────────────────────────────┘
                             │ HTTPS (cliproxy.jclee.me)
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                     Homelab (192.168.50.114)                    │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐       │
│  │ CLIProxyAPI  │   │   litellm    │   │  LLM Models  │       │
│  │   :8317      │──▶│   Router     │──▶│  (kimi/gpt)  │       │
│  └──────────────┘   └──────────────┘   └──────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 한국어

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub 호스티드 러너                         │
│                      (ubuntu-latest)                            │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐       │
│  │   워크플로우  │   │  Python 앱   │   │  Go 도구     │       │
│  │  (56 YAML)   │   │  (pr-agent)  │   │ (8 바이너리) │       │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘       │
│         │                  │                  │                │
│         └──────────────────┼──────────────────┘                │
│                            │                                    │
│                     ┌──────▼──────┐                            │
│                     │  CLIProxy   │                            │
│                     │  API Client │                            │
│                     └──────┬──────┘                            │
└────────────────────────────┼────────────────────────────────────┘
                             │ HTTPS (cliproxy.jclee.me)
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                     홈랩 (192.168.50.114)                      │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐       │
│  │ CLIProxyAPI  │   │   litellm    │   │  LLM 모델    │       │
│  │   :8317      │──▶│   라우터     │──▶│  (kimi/gpt)  │       │
│  └──────────────┘   └──────────────┘   └──────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Automation Inventory / 자동화 인벤토리

### English

#### Workflows (56 total)

##### Core PR Workflows

| Workflow | File | Purpose |
|----------|------|---------|
| **Branch to PR** | `01_branch-to-pr.yml` | Convert branch to PR |
| **Issue to Branch** | `02_issue-to-branch.yml` | Create branch from issue |
| **PR Checks** | `03_pr-checks.yml` | Run checks on PR |
| **PR Review** | `10_pr-review.yml` | AI-powered PR review |
| **PR Review (Security)** | `security/11_pr-review.yml` | Deep security review |
| **PR Auto Merge** | `13_pr-auto-merge.yml` | Auto-merge approved PRs |
| **PR Normalize** | `85_pr-normalize.yml` | Normalize PR format |
| **PR Size** | `87_pr-size.yml` | Track PR size metrics |
| **Merged PR Cleanup** | `15_merged-pr-cleanup.yml` | Clean up after merge |
| **Bot Auto Fix** | `14_bot-auto-fix.yml` | Auto-fix bot-detected issues |

##### Security & Compliance

| Workflow | File | Purpose |
|----------|------|---------|
| **Actionlint** | `04_actionlint.yml` | Lint GitHub Actions YAML |
| **Gitleaks** | `05_gitleaks.yml` | Secret pattern scanning |
| **CodeQL** | `06_codeql.yml` | Python SAST analysis |
| **Dependency Review** | `07_dependency-review.yml` | Dependency vulnerability check |
| **Scorecard** | `08_scorecard.yml` | Security scorecard |
| **Semantic PR** | `09_semantic-pr.yml` | Enforce semantic commits |
| **Auto Hardcode Scan** | `35_auto-hardcode-scan.yml` | Hardcoded credential scan |

##### Issue Management

| Workflow | File | Purpose |
|----------|------|---------|
| **Issue Management** | `18_issue-management.yml` | Manage issue lifecycle |
| **Issue Backfill** | `19_issue-backfill.yml` | Backfill issue metadata |
| **Issue Label** | `82_issue-label.yml` | Auto-label issues |
| **Issue Lifecycle** | `83_issue-lifecycle.yml` | Lifecycle automation |
| **Labeler** | `84_labeler.yml` | Auto-assign labels |
| **Stale** | `88_stale.yml` | Mark stale issues |
| **PR Stale Bot** | `17_pr-stale-bot.yml` | Mark stale PRs |
| **Stale Repo Identifier** | `16_stale-repo-identifier.yml` | Identify inactive repos |

##### Release & Deployment

| Workflow | File | Purpose |
|----------|------|---------|
| **Release Drafter** | `23_release-drafter.yml` | Draft release notes |
| **Release Notes** | `24_release-notes.yml` | Generate release notes |
| **Release Publish** | `25_release-publish.yml` | Publish releases |
| **Auto Deploy** | `34_auto-deploy.yml` | Automated deployment |
| **Build and Push App** | `36_build-and-push-app.yml` | Build Docker images |

##### Documentation & Sync

| Workflow | File | Purpose |
|----------|------|---------|
| **README Gen** | `20_readme-gen.yml` | Generate README files |
| **Docs Sync** | `21_docs-sync.yml` | Sync documentation |
| **Template Sync** | `22_template-sync.yml` | Sync PR/issue templates |

##### Health & Monitoring

| Workflow | File | Purpose |
|----------|------|---------|
| **ELK Health Check** | `26_elk-health-check.yml` | Monitor ELK stack |
| **ELK Setup** | `27_elk-setup.yml` | Setup ELK infrastructure |
| **Bot Health Monitor** | `28_bot-health-monitor.yml` | Monitor bot health |
| **Downstream Health Check** | `29_downstream-health-check.yml` | Check downstream deps |
| **Runtime Health Check** | `30_runtime-health-check.yml` | Runtime diagnostics |
| **Repo Health** | `31_repo-health.yml` | Repository health metrics |
| **Org Health Report** | `32_org-health-report.yml` | Organization health |
| **CI Failure Issues** | `37_ci-failure-issues.yml` | Create issues for CI failures |
| **Drift Detector** | `33_drift-detector.yml` | Detect configuration drift |
| **CI Auto Heal** | `60_ci-auto-heal.yml` | Auto-heal CI failures |

##### Testing

| Workflow | File | Purpose |
|----------|------|---------|
| **E2E** | `38_e2e.yml` | End-to-end tests |
| **E2E Live** | `39_e2e-live.yml` | Live E2E tests |
| **Repo Review Batch** | `40_repo-review-batch.yml` | Batch repo reviews |

##### Reusable Workflows

| Workflow | File | Purpose |
|----------|------|---------|
| **Reusable CI** | `41_reusable-ci.yml` | Reusable CI template |
| **Reusable Docs Sync** | `42_reusable-docs-sync.yml` | Reusable docs sync |
| **Reusable Issue Management** | `43_reusable-issue-management.yml` | Reusable issue mgmt |
| **Reusable PR Checks** | `44_reusable-pr-checks.yml` | Reusable PR checks |
| **Reusable Gitleaks** | `45_reusable-gitleaks.yml` | Reusable gitleaks |

##### Automation & Merging

| Workflow | File | Purpose |
|----------|------|---------|
| **Auto Merge** | `81_auto-merge.yml` | Auto-merge automation |
| **Dependabot Auto Merge** | `12_dependabot-auto-merge.yml` | Auto-merge Dependabot |
| **Welcome** | `89_welcome.yml` | Welcome message |
| **Sanity** | `90_sanity.yml` | Sanity checks |

#### Go Automation Tools (8 total)

| Tool | Path | Purpose |
|------|------|---------|
| **branch-protection** | `scripts/cmd/branch-protection/` | Manage branch protection rules |
| **deploy-to-repos** | `scripts/cmd/deploy-to-repos/` | Deploy workflows to repos |
| **drift-detector** | `scripts/cmd/drift-detector/` | Detect configuration drift |
| **repo-metadata** | `scripts/cmd/repo-metadata/` | Extract repository metadata |
| **repo-review** | `scripts/cmd/repo-review/` | Review repository health |
| **rulesets-manager** | `scripts/cmd/rulesets-manager/` | Manage GitHub Rulesets |
| **sync-secrets** | `scripts/cmd/sync-secrets/` | Synchronize secrets |
| **validate-naming** | `scripts/cmd/validate-naming/` | Validate naming conventions |

---

### 한국어

#### 워크플로우 (총 56개)

##### 핵심 PR 워크플로우

| 워크플로우 | 파일 | 목적 |
|-----------|------|------|
| **Branch to PR** | `01_branch-to-pr.yml` | 브랜치를 PR로 변환 |
| **Issue to Branch** | `02_issue-to-branch.yml` | 이슈에서 브랜치 생성 |
| **PR Checks** | `03_pr-checks.yml` | PR에서 체크 실행 |
| **PR Review** | `10_pr-review.yml` | AI 기반 PR 리뷰 |
| **PR Review (보안)** | `security/11_pr-review.yml` | 심층 보안 리뷰 |
| **PR Auto Merge** | `13_pr-auto-merge.yml` | 승인된 PR 자동 병합 |
| **PR Normalize** | `85_pr-normalize.yml` | PR 형식 정규화 |
| **PR Size** | `87_pr-size.yml` | PR 크기 메트릭 추적 |
| **Merged PR Cleanup** | `15_merged-pr-cleanup.yml` | 병합 후 정리 |
| **Bot Auto Fix** | `14_bot-auto-fix.yml` | 봇 감지 이슈 자동 수정 |

##### 보안 및 컴플라이언스

| 워크플로우 | 파일 | 목적 |
|-----------|------|------|
| **Actionlint** | `04_actionlint.yml` | GitHub Actions YAML 린트 |
| **Gitleaks** | `05_gitleaks.yml` | 시크릿 패턴 스캐닝 |
| **CodeQL** | `06_codeql.yml` | Python SAST 분석 |
| **Dependency Review** | `07_dependency-review.yml` | 의존성 취약점 검사 |
| **Scorecard** | `08
