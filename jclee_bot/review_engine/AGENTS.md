# pr_agent — PROJECT KNOWLEDGE BASE

## OVERVIEW

Upstream qodo-ai/pr-agent code. AI-powered PR review engine. Hard fork; no local modifications except `settings/configuration.toml` model line.

## STRUCTURE

```text
pr_agent/
├── agent/              # command orchestration (/review, /improve, /describe)
├── algo/               # AI handlers (litellm, openai)
├── tools/              # individual capabilities (PRReviewer, PRDescription, ...)
├── git_providers/      # github.py, gitlab.py, bitbucket.py
├── servers/
│   ├── github_app.py           # GitHub App entry point
│   └── github_action_runner.py # GitHub Actions entry point
├── settings/
│   ├── configuration.toml      # FORK: model line only
│   ├── pr_reviewer_prompts.toml
│   └── ...                     # other prompt templates
└── cli.py              # local CLI entry point
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Change default model | `settings/configuration.toml` `[config].model` |
| Override per-repo | `.pr_agent.toml` (repo root) |
| Edit review prompts | `settings/pr_reviewer_prompts.toml` |
| Add git provider | `git_providers/` |
| GitHub App server | `servers/github_app.py` |
| GitHub Actions runner | `servers/github_action_runner.py` |
| Local CLI | `cli.py` |

## CONVENTIONS

- Python >= 3.12
- This is upstream code — do not modify. Fork changes go in `.pr_agent.toml` or `.github/workflows/`.

## ANTI-PATTERNS

- Never edit `configuration.toml` beyond the model line — conflicts with upstream merges
- Never delete or rename prompt TOML files
- Never commit `.secrets.toml` or API keys inside this directory
- Never rewrite `algo/` or `tools/` — use `.pr_agent.toml` for config overrides
