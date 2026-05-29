# 자동화 고도화 — 브레인스토밍 / Automation Enhancement Brainstorm

> Status: **DRAFT for review**. 의사결정용 옵션 정리 문서입니다. 실제 적용은 별도 PR로 진행합니다.
> Scope: `jclee941/.github` GitOps 자동화 (PR-Agent fork + Go CLI + 56개 워크플로우 + 16개 repo 관리)
> Method: 코드 직접 검증 + Oracle 교차 검토. 각 항목에 `file:line` 근거 표기.

---

## 0. 현재 상태 / Current State

이 레포는 16개 `jclee941/*` repo를 단일 소스(`config/repos.yaml`)로 관리하는 성숙한 GitOps 시스템입니다.

| 영역 / Area | 현황 / Status |
|------|------|
| AI PR 리뷰 | `/review` `/improve` `/describe` 자동 실행, 한국어 출력, critical 발견 시 이슈 자동 생성 |
| 하드코드 탐지 | AWS/GitHub 토큰·JWT·private key·connection string regex + LLM (`pr_hardcode_detector.py`) |
| 워크플로우 | 56개 (`NN_` 접두사 실행 순서), `deploy-to-repos`로 다운스트림 배포 |
| Go CLI | 8개 (branch-protection, deploy-to-repos, sync-secrets, repo-review, rulesets-manager, drift-detector, repo-metadata, validate-naming) |
| 관측성 | Prometheus 메트릭 + `/health` + `/ready` (`monitoring.py`), ELK 연동 |
| 테스트 | Python 563 + Go 6 패키지 통과, `90_sanity.yml` CI 게이트 |

**진단 결론**: 핵심 기능은 견고함. 개선 여지는 **자동화 커버리지의 빈틈**(드리프트·메타데이터·정책)과 **2건의 실제 버그**에 집중됨.

---

## 1. 확인된 갭 / Verified Gaps

> 모든 항목은 코드에서 직접 확인하고 Oracle이 교차 검증했습니다.

### 🔴 버그 (즉시 수정 권장) / Confirmed Bugs

| # | 갭 / Gap | 근거 / Evidence | 영향 / Impact |
|---|----------|-----------------|---------------|
| **B1** | `20_readme-gen.yml` 커밋 스텝이 **중복**됨 — `git checkout -b bot/auto-readme-update`가 두 번 실행되어 두 번째에서 브랜치 충돌로 실패 | `.github/workflows/20_readme-gen.yml:82` 및 `:89` (동일 브랜치 2회) | README 변경이 있을 때 워크플로우 실패 |
| **B2** | `22_template-sync.yml`이 `contents: read` 권한만 선언하면서 다운스트림 repo에 push 시도 | `22_template-sync.yml:10-12` (read) vs `:105-109` (push) | 기본 `GITHUB_TOKEN`으로는 cross-repo write 불가 → 동작 실패 가능. PAT/App 토큰 필요 |

### 🟠 자동화 커버리지 갭 / Coverage Gaps

| # | 갭 / Gap | 근거 / Evidence | 영향 / Impact |
|---|----------|-----------------|---------------|
| **G1** | `repo-metadata` 도구는 존재·테스트됨이지만 이를 **주기 실행하는 워크플로우가 없음** (수동 전용) | `scripts/cmd/repo-metadata/main.go` 존재, `.github/workflows/`에 metadata 워크플로우 없음 | description/topics/homepage 드리프트가 자동 보정되지 않음 |
| **G2** | README 자동화 **정책 충돌** — `20_readme-gen`(AI 생성, Sun 00:00)과 `22_template-sync`(정적 템플릿 덮어쓰기, Sun 01:00)이 같은 `README.md`를 두고 경쟁 PR 생성 | `20_readme-gen.yml:82`, `22_template-sync.yml:78` (`cp ... README.md`) | 나중에 머지되는 쪽이 이김. README 소유권 불명확 |
| **G3** | `drift-detector`가 **파일 드리프트만** 감지 — repo 메타데이터·branch protection·rulesets·secrets 드리프트는 미감지 | `scripts/cmd/drift-detector/main.go:96-132` (`getManagedFiles`는 워크플로/dependabot/CODEOWNERS만) | 정책 차원의 fleet 일관성 침묵 붕괴 가능 |
| **G4** | `29_downstream-health-check`가 **3개 워크플로우만** 점검 (`actionlint`, `pr-checks`, `gitleaks`) | `29_downstream-health-check.yml:46` (`WORKFLOWS=(...)`) | pr-review·codeql·dependency-review·docs-sync·auto-merge·ci-auto-heal 실패 미탐지 |
| **G5** | `renovate.json`이 배포·감시되지만 **Renovate 실행 워크플로우가 없음** | `deploy-to-repos/main.go:73-82` (extraFiles), `34_auto-deploy.yml:7-9` (watch), 실행 워크플로우 부재 | 외부 Renovate App 미설치 시 config가 무의미(inert) |
| **G6** | 빌드·이미지 롤아웃(`36_build-and-push-app` + Watchtower) 후 **배포 검증/롤백 게이트 없음** | `36_build-and-push-app.yml:55-63` (`latest` push), 후속 canary gate 부재 | 깨진 이미지가 자동 배포되어도 자동 감지·롤백 없음 |

### 🟡 유지보수·견고성 / Maintainability & Robustness

| # | 갭 / Gap | 근거 / Evidence | 영향 / Impact |
|---|----------|-----------------|---------------|
| **M1** | `sync-secrets`가 repo 목록을 **하드코딩** — `config/repos.yaml` 단일 소스 미사용 (신규 도구들과 불일치) | `scripts/cmd/sync-secrets/main.go:30-49` (`publicRepos` 16개) | repo 추가/제거 시 누락 드리프트 위험 |
| **M2** | `sync-secrets`·`repo-review`에 `_test.go` 없음 | 해당 디렉터리에 `main.go`만 존재 | 고-blast-radius 스크립트의 회귀 무방비 |
| **M3** | 프로필 README(`jclee941/jclee941`) 미구현 — `profile-readme-sync.yml` 제안만 존재 | `docs/github-profile-enhancement-brainstorm.md:81` | 계정 디스커버리/첫인상 미흡 (라이브 미확인) |
| **M4** | 운영 설정 하드코딩 — `ELASTICSEARCH_HOSTS`, healthcheck 30s 간격(≈90s 탐지 지연) | `docker-compose.github_app.yml:45-50`, `:72-74` | ELK 호스트 변경 시 수동 수정, 장애 탐지 지연 |
| **M5** | 월요일 cron 군집 (00:00~09:30 UTC) | `35_*:00:00`, `31_*:02:00`, `08_*:09:00`, `32_*:09:15`, `33_*:09:30` | 일부 offset 적용됨. ubuntu-latest 큐 지연 관측 시에만 문제 |

---

## 2. 우선순위 / Priority (impact × effort)

| 순위 | 작업 / Work Item | 근거 / Rationale | 노력 / Effort |
|:---:|------|------|:---:|
| **1** | **B1 + G2**: README 소유권 정책 확정 + 중복 커밋 블록 제거 | 두 자동화가 같은 파일을 두고 충돌하며 생성기 자체가 버그로 실패. 가장 가시적인 fleet 영향 | M |
| **2** | **B2**: `22_template-sync` 토큰/권한 수정 (PAT/App token, `contents: write`) | cross-repo push가 현재 실패 가능 | S |
| **3** | **G1**: `repo-metadata` 주기 실행 워크플로우 추가 (dry-run → 드리프트 시 이슈/PR) | 테스트된 도구가 이미 있는데 자동화만 없음 — 최저 비용 최고 효과 | S |
| **4** | **G3**: 정책 드리프트 점검 추가 (metadata/branch-protection/rulesets/secrets) | fleet 정책의 침묵 붕괴 방지. `drift-detector` 비대화 대신 도메인별 분리 | M |
| **5** | **G6**: 이미지 롤아웃 후 배포 검증 게이트 (기존 runtime-health canary 활용) | 자동 배포의 안전망 | M |
| **6** | **M1 + M2**: `sync-secrets`를 `config/repos.yaml` 기반으로 + 단위 테스트 | 드리프트 위험 제거 + 회귀 방지 | S |
| **7** | **G4**: `29_downstream-health-check` 점검 워크플로우 목록 확장 | 배포된 핵심 워크플로우 실패 탐지 | S |
| **8** | **G5**: Renovate App 설치 확인 또는 자체 실행 워크플로우 추가 | inert config 제거 | S |
| **9** | **M4**: ELK 호스트 `.env` 파라미터화, healthcheck 간격 검토 | 운영 편의 | Quick |
| **10** | **M3**: 프로필 README 자동화 | 디스커버리 폴리시 (코어 신뢰성 아님) | S |
| **—** | **M5**: cron 분산 | 이미 부분 offset. 큐 지연 관측 시에만 | Quick/no-op |

---

## 3. 권장 구현 스케치 / Recommended Implementation Sketches

### 3.1 README 소유권 확정 (순위 1) — **결정 필요**

두 가지 모델 중 택일:

| 모델 / Model | 설명 | 장점 | 단점 |
|------|------|------|------|
| **A. AI 생성 우선** (권장) | `20_readme-gen`이 README 소유. `22_template-sync`는 README 제외 (CONTRIBUTING/LICENSE만 동기화) | 풍부한 repo별 문서 | LLM 비결정성 |
| **B. 템플릿 우선** | `22_template-sync`가 정적 골격 소유. AI는 마커(`<!-- AUTO:START -->`) 구간만 갱신 | 통제 가능·안정 | 구현 복잡 |

> 어느 쪽이든 **B1 중복 커밋 브록은 반드시 제거** (`20_readme-gen.yml:89` 이하 중복 블록).

### 3.2 metadata-sync 워크플로우 (순위 3)

```yaml
# .github/workflows/11_repo-metadata-sync.yml (NEW)
on:
  schedule: [{ cron: "0 3 * * 1" }]   # 월요일 03:00 UTC (기존 군집 회피)
  workflow_dispatch:
# 1단계: (cd scripts && go run ./cmd/repo-metadata --dry-run)
# 2단계: 드리프트 감지 시 이슈 생성 (신뢰 확보 후 --apply 모드 전환)
```

### 3.3 정책 드리프트 (순위 4)

`drift-detector`에 도메인별 점검 추가 — 단, 파일 드리프트 로직과 분리:

- `--check=metadata` → `repo-metadata --dry-run` 결과 집계
- `--check=protection` → `branch-protection` 기대치 vs 실제 GitHub API
- `--check=rulesets` → `rulesets-manager list` 비교
- `--check=secrets` → 필수 secret 존재 여부 (`gh secret list`)

---

## 4. 결정 필요 사항 / Decisions Needed

- [ ] **README 소유권**: 모델 A(AI 우선) vs B(템플릿 우선)?
- [ ] **metadata-sync 모드**: dry-run+이슈로 시작 후 자동 apply 전환 시점?
- [ ] **Renovate**: GitHub App 사용 중인가, 아니면 자체 워크플로우 필요한가?
- [ ] **B2 토큰**: cross-repo push에 기존 `GH_PAT` secret 재사용 가능한가?

---

## 5. 비고 / Notes

- 본 문서의 모든 갭은 `2026-05` 기준 코드(`HEAD`)에서 검증됨. 적용 시 재확인 권장.
- 업스트림(qodo-ai/pr-agent) 동기화는 본 문서 범위 밖 (별도 머지 작업).
- 프로필/계정 표준화는 [`github-profile-enhancement-brainstorm.md`](github-profile-enhancement-brainstorm.md) 참조.
