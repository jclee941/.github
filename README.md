# jclee-bot

>私有 AI 驱动的 PR 审查器，专为 `jclee941/*` 仓库打造。作为 [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) 的硬分支，完全在 jclee941 homelab 内运行。

>Private AI-powered PR reviewer for `jclee941/*` repos. Hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent), wired to run entirely inside the jclee941 homelab.

[![Sanity](https://img.shields.io/github/actions/workflow/status/jclee941/.github/sanity.yml?label=Sanity)](https://github.com/jclee941/.github/actions/workflows/90_sanity.yml)
[![CodeQL](https://img.shields.io/github/actions/workflow/status/jclee941/.github/codeql.yml?label=CodeQL)](https://github.com/jclee941/.github/codeql.yml)
[![Gitleaks](https://img.shields.io/github/actions/workflow/status/jclee941/.github/gitleaks.yml?label=Gitleaks)](https://github.com/jclee941/.github/workflows/05_gitleaks.yml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](pyproject.toml)
[![Go](https://img.shields.io/badge/go-1.23+-blue.svg)](go.mod)

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

`jclee-bot`은 **Qodo AI의 PR-Agent**를 하드 포크한 것으로, 다음 구성으로 homelab 환경에서 운영됩니다:

| 항목 / Item | 내용 / Value |
|-------------|--------------|
| **LLM 백엔드** | `CLIProxyAPI` @ `192.168.50.114:8317` (LXC 100) |
| **Webhook 엔드포인트** | `https://bot.jclee.me` (Cloudflare Tunnel) |
| **GitHub App** | `jclee-bot` (ID: 3540327) |
| **기본 모델** | `minimax-m2.7`, `gpt-5.5` (via CLIProxyAPI) |
| **적용 범위** | `jclee941/*` 프라이빗 리포지토리 |
| **런너** | GitHub-hosted `ubuntu-latest` + self-hosted (일부) |

> **Note / 참고**: Homelab에 공개 인터넷을 통해 접근하며, CLIProxyAPI는 Claude Code CLI / Codex CLI / Gemini CLI를 OpenAI 호환 API로 래핑합니다.

---

## 주요 기능 / Features

- ### AI PR 리뷰 / AI-Powered PR Review

  - `/review` — 자동 코드 리뷰 및 개선 제안
  - `/improve` — 코드 개선안 생성
  - `/describe` — PR 설명 생성
  - `/ask` — 코드 관련 질문 답변
  - `/update_changelog` — 체인지로그 업데이트

- ### 자동화 워크플로우 / Automated Workflows

  - PR 정규화, 사이즈 분류, 스탤 플래그
  - 자동 머지, 보안 리뷰, 의존성 검토
  - 이슈 라이프사이클 관리, 템플릿 동기화

- ### 보안 강화 / Security Hardening

  - CodeQL 정적 분석
  - Gitleaks 시크릿 스캐닝
  - Dependabot 자동 병합
  - 보안 리뷰 워크플로우 (심층 분석)

- ### Go 기반运维 도구 / Go Operational Tools

  - 브랜치 보호 관리
  - 리포지토리 일괄 배포
  - 드리프트 감지
  - 룰셋 관리
  - 시크릿 동기화

---

## 아키텍처 / Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub / Cloudflare                         │
│                  https://bot.jclee.me/webhook                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub App (jclee-bot)                        │
│                         ID: 3540327                              │
│              LXC 114 + Cloudflare Tunnel                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        PR Agent (Python)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  GitHub App  │  │   Webhook    │  │   GitHub Actions     │  │
│  │   Server     │  │   Handler    │  │   Runner (ubuntu)    │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  CLI Parser  │  │   Config     │  │   Secret Providers   │  │
│  │   (slash     │  │   Loader     │  │   (AWS/GCP)          │  │
│  │   commands)  │  │              │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLIProxyAPI (LXC 100)                        │
│                 192.168.50.114:8317                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              OpenAI-Compatible API                       │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────┐     │   │
│  │  │ minimax-m2.7│  │  gpt-5.5   │  │  (fallback)    │     │   │
│  │  └────────────┘  └────────────┘  └────────────────┘     │   │
│  └──────────────────────────────────────────────────────────┘   │
│  Wraps: Claude Code CLI / Codex CLI / Gemini CLI                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Go Automation Tools                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │branch-       │  │  deploy-     │  │     drift-           │  │
│  │protection    │  │  to-repos     │  │     detector         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  repo-review │  │ rulesets-    │  │     sync-secrets     │  │
│  │              │  │  manager     │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Docker Deployment                            │
│  ┌──────────────────────┐  ┌────────────────────────────────┐   │
│  │ Dockerfile.github_app│  │   Dockerfile.github_action    │   │
│  │  (GitHub App server) │  │   (Actions runner container)  │   │
│  └──────────────────────┘  └────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │          docker-compose.github_app.yml                   │    │
│  │          (LXC 114 deployment)                            │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 자동화 인벤토리 / Automation Inventory

### GitHub Actions 워크플로우 / Workflows

#### 🔄 CI/CD 파이프라인

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| **Sanity Check** | `sanity.yml` | 포크 CI 게이트 — 포크 전용 정적 검사 |
| **E2E Tests** | `e2e.yml` | 엔드투엔드 테스트 |
| **E2E Live** | `e2e-live.yml` | 라이브 환경 테스트 |
| **Reusable CI** | `reusable-ci.yml` | 공통 CI 템플릿 |
| **Build and Push** | `build-and-push-app.yml` | Docker 이미지 빌드 및 푸시 |
| **CodeQL** | `codeql.yml` | Python SAST (보안 + 품질 쿼리) |
| **Dependency Review** | `dependency-review.yml` | 의존성 보안 검토 |
| **Gitleaks** | `gitleaks.yml` | 시크릿 패턴 스캐닝 |
| **Actionlint** | `actionlint.yml` | GitHub Actions YAML 문법 검사 |
| **Scorecard** | `scorecard.yml` | OSS 보안 점수 측정 |

#### 🎯 PR 자동화

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| **PR Review** | `pr-review.yml` | AI PR 리뷰 (ubuntu-latest + cli_proxy) |
| **PR Checks** | `pr-checks.yml` | PR 상태 확인 |
| **PR Auto Merge** | `pr-auto-merge.yml` | 자동 병합 |
| **PR Stale Bot** | `pr-stale-bot.yml` | 스탤 PR 처리 |
| **PR Normalize** | `_pr-normalize.yml` | PR 정규화 (제목, 라벨) |
| **PR Size** | `_pr-size.yml` | 변경량 사이즈 분류 |
| **PR Review Security** | `_pr-review-security.yml` | 심층 보안 리뷰 |
| **Auto Merge** | `_auto-merge.yml` | 자동 병합 트리거 |
| **Branch to PR** | `branch-to-pr.yml` | 브랜치 → PR 변환 |
| **Merged PR Cleanup** | `merged-pr-cleanup.yml` | 병합 후 정리 |

#### 🔒 보안 워크플로우

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| **Security PR Review** | `security/pr-review.yml` | 심층 보안 리뷰 (Korean, label-triggered) |
| **Gitleaks Scan** | `gitleaks.yml` | 매 PR/push 시 시크릿 스캔 |
| **Dependency Review** | `dependency-review.yml` | 의존성 취약점 검토 |
| **Auto Hardcode Scan** | `auto-hardcode-scan.yml` | 주간 하드코드 패턴 스캔 |
| **Bot Auto Fix** | `bot-auto-fix.yml` | 자동 보안 수정 |

#### 📋 이슈 관리

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| **Issue Management** | `issue-management.yml` | 이슈 수명주기 관리 |
| **Issue to Branch** | `issue-to-branch.yml` | 이슈 → 브랜치 생성 |
| **CI Failure Issues** | `ci-failure-issues.yml` | CI 실패 시 이슈 생성 |
| **Issue Label** | `_issue-label.yml` | 자동 라벨링 |
| **Issue Lifecycle** | `_issue-lifecycle.yml` | 이슈 수명주기 관리 |
| **Org Health Report** | `org-health-report.yml` | 조직 건강도 보고 |
| **Stale Repo Identifier** | `stale-repo-identifier.yml` | 비활성 리포지토리 식별 |
| **Issue Backfill** | `issue-backfill.yml` | 이슈 백필 |

#### 📚 문서화

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| **Docs Sync** | `docs-sync.yml` | 문서 동기화 |
| **Readme Generator** | `readme-gen.yml` | README 자동 생성 |
| **Reusable Docs Sync** | `reusable-docs-sync.yml` | 문서 동기화 템플릿 |

#### 🚀 배포 및 유지보수

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| **Auto Deploy** | `auto-deploy.yml` | 자동 배포 |
| **Template Sync** | `template-sync.yml` | 템플릿 동기화 |
| **Dependabot Auto Merge** | `dependabot-auto-merge.yml` | Dependabot PR 자동 병합 |
| **Release Drafter** | `release-drafter.yml` | 릴리스 초안 생성 |
| **Release Notes** | `release-notes.yml` | 릴리스 노트 생성 |
| **Release Publish** | `release-publish.yml` | 릴리스 게시 |
| **Drift Detector** | `drift-detector.yml` | 구성 드리프트 감지 |
| **Bot Health Monitor** | `bot-health-monitor.yml` | 봇 건강도 모니터링 |
| **Runtime Health Check** | `runtime-health-check.yml` | 런타임 상태 확인 |
| **Downstream Health Check** | `downstream-health-check.yml` | 다운스트림 건강도 확인 |
| **Repo Health** | `repo-health.yml` | 리포지토리 건강도 |

#### 🔧 라벨링 및 접대

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| **Labeler** | `_labeler.yml` | 파일 경로 기반 자동 라벨링 |
| **Stale** | `_stale.yml` | 스탤 이슈/PR 처리 |
| **Welcome** | `_welcome.yml` | 신규 기여자 환영 |

#### 📦 리포지토리 리뷰

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| **Repo Review Batch** | `repo-review-batch.yml` | 리포지토리 일괄 리뷰 |
| **Reusable PR Checks** | `reusable-pr-checks.yml` | 재사용 가능한 PR 체크 |
| **Reusable Issue Management** | `reusable-issue-management.yml` | 재사용 가능한 이슈 관리 |

---

### Go 자동화 도구 / Go Automation Tools

| 도구 / Tool | 경로 / Path | 설명 / Description |
|-------------|-------------|---------------------|
| **branch-protection** | `scripts/cmd/branch-protection/` | 브랜치 보호 규칙 관리 (apply, list, check) |
| **deploy-to-repos** | `scripts/cmd/deploy-to-repos/` | `pr-review.yml`을 `jclee941/*` 리포지토리에 일괄 배포 |
