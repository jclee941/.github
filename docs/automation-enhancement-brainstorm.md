# 자동화 고도화 — 브레인스토밍 / Automation Enhancement Brainstorm

> Status: **CURRENT as of 2026-06-23**. 의사결정용 옵션 정리 문서입니다. 실제 적용은 별도 PR로 진행합니다.
> Scope: `jclee941/.github` GitOps 자동화 (PR-Agent review engine + jclee-bot GitHub App + Go CLI + 26개 워크플로우 + 16개 repo 관리)
> Method: 코드 직접 검증. 각 항목에 현재 파일 근거를 표기합니다.

---

## 0. 현재 상태 / Current State

이 레포는 16개 `jclee941/*` repo를 단일 소스(`config/repos.yaml`)로 관리하는 성숙한 GitOps 시스템입니다.

| 영역 / Area | 현황 / Status |
|------|------|
| AI PR 리뷰 | `/review` `/improve` `/describe` 자동 실행, 한국어 출력, critical 발견 시 이슈 자동 생성 |
| 하드코드 탐지 | AWS/GitHub 토큰·JWT·private key·connection string regex + LLM (`pr_hardcode_detector.py`) |
| 워크플로우 | 26개 (`NN_` 접두사 실행 순서), 다운스트림 per-repo workflow 배포 대신 App/API 위임 중심 |
| Go CLI | 5개 (`branch-protection`, `repo-review`, `rulesets-manager`, `sync-secrets`, `validate-naming`) |
| 관측성 | Prometheus 메트릭 + `/health` + `/ready` (`monitoring.py`), ELK 연동 |
| 테스트 | `scripts/cmd/*` 5개 Go command 패키지 모두 `_test.go` 보유, `90_sanity.yml` CI 게이트 |

**진단 결론**: 핵심 기능은 App 중심으로 정리됨. 개선 여지는 **정책 드리프트 관측성**과 **운영 검증 자동화**에 집중됨.

---

## 1. 확인된 갭 / Verified Gaps

> 모든 항목은 현재 코드에서 직접 확인했습니다.

### 🔴 버그 (즉시 수정 권장) / Confirmed Bugs

| # | 갭 / Gap | 근거 / Evidence | 영향 / Impact |
|---|----------|-----------------|---------------|
| **B1** | 자동화 상태 문서가 제거된 워크플로우와 이미 개선된 CLI 상태를 계속 실제 갭처럼 설명함 | `docs/automation-enhancement-brainstorm.md`, `scripts/cmd/validate-naming/current_required_checks_docs.go` | 표준화 현황 판단이 오래된 정보에 끌려가며 이미 해결된 작업을 다시 계획할 위험 |

### 🟠 자동화 커버리지 갭 / Coverage Gaps

| # | 갭 / Gap | 근거 / Evidence | 영향 / Impact |
|---|----------|-----------------|---------------|
| **G1** | 정책 드리프트 검증은 `branch-protection` / `rulesets-manager` dry-run 중심이며, 스케줄된 원격 비교 리포트는 별도 표면으로 분리되어 있지 않음 | `scripts/cmd/branch-protection/main.go`, `scripts/cmd/rulesets-manager/main.go`, `.github/workflows/31_repo-health.yml` | GitHub 원격 정책이 수동 변경될 때 감지는 가능하지만 전용 리포트로 모이지 않음 |
| **G2** | Downstream Health Check는 App-era 전환 후 per-workflow sweep을 비워 둔 no-op close 경로임 | `.github/workflows/29_downstream-health-check.yml` (`WORKFLOWS=()`) | 기존 issue 정리는 안전하지만 downstream 상태 관측 신호로는 약함 |
| **G3** | App 이미지 롤아웃 후 런타임 검증은 별도 health workflows에 의존함 | `.github/workflows/36_build-and-push-app.yml`, `.github/workflows/30_runtime-health-check.yml` | 배포 직후 canary/rollback 판단이 한 표면으로 묶여 있지 않음 |

### 🟡 유지보수·견고성 / Maintainability & Robustness

| # | 갭 / Gap | 근거 / Evidence | 영향 / Impact |
|---|----------|-----------------|---------------|
| **M1** | 자동화 상태 문서의 오래된 워크플로우/CLI 언급은 validator에서 계속 차단해야 함 | `scripts/cmd/validate-naming/current_required_checks_docs.go` | 같은 종류의 표준화 상태 오판 재발 방지 |
| **M2** | 운영 설정 일부가 compose 환경값에 직접 남아 있음 | `docker-compose.github_app.yml` | 환경 변경 시 설정 파일 수정이 필요할 수 있음 |

---

## 2. 우선순위 / Priority (impact × effort)

| 순위 | 작업 / Work Item | 근거 / Rationale | 노력 / Effort |
|:---:|------|------|:---:|
| **1** | **B1 + M1**: 오래된 상태 문서 차단 규칙 유지 | 표준화 상태 판단의 입력 품질을 먼저 고정 | S |
| **2** | **G1**: 원격 branch-protection/rulesets 비교 리포트 표면 추가 | 정책 드리프트를 App-era 상태 신호로 모으기 | M |
| **3** | **G2**: Downstream Health Check 역할 재정의 | no-op close 경로인지, 실제 downstream 상태 리포트인지 명확화 | S |
| **4** | **G3**: App 이미지 롤아웃 직후 canary/gate 연결 | 자동 배포 안전망 강화 | M |
| **5** | **M2**: compose 운영값 파라미터화 검토 | 환경 변경 비용 축소 | Quick |

---

## 3. 권장 구현 스케치 / Recommended Implementation Sketches

### 3.1 정책 드리프트 리포트 (순위 2)

기존 적용 도구와 분리된 read-only 리포트가 적합합니다.

- `branch-protection` 기대 payload vs GitHub branch protection API
- `rulesets-manager` expected payload vs GitHub rulesets API
- `config/repos.yaml`의 `branch_protection: true` repo 전체 커버리지
- `github-bot` 소스 리포지토리 자체 제외 상태 보존

---

## 4. 결정 필요 사항 / Decisions Needed

- [ ] **Downstream Health Check**: no-op issue-close workflow로 유지할지, 원격 상태 리포트 표면으로 재설계할지?
- [ ] **원격 정책 리포트**: read-only issue report로 시작할지, 실패 시 required CI gate로 올릴지?
- [ ] **App rollout gate**: build workflow 안에 canary를 붙일지, runtime-health workflow를 repository_dispatch로 호출할지?

---

## 5. 비고 / Notes

- 본 문서의 모든 갭은 `2026-06-23` 기준 코드(`HEAD`)에서 재검증됨. 적용 시 재확인 권장.
- 원본(qodo-ai/pr-agent) 동기화는 더 이상 본 문서 범위 밖 (별도 머지 작업 없음, de-forked).
- 프로필/계정 표준화는 [`github-profile-enhancement-brainstorm.md`](github-profile-enhancement-brainstorm.md) 참조.
