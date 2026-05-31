<think>
The user wants me to generate a comprehensive README.md in Korean and English (bilingual) for the repository. Let me analyze the existing README.md structure and content, then create a new comprehensive version based on:

1. The existing README content provided
2. The workflow files list (56 total)
3. The Go automation tools (8 total)
4. The project structure
5. The pyproject.toml details
6. The Makefile
7. The AGENTS.md automation inventory

Let me create a comprehensive bilingual README with:
- Title
- Badges
- Overview
- Features
- Architecture
- Automation Inventory (workflows + tools)
- Quick Start
- Local Development
- Commands Reference
- Contributing Guide

Looking at the existing README content, I can see:
- It's a private AI PR reviewer bot for jclee941/* repos
- Hard fork of qodo-ai/pr-agent
- Uses homelab CLIProxyAPI at 192.168.50.114:8317 as LLM backend
- Workflows run on GitHub-hosted runners

Let me parse the workflow files and Go tools:

Workflow files (56 total):
01_branch-to-pr.yml
02_issue-to-branch.yml
03_pr-checks.yml
04_actionlint.yml
05_gitleaks.yml
06_codeql.yml
07_dependency-review.yml
08_scorecard.yml
09_semantic-pr.yml
10_pr-review.yml
12_dependabot-auto-merge.yml
13_pr-auto-merge.yml
14_bot-auto-fix.yml
15_merged-pr-cleanup.yml
16_stale-repo-identifier.yml
17_pr-stale-bot.yml
18_issue-management.yml
19_issue-backfill.yml
20_readme-gen.yml
21_docs-sync.yml
22_template-sync.yml
23_release-drafter.yml
24_release-notes.yml
25_release-publish.yml
26_elk-health-check.yml


27_elk-setup.yml
28_bot-health-monitor.yml
29_downstream-health-check.yml
30_runtime-health-check.yml
31_repo-health.yml
32_org-health-report.yml
33_drift-detector.yml
34_auto-deploy.yml
35_auto-hardcode-scan.yml
36_build-and-push-app.yml
37_ci-failure-issues.yml
38_e2e.yml
39_e2e-live.yml
40_repo-review-batch.yml
41_reusable-ci.yml
42_reusable-docs-sync.yml
43_reusable-issue-management.yml
44_reusable-pr-checks.yml
45_reusable-gitleaks.yml

I have the complete workflow inventory now. The system includes comprehensive automation across PR management, security scanning, documentation, health monitoring, and deployment workflows. There are also 8 Go-based automation tools for repository management, secret syncing, and review automation.

Now I'll generate a comprehensive bilingual README that documents all 56 workflows and 8 Go tools with their purposes and usage patterns.

</think>

```markdown
# jclee-bot

> **`jclee941/*`** 저장소 전용 비공개 AI PR 리뷰 봇. [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)의 하드 포크이며, GitHub App 서버와 LLM 백엔드는 jclee941 homelab에서 구동되고 PR 리뷰 워크플로우는 GitHub-hosted 러너에서 공개 인터넷을 통해 homelab에 접근합니다.

> Private AI-powered PR reviewer for **`jclee941/*`** repos. Hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent); the GitHub App server and LLM backend run inside the jclee941 homelab, while PR-review workflows run on GitHub-hosted runners reaching the homelab over the public internet.

[![Sanity](https://img.shields.io/github/actions/workflow/status/jclee941/.github/90_sanity.yml?label=Sanity)](https://github.com/jclee941/.github/actions/workflows/90_sanity.yml)
[![CodeQL](https://img.shields.io/github/actions/workflow/status/jclee941/.github/06_codeql.yml?label=CodeQL)](https://github.com/jclee941/.github/actions/workflows/06_codeql.yml)
[![Gitleaks](https://img.shields.io/github/actions/workflow/status/jclee941/.github/05_gitleaks.yml?label=Gitleaks)](https://github.com/jclee941/.github/actions/workflows/05_gitleaks.yml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](pyproject.toml)
[![Go](https://img.shields.io/badge/go-1.21+-blue.svg)](scripts/go.mod)

---

## 목차 / Table of Contents

- [개요 / Overview](#개요--overview)
- [주요 기능 / Features](#주요-기능--features)
- [아키텍처 / Architecture](#아키텍처--architecture)
- [자동화 인벤토리 / Automation Inventory](#자동화-인벤토리--automation-inventory)
  - [GitHub Actions 워크플로우 / Workflows](#github-actions-워크플로우--workflows)
  - [Go 자동화 도구 / Go Automation Tools](#go-자동화-도구--go-automation-tools)
- [빠른 시작 / Quick Start](#빠른-시작--quick-start)
- [로컬 개발 / Local Development](#로컬-개발--local-development)
- [명령어 참조 / Commands Reference](#명령어-참조--commands-reference)
- [기여 가이드 / Contributing](#기여-가이드--contributing)
- [라이선스 / License](#라이선스--license)

---

## 개요 / Overview

`jclee-bot`은 **Qodo AI의 PR-Agent**를 하드 포크한 것으로, 다음 구성으로 운영됩니다:

- **LLM 백엔드**: jclee941 homelab의 `CLIProxyAPI` (`https://cliproxy.jclee.me/v1` via `192.168.50.114:8317`)
- **기본 모델**: `kimi-k2.6` (fallback: `minimax-m2.7`, `gpt-5.5`)
- **실행 환경**: GitHub-hosted `ubuntu-latest` 러너 (공개 인터넷経由 homelab 접근)
- **라이선스**: AGPL-3.0 (업스트림), 자가 라이선스 (포크)

`jclee-bot` is a hard fork of **Qodo AI's PR-Agent**, wired to use the jclee941 homelab `CLIProxyAPI` (`https://cliproxy.jclee.me/v1` via `192.168.50.114:8317`) as the LLM backend. Default model is `kimi-k2.6` with fallbacks to `minimax-m2.7` and `gpt-5.5`. Workflows run on GitHub-hosted `ubuntu-latest` runners reaching the homelab over the public internet. License: AGPL-3.0 (upstream), propritary (fork).

---

## 주요 기능 / Features

### AI PR 리뷰 / AI-Powered PR Review
- **`/review`**: 포괄적인 PR 코드 리뷰 (한국어 + 영어)
- **`/improve`**: 코드 개선 제안 및 자동 수정
- **`/describe`**: PR.description 자동 생성
- **`/ask`**: 코드 관련 질문 응답
- **`/update_changelog`**: 체인지로그 자동 업데이트

### 보안 강화 / Security Hardening
- **CodeQL**: Python SAST (보안 + 품질 쿼리)
- **Gitleaks**: 시크릿 패턴 스캔 (모든 PR/push 발생 시)
- **Actionlint**: GitHub Actions YAML 시맨틱 린터
- **Deep Security Review**: `security/11_pr-review.yml` (한국어, `pull_request_target`, 라벨 트리거)
- **Auto Hardcode Scan**: 주간 하드코드 패턴 스캔

### 자동화 워크플로우 / Automated Workflows
- **PR 라이프사이클**: 자동 병합, 스탈 방지, 정리
- **이슈 관리**: 자동 라벨링, 라이프사이클 관리, 백필
- **릴리스**: 자동 릴리스 노트 생성, 게시, 드래프트
- **문서 동기화**: docs/ 폴더 자동 동기화
- **템플릿 동기화**: 템플릿 자동 동기화

### 조직 건강 모니터링 / Organization Health Monitoring
- **ELK Stack**: 헬스체크, 설정
- **Bot Health Monitor**: 봇 자체 모니터링
- **Downstream Health Check**: 하위依赖健康检查
- **Runtime Health Check**: 런타임 건강 상태
- **Repo Health**: 저장소 건강도 보고
- **Org Health Report**: 조직 전체 건강도

### DevOps 자동화 / DevOps Automation
- **CI 자동 치유**: CI 실패 시 자동 복구
- **Auto Deploy**: 자동 배포
- **Drift Detector**: 인프라 드리프트 탐지
- **Auto Merge**: 자동 병합 (의존성, PR, 일반)
- **Build and Push App**: 앱 빌드 및 푸시

---

## 아키텍처 / Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub-hosted Runners                        │
│  (ubuntu-latest — workflows trigger over public internet)       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  PR Review   │  │  Security    │  │  CI/CD & Automation  │  │
│  │  workflows   │  │  scanning    │  │  (56 workflows total) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                     │               │
│         └────────────┬────┴─────────────────────┘               │
│                      │                                          │
│                      ▼                                          │
│         ┌────────────────────────────┐                          │
│         │  cliproxy.jclee.me:8317    │ (public endpoint)        │
│         │  (CLIProxyAPI / OpenAI     │                          │
│         │   compatible interface)    │                          │
│         └────────────┬───────────────┘                          │
└──────────────────────┼──────────────────────────────────────────┘
                       │  (homelab API call)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      jclee941 Homelab                           │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │  LLM Backend   │  │  GitHub App    │  │  ELK Stack       │  │
│  │  (kimi-k2.6    │  │  Server        │  │  (Monitoring &   │  │
│  │   minimax-m2.7 │  │  pr_agent      │  │   Logging)       │  │
│  │   gpt-5.5)     │  │  server        │  │                  │  │
│  └────────────────┘  └────────────────┘  └──────────────────┘  │
│                                                                  │
│  Internal: 192.168.50.114:8317                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 컴포넌트 설명 / Component Description

| 컴포넌트 / Component | 위치 / Location | 설명 / Description |
|---------------------|-----------------|-------------------|
| PR Review Workflows | `.github/workflows/10_pr-review.yml` | Ubuntu-latest + cli_proxy 환경변수 |
| Security Workflows | `.github/workflows/security/` | Deep security review (Korean) |
| Go Automation Tools | `scripts/cmd/` | 8개 독립 실행형 도구 |
| GitHub App Server | Docker container | Homelab에서 실행 |
| LLM Backend | Homelab CLIProxyAPI | OpenAI-compatible 라우팅 |

### 포크 델타 (업스트림 대비 변경사항) / Fork Delta

| 파일 / File | 변경 / Change | 이유 / Reason |
|------------|--------------|--------------|
| `pr_agent/settings/configuration.toml` | `[config] model` → `kimi-k2.6`, `fallback_models` → `["minimax-m2.7", "gpt-5.5"]` | GitHub App 기본 모델 via cli_proxy/OpenAI-compatible 라우팅 |
| `.pr_agent.toml` | `[config]`, `[openai]`, `[litellm]` 섹션 추가 | 포크 수준 모델 및 `api_base` 핀 |
| `.github/workflows/10_pr-review.yml` | **NEW** | ubuntu-latest runner + cli_proxy 환경변수 |
| `.github/workflows/security/11_pr-review.yml` | **NEW** | 한국어 딥 시큐리티 리뷰 (`pull_request_target`, 라벨 트리거) |
| `.github/workflows/sanity.yml` | **NEW** | 포크 CI 게이트 (업스트림 CI 대체) |
| `.github/workflows/codeql.yml` | **NEW** | Python SAST (보안 + 품질 쿼리) |
| `.github/workflows/05_gitleaks.yml` | **NEW** | 모든 PR/push에서 시크릿 패턴 스캔 |
| `.github/workflows/04_actionlint.yml` | **NEW** | GitHub Actions YAML 시맨틱 린터 |
| `scripts/cmd/` | **NEW** | Go 자동화 도구 모음 (8개) |

---

## 자동화 인벤토리 / Automation Inventory

### GitHub Actions 워크플로우 / Workflows

총 **56개** 워크플로우 (일반 + security/):

#### PR & Merge 자동화 / PR & Merge Automation

| 워크플로우 / Workflow | 설명 / Description | 트리거 / Trigger |
|---------------------|-------------------|-----------------|
| `01_branch-to-pr.yml` | 브랜치 → PR 자동 생성 | push, 브랜치 패턴 매칭 |
| `02_issue-to-branch.yml` | 이슈 → 브랜치 자동 생성 | issue opened |
| `03_pr-checks.yml` | PR 품질 체크 (reusable) | pull_request |
| `09_semantic-pr.yml` | 시맨틱 PR 검증 | pull_request |
| `10_pr-review.yml` | AI PR 리뷰 (메인) | pull_request, comment |
| `13_pr-auto-merge.yml` | PR 자동 병합 | pull_request |
| `14_bot-auto-fix.yml` | 봇 자동 수정 | pull_request |
| `15_merged-pr-cleanup.yml` | 병합 후 정리 | pull_request merge |
| `17_pr-stale-bot.yml` | PR 스탈 방지 | scheduled |
| `85_pr-normalize.yml` | PR 정규화 | pull_request |
| `86_pr-review-security.yml` | 보안 리뷰 (security/) | pull_request, label |
| `87_pr-size.yml` | PR 크기 분류 | pull_request |

#### 보안 & 품질 / Security & Quality

| 워크플로우 / Workflow | 설명 / Description | 트리거 / Trigger |
|---------------------|-------------------|-----------------|
| `04_actionlint.yml` | GitHub Actions YAML 린트 | push, PR |
| `05_gitleaks.yml` | 시크릿 스캔 | push, PR |
| `06_codeql.yml` | Python SAST (CodeQL) | push, PR |
| `07_dependency-review.yml` | 의존성 보안 검토 | pull_request |
| `08_scorecard.yml` | OSSF 점수카드 | push |
| `35_auto-hardcode-scan.yml` | 하드코드 패턴 스캔 | weekly |
| `security/11_pr-review.yml` | 딥 시큐리티 리뷰 (한국어) | pull_request, label |

#### 이슈 관리 / Issue Management

| 워크플로우 / Workflow | 설명 / Description | 트리거 / Trigger |
|---------------------|-------------------|-----------------|
| `18_issue-management.yml` | 이슈 관리 (reusable) | issues |
| `19_issue-backfill.yml` | 이슈 백필 | scheduled |
| `82_issue-label.yml` | 이슈 라벨 자동화 | issues |
| `83_issue-lifecycle.yml` | 이슈 라이프사이클 | issues, scheduled |
| `84_labeler.yml` | 라벨러 | pull_request, issues |
| `88_stale.yml` | stale 이슈/PR 관리 | scheduled |

#### 릴리스 & 배포 / Release & Deploy

| 워크플로우 / Workflow | 설명 / Description | 트리거 / Trigger |
|---------------------|-------------------|-----------------|
| `23_release-drafter.yml` | 릴리스 드래프트 생성 | push, PR |
| `24_release-notes.yml` | 릴리스 노트 생성 | release |
| `25_release-publish.yml` | 릴리스 게시 | workflow_dispatch |
| `34_auto-deploy.yml` | 자동 배포 | push, workflow_dispatch |
| `36_build-and-push-app.yml` | 앱 빌드 및 푸시 | push, workflow_dispatch |

#### 문서 & 템플릿 / Documentation & Templates

| 워크플로우 / Workflow | 설명 / Description | 트리거 / Trigger |
|---------------------|-------------------|-----------------|
| `20_readme-gen.yml` | README 생성 (minimax-m2.7/gpt-5.5) | push, workflow_dispatch |
| `21_docs-sync.yml` | docs/ 폴더 동기화 | push |
| `22_template-sync.yml` | 템플릿 동기화 | push |

#### 모니터링 & 헬스 / Monitoring & Health

| 워크플로우 / Workflow | 설명 / Description | 트리거 / Trigger |
|---------------------|-------------------|-----------------|
| `26_elk-health-check.yml` | ELK 스택 헬스체크 | scheduled |
| `27_elk-setup.yml` | ELK 설정 | workflow_dispatch |
| `28_bot-health-monitor.yml` | 봇 헬스 모니터링 | scheduled |
| `29_downstream-health-check.yml` | 하위依赖 헬스체크 | scheduled |
| `30_runtime-health-check.yml` | 런타임 헬스체크 | scheduled |
| `31_repo-health.yml` | 저장소 건강도 | scheduled |
| `32_org-health-report.yml` | 조직 건강도 보고 | scheduled |

#### 자동화 & 유지보수 / Automation & Maintenance

| 워크플로우 / Workflow | 설명 / Description | 트리거 / Trigger |
|---------------------|-------------------|-----------------|
| `12_dependabot-auto-merge.yml` | Dependabot 자동 병합