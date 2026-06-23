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

    subgraph 홈랩["🏠 홈랩 (<homelab-host>)"]
        WEB["github-bot-app<br/>(localhost:3001)"]
        PROXY["CLIProxyAPI<br/>(localhost:8317)"]
        LLM["Claude / Codex / Gemini<br/>CLI"]
        FB["Filebeat<br/>(로그 수집)"]
        ES["Elasticsearch<br/>(<homelab-elk>:9200)"]
    end

    GH -->|"Webhook<br/>pull_request.opened"| CF
    CF -->|"TLS Reverse Proxy"| WEB
    WEB -->|"litellm.completion<br/>model=minimax-m3"| PROXY
    WEB -->|"Docker JSON logs"| FB
    FB -->|"로그 전송"| ES
    PROXY -->|"OpenAI-compatible API"| LLM
    LLM -->|"생성된 리뷰"| PROXY
    PROXY -->|"JSON 응답"| WEB
    WEB -->|"POST /issues/:id/comments"| GH

    style GH fill:#6ba06a,stroke:#333,color:#fff
    style CF fill:#f48120,stroke:#333,color:#fff
    style WEB fill:#4a90d9,stroke:#333,color:#fff
    style PROXY fill:#9b59b6,stroke:#333,color:#fff
    style LLM fill:#e74c3c,stroke:#333,color:#fff
    style FB fill:#f39c12,stroke:#333,color:#fff
    style ES fill:#27ae60,stroke:#333,color:#fff
```

### 구성 요소 설명

| 구성 요소 | 역할 | 위치 |
|-----------|------|------|
| **GitHub** | PR 이벤트 발생, 리뷰 코멘트 표시 | Public Cloud |
| **Cloudflare Tunnel** | 홈랩 남부 네트워크에 퍼블릭 HTTPS 엔드포인트 제공 | Cloudflare Edge |
| **github-bot-app** | Webhook 수신, 리뷰 엔진 실행, GitHub API 호출 | <homelab-host> (:3001) |
| **CLIProxyAPI** | Claude/Codex/Gemini CLI를 OpenAI API로 래핑 | <homelab-host> (:8317) |
| **AI CLI** | 실제 LLM 추론 수행 (Claude Code / Codex CLI / Gemini CLI) | <homelab-host> (로컬 실행) |
| **Filebeat** | Docker 컨테이너 로그 수집 및 전송 | <homelab-host> (로컬) |
| **Elasticsearch** | 중앙 로그 저장 및 검색 | <homelab-elk> (:9200) |

---

## 2. PR 라이프사이클 (PR Lifecycle)

```mermaid
flowchart TD
    START(("PR 열림")) --> CHECKS["jclee-bot / pr-metadata<br/>(PR 메타데이터)"]
    
    CHECKS --> TITLE{제목 OK?}
    TITLE -->|No| FAIL1["❌ jclee-bot / pr-metadata<br/>Required"]
    TITLE -->|Yes| BRANCH{브랜치명 OK?}
    
    BRANCH -->|No| FAIL2["❌ jclee-bot / pr-metadata<br/>Required"]
    BRANCH -->|Yes| REVIEW["10_pr-review.yml<br/>(AI 리뷰)"]
    
    REVIEW --> GITLEAKS["jclee-bot / secret-scan<br/>(Secret 스캔)"]
    GITLEAKS --> SECRET{Secret 발견?}
    SECRET -->|Yes| FAIL3["❌ jclee-bot / secret-scan<br/>Required"]
    SECRET -->|No| OPTIONAL["선택적 검증"]
    
    OPTIONAL --> CODEQL["GitHub-native CodeQL<br/>(SAST)"]
    OPTIONAL --> ACTIONLINT["jclee-bot / actionlint<br/>(워크플로우 문법)"]
    OPTIONAL --> DOCS["jclee-bot / docs-policy<br/>(문서 품질)"]
    
    OPTIONAL --> SECURITY{"security-review<br/>라벨?"}
    SECURITY -->|Yes| DEEP["11_security-pr-review.yml<br/>(심층 보안 감사)"]
    SECURITY -->|No| MERGE_CHECK
    
    DEEP --> MERGE_CHECK{머지 조건 충족?}
    MERGE_CHECK -->|No| WAIT["⏳ 대기 중"]
    MERGE_CHECK -->|Yes| MERGED["✅ 머지 완료"]
    
    MERGED --> CLEANUP["15_merged-pr-cleanup.yml<br/>(이슈 종료 + 브랜치 삭제)"]
    MERGED --> RELEASE["23_release-drafter.yml<br/>(릴리즈 노트 초안)"]
    
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
| PR 메타데이터 | `jclee-bot / pr-metadata` | ❌ 머지 차단 |
| Secret 노출 | `jclee-bot / secret-scan` | ❌ 머지 차단 |
| 워크플로우 문법 | `jclee-bot / actionlint` | ❌ 머지 차단 |

### 권고 검증 (Advisory Checks)

| 검증 항목 | 워크플로우 | 실패 시 |
|-----------|-----------|---------|
| Python SAST | `CodeQL` | ⚠️ Security 탭 |
| 문서 품질 | `jclee-bot / docs-policy` | ⚠️ Check Run |
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
    participant LLM as minimax-m3

    Dev->>GH: PR 생성
    GH->>Bot: Webhook: pull_request.opened
    
    activate Bot
    Bot->>Bot: Webhook 서명 검증
    Bot->>Bot: Payload 파싱 (Dynaconf)
    
    Bot->>GH: GET /repos/:owner/:repo/pulls/:pr
    GH-->>Bot: PR diff + 파일 목록
    
    Bot->>Bot: 명령어 선택 로직 실행
    Note over Bot: <50 LOC → review<br/>>1000 LOC → describe+review<br/>feat/fix → describe+review+improve+agentic
    
    Bot->>Proxy: POST /v1/chat/completions<br/>model=minimax-m3
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
        B -->|Yes| C["jclee-bot App<br/>브랜치 생성"]
        B -->|No| D["수동 할당 대기"]
    end
    
    subgraph 할당["👤 할당"]
        E["Assignee 지정"] --> C
    end
    
    subgraph 정리["🧹 정리"]
        C --> H["개발 진행"]
        H --> I["PR 생성"]
        I --> J["PR 머지"]
        J --> K["15_merged-pr-cleanup.yml<br/>이슈 자동 종료"]
    end
    
    subgraph 스테일["⏰ 스테일 라벨 정리"]
        L["jclee-bot App<br/>issues / issue_comment webhook"] --> M{"활동 발생?"}
        M -->|Issue edited/reopened| Q["stale 라벨 제거"]
        M -->|Comment created| Q
        L --> N["Issue opened<br/>키워드 라벨 부착"]
    end
    
    style A fill:#6ba06a,stroke:#333,color:#fff
    style K fill:#4a90d9,stroke:#333,color:#fff
    style Q fill:#d9b430,stroke:#333,color:#000
```

---

## 5. App 기반 레포 자동화 흐름 (Repository Automation)

```mermaid
flowchart TD
    START(("운영 트리거<br/>(webhook / API / schedule)")) --> APP["jclee-bot App<br/>(github-bot-app)"]
    
    APP --> INSTALL["GitHub App installation<br/>repo + permission 조회"]
    INSTALL --> TARGETS["config/repos.yaml<br/>관리 대상 필터"]
    
    TARGETS --> README["README 자동화<br/>bot/auto-readme-update"]
    TARGETS --> CHECKS["Checks API<br/>jclee-bot / pr-metadata<br/>jclee-bot / secret-scan<br/>jclee-bot / actionlint"]
    TARGETS --> ISSUES["Issue automation<br/>label / stale cleanup"]
    
    README --> BRANCH["App token clone + render + push"]
    BRANCH --> PR{"PR 존재?"}
    
    PR -->|Yes| UPDATE["기존 PR 업데이트"]
    PR -->|No| CREATE["신규 PR 생성"]
    
    UPDATE --> WAIT["required checks<br/>대기"]
    CREATE --> WAIT
    WAIT --> PASS{"전체 통과?"}
    
    PASS -->|Yes| AUTO_MERGE["Auto-merge<br/>(squash)"]
    PASS -->|No| MANUAL["수동 개입 필요"]
    
    AUTO_MERGE --> END(("배포 완료"))
    MANUAL --> END
    
    style START fill:#6ba06a,stroke:#333,color:#fff
    style END fill:#4a90d9,stroke:#333,color:#fff
    style AUTO_MERGE fill:#6ba06a,stroke:#333,color:#fff
    style MANUAL fill:#d9b430,stroke:#333,color:#000
```

### App 관리 리포지토리

`config/repos.yaml`이 단일 인벤토리입니다. `.github`는 소스 리포로 자체 운영되고,
리뷰 엔진은 인트리에 흡수된 first-party 패키지라 App 자동화 롤아웃에서 제외됩니다. 나머지 공개/비공개
대상 리포는 per-repo workflow 배포가 아니라 `jclee-bot` App 토큰과 Checks API 경로로
운영됩니다.

---

## 6. 리뷰 명령어 선택 로직 (Review Command Selection)

```mermaid
flowchart TD
    START(("PR 이벤트")) --> AUTHOR{"작성자?"}
    
    AUTHOR -->|bot| BOT["review only"]
    AUTHOR -->|human| TYPE{"변경 유형?"}
    
    TYPE -->|docs only| DOCS["describe only"]
    TYPE -->|feat/fix/refactor| FULL1["describe + review"]
    TYPE -->|other| SIZE{"변경량?"}
    
    SIZE -->|< 50 LOC| SMALL["review only"]
    SIZE -->|> 1000 LOC| LARGE["describe + review"]
    SIZE -->|50~1000 LOC| DEFAULT["describe + review"]
    
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
    
    PR --> PR_CHECK["jclee-bot / pr-metadata"]
    PR --> PR_REVIEW["10_pr-review.yml"]
    PR --> GITLEAKS["jclee-bot / secret-scan"]
    PR --> CODEQL["GitHub-native CodeQL<br/>(조건부)"]
    PR --> ACTIONLINT["jclee-bot / actionlint<br/>(조건부)"]
    PR --> DOCS["jclee-bot / docs-policy"]
    PR --> DEPENDABOT["jclee-bot App<br/>Dependabot merge policy"]
    
    PUSH --> APP_BUILD["36_build-and-push-app.yml<br/>(App image)"]
    PUSH --> RELEASE_D["23_release-drafter.yml"]
    PUSH --> RELEASE_P["25_release-publish.yml"]
    PUSH --> GITLEAKS
    
    PUSH --> HARDSCAN["35_auto-hardcode-scan.yml<br/>(workflow_dispatch / weekly manual)"]
    PR --> CODEQL_S["GitHub-native CodeQL"]
    
    ISSUE --> ISSUE_BRANCH["jclee-bot App<br/>issue branch"]
    ISSUE --> ISSUE_MGMT["jclee-bot App<br/>issue auto-label / stale remove / stale sweep"]
    
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
    GUARD -->|Yes| SECURE["11_security-pr-review.yml<br/>심층 보안 감사"]
    
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
    MERGED["PR 머지"] --> DRAFTER["23_release-drafter.yml<br/>릴리즈 노트 초안"]
    
    DRAFTER --> TAG["25_release-publish.yml<br/>태그 생성"]
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
    subgraph Origin["📚 Original Source (qodo-ai/pr-agent)"]
        U1["jclee_bot/review_engine/settings/<br/>configuration.toml"]
    end

    subgraph Project_Config["⚙️ Project Configuration"]
        F1[".pr_agent.toml<br/>(최우선)"]
        F2["jclee_bot/review_engine/settings/<br/>configuration.toml<br/>(model/fallback 오버라이드)"]
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

### 우선순위 (높음 → 낮음)

1. **환경 변수** (`CONFIG.MODEL`, `OPENAI.KEY`) — 런타임 오버라이드
2. **`.pr_agent.toml`** — Per-repo 설정 (cli_proxy, 한국어 응답, 리뷰 템플릿)
3. **`jclee_bot/review_engine/settings/configuration.toml`** — 엔진 기본값 (model/fallback 변경)
4. **리뷰 엔진 내부 DEFAULTS** — 하드코딩된 폴백

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
