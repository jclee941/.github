# GitHub 계정 고도화 — 브레인스토밍

> Status: **DRAFT for review**. 이 문서는 의사결정용 옵션 정리입니다. 실제 적용은 별도 PR로 진행합니다.
> Author: jclee-bot stabilization session
> Scope: `jclee941` 계정 + 16개 레포 전반의 프로필/디스커버리/커뮤니티 표준화

---

## 0. 현재 상태 진단 (measured)

| 항목 | 현재 | 목표 |
|------|------|------|
| Profile README (`jclee941/jclee941`) | ❌ 존재 안 함 | ✅ 자동 생성 README |
| User bio | ❌ 비어 있음 | ✅ 1줄 요약 |
| User blog / location / twitter | ❌ 모두 비어 있음 | ✅ resume.jclee.me + 위치 |
| `.github` community health | 71% | 100% |
| repo topics (검색 키워드) | 14/14 repo가 **0개** | 각 repo 3~6개 |
| repo description | 11/14 양호, 3개 부실 | 14/14 의미있는 설명 |
| repo homepage URL | 0/14 설정 | 배포된 repo는 URL 설정 |
| 2FA | ✅ 활성 | 유지 |
| Plan | Pro | 유지 |

**엔지니어 프로파일** (repo description에서 추출):

- **인프라/보안 엔지니어** 9년차 (한국)
- 홈랩 IaC: Proxmox + Terraform + 모니터링
- 보안: Splunk + FortiGate (FAZ→HEC 브리지, 15+ 알림), IP 위협 인텔리전스
- 자동화: n8n + FastAPI + FFmpeg (YouTube 파이프라인), Gmail 자동화, 버그바운티 recon
- 웹: Cloudflare Workers + Hono + Drizzle + D1 + Next.js (SafetyWallet PWA, 포트폴리오)
- ML: Formula Student Driverless 자율주행 (한양사이버대 경진대회 우수상 2026)
- **메타**: 이 `.github` 레포 자체 — 16개 repo를 관리하는 정교한 GitOps 자동화 (PR-Agent fork, 자체 CI/CD, ELK 모니터링)

---

## 1. Profile README (`jclee941/jclee941`)

### 배경

GitHub은 username과 동일한 이름의 public repo에 `README.md`가 있으면 프로필 페이지 상단에 렌더링합니다. 현재 이 repo가 없습니다.

### 옵션

| 옵션 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **A. 정적 README** (Recommended) | 손으로 작성한 고정 마크다운 | 통제 가능, 안정적 | 수동 갱신 |
| B. 동적 생성 | `20_readme-gen.yml` (CLIProxyAPI)로 자동 생성 | 무손 갱신 | LLM 의존, 비결정적 |
| C. Stats 위젯 중심 | github-readme-stats 등 서드파티 이미지 | 화려함 | 외부 서비스 의존, rate limit |
| **D. 하이브리드** (Best) | 정적 골격 + stats 위젯 + 자동 업데이트되는 "latest activity" 섹션 | 균형 | 약간 복잡 |

### 권장: 옵션 D — 하이브리드 구조

```markdown
# 안녕하세요, JAECHEOL LEE 입니다 👋

> Infrastructure & Security Engineer · 9 yrs · Homelab GitOps 운영자

- 🏗️  **Infra-as-Code**: Proxmox + Terraform 홈랩, 16개 repo를 단일 `.github`에서 GitOps로 관리
- 🛡️  **Security**: Splunk + FortiGate SIEM 파이프라인, IP threat intel, bug bounty 자동화
- 🤖  **Automation**: PR-Agent fork 기반 자체 CI/CD 봇, n8n/FastAPI 워크플로
- 🌐  **Web**: Cloudflare Workers + Hono + D1 (SafetyWallet PWA, portfolio)
- 🏎️  **ML**: Formula Student Driverless 자율주행 (경진대회 우수상 2026)

### 🔧 Tech Stack
[badges: Python, Go, TypeScript, Terraform, Docker, Cloudflare, Splunk ...]

### 📊 GitHub Stats
[github-readme-stats card] [top-langs card] [streak]

### 📌 Featured
- [terraform](https://github.com/jclee941/terraform) — Homelab IaC monorepo
- [splunk](https://github.com/jclee941/splunk) — FortiGate SIEM app
- [safetywallet](https://github.com/jclee941/safetywallet) — Field-worker safety PWA
- [.github](https://github.com/jclee941/.github) — 16-repo GitOps automation

<!-- AUTO-ACTIVITY:START (workflow가 매일 갱신) -->
<!-- AUTO-ACTIVITY:END -->
```

### 자동화 연계

- `.github` 레포에 새 workflow `profile-readme-sync.yml` 추가 → cron으로 `jclee941/jclee941`의 activity 섹션 갱신
- 또는 `20_readme-gen.yml`을 profile repo에도 적용 (단, 정적 골격은 보존)

### 결정 필요 사항

- [ ] 한국어 / 영어 / 이중 언어?  → **이중 언어 권장** (헤더 한글, 기술 섹션 영어)
- [ ] 이메일/연락처 공개 범위?
- [ ] Stats 위젯 테마 (dark/light/auto)?

---

## 2. User Profile Fields

API로 설정 가능: `gh api -X PATCH user -f bio=... -f blog=... -f location=... -f twitter_username=...`

| 필드 | 추천 값 | 근거 |
|------|---------|------|
| `bio` | `Infrastructure & Security Engineer · Homelab GitOps · 자동화 덕후` (최대 160자) | repo 프로파일 종합 |
| `blog` | `https://resume.jclee.me` | resume repo가 Cloudflare Worker portfolio 운영 |
| `location` | `Seoul, South Korea` (확인 필요) | repo가 한국어 + 한양사이버대 |
| `company` | (선택) | freelance면 비워두거나 `@jclee941` |
| `twitter_username` | (있으면) | 없으면 생략 |
| `hireable` | `true` (이미 설정됨) | 유지 |

### 결정 필요 사항

- [ ] location 정확한 값 (Seoul? 다른 도시?)
- [ ] blog URL을 resume.jclee.me로 확정?
- [ ] bio 한글 vs 영어

---

## 3. Community Health 71% → 100%

`.github` 레포의 community profile에서 누락된 것:

| 파일 | 현재 | 조치 |
|------|------|------|
| `CONTRIBUTING.md` | ✅ 있음 | 유지 |
| `PULL_REQUEST_TEMPLATE.md` | ✅ 있음 | 유지 |
| `LICENSE` (AGPL-3.0) | ✅ 있음 | 유지 |
| `README.md` | ✅ 있음 | 유지 |
| `ISSUE_TEMPLATE/` | ✅ 있음 (3종 + config) | 유지 |
| **`SECURITY.md`** | ❌ 누락 | ➕ 추가 (취약점 신고 절차) |
| **`CODE_OF_CONDUCT.md`** | ❌ 누락 | ➕ 추가 (Contributor Covenant 2.1) |
| **`FUNDING.yml`** | ❌ 누락 | ➕ 선택 (GitHub Sponsors 등) |

> 참고: community profile API는 org-level `.github`의 일부 파일을 다르게 인식할 수 있음.
> ISSUE_TEMPLATE는 실제로 존재하나 71% 측정에 안 잡혔을 수 있어 **루트 레벨 배치** 검토 필요.

### 권장 파일 내용 골격

**SECURITY.md**:

```markdown
# Security Policy
## Supported Versions
모든 repo는 최신 main/master만 지원합니다.
## Reporting a Vulnerability
보안 취약점은 Issue가 아닌 [security advisory](../../security/advisories/new) 또는
이메일로 비공개 신고해 주세요. 48시간 내 1차 응답.
```

**CODE_OF_CONDUCT.md**: Contributor Covenant 2.1 표준 템플릿 (한글 번역 병기 가능)

**FUNDING.yml**: GitHub Sponsors 미사용 시 생략 가능. 사용 시:

```yaml
github: [jclee941]
```

### 결정 필요 사항

- [ ] FUNDING.yml 필요? (Sponsors 계정 있는지)
- [ ] CODE_OF_CONDUCT 연락 이메일
- [ ] SECURITY.md 신고 채널 (advisory vs 이메일)

---

## 4. Org-Level Community Files 전파

`.github` 레포는 이미 `deploy-to-repos`로 16개 레포에 workflow + dependabot + ISSUE_TEMPLATE를 동기화합니다. 같은 메커니즘으로:

| 항목 | 전파 방식 |
|------|-----------|
| 공통 README 골격 | `22_template-sync.yml` (이미 존재) — README/CONTRIBUTING/LICENSE 템플릿 |
| SECURITY.md / CODE_OF_CONDUCT.md | `extraFiles`에 추가 → 모든 repo로 전파 |
| Profile README | **별개** — `jclee941/jclee941`은 deploy 타겟 아님, 직접 관리 |

> GitHub 동작: org-level `.github` 레포의 community health 파일(SECURITY 등)은
> **자체 community health file이 없는 repo에만** 상속됩니다.
> 따라서 `.github`에 SECURITY.md를 두면 16개 repo 전부가 자동 상속받습니다(중복 배포 불필요).

### 권장

- SECURITY.md, CODE_OF_CONDUCT.md를 **`.github` 레포 루트에만** 추가 → 16개 전 repo 자동 상속
- `deploy-to-repos`의 `extraFiles`에는 추가하지 **않음** (org 상속이 더 깔끔)

### 결정 필요 사항

- [ ] org 상속에 의존 vs 각 repo에 명시적 배포 (상속 권장)

---

## 5. Repository 표준화 (description + topics + homepage)

### 5a. Topics (검색 키워드) — 14/14 repo 모두 0개

| Repo | 추천 topics |
|------|-------------|
| account | `gmail-api`, `automation`, `javascript`, `email` |
| blacklist | `threat-intelligence`, `ip-reputation`, `security`, `osint` |
| bug | `bug-bounty`, `recon`, `security`, `automation`, `pentesting` |
| hycu_fsds | `autonomous-driving`, `formula-student`, `simulation`, `python`, `robotics` |
| idle-outpost | (description 먼저 필요) |
| opencode | `golang`, `cli`, `developer-tools` (description 재작성 필요) |
| resume | `portfolio`, `cloudflare-workers`, `resume`, `personal-website` |
| safetywallet | `pwa`, `cloudflare-workers`, `hono`, `drizzle`, `nextjs`, `safety` |
| splunk | `splunk`, `siem`, `fortigate`, `security-monitoring`, `python` |
| terraform | `terraform`, `infrastructure-as-code`, `proxmox`, `homelab`, `iac` |
| tmux | `tmux`, `dotfiles`, `terminal`, `productivity` |
| propose | (description 재작성 필요) |
| hycu | (description 먼저 필요) |
| youtube | `youtube`, `automation`, `n8n`, `fastapi`, `ffmpeg`, `python` |

### 5b. Description 재작성 필요 (3개)

| Repo | 현재 | 문제 |
|------|------|------|
| idle-outpost | (없음) | Python 프로젝트인데 설명 없음 |
| opencode | "Restored from gitlab..." | 복원 메모, 의미 없음 |
| propose | "Restored from gitlab..." | 동일 |
| hycu | (없음) | TypeScript, 설명 없음 |

→ 이 4개는 **소유자가 실제 목적을 알려줘야** 정확한 description 작성 가능.

### 5c. Homepage URL

| Repo | 배포 URL (있으면) |
|------|-------------------|
| resume | `https://resume.jclee.me` |
| safetywallet | (배포됐으면 admin/PWA URL) |
| 나머지 | 없으면 생략 |

### 자동화 옵션

- `config/repos.yaml`에 `description`, `topics`, `homepage` 필드 추가
- 새 Go 명령 `cmd/repo-metadata` 또는 기존 deploy에 통합 → `gh api -X PATCH repos/...` + topics API
- **장점**: 단일 진실 소스(repos.yaml)에서 메타데이터까지 관리, drift 방지

### 결정 필요 사항

- [ ] idle-outpost / opencode / propose / hycu 의 실제 목적?
- [ ] topics를 repos.yaml에 넣어 자동 관리할지, 1회성 수동 설정할지
- [ ] homepage URL이 있는 repo 목록

---

## 6. 실행 우선순위 (제안)

| Wave | 작업 | 의존성 | 자동화 여부 |
|------|------|--------|-------------|
| **W1** | SECURITY.md + CODE_OF_CONDUCT.md를 `.github` 루트에 추가 (→ 16 repo 상속, health 100%) | 없음 | 직접 commit |
| **W1** | 14개 repo topics 설정 (의미 명확한 10개 먼저) | 없음 | `gh api` 스크립트 |
| **W1** | user profile fields (bio/blog/location) | 사용자 값 확정 | `gh api -X PATCH user` |
| **W2** | Profile README (`jclee941/jclee941`) 생성 | 사용자 톤/언어 결정 | repo 생성 + 정적 README |
| **W2** | description 부실한 4개 repo 재작성 | **사용자 입력 필수** | `gh api -X PATCH` |
| **W3** | repos.yaml에 metadata 필드 + Go 동기화 명령 | W1 topics 패턴 확정 후 | 신규 Go 코드 |
| **W3** | profile activity auto-update workflow | W2 README 골격 후 | 신규 workflow |

---

## 7. 확정된 결정 (사용자 지시: "한국어, 나머지 알아서")

| # | 질문 | 확정 |
|---|------|------|
| 1 | 언어 | **한국어 기본** (기술 스택 배지/키워드만 영어 허용) ✅ 확정 |
| 2 | 연락처 | blog = `https://resume.jclee.me` (resume repo가 운영 중), location = `Seoul, South Korea`(추정), 이메일 비공개 |
| 3 | 부실 repo 4개 | idle-outpost/opencode/propose/hycu — 목적 불명확. **description은 "비공개/실험" 수준으로 보수적 작성**, topics는 언어 기반만 |
| 4 | FUNDING.yml | Sponsors 계정 미확인 → **생략** (필요 시 추후 추가) |
| 5 | 자동화 수준 | **repos.yaml + Go 영구 관리** (drift 방지가 이 레포 철학과 일치) |

### 추론 근거

- **언어=한국어**: 사용자 명시 지시. README 헤더/소개/섹션 제목 모두 한국어, 코드/배지/topic만 영어.
- **연락처**: resume repo가 `resume.jclee.me` portfolio를 운영하므로 blog로 적합.
  location은 한국어 근거로 Seoul 추정(틀리면 수정).
- **부실 repo**: opencode/propose는 "Restored from gitlab" 복원 메모뿐이고 hycu/idle-outpost는 설명 없음.
  목적을 추측해 잘못 쓰느니 보수적으로. 정확한 목적을 알면 정밀화.
- **FUNDING 생략**: Sponsors 미사용으로 보임. 빈 FUNDING.yml은 오히려 혼란.
- **자동화**: 이 레포는 모든 것을 `config/repos.yaml` 단일 소스 + Go로 관리하는 GitOps 철학. 메타데이터도 동일 패턴이 일관적.

> 위 확정안 기준으로 W1(SECURITY/CODE_OF_CONDUCT/topics/profile fields)은 즉시 자동 적용 가능합니다.
> 부실 repo 4개의 정확한 목적만 추가로 알려주시면 W2 description까지 정밀화됩니다.
