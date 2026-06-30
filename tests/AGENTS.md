# tests - verification surface

## OVERVIEW

Repo tests split into Python unit tests, mocked FastAPI/webhook e2e tests, and live GitHub e2e tests. The live suite has stricter local rules in `tests/e2e_live/AGENTS.md`; read that file before running or editing live tests.

## STRUCTURE

```text
tests/
├── unittest/     # large mocked Python suite; has its own AGENTS.md
├── e2e/          # mocked FastAPI/webhook health tests
└── e2e_live/     # real GitHub API tests; has its own AGENTS.md
```

## COMMANDS

```bash
make test-unit
make test-e2e
make test-live
make test

pytest tests/e2e_live -m readonly -v
pytest tests/e2e_live -m "private_canary or security_review" -v
```

## CONVENTIONS

- Pytest configuration lives in `pyproject.toml`; keep markers declared there when adding live-test categories.
- Unit tests belong in `tests/unittest/` and should mock GitHub, CLIProxyAPI, filesystem mutation, and subprocess calls unless the behavior is explicitly meant to be live.
- `tests/unittest/AGENTS.md` owns denser rules for the mixed App/review-engine/evolution unit surface.
- Mocked e2e tests in `tests/e2e/` should exercise the FastAPI/webhook surface without using real GitHub tokens.
- Prefer focused tests near the changed behavior: App checks in `test_jclee_bot_checks.py`, App routes in `test_jclee_bot_app*.py`, README automation in `test_jclee_bot_readme_*` and `test_generate_readme_*`.
- Go CLI tests live beside the Go commands under `scripts/cmd/**`; run them with `(cd scripts && go test ./...)`.

## ANTI-PATTERNS

- Do not add production GitHub mutations outside `tests/e2e_live/`.
- Do not bypass `guard_mutation()` for any helper that creates branches, writes files, opens PRs, edits labels, or deletes remote state.
- Do not make `make test-unit` depend on live credentials or external network availability.
