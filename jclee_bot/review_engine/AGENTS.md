# jclee_bot.review_engine - PROJECT KNOWLEDGE BASE

## OVERVIEW

AI-powered PR review engine, originally derived from `qodo-ai/pr-agent` and
absorbed into the first-party `jclee_bot/review_engine/` package. It is now a
project-owned codebase: edits are allowed and expected, but changes to the
deep modules (`algo/`, `tools/`, `git_providers/`) should be deliberate because
the package still ships the original code shape.

Attribution to the original project is preserved in `NOTICE` and
`docs/defork-provenance.md`.

## STRUCTURE

```text
jclee_bot/review_engine/
├── agent/             # command orchestration (/review, /improve, /describe)
├── algo/              # AI handlers (litellm, openai) - legacy code shape
├── tools/             # individual capabilities (PRReviewer, PRDescription, ...) - legacy code shape
├── git_providers/     # github.py, gitlab.py, bitbucket.py, ...
├── servers/
│   ├── github_app.py           # GitHub App entry point
│   └── github_action_runner.py # GitHub Actions entry point
├── identity_providers/         # OIDC / SSO helpers (added in-tree)
├── secret_providers/           # aws_secrets_manager, gcs, base interface
├── log/                        # structured-log helpers
├── settings/
│   ├── configuration.toml      # engine-wide defaults (model, fallback)
│   ├── pr_reviewer_prompts.toml
│   └── ...                     # other prompt templates
└── cli.py             # local CLI entry point (installed as the `pr-agent` console script)
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Installed console scripts | `pyproject.toml` maps `jclee-bot`, `github-bot`, and `pr-agent` to `cli.py` |
| Change default model | `settings/configuration.toml` `[config].model` |
| Override per-repo | `.pr_agent.toml` (repo root) |
| Edit review prompts | `settings/pr_reviewer_prompts.toml` |
| Add git provider | `git_providers/` |
| GitHub App server | `servers/github_app.py` |
| GitHub Actions runner | `servers/github_action_runner.py` |
| Local CLI | `cli.py` |

## CONVENTIONS

- Python >= 3.12.
- This is first-party project code; modify it directly when behavior needs to
  change. Prefer narrow, well-tested edits over large rewrites of the legacy
  `algo/` and `tools/` modules.
- Per-repo overrides go in `.pr_agent.toml`; engine-wide defaults and prompt
  packs go in `settings/`.
- `github_action_runner.py` is the GitHub Actions runtime entry point; keep its
  environment-variable contract aligned with `.github/workflows/10_pr-review.yml`
  and `.github/workflows/11_security-pr-review.yml`.
- Review output is Korean-first unless a prompt/config override intentionally
  changes `CONFIG.RESPONSE_LANGUAGE`.

## ANTI-PATTERNS

- Do not delete or rename prompt TOML files without a deliberate migration plan
  (downstream `.pr_agent.toml` files may reference them).
- Do not commit `.secrets.toml` or API keys inside this directory.
- Do not re-introduce an external "upstream" remote or re-create the `pr_agent/`
  package layout; the project is now standalone and the review engine is
  in-tree.
- Do not import the App integration layer from this package. `jclee_bot.app`
  wraps the review engine; the review engine should stay reusable by CLI,
  GitHub Action, and server entry points.
