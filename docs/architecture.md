# jclee-bot 아키텍처 및 자동화 흐름

> 본 문서는 `jclee941/.github` 저장소의 전체 자동화 스택을 시각적으로 설명합니다.  
> 모든 다이어그램은 GitHub 네이티브 Mermaid 렌더러로 표시됩니다.

---

## 1. 시스템 개요 (System Architecture)

```mermaid
flowchart TB
    subgraph 외부_서비스["🌐 외부 서비스"]
        GH["GitHub.com<br/>(jclee941/* 리포)"]
        CF["Cloudflare Tunnel<br/>(bot.jclee.me)"]
    end

    subgraph 홈랩_LXC100["🏠 홈랩 LXC 100"]
        WEB["github-bot-app<br/>(localhost:3001)"]
        PROXY["CLIProxyAPI<br/>(localhost:8317)"]
        LLM["Claude / Codex / Gemini<br/>CLI"]
    end

    GH -->|"Webhook<br/>pull_request.opened"| CF
    CF -->|"TLS Reverse Proxy"| WEB
    WEB -->|"litellm.completion<br/>model=kimi-k2.6"| PROXY
    PROXY -->|"OpenAI-compatible API"| LLM
    LLM -->|"생성된 리뷰"| PROXY
    PROXY -->|"JSON 응답"| WEB
    WEB -->|"POST /issues/:id/comments"| GH

    style GH fill:#6ba06a,stroke:#333,color:#fff
    style CF fill:#f48120,stroke:#333,color:#fff
    style WEB fill:#4a90d9,stroke:#333,color:#fff
    style PROXY fill:#9b59b6,stroke:#333,color:#fff
    style LLM fill:#e74c3c,stroke:#333,color:#fff
```

### 구성 요소 설명

| 구성 요소 | 역할 | 위치 |
|-----------|------|------|
| **GitHub** | PR 이벤트 발생, 리뷰 코멘트 표시 | Public Cloud |
| **Cloudflare Tunnel** | 홈랩 남부 네트워크에 퍼블릭 HTTPS 엔드포인트 제공 | Cloudflare Edge |
| **github-bot-app** | Webhook 수신, pr-agent 실행, GitHub API 호출 | LXC 100 (192.168.50.102) |
| **CLIProxyAPI** | Claude/Codex/Gemini CLI를 OpenAI API로 래핑 | LXC 100 (localhost:8317) |
| **AI CLI** | 실제 LLM 추론 수행 (Claude Code / Codex CLI / Gemini CLI) | LXC 100 (로컬 실행) |

---

## 2. PR 라이프사이클 (PR Lifecycle)

```mermaid
flowchart TD
    START(("PR 열림")) --> CHECKS["pr-checks.yml<br/>(6가지 검증)"]
    
    CHECKS --> TITLE{제목 OK?}
    TITLE -->|No| FAIL1["❌ Check PR Title<br/>Required"]
    TITLE -->|Yes| BRANCH{브랜치명 OK?}
    
    BRANCH -->|No| FAIL2["❌ Check Branch Name<br/>Required"]
    BRANCH -->|Yes| REVIEW["pr-review.yml<br/>(AI 리뷰)"]
    
    REVIEW --> GITLEAKS["gitleaks.yml<br/>(Secret 스캔)"]
    GITLEAKS --> SECRET{Secret 발견?}
    SECRET -->|Yes| FAIL3["❌ Gitleaks / scan<br/>Required"]
    SECRET -->|No| OPTIONAL["선택적 검증"]
    
    OPTIONAL --> CODEQL["codeql.yml<br/>(Python SAST)"]
    OPTIONAL --> ACTIONLINT["actionlint.yml<br/>(워크플로우 문법)"]
    OPTIONAL --> DOCS["docs-sync.yml<br/>(문서 품질)"]
    
    OPTIONAL --> SECURITY{"security-review<br/>라벨?"}
    SECURITY -->|Yes| DEEP["security/pr-review.yml<br/>(심층 보안 감사)"]
    SECURITY -->|No| MERGE_CHECK
    
    DEEP --> MERGE_CHECK{머지 조건 충족?}
    MERGE_CHECK -->|No| WAIT["⏳ 대기 중"]
    MERGE_CHECK -->|Yes| MERGED["✅ 머지 완료"]
    
    MERGED --> CLEANUP["merged-pr-cleanup.yml<br/>(이슈 종료 + 브랜치 삭제)"]
    MERGED --> RELEASE["release-drafter.yml<br/>(릴리즈 노트 초안)"]
    
    FAIL1 --> END1(("종료"))
    FAIL2 --> END1
    FAIL3 --> END1
    WAIT --> END1
    CLEANUP --> END2(("완료"))
    RELEASE --> END2
    
    style START fill:#6ba06a,stroke:#333,color:#fff
    style END1 fill:#d9b430,stroke:#333,color:#000
    style END2 fill:#6ba06a,stroke:#333,color:#fff
    style FAIL1 fill:#e74c3c,stroke:#333,color:#fff
    style FAIL2 fill:#e74c3c,stroke:#333,color:#fff
    style FAIL3 fill:#e74c3c,stroke:#333,color:#fff
    style MERGED fill:#4a90d9,stroke:#333,color:#fff
```

### 필수 검증 (Required Checks)

| 검증 항목 | 워크플로우 | 실패 시 |
|-----------|-----------|---------|
| PR 제목 (Conventional Commits) | `pr-checks / Check PR Title` | ❌ 머지 차단 |
| 브랜치명 표준 prefix | `pr-checks / Check Branch Name` | ❌ 머지 차단 |
| Secret 노출 | `Gitleaks / scan` | ❌ 머지 차단 (Phase 3+) |

### 권고 검증 (Advisory Checks)

| 검증 항목 | 워크플로우 | 실패 시 |
|-----------|-----------|---------|
| PR 설명 길이 | `pr-checks / Check PR Description` | ⚠️ 코멘트만 |
| PR 크기 (500 LOC) | `pr-checks / Check PR Size` | ⚠️ 코멘트만 |
| 대용량 파일 | `pr-checks / Check Large Files` | ⚠️ 코멘트만 |
| 민감 파일 | `pr-checks / Check Sensitive Files` | ⚠️ 코멘트만 |
| Python SAST | `CodeQL` | ⚠️ Security 탭 |
| 워크플로우 문법 | `actionlint` | ⚠️ 코멘트만 |
| 문서 품질 | `docs-sync` | ⚠️ 코멘트만 |
| AI 코드 리뷰 | `pr-review` | 💬 리뷰 코멘트 |

---

## 3. 시퀀스 다이어그램: 리뷰 생성 과정

```mermaid
sequenceDiagram
    autonumber
    participant Dev as 개발자
    participant GH as GitHub
    participant Bot as jclee-bot
    participant Proxy as CLIProxyAPI
    participant LLM as kimi-k2.6

    Dev->>GH: PR 생성
    GH->>Bot: Webhook: pull_request.opened
    
    activate Bot
    Bot->>Bot: Webhook 서명 검증
    Bot->>Bot: Payload 파싱 (Dynaconf)
    
    Bot->>GH: GET /repos/:owner/:repo/pulls/:pr
    GH-->>Bot: PR diff + 파일 목록
    
    Bot->>Bot: 명령어 선택 로직 실행
    Note over Bot: <50 LOC → review<br/>>1000 LOC → describe+review<br/>feat/fix → describe+review+improve+agentic
    
    Bot->>Proxy: POST /v1/chat/completions<br/>model=kimi-k2.6
    activate Proxy
    Proxy->>LLM: Claude Code CLI 실행
    activate LLM
    LLM-->>Proxy: 생성된 한국어 리뷰
    deactivate LLM
    Proxy-->>Bot: JSON 응답
    deactivate Proxy
    
    Bot->>GH: POST /issues/:id/comments<br/>(마크다운 테이블 + 코드 블록)
    GH-->>Bot: 201 Created
    deactivate Bot
    
    GH->>Dev: 💬 PR에 AI 리뷰 표시
```

---

## 4. 이슈 라이프사이클 (Issue Lifecycle)

```mermaid
flowchart LR
    subgraph 생성["📝 이슈 생성"]
        A["Issue Opened"] --> B{"in-progress 라벨?"}
        B -->|Yes| C["issue-to-branch.yml<br/>브랜치 생성"]
        B -->|No| D["수동 할당 대기"]
    end
    
    subgraph 할당["👤 할당"]
        E["Assignee 지정"] --> C
    end
    
    subgraph 백필["🔄 백필"]
        F["issue-backfill.yml<br/>(매일 09:00 UTC)"] --> G["오래된 이슈에<br/>in-progress 라벨"]
        G --> C
    end
    
    subgraph 정리["🧹 정리"]
        C --> H["개발 진행"]
        H --> I["PR 생성"]
        I --> J["PR 머지"]
        J --> K["merged-pr-cleanup.yml<br/>이슈 자동 종료"]
    end
    
    subgraph 스테일["⏰ 스테일 관리"]
        L["issue-management.yml<br/>(매일 00:00 UTC)"] --> M{"30일 활동 없음?"}
        M -->|Yes| N["stale 라벨 부착"]
        N --> O{"7일 추가 경과?"}
        O -->|Yes| P["이슈 자동 종료"]
        O -->|No| Q["활동 발생 시<br/>stale 제거"]
    end
    
    style A fill:#6ba06a,stroke:#333,color:#fff
    style K fill:#4a90d9,stroke:#333,color:#fff
    style P fill:#d9b430,stroke:#333,color:#000
```

---

## 5. 다운스트림 배포 흐름 (Downstream Deploy)

```mermaid
flowchart TD
    START(("Push to master<br/>(.github)")) --> TRIGGER{"변경된 파일?"}
    
    TRIGGER -->|workflows/| DEPLOY["auto-deploy.yml"]
    TRIGGER -->|dependabot.yml| DEPLOY
    TRIGGER -->|CODEOWNERS| DEPLOY
    TRIGGER -->|PR template| DEPLOY
    TRIGGER -->|deploy script| DEPLOY
    
    DEPLOY --> DRY["Dry-run<br/>Preview"]
    DRY --> GO{"실행?"}
    
    GO -->|No| SKIP["스킵"]
    GO -->|Yes| CLONE["11개 리포 클론"]
    
    CLONE --> COPY["워크플로우 + 설정<br/>복사"]
    COPY --> COMMIT["chore: standardize<br/>automation workflows"]
    COMMIT --> PUSH["force-with-lease<br/>푸시"]
    PUSH --> PR{"PR 존재?"}
    
    PR -->|Yes| UPDATE["기존 PR 업데이트"]
    PR -->|No| CREATE["신규 PR 생성"]
    
    UPDATE --> WAIT["required checks<br/>대기"]
    CREATE --> WAIT
    WAIT --> PASS{"전체 통과?"}
    
    PASS -->|Yes| AUTO_MERGE["Auto-merge<br/>(squash)"]
    PASS -->|No| MANUAL["수동 개입 필요"]
    
    AUTO_MERGE --> END(("배포 완료"))
    MANUAL --> END
    SKIP --> END
    
    style START fill:#6ba06a,stroke:#333,color:#fff
    style END fill:#4a90d9,stroke:#333,color:#fff
    style AUTO_MERGE fill:#6ba06a,stroke:#333,color:#fff
    style MANUAL fill:#d9b430,stroke:#333,color:#000
```

### 배포 대상 리포지토리 (11개)

| 리포지토리 | 상태 |
|-----------|------|
| `jclee941/resume` | ✅ 자동화 적용 |
| `jclee941/safetywallet` | ✅ 자동화 적용 |
| `jclee941/tmux` | ✅ 자동화 적용 |
| `jclee941/hycu_fsds` | ✅ 자동화 적용 |
| `jclee941/splunk` | ✅ 자동화 적용 |
| `jclee941/blacklist` | ✅ 자동화 적용 |
| `jclee941/opencode` | ✅ 자동화 적용 |
| `jclee941/terraform` | ✅ 자동화 적용 |
| `jclee941/account` | ✅ 자동화 적용 |
| `jclee941/idle-outpost` | ✅ 자동화 적용 |
| `jclee941/bug` | ✅ 자동화 적용 |

**제외 리포**: `pr-agent` (업스트림 포크, 자체 워크플로우 보유), `hycu`/`youtube`/`propose` (private, Dependabot만)

---

## 6. 리뷰 명령어 선택 로직 (Review Command Selection)

```mermaid
flowchart TD
    START(("PR 이벤트")) --> AUTHOR{"작성자?"}
    
    AUTHOR -->|bot| BOT["review only"]
    AUTHOR -->|human| TYPE{"변경 유형?"}
    
    TYPE -->|docs only| DOCS["describe only"]
    TYPE -->|feat/fix/refactor| FULL1["describe + review<br/>+ improve + agentic_review"]
    TYPE -->|other| SIZE{"변경량?"}
    
    SIZE -->|< 50 LOC| SMALL["review only"]
    SIZE -->|> 1000 LOC| LARGE["describe + review"]
    SIZE -->|50~1000 LOC| DEFAULT["describe + review<br/>+ improve + agentic_review"]
    
    BOT --> END(("실행"))
    DOCS --> END
    FULL1 --> END
    SMALL --> END
    LARGE --> END
    DEFAULT --> END
    
    style START fill:#6ba06a,stroke:#333,color:#fff
    style END fill:#4a90d9,stroke:#333,color:#fff
    style FULL1 fill:#9b59b6,stroke:#333,color:#fff
    style DEFAULT fill:#9b59b6,stroke:#333,color:#fff
```

---

## 7. 워크플로우 트리거 관계도 (Workflow Trigger Map)

```mermaid
flowchart LR
    subgraph PR_Events["📋 PR 이벤트"]
        PR["pull_request"]
    end
    
    subgraph Push_Events["🚀 Push 이벤트"]
        PUSH["push to master"]
    end
    
    subgraph Schedule_Events["⏰ 스케줄"]
        CRON["cron schedule"]
    end
    
    subgraph Issue_Events["🐛 이슈 이벤트"]
        ISSUE["issues"]
    end
    
    PR --> PR_CHECK["pr-checks.yml"]
    PR --> PR_REVIEW["pr-review.yml"]
    PR --> GITLEAKS["gitleaks.yml"]
    PR --> CODEQL["codeql.yml<br/>(조건부)"]
    PR --> ACTIONLINT["actionlint.yml<br/>(조건부)"]
    PR --> DOCS["docs-sync.yml"]
    PR --> DEPENDABOT["dependabot-auto-merge.yml<br/>(dependabot만)"]
    
    PUSH --> AUTO_DEPLOY["auto-deploy.yml<br/>(조건부)"]
    PUSH --> RELEASE_D["release-drafter.yml"]
    PUSH --> RELEASE_P["release-publish.yml"]
    PUSH --> GITLEAKS
    
    CRON --> HARDSCAN["auto-hardcode-scan.yml<br/>(월요일 00:00)"]
    CRON --> ISSUE_MGMT["issue-management.yml<br/>(매일 00:00)"]
    CRON --> ISSUE_BACK["issue-backfill.yml<br/>(매일 09:00)"]
    CRON --> CODEQL_S["codeql.yml<br/>(월요일 04:23)"]
    
    ISSUE --> ISSUE_BRANCH["issue-to-branch.yml"]
    
    PR_CHECK --> REUSABLE1["reusable-pr-checks.yml"]
    DOCS --> REUSABLE2["reusable-docs-sync.yml"]
    ISSUE_MGMT --> REUSABLE3["reusable-issue-management.yml"]
    
    style PR fill:#6ba06a,stroke:#333,color:#fff
    style PUSH fill:#4a90d9,stroke:#333,color:#fff
    style CRON fill:#d9b430,stroke:#333,color:#000
    style ISSUE fill:#e74c3c,stroke:#333,color:#fff
```

---

## 8. 보안 리뷰 흐름 (Security Review Flow)

```mermaid
flowchart TD
    START(("PR 생성")) --> NORMAL["일반 리뷰 실행"]
    
    NORMAL --> LABEL{"security-review<br/>라벨 추가?"}
    LABEL -->|No| END1(("완료"))
    LABEL -->|Yes| GUARD{"head.repo.full_name ==<br/>github.repository?"}
    
    GUARD -->|No| BLOCK["❌ 차단<br/>(fork PR 토큰 탈취 방지)"]
    GUARD -->|Yes| SECURE["security/pr-review.yml<br/>심층 보안 감사"]
    
    SECURE --> OWASP["OWASP Top 10<br/>체크리스트"]
    OWASP --> SECRET["Secret / Key<br/>관리 검증"]
    SECRET --> SAST["CodeQL SAST<br/>결과 연동"]
    
    SAST --> FINDING{"취약점 발견?"}
    FINDING -->|Yes| CRIT["[CRITICAL] 코멘트"]
    FINDING -->|No| SAFE["✅ 보안 통과"]
    
    CRIT --> END2(("완료"))
    SAFE --> END2
    BLOCK --> END3(("종료"))
    
    style START fill:#6ba06a,stroke:#333,color:#fff
    style SECURE fill:#e74c3c,stroke:#333,color:#fff
    style BLOCK fill:#d9b430,stroke:#333,color:#000
    style SAFE fill:#6ba06a,stroke:#333,color:#fff
    style CRIT fill:#e74c3c,stroke:#333,color:#fff
```

---

## 9. 릴리즈 자동화 흐름 (Release Automation)

```mermaid
flowchart LR
    MERGED["PR 머지"] --> DRAFTER["release-drafter.yml<br/>릴리즈 노트 초안"]
    
    DRAFTER --> TAG["release-publish.yml<br/>태그 생성"]
    TAG --> SEMVER{"Conventional Commits<br/>분석"}
    
    SEMVER -->|fix:| PATCH["vX.Y.Z+1<br/>Patch"]
    SEMVER -->|feat:| MINOR["vX.Y+1.0<br/>Minor"]
    SEMVER -->|BREAKING:| MAJOR["vX+1.0.0<br/>Major"]
    
    PATCH --> RELEASE["GitHub Release<br/>게시"]
    MINOR --> RELEASE
    MAJOR --> RELEASE
    
    RELEASE --> NOTIFY["CI Failure Issues<br/>(성공 알림)"]
    
    style MERGED fill:#4a90d9,stroke:#333,color:#fff
    style RELEASE fill:#6ba06a,stroke:#333,color:#fff
    style MAJOR fill:#e74c3c,stroke:#333,color:#fff
```

---

## 10. 설정 파일 계층 구조 (Configuration Hierarchy)

```mermaid
flowchart TB
    subgraph Upstream["🔄 Upstream (qodo-ai/pr-agent)"]
        U1["pr_agent/settings/<br/>configuration.toml"]
    end
    
    subgraph Fork_Config["⚙️ Fork 설정"]
        F1[".pr_agent.toml<br/>(최우선)"]
        F2["pr_agent/settings/<br/>configuration.toml<br/>(model만 오버라이드)"]
    end
    
    subgraph Runtime["🏃 런타임"]
        R1["환경 변수<br/>OPENAI.KEY<br/>CONFIG.MODEL"]
        R2["GitHub Secrets"]
    end
    
    U1 -->|"기본값 제공"| F2
    F2 -->|"병합"| F1
    F1 -->|"최종 설정"| RUN["pr-agent 실행"]
    R1 -->|"오버라이드"| RUN
    R2 -->|"주입"| R1
    
    style F1 fill:#6ba06a,stroke:#333,color:#fff
    style U1 fill:#95a5a6,stroke:#333,color:#fff
    style RUN fill:#4a90d9,stroke:#333,color:#fff
```

### 우선순위 (높음 → 낮음)

1. **환경 변수** (`CONFIG.MODEL`, `OPENAI.KEY`) — 런타임 오버라이드
2. **`.pr_agent.toml`** — Fork-level 설정 (cli_proxy, 한국어 응답, 리뷰 템플릿)
3. **`pr_agent/settings/configuration.toml`** — Upstream 기본값 (model만 변경)
4. **pr-agent 내부 DEFAULTS** — 하드코딩된 폴백

---

## 다이어그램 렌더링 테스트

> **참고**: 위 다이어그램들은 GitHub 네이티브 Mermaid 렌더러에서 자동 표시됩니다.  
> 로컬에서 미리 보려면 [Mermaid Live Editor](https://mermaid.live)에 코드를 붙여넣으세요.

### Mermaid 버전 호환성

| 다이어그램 유형 | GitHub 지원 | 사용 여부 |
|----------------|-------------|-----------|
| `flowchart` | ✅ 완전 지원 | ✅ 사용 중 |
| `sequenceDiagram` | ✅ 완전 지원 | ✅ 사용 중 |
| `gitGraph` | ✅ 완전 지원 | ❌ 미사용 |
| `architecture-beta` | ⚠️ v11.1+ 필요 | ❌ 사용 안 함 |
| Custom CSS / 테마 | ❌ 미지원 | ❌ 사용 안 함 |

### 다크 모드 대응

GitHub의 다크 모드에서도 다이어그램이 가독성 있게 표시되도록 `style` 지시어로 명시적 색상을 지정했습니다.  
GitHub의 iframe 기반 렌더러는 시스템 테마를 자동으로 따릅니다.
