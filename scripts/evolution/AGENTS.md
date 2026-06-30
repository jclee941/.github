# scripts/evolution - suggestion and regression feedback engine

## OVERVIEW

File-based JSON in/out engine for regression detection, suggestion scoring,
and self-refinement feedback. It is intentionally repo-local under `scripts/`
so it can run offline without GitHub, LLM, or installed-package entry points.

## WHERE TO LOOK

| Task | File | Notes |
|------|------|-------|
| CLI commands | `cli.py` | JSON input/output surface and argparse wiring |
| Public facade | `facade.py` | `EvolutionEngine` composition API |
| Data models | `models.py` | Enums/dataclasses for findings, suggestions, refinement |
| SQLite schema and writes | `storage.py` | `SCHEMA_VERSION`, migrations, transactions |
| Finding identity | `fingerprint.py` | Stable normalized fingerprints |
| Regression matching | `regression.py` | Finding reopen/close behavior |
| Suggestion scoring | `scoring.py` | Weight adjustment and outcome recording |
| Self-refinement loops | `refinement.py` | Generic flat and recursive refinement |
| Review-engine adapters | `adapters.py` | Converts review/improve outputs to engine models |
| Tests | `../../tests/unittest/test_evolution_*.py` | Offline property, concurrency, CLI, facade coverage |

## COMMANDS

```bash
.venv/bin/python -m scripts.evolution.cli init-db --db .cache/evolution.sqlite
.venv/bin/python -m scripts.evolution.cli ingest-findings --db /tmp/evolution.sqlite --repo owner/repo --input findings.json
.venv/bin/python -m scripts.evolution.cli adjust-suggestions --db /tmp/evolution.sqlite --repo owner/repo --input suggestions.json --output adjusted.json
.venv/bin/python -m pytest tests/unittest/test_evolution_facade.py -q
```

## CONVENTIONS

- Preserve the JSON-in/out boundary. External GitHub, review-engine, or LLM output must be adapted before it enters this package.
- Keep storage deterministic: schema migrations, JSON serialization, and fingerprint normalization must be stable across runs.
- Concurrency behavior belongs in `storage.py` tests; do not hand-wave SQLite transaction semantics.
- `refinement.py` is generic over candidate type; non-string candidates require explicit serializers.
- Use temp DB paths in tests. Do not write durable `.cache/evolution.sqlite` state unless the command is explicitly operational.

## ANTI-PATTERNS

- Do not import this as an installed package entry point; `pyproject.toml` packages only `jclee_bot*`.
- Do not add live GitHub, CLIProxyAPI, or LLM calls here.
- Do not change fingerprint fields without migration/backfill thinking.
- Do not weaken duplicate/outcome guards to make concurrency tests pass.
