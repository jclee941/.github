# De-fork Provenance

This repository was originally a hard fork of [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent).
As of this record, the `upstream` git remote and its tracking refs were removed; the AI review
engine was absorbed into the first-party `jclee_bot.review_engine` package. This file preserves
the upstream provenance for license/attribution purposes (see also `NOTICE`).

## Fork point

- Initial fork commit: `d82f7d3e` (2026-04-10)
  - <https://github.com/qodo-ai/pr-agent/commit/d82f7d3e>

## Last observed upstream state at de-fork

- `upstream` remote: `https://github.com/qodo-ai/pr-agent.git`
- `upstream/main` HEAD: `43de5e0ddd58132e234ba3123d020d2501477656`
  - `2026-05-31` — "Merge pull request #2415 from The-PR-Agent/of/a2a-mosaico-fixes"

## What changed

- Removed git remote `upstream` and pruned its tracking refs.
- Relocated the former `pr_agent/` package to `jclee_bot/review_engine/` (topology preserved).
- The project is no longer maintained as a fork; upstream sync is out of scope.

Attribution and the AGPL-3.0 license obligations remain unchanged — see `LICENSE` and `NOTICE`.
