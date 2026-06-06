# Session Improvements History | 작업 세션 개선 이력

> A record of what was improved across the recent automation work session, and
> why. Managed by jclee-bot. Every entry references the real commit(s) that
> delivered it (short SHA in parentheses).

---

## 1. Evolution package — generic + recursive + parallel | 진화 패키지

**What**: Evolved `scripts/evolution` from a `str`-only self-refinement loop into
a generic, recursive, and parallel engine.

- Generic candidate type `T` with injectable serializer; `str` stays the default
  (`7ac7b4b3`, `a278b2ca`).
- Recursive descent: decompose → recurse (depth-bounded) → recompose, with honest
  per-node iteration accounting (`a278b2ca`).
- SQLite schema v2 persisting the recursive run tree with idempotent migration
  (`5cf25eb4`).
- Deterministic **parallel** recursive descent: opt-in `max_workers`, shared
  globally-bounded thread pool, byte-identical to sequential (`21436372`).

**Why**: support structured candidates and parallel refinement of large
decomposition trees without losing reproducibility.

**Detail**: see [`evolution-changelog.md`](evolution-changelog.md).

---

## 2. Drift-detector visual 구성도 | 다운스트림 표준화 점검 시각화

**What**: Improved the downstream standardization audit output from a flat raw
text/table dump into a GitHub-native **Mermaid 구성도** (`--format=mermaid`):
per-repo nodes colored by drift severity (clean / warning / critical) with
drifted-file children, matching `docs/architecture.md` style (`0aa83a8a`).

**Also fixed (critical)**: `drift-detector`'s `findRepoRoot` probed the renamed
`pr-checks.yml`, returning "could not find repo root" and silently breaking the
**entire** audit. Switched to the stable `config/repos.yaml` marker (`0aa83a8a`).

**Why**: the raw audit output was unreadable and the root-find bug meant the
audit had not actually been running.

**Detail**: see [`downstream-standardization.md`](downstream-standardization.md).

---

## 3. GitHub Pages automation | GitHub Pages 자동화

**What**: Added a Pages publishing pipeline for the `docs/` tree
(`41_pages-deploy.yml` + `.github/scripts/build_pages.py`) that renders Markdown
to HTML with client-side Mermaid and an index page (`412535ff`, `9fe319e5`).
Enabled GitHub Pages (`build_type=workflow`); the site is live at
`https://jclee941.github.io/.github/`.

**Why**: surface the architecture and standardization docs (including the new
구성도) as a browsable site. First attempt 404'd because `deploy-pages` serves
artifacts statically with no Jekyll; fixed by building real HTML in the workflow.

---

## 4. CI auto-heal coverage | CI 자동 복구 범위 확장

**What**: Extended `60_ci-auto-heal.yml`'s `workflow_run` trigger to cover
**Release Publish** and **Scorecard supply-chain security** (`a345923d`).

**Why**: both workflows had failed on `main` after a merge but were absent from
the auto-heal trigger list, so their failures were never auto-remediated.

---

## Downstream standardization auto-fix | 다운스트림 표준화 자동 조치

Alongside the above, the full standardization audit was run across the 16
`jclee941/*` repos and drift was auto-fixed live:

- Branch protection applied to all 15 managed repos (idempotent).
- `chore/sync-automation-workflows` PRs opened on all 14 downstream repos
  (auto-merge squash); several merged on the spot as checks passed.
- Re-audit confirmed drift dropping as the sync PRs land.

---

## Verification summary | 검증 요약

| Area | Evidence |
|------|----------|
| Evolution package | 150 unit tests pass; Oracle-reviewed (multi-round) |
| Repo-wide tests | 743 pass, 0 regressions |
| Workflows | `actionlint` clean |
| Docs | `markdownlint` clean |
| Pages site | live HTTP 200 (`index.html`, `downstream-standardization.html`) |
