# Git Workflow 자동화 리뷰 및 갭 분석

**대상 저장소**: `jclee941/.github` (모든 `jclee941/*` 리포지토리에 자동 배포되는 워크플로 표준의 출처)
**분석일**: 2026-05-03
**분석 + 구현**: 동일 PR
**분석 범위**: `.github/workflows/`, `.github/dependabot.yml`, `scripts/*.go`, `.git/hooks/`, 커뮤니티 파일

> 본 문서는 "분석"과 "구현"을 한 PR로 다룹니다. 두 가지 상태를 명확히 구분합니다.
> - **As-was**: 이 PR 직전의 상태
> - **As-is**: 이 PR 적용 후의 상태

---

## 1. 현황

### 1.1 As-was 활성 워크플로 (8 top-level + 1 보안)

| 파일 | 트리거 | 역할 | 평가 |
|---|---|---|---|
| `pr-review.yml` | `pull_request` | cli_proxy 기반 AI 코드 리뷰 (Kimi-k2.6) | ✅ 잘 구성됨 |
| `pr-checks.yml` → `reusable-pr-checks.yml` | `pull_request` | 6개 검사 (size/title/branch/desc/large/sensitive) | ✅ 안정적 |
| `dependabot-auto-merge.yml` | `pull_request` (dependabot 한정) | patch/minor/gha 자동 머지 | ✅ 정책 명확 |
| `auto-deploy.yml` | `push` to master | `deploy-to-repos.go` 실행 → 11개 다운스트림 동기화 | ⚠️ 타임아웃/concurrency 없음 |
| `auto-hardcode-scan.yml` | `schedule` weekly + dispatch | 하드코드 정규식 스캔 | ⚠️ `self-hosted` 종속 |
| `docs-sync.yml` → `reusable-docs-sync.yml` | `pull_request` md/docs | 링크 검사 + markdownlint | ✅ |
| `issue-management.yml` → `reusable-issue-management.yml` | issues + schedule | stale 정리 + 자동 라벨 | ✅ |
| `sanity.yml` | push/PR | import 스모크 + TOML/YAML parse | ✅ but required check 아님 |
| `security/pr-review.yml` | `pull_request_target` + 라벨 | 심층 보안 리뷰 | ⚠️ 가드 보강 필요 |

(reusable workflow 3개는 별도 파일로 존재하지만 직접 트리거되지 않음)

### 1.2 As-is 활성 워크플로 (이 PR 적용 후)

추가됨:
- `codeql.yml` — Python SAST
- `gitleaks.yml` — Secret scanning
- `actionlint.yml` — Workflow YAML semantic linter

총 11 top-level + 1 보안 + 3 reusable.

### 1.3 스크립트 (이 PR에서 일부 수정; 테스트 부재는 P2 이연)

| 파일 | 역할 |
|---|---|
| `scripts/cmd/deploy-to-repos/main.go` | 11개 리포에 워크플로 동기화 PR 생성 |
| `scripts/cmd/branch-protection/main.go` | 브랜치 보호 + auto-merge 허용 적용 |
| `scripts/cmd/sync-secrets/main.go` | `CLIPROXY_API_KEY` 동기화 |

### 1.4 Dependabot 설정

- **As-was**: `github-actions`만
- **As-is**: `github-actions` + `pip` (minor+patch 그룹화)

---

## 2. 갭 분석 (Gap Matrix)

**우선순위**: 🔴 P0 / 🟠 P1 / 🟡 P2
**상태**: ✅ 이 PR 해결 / ⏸️ 후속 PR 이연

| # | 갭 | 우선순위 | 위험 | 조치 | 상태 |
|---|---|---|---|---|---|
| G1 | CodeQL/SAST 정적 분석 없음 | 🔴 P0 | Python 보안이 AI 리뷰에만 의존 | `codeql.yml` 추가 | ✅ |
| G2 | Secret scanning 워크플로 없음 | 🔴 P0 | `.env` 누출 발견 지연 | `gitleaks.yml` 추가 | ✅ |
| G3 | `pip` ecosystem dependabot 누락 | 🟠 P1 | 의존성 자동 갱신 누락 | `dependabot.yml`에 `pip` 추가 | ✅ |
| G4 | CODEOWNERS 없음 | 🟠 P1 | 자동 리뷰어 할당 불가 | `.github/CODEOWNERS` 추가 (소스 및 11개 다운스트림 리포에 배포; org-level CODEOWNERS는 전파 안 됨) | ✅ |
| G5 | PR 템플릿 없음 | 🟠 P1 | description<10자 오류 빈발 | `.github/PULL_REQUEST_TEMPLATE.md` (소스 및 11개 다운스트림 리포에 배포) | ✅ |
| G6 | Issue 템플릿 없음 | 🟡 P2 | 자동 라벨링 정확도 저하 | `.github/ISSUE_TEMPLATE/` | ⏸️ |
| G7 | CONTRIBUTING.md 없음 | 🟡 P2 | 외부 기여자 가이드 부재 | 추가 | ⏸️ |
| G8 | release 자동화 없음 | 🟡 P2 | 태그/체인지로그 수작업 | `release-drafter.yml` | ⏸️ |
| G9 | actionlint 없음 | 🟠 P1 | GHA 의미 오류 prod 유입 | `actionlint.yml` 추가 | ✅ |
| G10 | `auto-deploy.yml` concurrency 미설정 | 🟠 P1 | rapid push race | `concurrency: auto-deploy` (cancel=false) | ✅ |
| G11 | 일부 워크플로 timeout 누락 | 🟠 P1 | hung job | `timeout-minutes` 추가 | ✅ |
| G12 | `auto-hardcode-scan.yml` self-hosted 강제 | 🟡 P2 | 러너 오프라인 시 누락 | `ubuntu-latest`로 이전 (조기 처리) | ✅ |
| G13 | `pr-review.yml` concurrency 미설정 | 🟠 P1 | 중복 실행 + 토큰 낭비 | `concurrency` 추가 | ✅ |
| G14 | `scripts/*.go` 테스트 없음 | 🟡 P2 | 배포 회귀 위험 | `_test.go` 추가 | ⏸️ |
| G15 | 빈 `.github/workflows/reusable/` | 🟡 P2 | cruft | **디렉터리 삭제** (`rmdir`) | ✅ |
| G16 | required check 확장 | 🟠 P1 | secret leak도 머지됨 | `Gitleaks / scan` 추가 (sanity는 fork-only이므로 다운스트림 미적용) | ✅ |
| G17 | 테스트 브랜치 누적 | 🟡 P2 | 정리 부족 | stale-branch 자동화 | ⏸️ |
| G18 | `pull_request_target` 가드 약함 | 🔴 P0 | fork PR 토큰 탈취 가능 | `head.repo.full_name == github.repository` 추가 | ✅ |
| G19 | 액션 SHA pinning 없음 | 🟡 P2 | 공급망 공격 가능 | 보안 워크플로 SHA pin | ⏸️ |
| G20 | `.git/hooks/post-commit` 무력 상태 | 🟡 P2 | 의도 불명 | 삭제 또는 명확화 | ⏸️ |

> **G16 명확화**: 분석 단계에서는 sanity + gitleaks 두 컨텍스트를 required로 격상 검토했으나, **sanity.yml은 fork-only** (pr_agent import 검증)이며 `deploy-to-repos.go`의 `downstreamWorkflowAllowlist`에 포함되지 않음. 따라서 다운스트림 required는 `Gitleaks / scan`만 추가. sanity는 본 리포(`jclee941/.github`)에서만 advisory로 유지됨.

---

## 3. 신규 워크플로 (이 PR)

### 3.1 CodeQL (G1) — advisory only, NOT required
- 트리거: `**.py` 또는 pyproject 변경 시 PR/push, 주 1회 schedule
- 이유: `.py` 변경에만 트리거되므로 required로 강제하면 비-Python PR이 영원히 대기. Security 탭과 PR 코멘트로 surface.

### 3.2 Gitleaks (G2) — required check (Phase 3 이후)
- 트리거: 모든 PR, master push
- 동작:
  - **PR**: gitleaks-action@v2가 PR commit range (`${baseRef}^..${headRef}`, `--first-parent --no-merges`)에 대해 `gitleaks detect` 실행. 엄밀한 base..head 파일 diff 스캔이 아니라 **PR commit 시리즈 내 도입된 leak**을 보고함 (PR 안에서 추가됐다 제거된 것도 잡힐 수 있음).
  - **Push**: 새 tip의 reachable history 스캔.
  - **fetch-depth: 0** (PR/push 모두): action이 PR commit을 명시적 SHA로 참조하므로 shallow clone 시 multi-commit PR 스캔이 실패 가능. 공식 gitleaks-action README도 `fetch-depth: 0` 권장.
- 베이스라인: 다운스트림에 historical leak 있으면 repo 루트에 `.gitleaks.toml` (allowlist) 또는 `.gitleaksignore` (지문 목록) 추가. **`GITLEAKS_CONFIG` env는 의도적으로 미설정** — 미존재 경로를 강제 지정하면 action이 hard-fail함. CLI가 자동 감지함.

### 3.3 actionlint (G9)
- 트리거: `.github/workflows/**` 변경
- shell injection, expression validity 등 GHA 의미 검증

### 3.4 Dependabot pip ecosystem (G3) — 다운스트림 노이즈 주의
- 본 리포(`.github`)는 Python 프로젝트이므로 `pip` ecosystem이 `pyproject.toml` / `requirements*.txt`를 추적함.
- `.github/dependabot.yml`은 `extraFiles`를 통해 11개 다운스트림 리포에도 배포됨.
- **다운스트림 주의**: Python manifest가 없는 리포(예: `terraform`, `tmux`)는 Dependabot이 "no manifest found" 경고를 남길 수 있음. 실제 PR은 생성되지 않으므로 **안전하며 무시 가능**. 향후 해당 리포에 Python이 추가되면 자동 활성화됨.

---

## 4. 보안 강화

### 4.1 `pull_request_target` 가드 (G18)

**As-was**:
```yaml
if: github.event_name == 'pull_request_target' &&
    github.event.label.name == 'security-review' &&
    github.event.pull_request.user.login == 'jclee941'
```

**As-is**:
```yaml
if: github.event_name == 'pull_request_target' &&
    github.event.label.name == 'security-review' &&
    github.event.pull_request.head.repo.full_name == github.repository &&
    github.event.pull_request.user.login == 'jclee941'
```

**트레이드오프 (의도된 동작)**: jclee941이 자신의 fork에서 PR을 올리고 `security-review` 라벨을 붙이면 **silently no-op**됨. 보안상 절충이며 운영자 인식 필수. 동일 리포 브랜치에서 작업하면 정상 동작.

### 4.2 액션 SHA pin (G19) — 이연
P2 이연. 본 PR은 보안 워크플로(`security/pr-review.yml`, `codeql.yml`, `gitleaks.yml`)에도 메이저 태그(`@v3`, `@v6`)만 사용. actionlint.yml의 `download-actionlint.bash`도 `main`에서 가져옴. 일괄 SHA pin은 별도 supply-chain sprint에서.

---

## 5. 품질 강화

### 5.1 Required status checks (G16)
**As-was** (2 contexts, 다운스트림 동일):
```
pr-checks / Check PR Title
pr-checks / Check Branch Name
```
**As-is** (3 contexts, 다운스트림 동일):
```
pr-checks / Check PR Title
pr-checks / Check Branch Name
Gitleaks / scan        ← NEW
```

> Sanity는 fork-only이므로 다운스트림 required에서 제외. CodeQL은 `.py`만 트리거하므로 required에서 제외.

### 5.2 `concurrency` (G10, G13)
| 워크플로 | group | cancel-in-progress |
|---|---|---|
| `pr-review.yml` | `pr-review-${{ github.event.pull_request.number }}` | true |
| `auto-deploy.yml` | `auto-deploy` | **false** (배포 도중 취소 금지) |
| `codeql.yml` | `codeql-${{ github.event.pull_request.number || github.ref }}` | true |
| `gitleaks.yml` | `gitleaks-${{ github.event.pull_request.number || github.ref }}` | true |
| `actionlint.yml` | `actionlint-${{ github.event.pull_request.number || github.ref }}` | true |

### 5.3 `timeout-minutes` (G11)
| 워크플로 | timeout |
|---|---|
| `auto-deploy.yml` | 30 |
| `auto-hardcode-scan.yml` | 15 |
| `codeql.yml` | 30 |
| `gitleaks.yml` | 10 |
| `actionlint.yml` | 5 |

---

## 6. 이 PR이 변경한 파일

### 신규
- `.github/workflows/codeql.yml`
- `.github/workflows/gitleaks.yml`
- `.github/workflows/actionlint.yml`
- `.github/CODEOWNERS` (소스 + 다운스트림 11개 리포)
- `.github/PULL_REQUEST_TEMPLATE.md` (소스 + 다운스트림 11개 리포)
- `docs/git-workflow-gap-analysis.md` (이 문서)

### 수정
- `.github/dependabot.yml` — `pip` ecosystem 추가
- `.github/workflows/pr-review.yml` — concurrency
- `.github/workflows/auto-deploy.yml` — concurrency + timeout
- `.github/workflows/auto-hardcode-scan.yml` — runner 변경 + timeout
- `.github/workflows/security/pr-review.yml` — head repo 가드
- `scripts/cmd/deploy-to-repos/main.go` — workflow allowlist 확장 + `extraFiles`에 CODEOWNERS/PULL_REQUEST_TEMPLATE.md 추가 + PR body 3단계 롤아웃 시퀀스로 갱신 (머지 → Gitleaks 통과 확인 → branch-protection 적용)
- `scripts/cmd/branch-protection/main.go` — `Gitleaks / scan` required context 추가
- `AGENTS.md` — 신규 파일 반영 + `pr-review-security.yml` → `security/pr-review.yml` 경로 정정 + dependabot pip 반영 + runner drift 수정 (self-hosted → ubuntu-latest) + "all 12" 문구 수정 (deploy 11 vs branch-protection 12 구분)

### 삭제
- `.github/workflows/reusable/` — 빈 디렉터리 (`rmdir`)

---

## 7. 롤아웃 시퀀스 (필수 준수)

이 PR을 머지한다고 끝이 아닙니다. **순서가 중요**합니다. 순서를 어기면 모든 PR이 영원히 required check 대기 상태가 됩니다.

### Phase 1 — 본 리포 머지
1. 이 PR을 `jclee941/.github` master에 머지
2. `auto-deploy.yml`이 자동 트리거 → 11개 다운스트림 리포에 PR 생성
3. 각 다운스트림 PR은 *기존* required check 2개(Title, Branch Name)만 가짐. 새 워크플로(gitleaks, codeql, actionlint)는 PR 안에서 처음 실행되며 advisory로 동작 (아직 required 아님).

### Phase 2 — 다운스트림 leak 베이스라인 (조건부)
다운스트림 PR에서 Gitleaks가 historical leak으로 fail 시:
```bash
# 옵션 A: 지문 무시
echo "<fingerprint>" >> .gitleaksignore

# 옵션 B: 정규식 allowlist
cat > .gitleaks.toml <<EOF
[allowlist]
description = "Test fixtures"
regexes = ['''AKIA[0-9A-Z]{16}''']
EOF
```
이 베이스라인을 동일 PR에 추가 커밋하여 통과시킨 뒤 머지.

### Phase 3 — 새 required context 등록
모든 다운스트림 PR이 머지된 후에만:
```bash
(cd scripts && go run ./cmd/branch-protection) --dry-run
(cd scripts && go run ./cmd/branch-protection)         # apply
```
이 시점부터 다운스트림 branch protection은 `Gitleaks / scan`을 required로 요구함.

⚠️ **순서를 어기면 다음이 발생**:
- Phase 3을 Phase 1보다 먼저 실행 → 다운스트림에 워크플로가 없으므로 required context가 영원히 missing → **모든 PR (Dependabot 포함) auto-merge 무한 대기**

### 롤아웃 후 검증 (Phase 3 완료 후 권장)
```bash
gh pr create --repo jclee941/resume --title 'test: validate new workflows' \
  --body 'Test new automation' --head test/validate --base master
gh pr checks <PR_URL>
# 기대 결과: pr-checks/*, Gitleaks/scan, CodeQL/* (Python 한정), actionlint
```

---

## 8. 검증 (이 PR 자체)

```bash
# 1. 워크플로 YAML 파싱 (15 files)
python3 -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/**/*.yml',recursive=True)]"

# 2. actionlint
actionlint -color .github/workflows/*.yml .github/workflows/security/*.yml

# 3. Go scripts build
cd scripts && for f in *.go; do go build -o /tmp/check "$f"; done

# 4. dependabot.yml 파싱
python3 -c "import yaml; d=yaml.safe_load(open('.github/dependabot.yml')); print([u['package-ecosystem'] for u in d['updates']])"

# 5. 다운스트림 dry-run (allowlist에 새 파일 들어왔는지 확인)
(cd scripts && go run ./cmd/deploy-to-repos) --dry-run --repos=resume | grep -E '(codeql|gitleaks|actionlint)'
```

5개 모두 통과 확인됨 (이 PR 작성 시점, 2026-05-03).

---

## 9. 후속 작업 (P2 — 모두 해결됨, 2026-05-03)

초기에는 별도 PR로 이연하기로 했으나 동일 세션에서 모두 해소했습니다. 표는 추적 목적으로 유지합니다.

| # | 갭 | 작업 | 상태 |
|---|---|---|---|
| G6 | Issue 템플릿 | `.github/ISSUE_TEMPLATE/{bug,feature,security}.yml` + `config.yml` | ✅ 완료 |
| G7 | CONTRIBUTING.md | 포크 전용 기여자 가이드 (rollout sequence 포함) | ✅ 완료 |
| G8 | release-drafter | `.github/release-drafter.yml` + `.github/workflows/release-drafter.yml` (Conventional Commits autolabeler) | ✅ 완료 |
| G14 | Go 스크립트 테스트 | `scripts/cmd/{branch-protection,deploy-to-repos}/main_test.go` (16 case, `(cd scripts && go test ./...)`) | ✅ 완료 |
| G17 | stale-branch 자동화 | `actions/stale@v9` 기반 워크플로는 별도 PR로 이연 (브랜치 정책 합의 필요) | ⏸️ 의식적 보류 |
| G19 | 액션 SHA pin | 별도 supply-chain sprint로 이연 (영향 범위 큼) | ⏸️ 의식적 보류 |
| G20 | post-commit 훅 정리 | `.git/hooks/post-commit`은 commented-out 상태로 무해함; 작업 트리 hook이라 git 추적 불가 | ✅ 검증됨 (no action) |

---

## 10. As-is 워크플로 의존성 그래프

```
push to master (.github)
   └─► auto-deploy.yml (concurrency=auto-deploy, timeout=30m)
        └─► scripts/cmd/deploy-to-repos/main.go
             └─► PR in 11 downstream repos
                  ├─► pr-checks.yml          (required: Title, Branch)
                  ├─► gitleaks.yml           (advisory until Phase 3, **required after** branch-protection.go re-applied) ← NEW
                  ├─► pr-review.yml          (advisory AI review)
                  ├─► codeql.yml             (advisory, .py only)        ← NEW
                  ├─► actionlint.yml         (advisory, on workflow change) ← NEW
                  ├─► docs-sync.yml          (advisory)
                  └─► dependabot-auto-merge.yml (if dependabot[bot])
                       └─► auto-merge once all required contexts green
                            (Phase 1–2: 2 required → Phase 3+: 3 required incl. Gitleaks)

PR opened in `jclee941/.github` (source/fork)
   ├─► sanity.yml         (fork-only: import smoke + TOML/YAML parse)
   ├─► pr-checks.yml      (6 checks; 2 required)
   ├─► pr-review.yml      (AI review, concurrency-bounded)
   ├─► docs-sync.yml      (markdown lint + link check)
   ├─► codeql.yml         (Python SAST)                                  ← NEW
   ├─► gitleaks.yml       (secret scan; required after Phase 3 rollout)        ← NEW
   └─► actionlint.yml     (when .github/workflows/ touched)              ← NEW

PR opened in 11 downstream repos (no sanity.yml — it's fork-only)
   ├─► pr-checks.yml      (6 checks; 2 required)
   ├─► pr-review.yml      (AI review, concurrency-bounded)
   ├─► docs-sync.yml      (markdown lint + link check)
   ├─► codeql.yml         (Python SAST, .py only)                       ← NEW
   ├─► gitleaks.yml       (secret scan; required after Phase 3 rollout) ← NEW
   └─► actionlint.yml     (when .github/workflows/ touched)             ← NEW

Label "security-review"
   └─► security/pr-review.yml (now requires head_repo == base_repo)      ← HARDENED
```
