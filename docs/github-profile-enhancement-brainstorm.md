# GitHub Profile Enhancement Notes

> Status: current planning note. This document covers profile and community-file ideas only; it is not a fleet rollout design.

## Scope

Profile work is separate from the `jclee-bot` App automation path. Use it for:

- the `jclee941/jclee941` profile README;
- account bio, blog, location, and social fields;
- root community-health files in this repository;
- optional repository metadata after owner-approved descriptions and topics exist.

Do not copy the managed repository inventory into this document. Use `config/repos.yaml` whenever tooling needs the current repo set.

## Recommended Profile README Shape

Use a static, reviewable README as the base. Automated updates can later fill a narrow activity section, but the identity and project descriptions should stay deterministic.

Suggested sections:

- Korean introduction and one-line professional summary;
- infrastructure, security, automation, web, and ML focus areas;
- selected repositories derived from approved metadata;
- current contact and portfolio link;
- optional GitHub stats widgets only if their external dependency is acceptable.

## Community Files

Root-level community files in this repository can be inherited by repositories that do not define their own versions. Favor inheritance over copying the same file into every repository.

Candidates:

| File | Status |
| --- | --- |
| `SECURITY.md` | Add only after the private reporting channel is confirmed. |
| `CODE_OF_CONDUCT.md` | Add if public contribution expectations are needed. |
| `FUNDING.yml` | Add only when a real funding account exists. |

## Repository Metadata

Repository descriptions, topics, and homepage URLs are public signals. Do not infer them aggressively from partial code history.

Safe path:

1. Add optional metadata fields to `config/repos.yaml`.
2. Review values manually.
3. Add a dry-run-only metadata checker.
4. Move to apply mode only after the checker has produced stable output.

## Decisions Still Needed

- Profile README language balance: Korean-only or bilingual.
- Public contact channel for security and collaboration.
- Which repositories should expose homepage URLs.
- Whether repository topics should be continuously enforced or applied once.
