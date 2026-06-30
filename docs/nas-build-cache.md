# NAS-Backed Build Cache for the Self-Hosted Runner

> **NOTE: partially historical** — the build cache + HOME-routing design still works for the self-hosted runner. The old per-repository file rollout references are obsolete; production automation now centers on the `jclee-bot` GitHub App and App image.

The private `propose` repo runs CI on a self-hosted GitHub Actions runner in a
homelab container. That runner had two
problems:

- `HOME` is unset in workflow shells, so `go env`, `python3 -m venv`, and
  `~/.cache` paths broke.
- Build caches (Go, pip, uv, npm, Docker buildx) lived on a small local root
  filesystem and were ephemeral per run, causing slow builds and disk pressure.

This setup routes those caches to the homelab **NAS over NFS** and gives `HOME`
a stable local path.

## Architecture

![NAS-backed build cache architecture](assets/nas-build-cache-architecture.svg)

Key decisions:

- **Caches → NAS; `HOME` → local.** `HOME` is set to `$RUNNER_TEMP/gha-home`
  (local), never the NAS, to avoid persisting credentials / git / ssh state and
  NFS lock contention. Only deterministic build caches go to NAS.
- **Docker `data-root` stays local.** OverlayFS/overlay2 on NFS is unsupported.
  Only the buildx **build cache** (`cache-to type=local`) is exported to NAS.
- **Per-runner/per-repo namespacing.** Cache root is
  `<runner-cache-path>/<runner>/<owner_repo>/...` so concurrent or cross-repo
  runs do not corrupt each other's caches.
- **Graceful degradation.** If the shared cache path is missing or unwritable, the
  composite action falls back to `$RUNNER_TEMP` and emits a warning instead of
  hard-failing.
- **GitHub-hosted runners are untouched.** The composite action is a no-op on
  `runner.environment != 'self-hosted'`, so public repos keep `actions/cache`.

## One-time Host Setup

The mount is configured on the virtualization host, not through a workflow
token. Use the bundled idempotent script:

```bash
cd /path/to/.github
./scripts/setup-nas-build-cache.sh --ctid <runner-ctid>
./scripts/setup-nas-build-cache.sh --ctid <runner-ctid> --apply
pct reboot <runner-ctid>
```

The script:

1. Creates `<host-cache-path>/{go-build,go-mod,pip,uv,npm,xdg,tmp,docker-buildx,docker-buildx-new,home,workspace}`.
2. `chown`s the tree to the host-mapped runner UID/GID; override with `--uid` if the runner user is not UID 1000.
3. Adds a restricted cache mount from `<host-cache-path>` to `<runner-cache-path>`.
4. Verifies the runner can write to `<runner-cache-path>`.

If the shared storage export squashes writes, grant the numeric host-mapped
UID/GID write access on the cache export. Do **not** enable root write
passthrough on the whole export.

## Repo wiring (already in this repo)

- `.github/actions/setup-build-cache/action.yml` — exports the cache env vars
  on self-hosted runners (no-op on GitHub-hosted). Keep this action in this
  repository as the source implementation.
- Wired as the first step after checkout in `10_pr-review.yml`,
  `11_security-pr-review.yml`, `14_bot-auto-fix.yml`, and
  `36_build-and-push-app.yml`.
- `36_build-and-push-app.yml` uses `docker/setup-buildx-action`
  (`driver: docker-container`) with `cache-from/cache-to: type=local` pointing
  at `$DOCKER_BUILDX_CACHE`, plus a cache-rotation step.
- `46_nas-cache-prune.yml` ages out stale cache (default 30 days) on build
  completion and on manual dispatch.

## Verification

After the host mount is applied and a workflow runs on the self-hosted runner:

```bash
mount | grep '<runner-cache-path>'
ls -la <runner-cache-path>/*/
du -sh <runner-cache-path>

# In a workflow log, the "Set up build cache" step prints:
#   build cache: using shared cache mount <runner-cache-path>
#   build cache root: <runner-cache-path>/<runner>/<repo> (HOME=/.../gha-home)
```

For the Docker build, confirm `cache-from`/`cache-to` reference
`<runner-cache-path>/.../docker-buildx` in the `36_build-and-push-app.yml` run
log, and that `du -sh <runner-cache-path>/.../docker-buildx` grows after the
first build.
