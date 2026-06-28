# docs - architecture and policy documentation

## OVERVIEW

Project documentation for the App-centered automation model, GitOps validation, defork provenance, review templates, operational history, and README-generation policy. These files are user-facing and are often checked by docs-policy and README inventory validators.

## STRUCTURE

```text
docs/
├── architecture.md                 # App/checks/GitOps architecture diagrams
├── defork-provenance.md            # qodo-ai/pr-agent attribution and de-fork notes
├── git-workflow-gap-analysis.md    # Git workflow and required-check analysis
├── gitops-validation-brainstorm.md # GitOps validation notes
├── nas-build-cache.md              # NAS/self-hosted cache notes
├── review-templates/               # Korean-first review output templates
└── assets/                         # checked-in documentation images
```

## CONVENTIONS

- Keep architecture docs aligned with the App-centered operating model: Checks API, review, issue maintenance, README automation, and CI-failure cleanup are owned by `jclee_bot`.
- Branch-protection-required contexts are `jclee-bot / pr-metadata`, `jclee-bot / secret-scan`, and `jclee-bot / actionlint`; `jclee-bot / docs-policy` is an App Check Run but not required by branch protection.
- Use sanitized placeholders such as `<homelab-host>` and `<homelab-elk>` instead of private IPs, LXC IDs, or internal hostnames.
- Review templates should preserve Korean-first output unless a specific downstream policy says otherwise.
- When workflow inventories or README claims change, run `(cd scripts && go run ./cmd/validate-naming)`.

## ANTI-PATTERNS

- Do not add invented external repository links. Historical upstream references should point to `qodo-ai/pr-agent` only when documenting provenance.
- Do not describe retired per-repo workflow deployment as the production rollout path.
- Do not duplicate generated README workflow tables by hand; the current README intentionally presents the App automation surface instead.
