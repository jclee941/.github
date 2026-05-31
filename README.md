<think>
The user wants me to generate a comprehensive README.md for a repository. Let me analyze the provided information:

1. **Project**: `jclee-bot` - A private AI-powered PR reviewer bot for `jclee941/*` repositories
2. **Fork**: Hard fork of `qodo-ai/pr-agent`
3. **Architecture**: GitHub App server + LLM backend run in homelab, workflows run on GitHub-hosted runners
4. **Key features**: PR review, AI agents, automation workflows

From the project structure, I can see:
- 56 workflow files (GitHub Actions)
- 8 Go automation tools
- Python-based pr-agent with various dependencies
- Docker support for GitHub App and Actions
- Comprehensive test suite

Let me create a bilingual (Korean/English) README with:
1. Title and badges
2. Overview
3. Features
4. Architecture
5. Automation inventory (workflows + tools)
6. Quick start
7. Local development
8. Commands reference
9. Contribution guide

I need to be specific about:
- Workflow names (from the 56 provided)
- Go tool names (from the 8 provided)
- README-gen models: minimax-m2.7 with fallback gpt-5.5 (via CLIProxyAPI)

Let me write this comprehensive README.

</think>

# jclee-bot

> `jclee941/*` 저장소 전용 비공개 AI PR 리뷰 봇. [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)의 하드 포크이며, GitHub App 서버와 LLM 백엔드는 jclee941 homelab에서 구동되고 PR 리뷰 워크플로우는 GitHub-hosted 러너에서 공개 인터넷을 통해 homelab에 접근합니다.
>
> Private AI-powered PR reviewer for `jclee941/*` repos. Hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent); the GitHub App server and LLM backend run inside the jclee941 homelab, while PR-review workflows run on GitHub-hosted runners reaching the homelab over the public internet.

[![Sanity](https://img.shields.io/github/actions/workflow/status/jclee941/.github/90_sanity.yml?label=Sanity)](https://github.com/jclee941/.github/actions/workflows/90_sanity.yml)
[![CodeQL](https://img.shields.io/github/actions/workflow/status/jclee941/.github/06_codeql.yml?label=CodeQL)](https://github.com/jclee941/.github/actions/workflows/06_codeql.yml)
[![Gitleaks](https://img.shields.io/github/actions/workflow/status/jclee941/.github/05_gitleaks.yml?label=Gitleaks)](https://github.com/jclee941/.github/actions/workflows/05_gitleaks.yml)
[![Dependency Review](https://img.shields.io/github/actions/workflow/status/jclee941/.github/07_dependency-review.yml?label=Dependency%20Review)](https://github.com/jclee941/.github/actions/workflows/07_dependency-review.yml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](pyproject.toml)
[![Go](https://img.shields.io/badge/go-1.21+-blue.svg)](scripts/go.mod)
[![PR Review](https://img.shields.io/github/actions/workflow/status/jclee941/.github/10_pr-review.yml?label=PR%20Review)](https://github.com/jclee941/.github/actions/workflows/10_pr-review.yml)

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

`jclee-bot`은 **Qodo AI의 PR-Agent**를 하드 포크한 것으로, 다음과 같은架构으로 운영됩니다:

- **GitHub App Server**: jclee941 homelab (`192.168.50.114:8317`)에서 실행
- **LLM Backend**: homelab 내 CLIProxyAPI (`https://cliproxy.jclee.me/v1`) — 기본 모델 `minimax-m2.7`, 폴백 `gpt-5.5`
- **Workflow 실행**: GitHub-hosted `ubuntu-latest` 러너에서 실행되어 공개 인터넷을 통해 homelab LLM에 접근

### 포크 변동 사항 / Fork Delta

| 항목 / Item | 변경 내용 / Change | 이유 / Reason |
|-------------|-------------------|---------------|
| `pr_agent/settings/configuration.toml` | 모델 → `kimi-k2.6`, fallback → `["minimax-m2.7", "gpt-5.5"]` | CLIProxyAPI 라우팅 |
| `.pr_agent.toml` | `[config]`, `[openai]`, `[litellm]` 섹션 추가 | 포크 레벨 설정 pinning |
| `.github/workflows/10_pr-review.yml` | **NEW** | Ubuntu-latest + cli_proxy 환경변수 |
| `.github/workflows/security/11_pr-review.yml` | **NEW** | 심층 보안 리뷰 (한국어, `pull_request_target`, 라벨 트리거) |
| `scripts/go.mod` | **NEW** | Go 도구 모듈화 (`go run ./cmd/<name>`) |
| `README.md` | **REPLACED** | 포크 특화 README |

---

## 주요 기능 / Features

### 🤖 AI PR 리뷰 / AI PR Review

- **`/review`**: 자동 PR 코드 리뷰 (한국어/영어双语 지원)
- **`/improve`**: 코드 개선 제안 생성
- **`/describe`**: PR 설명 자동 생성
- **`/ask`**: 코드 관련 질문 답변
- **`/update_changelog`**: 체인지로그 업데이트

### 🔒 보안 강화 / Security Hardening

- **Secret Scanning**: Gitleaks 기반 비밀번호/토큰 스캔
- **CodeQL Analysis**: Python SAST (보안 + 품질 쿼리)
- **Dependency Review**: 의존성 취약점 검사
- **Security PR Review**: 심층 보안 리뷰 워크플로우 (라벨 트리거)
- **Hardcode Scan**: 주기적 하드코딩 패턴 스캔

### 🔄 자동화 워크플로우 / Automated Workflows

- **PR 라이프사이클**: 자동 병합, 스탠프 처리, 정규화
- **Issue 관리**: 자동 라벨링, 수명 주기 관리, 백필
- **릴리스**: Release Drafter, 릴리스 노트 생성, 게시
- **CI/CD**: 자동 배포, Drift 감지, 헬스 체크
- **Repository Health**: 상태 모니터링 및 리포트

### 🛠️ Go 도구 / Go Tools

- `branch-protection`: 브랜치 보호 규칙 관리
- `deploy-to-repos`: PR 리뷰 워크플로우 배포
- `drift-detector`: 인프라 drift 감지
- `repo-metadata`: 리포지토리 메타데이터 관리
- `repo-review`: 리포지토리 리뷰 자동화
- `rulesets-manager`: GitHub Rulesets 관리
- `sync-secrets`: 시크릿 동기화
- `validate-naming`: 네이밍 규칙 검증

---

## 아키텍처 / Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub-hosted Runners                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ubuntu-latest                                           │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │ PR Review   │  │ CI Checks   │  │ Security    │      │   │
│  │  │ Workflow    │  │ Workflow    │  │ Workflow    │      │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘      │   │
│  │         │                │                │              │   │
│  └─────────┼────────────────┼────────────────┼──────────────┘   │
│            │                │                │                   │
│            └────────────────┼────────────────┘                   │
│                             │                                    │
│                      Public Internet                             │
│                             │                                    │
└─────────────────────────────┼────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     jclee941 Homelab                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  CLIProxyAPI Server                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │ minimax-m2.7│  │   gpt-5.5   │  │  kimi-k2.6  │      │   │
│  │  │  (primary)  │  │  (fallback) │  │  (default)  │      │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘      │   │
│  │                                                          │   │
│  │  GitHub App Server (FastAPI + PyGithub)                  │   │
│  │  - PR-Agent Logic                                        │   │
│  │  - Webhook Handler                                       │   │
│  │  - Git Provider Integration (GitHub, GitLab, Bitbucket)  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  Host: 192.168.50.114:8317                                     │
│  Endpoint: https://cliproxy.jclee.me/v1                        │
└─────────────────────────────────────────────────────────────────┘
```

### 컴포넌트 / Components

| 컴포넌트 / Component | 기술 스택 / Tech Stack | 용도 / Purpose |
|---------------------|----------------------|---------------|
| **PR Agent** | Python 3.12+, Litellm | AI 코드 리뷰引擎 |
| **CLIProxyAPI** | FastAPI, uvicorn | LLM 라우팅 (OpenAI 호환) |
| **GitHub App** | PyGithub, Flask/Starlette | 웹훅 처리 및 API 상호작용 |
| **Workflows** | GitHub Actions (YAML) | CI/CD 및 자동화 |
| **Go Tools** | Go 1.21+ | Infrastructure automation |

---

## 자동화 인벤토리 / Automation Inventory

### GitHub Actions 워크플로우 / Workflows

#### 🔴 품질 gates (Quality Gates)

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|---------------------|------------|-------------------|
| **Sanity** | `90_sanity.yml` | 포크 CI gate — 필수 정적 검사 |
| **CodeQL** | `06_codeql.yml` | Python SAST (보안 + 품질 쿼리) |
| **Gitleaks** | `05_gitleaks.yml` | 비밀번호/토큰 스캔 |
| **Actionlint** | `04_actionlint.yml` | GitHub Actions YAML 유효성 검사 |
| **Dependency Review** | `07_dependency-review.yml` | 의존성 취약점 검사 |
| **Scorecard** | `08_scorecard.yml` | OpenSSF 보안 점수 |

#### 🟡 PR 처리 (PR Processing)

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|---------------------|------------|-------------------|
| **PR Review** | `10_pr-review.yml` | AI PR 리뷰 (ubuntu-latest + cli_proxy) |
| **Security PR Review** | `security/11_pr-review.yml` | 심층 보안 리뷰 (라벨 트리거) |
| **PR Checks** | `03_pr-checks.yml`, `44_reusable-pr-checks.yml` | PR 필수 체크 |
| **PR Auto-Merge** | `13_pr-auto-merge.yml` | 자동 병합 |
| **PR Stale Bot** | `17_pr-stale-bot.yml` | 오래된 PR 처리 |
| **PR Size** | `87_pr-size.yml` | PR 크기 분류 |
| **PR Normalize** | `85_pr-normalize.yml` | PR 정규화 |
| **Semantic PR** | `09_semantic-pr.yml` | 시맨틱 커밋 검증 |
| **Branch to PR** | `01_branch-to-pr.yml` | 브랜치 → PR 변환 |
| **Auto-Fix** | `14_bot-auto-fix.yml` | 자동 수정 시도 |
| **Merged PR Cleanup** | `15_merged-pr-cleanup.yml` | 병합 후 정리 |

#### 🔵 Issue 관리 (Issue Management)

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|---------------------|------------|-------------------|
| **Issue Management** | `18_issue-management.yml`, `43_reusable-issue-management.yml` | Issue lifecycle management |
| **Issue Backfill** | `19_issue-backfill.yml` | Issue 데이터 백필 |
| **Issue Label** | `82_issue-label.yml` | 자동 라벨링 |
| **Issue Lifecycle** | `83_issue-lifecycle.yml` | Issue 수명 주기 관리 |
| **Stale** | `88_stale.yml` | 오래된 항목 처리 |
| **Labeler** | `84_labeler.yml` | 라벨 자동 할당 |

#### 🟢 Release 및 배포 (Release & Deploy)

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|---------------------|------------|-------------------|
| **Release Drafter** | `23_release-drafter.yml` | 릴리스 초안 자동 생성 |
| **Release Notes** | `24_release-notes.yml` | 릴리스 노트 생성 |
| **Release Publish** | `25_release-publish.yml` | 릴리스 게시 |
| **Auto-Deploy** | `34_auto-deploy.yml` | 자동 배포 |
| **Build and Push App** | `36_build-and-push-app.yml` | Docker 이미지 빌드/푸시 |
| **Dependabot Auto-Merge** | `12_dependabot-auto-merge.yml` | Dependabot PR 자동 병합 |
| **Auto-Merge** | `81_auto-merge.yml` | 범용 자동 병합 |

#### 🟣 Docs 및 동기화 (Docs & Sync)

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|---------------------|------------|-------------------|
| **README Gen** | `20_readme-gen.yml` | README 생성 (minimax-m2.7 + gpt-5.5 fallback) |
| **Docs Sync** | `21_docs-sync.yml`, `42_reusable-docs-sync.yml` | 문서 동기화 |
| **Template Sync** | `22_template-sync.yml` | 템플릿 동기화 |

#### 🔵 모니터링 및 헬스 (Monitoring & Health)

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|---------------------|------------|-------------------|
| **Bot Health Monitor** | `28_bot-health-monitor.yml` | 봇 상태 모니터링 |
| **ELK Health Check** | `26_elk-health-check.yml` | ELK 스택 헬스 체크 |
| **ELK Setup** | `27_elk-setup.yml` | ELK 설정 |
| **Downstream Health Check** | `29_downstream-health-check.yml` | 다운스트림 상태 확인 |
| **Runtime Health Check** | `30_runtime-health-check.yml` | 런타임 헬스 체크 |

#### 🟡 Repository 관리 (Repository Management)

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|---------------------|------------|-------------------|
| **Repo Health** | `31_repo-health.yml` | 리포지토리 건강 상태 |
| **Org Health Report** | `32_org-health-report.yml` | 조직 건강 리포트 |
| **Stale Repo Identifier** | `16_stale-repo-identifier.yml` | 오래된 리포지토리 식별 |
| **Drift Detector** | `33_drift-detector.yml` | 인프라 drift 감지 |
| **Ignore Repositories** | `test_ignore_repositories.py` | 리포지토리 무시 관리 |

#### 🟠 CI 및 빌드 (CI & Build)

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|---------------------|------------|-------------------|
| **CI Failure Issues** | `37_ci-failure-issues.yml` | CI 실패 시 Issue 생성 |
| **CI Auto-Heal** | `60_ci-auto-heal.yml` | CI 자동 복구 |
| **Reusable CI** | `41_reusable-ci.yml` | 재사용 가능 CI 템플릿 |
| **E2E** | `38_e2e.yml` | End-to-End 테스트 |
| **E2E Live** | `39_e2e-live.yml` | 라이브 E2E 테스트 |
| **Repo Review Batch** | `40_repo-review-batch.yml` | 배치 리포지토리 리뷰 |
| **Auto Hardcode Scan** | `35_auto-hardcode-scan.yml` | 하드코딩 패턴 주기적 스캔 |
| **Welcome** | `89_welcome.yml` | 신규 기여자 환영 |

---

### Go 자동화 도구 / Go Automation Tools

| 도구 / Tool | 경로 / Path | 설명 / Description |
|------------|------------|-------------------|
| **branch-protection** | `scripts/cmd/branch-protection/` | 브랜치 보호 규칙 관리 (list/apply/delete) |
| **deploy-to-repos** | `scripts/cmd/deploy-to-repos/` | `pr-review.yml` 워크플로우를 `jclee941/*` 리포지토리에 배포