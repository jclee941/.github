# jclee-bot

>`jclee941/*` 저장소 전용 비공개 AI PR 리뷰 봇. [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)의 하드 포크이며, GitHub App 서버와 LLM 백엔드는 jclee941 homelab에서 구동되고 PR 리뷰 워크플로우는 GitHub-hosted 러너에서 공개 인터넷을 통해 homelab에 접근합니다.

>Private AI-powered PR reviewer for `jclee941/*` repos. Hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent); the GitHub App server and LLM backend run inside the jclee941 homelab, while PR-review workflows run on GitHub-hosted runners reaching the homelab over the public internet.

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

`jclee-bot`은 **Qodo AI의 PR-Agent**를 하드 포크한 것으로, 다음 구성으로 homelab 환경에서 운영됩니다:

| 항목 / Item | 내용 / Value |
|-------------|--------------|
| **LLM 백엔드** | `CLIProxyAPI` @ `192.168.50.114:8317` (LXC 100) |
| **Webhook 엔드포인트** | `https://bot.jclee.me` (Cloudflare Tunnel) |
| **GitHub App** | `jclee-bot` (ID: 3540327) |
| **기본 모델 / GitHub App** | `kimi-k2.6` (fallback: `minimax-m2.7`, `gpt-5.5`) via CLIProxyAPI |
| **적용 범위** | `jclee941/*` 관리 리포지토리 (public + private, 16개) |
| **런너** | GitHub-hosted `ubuntu-latest` + self-hosted (일부) |

> **Note / 참고**: Homelab에 공개 인터넷을 통해 접근하며, CLIProxyAPI는 Claude Code CLI / Codex CLI / Gemini CLI를 OpenAI 호환 API로 래핑합니다. GitHub App(웹훅) 기본 모델은 `kimi-k2.6`이며, PR 리뷰 워크플로우(`10_pr-review.yml`)는 `[minimax-m2.7, gpt-5.5]` 매트릭스로 실행됩니다 (공통 fallback: `minimax-m2.7`, `gpt-5.5`).

> **Upstream / 업스트림**: 이 README는 포크 전용입니다. 원본 qodo-ai/pr-agent README는 [`docs/pr-agent-upstream-README.md`](docs/pr-agent-upstream-README.md)에 보존되어 있으며, 모든 업스트림 기능(`/review`, `/improve`, `/describe`, `/ask`, `/update_changelog`, 멀티모델 fallback)은 그대로 유지됩니다.

---

## 주요 기능 / Features

- ### AI PR 리뷰 / AI-Powered PR Review

  - `/review` — 자동 코드 리뷰 (한국어 출력, 점수·테스트·보안·TODO·티켓 준수 검사)
  - `/improve` — 코드 개선안 생성
  - `/describe` — PR 설명 생성
  - `/ask`, `/ask_line` — 코드·라인 관련 질문 답변
  - `/hardcode` — 하드코딩된 시크릿/AWS·GitHub 토큰/JWT/접속문자열 탐지 (포크 전용)
  - `/readme` — README.md 자동 생성 (포크 전용)
  - `/add_docs`, `/generate_labels`, `/similar_issue`, `/update_changelog`, `/config`, `/help`
  - **자동 이슈 생성** — critical/security/bug 리뷰 발견 시 GitHub 이슈 자동 등록 (포크 전용, 중복 방지)

- ### 자동화 워크플로우 / Automated Workflows

  - PR 정규화, 사이즈 분류, 스탤 플래그
  - 자동 머지, 보안 리뷰, 의존성 검토
  - 이슈 라이프사이클 관리, 템플릿 동기화

- ### 보안 강화 / Security Hardening

  - CodeQL 정적 분석
  - Gitleaks 시크릿 스캐닝
  - Dependabot 자동 병합
  - 보안 리뷰 워크플로우 (심층 분석)

- ### Go 기반 운영 도구 / Go Operational Tools

  - 브랜치 보호 관리, 리포지토리 일괄 배포
  - 드리프트 감지, 룰셋 관리, 시크릿 동기화
  - 리포 메타데이터 동기화, 명명 규칙 검증
  - 룰셋 관리
  - 시크릿 동기화

---

## 아키텍처 / Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub / Cloudflare                         │
│           https://bot.jclee.me  /api/v1/github_webhooks         │
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
│  │  │ kimi-k2.6   │  │ minimax-m2.7│  │    gpt-5.5     │     │   │
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

워크플로우는 `NN_` 숫자 접두사로 실행 순서를 나타냅니다 (`.github/workflows/`). `81_`~`89_`와 `41_reusable-ci.yml`은 `.github` 소스 전용이며 다운스트림 배포 대상이 아닙니다. 실제 배포 대상은 `scripts/cmd/deploy-to-repos`의 `downstreamWorkflowAllowlist`로 관리되며, 여기에는 `42_`~`45_` reusable 워크플로우도 포함됩니다.

#### 🎯 PR 자동화 / PR Automation

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| Branch to PR | `01_branch-to-pr.yml` | 브랜치 push → PR 자동 생성 |
| Issue to Branch | `02_issue-to-branch.yml` | 이슈 → 작업 브랜치 생성 |
| PR Checks | `03_pr-checks.yml` | PR 필수 검증 (제목/브랜치/사이즈/설명) |
| Semantic PR | `09_semantic-pr.yml` | Conventional Commits 제목 강제 |
| PR Review | `10_pr-review.yml` | AI PR 리뷰 (ubuntu-latest + CLIProxyAPI 매트릭스) |
| Dependabot Auto Merge | `12_dependabot-auto-merge.yml` | Dependabot patch/minor 자동 병합 |
| PR Auto Merge | `13_pr-auto-merge.yml` | PR auto-merge 활성화 |
| Bot Auto Fix | `14_bot-auto-fix.yml` | 명명 규칙 위반 자동 수정 |
| Merged PR Cleanup | `15_merged-pr-cleanup.yml` | 병합 후 정리 |
| PR Stale Bot | `17_pr-stale-bot.yml` | 스탤 PR 플래그 |

#### 🔒 보안 / Security

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| Actionlint | `04_actionlint.yml` | GitHub Actions YAML 시맨틱 린터 |
| Gitleaks | `05_gitleaks.yml` | 매 PR/push 시크릿 패턴 스캔 |
| CodeQL | `06_codeql.yml` | Python SAST (security-extended + quality) |
| Dependency Review | `07_dependency-review.yml` | 의존성 취약점 검토 |
| Scorecard | `08_scorecard.yml` | OpenSSF Scorecard |
| Security PR Review | `security/11_pr-review.yml` | 심층 보안 리뷰 (한국어, 라벨 트리거) |
| Auto Hardcode Scan | `35_auto-hardcode-scan.yml` | 주간 하드코드 패턴 스캔 |
| PR Review Security | `86_pr-review-security.yml` | 보안 리뷰 (대체 경로) |

#### 📋 이슈 관리 / Issue Management

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| Stale Repo Identifier | `16_stale-repo-identifier.yml` | 비활성 리포지토리 식별 |
| Issue Management | `18_issue-management.yml` | 이슈 수명주기 관리 |
| Issue Backfill | `19_issue-backfill.yml` | 이슈 백필 |
| CI Failure Issues | `37_ci-failure-issues.yml` | CI 실패 시 이슈 생성 |
| Org Health Report | `32_org-health-report.yml` | 조직 건강도 보고 (주간) |
| Issue Label | `82_issue-label.yml` | 자동 라벨링 |
| Issue Lifecycle | `83_issue-lifecycle.yml` | 이슈 수명주기 (소스 전용) |

#### 📚 문서·릴리스 / Docs & Release

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| Readme Generator | `20_readme-gen.yml` | README.md 자동 생성 (다운스트림 배포, `.github` 자신은 제외) |
| Docs Sync | `21_docs-sync.yml` | markdown 린트 + 링크 체크 |
| Template Sync | `22_template-sync.yml` | README/CONTRIBUTING/LICENSE 템플릿 동기화 (주간) |
| Release Drafter | `23_release-drafter.yml` | 릴리스 초안 생성 |
| Release Notes | `24_release-notes.yml` | 릴리스 노트 생성 |
| Release Publish | `25_release-publish.yml` | 릴리스 게시 |

#### 🚀 배포·운영 / Deploy & Ops

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| ELK Health Check | `26_elk-health-check.yml` | Elasticsearch + 인덱스 헬스 (일간) |
| ELK Setup | `27_elk-setup.yml` | ILM + 인덱스 템플릿 배포 (주간) |
| Bot Health Monitor | `28_bot-health-monitor.yml` | CLIProxyAPI + 봇 활동 점검 (일간) |
| Downstream Health Check | `29_downstream-health-check.yml` | 다운스트림 CI 헬스 (일간) |
| Runtime Health Check | `30_runtime-health-check.yml` | 런타임 상태 확인 |
| Repo Health | `31_repo-health.yml` | README/CONTRIBUTING/LICENSE 존재 검사 (주간) |
| Drift Detector | `33_drift-detector.yml` | 워크플로 파일 드리프트 감지 (주간) |
| Auto Deploy | `34_auto-deploy.yml` | 워크플로 다운스트림 배포 |
| Build and Push | `36_build-and-push-app.yml` | Docker 이미지 빌드 및 푸시 |
| CI Auto Heal | `60_ci-auto-heal.yml` | CI 실패 자동 복구 (일간) |

#### 🧪 CI 게이트·테스트 / CI Gate & Tests

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| E2E | `38_e2e.yml` | 엔드투엔드 테스트 |
| E2E Live | `39_e2e-live.yml` | 라이브 환경 테스트 (dispatch) |
| Repo Review Batch | `40_repo-review-batch.yml` | 리포지토리 일괄 AI 리뷰 (dispatch) |
| Sanity | `90_sanity.yml` | 포크 CI 게이트 (import/TOML/명명 검증) |

#### ♻️ 재사용 템플릿·소스 전용 / Reusable & Source-only (`41_`-`45_`, `81_`-`89_`)

| 워크플로우 / Workflow | 파일 / File | 설명 / Description |
|----------------------|-------------|---------------------|
| Reusable CI | `41_reusable-ci.yml` | 공통 CI 템플릿 (소스 전용) |
| Reusable Docs Sync | `42_reusable-docs-sync.yml` | 문서 동기화 템플릿 (다운스트림 배포) |
| Reusable Issue Mgmt | `43_reusable-issue-management.yml` | 이슈 관리 템플릿 (다운스트림 배포) |
| Reusable PR Checks | `44_reusable-pr-checks.yml` | PR 체크 템플릿 (다운스트림 배포) |
| Reusable Gitleaks | `45_reusable-gitleaks.yml` | Gitleaks 템플릿 (다운스트림 배포) |
| Auto Merge | `81_auto-merge.yml` | auto-merge (소스 전용) |
| Labeler | `84_labeler.yml` | 경로 기반 라벨링 (소스 전용) |
| PR Normalize | `85_pr-normalize.yml` | PR 제목 정규화 (소스 전용) |
| PR Size | `87_pr-size.yml` | 변경량 분류 (소스 전용) |
| Stale | `88_stale.yml` | 스탤 이슈/PR 처리 (소스 전용) |
| Welcome | `89_welcome.yml` | 신규 기여자 환영 (소스 전용) |

---

### Go 자동화 도구 / Go Automation Tools

| 도구 / Tool | 경로 / Path | 설명 / Description | 테스트 |
|-------------|-------------|---------------------|:----:|
| **branch-protection** | `scripts/cmd/branch-protection/` | 브랜치 보호 + auto-merge 규칙 적용 | ✅ |
| **deploy-to-repos** | `scripts/cmd/deploy-to-repos/` | 워크플로·dependabot·CODEOWNERS를 다운스트림 리포에 배포 | ✅ |
| **sync-secrets** | `scripts/cmd/sync-secrets/` | `CLIPROXY_API_KEY`·`GH_PAT` 시크릿 동기화 | — |
| **repo-review** | `scripts/cmd/repo-review/` | 리포 일괄 AI 리뷰 + 이슈 생성 | — |
| **rulesets-manager** | `scripts/cmd/rulesets-manager/` | GitHub Rulesets 관리 (apply/list/delete) | ✅ |
| **drift-detector** | `scripts/cmd/drift-detector/` | 다운스트림 워크플로 파일 드리프트 감지 | ✅ |
| **repo-metadata** | `scripts/cmd/repo-metadata/` | 리포 description/topics/homepage 동기화 | ✅ |
| **validate-naming** | `scripts/cmd/validate-naming/` | 교차 파일 불변조건·명명 규칙 검증 (`--fix`) | ✅ |

> 실행: `(cd scripts && go run ./cmd/<name>)`. 루트 레벨 레거시 바이너리는 사용하지 마세요. 테스트: `(cd scripts && go test ./...)`.

---

## 빠른 시작 / Quick Start

봇은 GitHub App(LXC 114, Docker)으로 상시 구동되며 `jclee941/*` PR 이벤트를 자동 처리합니다. 별도 설치 없이 PR을 열면 `/describe` → `/review` → `/improve`가 자동 실행됩니다.

```bash
# 배포된 컨테이너 상태 확인 (LXC 114)
docker compose -f docker-compose.github_app.yml ps
curl -fsS http://localhost:3001/health   # CF 터널 ingress → localhost:3001
```

PR에서 수동으로 명령을 호출하려면 코멘트로 `/review`, `/improve`, `/hardcode`, `/readme` 등을 입력합니다.

---

## 로컬 개발 / Local Development

```bash
make install        # python3.12 venv 생성 + editable 설치
make test-unit      # 단위 테스트 (tests/unittest)
make test-e2e       # E2E (mocked, tests/e2e)
make test-live      # 라이브 E2E (GITHUB_TOKEN / CLIPROXY_API_KEY 필요)
make test           # 위 세 가지 전부
make lint           # ruff check

# Go 도구 테스트
(cd scripts && go test ./...)
```

---

## 명령어 참조 / Commands Reference

| 명령 / Command | 동작 / Action |
|------------------|------------------|
| `/review` | 한국어 코드 리뷰 (점수·테스트·보안·TODO·티켓 준수) + critical 발견 시 이슈 자동 생성 |
| `/improve` | 코드 개선안 제안 |
| `/describe` | PR 설명 자동 생성 |
| `/ask <질문>` | PR 전체 관련 질문 답변 |
| `/ask_line <질문>` | 특정 라인 관련 질문 답변 |
| `/hardcode` | 하드코딩된 시크릿/AWS·GitHub 토큰/JWT/접속문자열 탐지 |
| `/readme` | README.md 생성 제안 |
| `/add_docs` | 도큐멘트/주석 추가 |
| `/generate_labels` | PR 라벨 자동 생성 |
| `/similar_issue` | 유사 이슈 검색 |
| `/update_changelog` | CHANGELOG 업데이트 |
| `/config`, `/settings` | 현재 설정 표시 |
| `/help`, `/help_docs` | 사용 가능 명령 표시 |

> 자동 실행: PR open 시 `/describe` → `/review` → `/improve`, push 시 `/improve` (`.pr_agent.toml [github_app]`).

---

## 기여 가이드 / Contributing

[`CONTRIBUTING.md`](CONTRIBUTING.md)를 참고하세요. 모든 PR은 Conventional Commits 제목, 포크 CI 게이트(`90_sanity.yml`), 브랜치 보호(PR Title · Branch Name · Gitleaks)를 통과해야 합니다.

---

## 라이선스 / License

[AGPL-3.0](LICENSE). 이 프로젝트는 [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent)(AGPL-3.0)의 하드 포크이며, 업스트림 귀속 표시는 [`NOTICE`](NOTICE)에 있습니다.
