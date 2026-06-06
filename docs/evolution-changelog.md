# Evolution Package Changelog | `scripts/evolution` 변경 이력

> History of improvements to the fork-owned recursive regression & evolution
> package (`scripts/evolution`). Managed by jclee-bot.
> Format based on [Keep a Changelog](https://keepachangelog.com/). All entries
> are grounded in real commits (short SHAs in parentheses).

The package provides three deterministic, unit-testable services:

1. **Regression detection** — fingerprint review findings per repo and flag when a previously closed finding reappears.
2. **Evolutionary scoring** — track accepted/rejected suggestions and evolve a bounded, explainable per-`(repo, category, label)` weight.
3. **Recursive self-refinement** — iterate candidate → critique → regenerate with convergence and anti-oscillation guards.

---

## [Unreleased]

### Added — Parallel recursive descent (`21436372`)

- `RecursiveRefiner` gained an opt-in `max_workers` parameter (default `1` =
  sequential, fully backward compatible).
- Sibling subtrees refine **concurrently** via a single shared, globally-bounded
  `ThreadPoolExecutor(max_workers-1)` plus a non-blocking `BoundedSemaphore`
  (try-acquire → submit, else run inline). This caps total live helper threads
  globally (no per-node thread explosion) and is deadlock-free.
- **Deterministic**: children are collected in original index order regardless of
  inline-vs-threaded execution, so the parallel result tree is byte-identical to
  the sequential one (`aggregate_quality`, `total_iterations`,
  `max_observed_depth` all match).
- Exposed `max_workers` through `EvolutionEngine.refine_recursive` and the
  `refine-recursive --max-workers` CLI flag.
- Why: large decomposition trees were refined strictly serially; parallelism
  cuts wall-clock time while preserving reproducibility.

## [0.2.0] — Generic + recursive refinement (PR #463)

### Added — Generic candidate type `T`

- Genericized the self-refinement loop over a candidate type `T` instead of a
  hardcoded `str`: `SelfRefinementLoop(Generic[T])` with an injectable
  `CandidateSerializer[T]`; generic `Critic[T]`, `Generator[T]`,
  `RefinementIteration[T]`, `RefinementResult[T]` (`7ac7b4b3`, `a278b2ca`).
- `str` remains the fully backward-compatible default; non-`str` candidates
  require an explicit serializer (used for hashing / oscillation detection).
- Why: enable refinement over structured candidates (dataclasses, tuples), not
  just text.

### Added — Recursive descent refinement

- `RecursiveRefiner[T].refine_recursive(...)`: flat-refine → `decompose` →
  recurse (depth-bounded by `max_depth`) → `recompose` → re-refine, returning a
  `RecursiveRefinementResult[T]` tree (`a278b2ca`).
- Honest iteration accounting: internal nodes retain the pre-decompose
  refinement in `pre_refinement`, counted once in `total_iterations`.
- Why: refine a document section-by-section (or any decomposable candidate) and
  aggregate the improvements back.

### Added — SQLite persistence, schema v2 (`5cf25eb4`)

- Recursive refinement trees persist as nested `refinement_runs` rows
  (`parent_run_id` / `node_path` / `depth` + `#pre` phase rows) so persisted DB
  iteration rows equal `total_iterations`.
- Idempotent, additive v1 → v2 migration (guarded by `PRAGMA table_info`).
- Serializing write transactions (`BEGIN IMMEDIATE` + busy timeout) so
  concurrent writers cannot lose read-modify-write weight updates.

### Added — Foundation services

- Domain exceptions (`d54260c3`): `EvolutionError`, `ValidationError`,
  `FingerprintCollisionError`, `DuplicateOutcomeError`.
- Pure data models — frozen dataclasses, `StrEnum`, callable aliases (`7ac7b4b3`).
- Deterministic finding fingerprints (upstream pr-agent marker compatible) +
  per-repo regression detection (`66c49dea`).
- Evolutionary suggestion scoring — bounded `[0.5, 1.5]` weights evolved from
  accept/reject outcomes (`71d53ede`).
- `EvolutionEngine` orchestration facade, upstream `pr_agent` output adapters,
  and a file-based CLI (`242c2a25`).
- Hypothesis added as a dev dependency for property-based invariant tests
  (`11468284`).

---

## Test & quality history

Test counts are reproducible from the repo root **with the dev virtualenv active**
(`hypothesis` is required for the property tests; without it the property suite is
not collected and the count is lower):

```bash
source .venv/bin/activate
python -m pytest tests/unittest/test_evolution_*.py -q   # evolution suite
```

| Milestone | Evolution tests | Notes |
|-----------|----------------:|-------|
| Generic + recursive (PR #463) | 141 | baseline after merge |
| Parallel recursive descent (`21436372`) | 150 | +9 (determinism, concurrency, global thread bound, permit-leak safety, hypothesis property) |

> The `150` figure is the count produced by the command above in the dev venv at
> commit `21436372`. Run it yourself to reproduce.

All changes are TDD (RED → GREEN), `ruff`-clean, and reviewed via the Oracle
gate before merge. Notable defects caught & fixed during review:

- **Iteration undercount**: internal recursive nodes discarded their
  pre-decompose refinement → fixed with `pre_refinement` accounting.
- **`findRepoRoot` breakage**: probed the renamed `pr-checks.yml` → fixed to use
  the stable `config/repos.yaml` marker.
- **Thread explosion**: per-node executors made `max_workers` a per-node cap →
  fixed with one shared globally-bounded pool.
- **Permit leak**: `executor.submit` failure after acquiring a permit leaked it
  → fixed by releasing on submit failure.
