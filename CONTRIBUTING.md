# Contributing

`jclee941/.github` is the source of truth for the standard automation that runs across all `jclee941/*` public repositories. The jclee-bot GitHub App (see `jclee_bot/` Python package) handles PR/CI checks centrally via the Checks API for every managed repo.

## Scope

This repo accepts changes to:

- `.github/workflows/**` — workflow files in this source repo
- `.github/dependabot.yml` — Dependabot config synced downstream
- `.github/CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/**` — community files synced downstream via `extraFiles`
- `scripts/*.go` — deploy / branch-protection / secret-sync tooling
- `pr_agent/**` — fork-specific overrides on top of upstream `qodo-ai/pr-agent` (see `AGENTS.md` for what is/isn't safe to touch)
- `docs/**` — design notes, gap analyses, review templates

It does **not** accept contributions that re-implement private business logic, leak secrets, or override upstream `pr-agent` files outside the documented exception list (`pr_agent/settings/configuration.toml` cli_proxy block only).

## Pull request workflow

1. **Branch naming**: use a Conventional-Commits-aligned prefix.
   - `feat/<scope>` — new functionality
   - `fix/<scope>` — bug fix
   - `docs/<scope>` — docs only
   - `refactor/<scope>`, `chore/<scope>`, `test/<scope>` — as appropriate
   - Allowed alternates enforced by `jclee-bot / pr-metadata`: `feat/`, `fix/`, `docs/`, `refactor/`, `chore/`, `test/` (plus the alternates `dependabot/`, `fork/`, `release/`)
2. **PR title**: must follow Conventional Commits — `<type>(<scope>): <subject>`. Examples:
   - `fix(pr-review): unblock LLM review for downstream repos`
   - `docs(rollout): clarify Phase 3 ordering`
3. **PR description**: minimum 10 characters and must explain the *why*, not just the *what*. The PR template scaffolds this.
4. **Required status checks** (enforced via branch protection):
   - `jclee-bot / pr-metadata`
   - `jclee-bot / secret-scan`
   Advisory checks (do NOT block merge): the AI review, the actionlint context, repo health.
5. **Auto-merge**: enabled at the repo level. Patch / minor / `github_actions` Dependabot PRs auto-merge after required checks pass; majors require manual review.

## Local development

```bash
# Repo prerequisites
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Run the unit test gate that pre-commit / sanity uses
PYTHONPATH=. pytest tests/unittest -v

# YAML / actionlint / gitleaks (optional but recommended)
python3 -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/**/*.yml',recursive=True)]"
actionlint .github/workflows/*.yml
gitleaks detect --redact

# Build all Go scripts
for f in scripts/*.go; do go build -o /tmp/check-$(basename "$f" .go) "$f"; done

# Branch protection (dry-run)
(cd scripts && go run ./cmd/branch-protection) --dry-run
```

## Commit conventions

- **Conventional Commits required**: `type(scope): subject`. Body explains why; footer references issues / PRs.
- **Fork-specific commits**: tag with `fork:` scope when the change is a fork override (e.g. `feat(fork): pin model to kimi-k2.6`).
- **Upstream sync commits**: use `chore(upstream): merge qodo-ai/pr-agent@<sha>`.
- Keep commits atomic. One logical change per commit.

## Secrets & sensitive data

- Never commit `.env`, `.secrets.toml`, `pr_agent/settings/.secrets.toml`, or anything under `.cache/`. They are gitignored.
- Never paste API keys, tokens, or PII into PR descriptions, issue bodies, or commit messages.
- The `jclee-bot / secret-scan` check (gitleaks run inside the App image) blocks merges that introduce real-looking secrets. False positives can be allowlisted in `.gitleaksignore` (commit-pinned fingerprint format).
- For active vulnerabilities, open a **private** security advisory:
  <https://github.com/jclee941/.github/security/advisories/new>

## Documentation expectations

When you change behavior, also update:

- `README.md` — high-level user-facing description
- `AGENTS.md` — internal knowledge base; mandatory for changes that affect:
  - workflow behavior
  - downstream repo automation guarantees
  - pr-agent fork delta
  - cli_proxy integration
- `docs/git-workflow-gap-analysis.md` — extend/update only if you are closing or reopening a gap (do not silently mutate the as-was/as-is delta).

## Rolling out workflow changes

In the App era there is no per-repo file deploy. The jclee-bot GitHub App posts Checks API runs (`jclee-bot / pr-metadata`, `jclee-bot / secret-scan`, `jclee-bot / actionlint`) to every managed repo on every PR; the runtime image is rebuilt by `36_build-and-push-app.yml` whenever this repo's `master` changes, so a merge here is the only rollout step.

For new required checks, follow the **2-phase rollout**:

1. Merge the source change → the new check is reported as advisory on the next PR
2. After confirming the new check is green on every downstream repo, re-run `(cd scripts && go run ./cmd/branch-protection)` to register the new context as required

Skipping Phase 1 will deadlock auto-merge across all 15 managed repos.

## Code of conduct

Be technically honest. Cite evidence. Do not flatter or hand-wave. Disagreement on technical merit is welcome; ad-hominem is not.

## License

By contributing you agree that your contribution is licensed under the project's [AGPL-3.0](LICENSE), inherited from the upstream `qodo-ai/pr-agent` fork.
