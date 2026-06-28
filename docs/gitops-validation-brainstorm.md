# GitOps 검증 강화 및 중복 기능 제거 브레인스토밍

**대상 저장소**: `jclee941/jclee-bot` (모든 `jclee941/*` 리포지토리에 자동 배포되는 워크플로 표준의 출처)
**분석일**: 2026-06-03
**분석 + 구현**: 동일 PR
**분석 범위**: `.github/workflows/` (57개 → 47개), `scripts/cmd/*` (Go 도구 8개), `scripts/*.py`, `scripts/cmd/deploy-to-repos/main.go` 배포 매니페스트

> 본 문서는 "분석(브레인스토밍)"과 "구현(중복 제거 + 검증 도구 추가)"을 한 PR로 다룹니다.
>
> - **As-was**: 이 PR 직전의 상태
> - **As-is**: 이 PR 적용 후의 상태

---

## 0. 요약 (TL;DR)

| 항목 | As-was | As-is |
|---|---|---|
| 활성/존재 워크플로 수 | 57 | **47** |
| 고아(orphan) 재사용 워크플로 | 10개 (호출자 없음, 다운스트림 미배포) | **0개** |
| GitOps 교차 검증 항목 (`validate-naming`) | 9 | **10** (orphan 탐지기 추가) |
| 중복 클러스터 | 9개 식별 | 핵심 dead-code 클러스터 제거 |

핵심 결론: **57개 워크플로 중 10개는 `on: workflow_call` 전용이면서 로컬에서 아무도 호출하지 않고, 다운스트림 배포 매니페스트(`downstreamWorkflowAllowlist`)에도 없는 "고아 재사용 워크플로"** 였다. 이들은 활성 워크플로(12/13/17/18/91 등)의 기능을 중복하는 dead code였고, 인벤토리 정확도를 떨어뜨리며 GitOps 드리프트의 원인이 되었다. 전부 제거하고, **재발 방지용 자동 검증기**(`orphanReusableWorkflows`)를 추가했다.

---

## 1. 현황 분석 (중복 클러스터)

### 1.1 중복 클러스터 매트릭스 (As-was)

57개 워크플로를 트리거(`on:`)와 역할 기준으로 군집화한 결과, 다음 9개 클러스터에서 기능 중복이 관찰되었다.

| 클러스터 | 멤버 | 중복 성격 | 처리 |
|---|---|---|---|
| C1 Auto-merge | `jclee-bot` App merge policy, `81_auto-merge` | `81`은 App merge policy를 복제한 미사용 reusable | 🔴 `81` 제거 |
| C2 PR 리뷰 | `10_pr-review`(CLIProxy), `11_security-pr-review`(보안 감사), `86_pr-review-security` | `86`은 `security/11`을 복제한 미사용 reusable | 🔴 `86` 제거 |
| C3 Stale | `16_stale-repo-identifier`, `17_pr-stale-bot`, `88_stale` | `88`은 `16`/`17`을 복제한 미사용 reusable | 🔴 `88` 제거 |
| C4 이슈 관리 | `jclee-bot` App issue webhooks, `82_issue-label`, `83_issue-lifecycle`, `84_labeler` | `82`/`83`/`84`는 App issue webhooks를 복제한 미사용 reusable | 🔴 `82`/`83`/`84` 제거 |
| C5 PR 보조 | `03_pr-checks`+`44_reusable-pr-checks`, `85_pr-normalize`, `87_pr-size` | `85`/`87`은 어디서도 호출 안 됨 | 🔴 `85`/`87` 제거 |
| C6 환영/온보딩 | `89_welcome` | 호출자 없음 | 🔴 `89` 제거 |
| C7 재사용 CI | `41_reusable-ci` | 호출자 없음, 배포 매니페스트에도 없음 | 🔴 `41` 제거 |
| C8 Gitleaks | `05_gitleaks` → `45_reusable-gitleaks` | 정상 caller/reusable 쌍 | ✅ 유지 |
| C9 활성 reusable | `42/43/44/45_reusable-*` | `20`/`21`/`18`/`03`/`05`가 실제 호출 | ✅ 유지 |

### 1.2 고아 판정 근거 (3중 확인)

각 후보는 다음 **세 조건을 모두** 만족할 때만 "고아"로 판정했다(거짓 양성 방지).

1. `on:` 블록이 `workflow_call` 전용 (+ 선택적 `workflow_dispatch`). 즉 자체 트리거(push/pull_request/schedule/issues 등)가 없어 스스로 실행되지 않음.
2. 동일 저장소의 어떤 워크플로도 `uses: ./.github/workflows/<name>` 로 호출하지 않음.
3. `scripts/cmd/deploy-to-repos/main.go` 의 `downstreamWorkflowAllowlist` 에 없음 → 다운스트림 repo로도 배포되지 않으므로 외부에서 소비될 수 없음.

검증 명령:

```bash
# (1) 로컬 caller 부재 확인
for n in 41 81 82 83 84 85 86 87 88 89; do
  grep -rl "uses:.*${n}_" .github/workflows/ | grep -v "/${n}_"   # → 빈 결과
done
# (3) 배포 매니페스트 부재 확인
grep -E "8[0-9]_|41_reusable" scripts/cmd/deploy-to-repos/main.go   # → 빈 결과
```

세 조건을 모두 만족한 10개: `41_reusable-ci`, `81_auto-merge`, `82_issue-label`, `83_issue-lifecycle`, `84_labeler`, `85_pr-normalize`, `86_pr-review-security`, `87_pr-size`, `88_stale`, `89_welcome`.

> 비교군이었던 docs, issue-management, PR-checks, gitleaks reusable workflows는 이후 App-owned checks/webhooks로 이관되어 제거됨. `11_security-pr-review` 는 `pull_request_target` 자체 트리거 + 다운스트림 배포 대상이므로 유지.

---

## 2. GitOps 검증 전략 (3차원)

사용자 요청의 "GitOps 검증"을 세 축으로 분해하고, 각 축을 담당하는 도구와 강화 포인트를 정리한다.

### 2.1 차원 A — 워크플로 중복/충돌 검증 (이번 PR 신규)

| 항목 | As-was | As-is |
|---|---|---|
| 고아 reusable 탐지 | ❌ 수동 grep | ✅ `validate-naming` 의 `orphanReusableWorkflows()` 자동 검사 |
| 동작 | — | `workflow_call` 전용 + 로컬 caller 없음 + 매니페스트 미포함 → FAIL |
| 실행 | — | `90_sanity.yml` / CI에서 `go test ./...` + `go run ./cmd/validate-naming` |

설계: `extractGoStringLiterals()` 로 `downstreamWorkflowAllowlist`(map) 키를 파싱하고, `extractOnBlock()` + `isWorkflowCallOnly()` 로 `on:` 블록만 정밀 파싱해 권한(`permissions: issues: write`)·잡 이름(`label:`)을 트리거로 오인하지 않도록 한다.

### 2.2 차원 B — 설정 드리프트 / 매니페스트 정합성 검증 (이번 PR 강화)

| 도구 / 검사 | 역할 | As-is |
|---|---|---|
| `scripts/cmd/drift-detector` | 다운스트림 repo의 관리 대상 파일이 원본과 일치하는지 비교 | ✅ 유지 |
| `deployManifestConsistency()` (신규) | 같은 경로가 `downstreamWorkflowAllowlist` ↔ `removedWorkflows` 에 동시 존재(배포·삭제 모순) 금지 + `removedWorkflows` 가 가리키는 파일이 로컬에 아직 존재(드리프트)하지 않음 | ✅ 추가 |
| `33_drift-detector.yml` | 위 도구를 스케줄 실행 | ✅ 유지 |

### 2.3 차원 C — 배포 정합성 검증 (이번 PR 강화)

| 항목 | As-was | As-is |
|---|---|---|
| 배포 매니페스트 ↔ E2E 상수 | `deployConstantsMatchE2E` | ✅ 유지 |
| auto-deploy 경로 ↔ extraFiles | `autoDeployPathsCoverExtraFiles` | ✅ 유지 |
| 필수 상태 체크 ↔ 워크플로 컨텍스트 | `requiredStatusChecksMatchWorkflowContexts` | ✅ 유지 |
| 배포 매니페스트 ↔ 실제 파일 존재 | ❌ 없음 | ✅ `deployManifestPathsExist()` (신규) — 매니페스트(allowlist+extraFiles)가 가리키는 모든 경로가 repo에 실제 존재하는지 검사 (subdir 포함) |

---

## 3. 구현 (As-is)

### 3.1 제거된 워크플로 (10)

`git rm` 으로 삭제: `41_reusable-ci.yml`, `81_auto-merge.yml`, `82_issue-label.yml`, `83_issue-lifecycle.yml`, `84_labeler.yml`, `85_pr-normalize.yml`, `86_pr-review-security.yml`, `87_pr-size.yml`, `88_stale.yml`, `89_welcome.yml`.

→ 57 → 47개. README 인벤토리(badge/TOC/표/디렉터리 트리) 동기화 완료.

### 3.2 신규 GitOps 검증기 4종 (validate-naming)

파일: `scripts/cmd/validate-naming/main.go`, `validations` 슬라이스에 등록. 모두 TDD(RED→GREEN).

| 검증기 | 차원 | 동작 |
|---|---|---|
| `orphanReusableWorkflows()` | A 중복/충돌 | `workflow_call` 전용 + 로컬 caller 없음 + 매니페스트 미포함 → FAIL |
| `deployManifestPathsExist()` | C 배포 정합 | allowlist+extraFiles 경로가 실제 존재하는지 |
| `deployManifestConsistency()` | B 드리프트 | allowlist∩removedWorkflows 충돌 금지 + removedWorkflows가 로컬에 잔존 금지 |
| `readmeWorkflowInventoryUnique()` | A/문서 정합 | README 인벤토리 표가 각 워크플로를 정확히 1회만 열거(중복 금지) + 실제 파일 집합과 일치 |

견고성(hardening): `orphanReusableWorkflows` 는 `filepath.WalkDir` 로 서브디렉터리(security/)와 `.yml`/`.yaml` 모두 재귀 스캔; `isWorkflowCallOnly` 는 블록 매핑 + 인라인 스칼라(`on: workflow_call`)·배열(`on: [workflow_call]`) 형태 모두 처리; 매니페스트 파싱 실패는 조용히 무시하지 않고 에러를 표면화. 헬퍼: `extractGoStringLiterals()`(slice+map 키 AST 파싱), `extractOnBlock()`(on: 블록만 추출).

### 3.3 검증 결과 (실측)

```text
$ (cd scripts && go run ./cmd/validate-naming)
PASS: ... (9개 기존)
PASS: no orphaned reusable workflows
PASS: deploy manifest paths exist
PASS: deploy manifest internally consistent
All validations passed
```

---

## 4. 향후 고도화 후보 (Backlog)

**우선순위**: 🔴 P0 / 🟠 P1 / 🟡 P2

| ID | 항목 | 근거 | 우선 |
|---|---|---|---|
| G1 | App-owned Dependabot merge policy의 실패 신호 검증 | workflow-owned Dependabot merge 표면은 제거됨 | ✅ App 경로 유지 |
| G4 | 헬스체크 클러스터(26/28/29/30/31/32) 통합 검토 | 6개 스케줄 워크플로가 유사 패턴 — reusable 1개 + 매트릭스로 통합 가능성 | 🟡 P2 |
| G5 | README 생성기(LLM)와 인벤토리 자동 동기화 회귀 가드 | 워크플로 추가/삭제 시 README가 LLM 환각 없이 정확히 반영되는지 검사 | 🟡 P2 |

> G1은 이번 PR 범위(중복 제거)와 별개의 선재(pre-existing) 버그이므로 본 PR에서 손대지 않았고, 백로그로 기록한다.

---

## 5. 검증 체크리스트 (이 PR)

- [x] 10개 고아 워크플로 제거 (57 → 47)
- [x] `orphanReusableWorkflows()` 검증기 추가 (TDD RED→GREEN)
- [x] GitOps 검증기 3종 추가 (orphan / deploy-paths-exist / manifest-consistency) — TDD RED→GREEN, 총 12개 검사 PASS
- [x] `go test ./cmd/validate-naming` GREEN (RepoClean + inline/array/.yaml/manifest-parse 엣지케이스 포함)
- [x] `gofmt`/`go vet` clean
- [x] `validate-naming` 바이너리 실행 → 12개 전원 PASS
- [x] README 끌글링 참조 0개, 카운트 47 동기화, 카테고리 소계 일치, markdownlint 0 error
- [x] 삭제 워크플로에 대한 다운스트림/cross-repo 참조 없음 확인 (`gh search code` 10/10 → 0 hits)
