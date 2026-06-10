# NAS-Backed Build Cache for the Self-Hosted Runner

The private `propose` repo runs CI on a self-hosted GitHub Actions runner —
Proxmox **LXC 101** (`runner`, Debian) on node `pve3`. That runner had two
problems:

- `HOME` is unset in workflow shells, so `go env`, `python3 -m venv`, and
  `~/.cache` paths broke.
- Build caches (Go, pip, uv, npm, Docker buildx) lived on the small **32 GB**
  LXC rootfs and were ephemeral per run, causing slow builds and disk pressure.

This setup routes those caches to the homelab **NAS over NFS** and gives `HOME`
a stable local path.

## Architecture

```
Synology NAS (NFS)  192.168.50.215:/volume1/shared
        │  (Proxmox storage "shared", vers=3)
        ▼
Proxmox host pve3   /mnt/pve/shared/ci-cache
        │  (LXC bind mount, mp0, root@pam only)
        ▼
Runner LXC 101      /mnt/nas-cache
        │  (composite action exports cache env vars)
        ▼
GitHub Actions      GOCACHE / GOMODCACHE / PIP_CACHE_DIR / UV_CACHE_DIR /
                    npm_config_cache / XDG_CACHE_HOME / DOCKER_BUILDX_CACHE
```

Key decisions:

- **Caches → NAS; `HOME` → local.** `HOME` is set to `$RUNNER_TEMP/gha-home`
  (local), never the NAS, to avoid persisting credentials / git / ssh state and
  NFS lock contention. Only deterministic build caches go to NAS.
- **Docker `data-root` stays local.** OverlayFS/overlay2 on NFS is unsupported.
  Only the buildx **build cache** (`cache-to type=local`) is exported to NAS.
- **Per-runner/per-repo namespacing.** Cache root is
  `/mnt/nas-cache/<runner>/<owner_repo>/...` so concurrent or cross-repo runs do
  not corrupt each other's caches.
- **Graceful degradation.** If `/mnt/nas-cache` is missing or unwritable, the
  composite action falls back to `$RUNNER_TEMP` and emits a warning instead of
  hard-failing.
- **GitHub-hosted runners are untouched.** The composite action is a no-op on
  `runner.environment != 'self-hosted'`, so public repos keep `actions/cache`.

## One-time host setup (run as root on pve3)

Bind mounts require `root@pam`, so this step is performed on the Proxmox host,
not via the API token. Use the bundled idempotent script:

```bash
# On pve3 as root:
cd /path/to/.github
./scripts/setup-nas-build-cache.sh --ctid 101            # dry-run preview
./scripts/setup-nas-build-cache.sh --ctid 101 --apply    # apply
pct reboot 101                                            # activate the mount
```

The script:

1. Creates `/mnt/pve/shared/ci-cache/{go-build,go-mod,pip,uv,npm,xdg,tmp,docker-buildx,docker-buildx-new,home,workspace}`.
2. `chown`s the tree to the host-mapped runner UID/GID (default `100000 + 1000 = 101000`; override with `--uid` if the runner user is not UID 1000).
3. Adds the LXC bind mount `mp0: /mnt/pve/shared/ci-cache,mp=/mnt/nas-cache,backup=0`.
4. Verifies the runner can write to `/mnt/nas-cache`.

If the Synology NFS export squashes writes, grant the numeric host-mapped
UID/GID write access on `/volume1/shared/ci-cache` (do **not** enable
`no_root_squash` on the whole export).

## Repo wiring (already in this repo)

- `.github/actions/setup-build-cache/action.yml` — exports the cache env vars
  on self-hosted runners (no-op on GitHub-hosted). Deployed downstream via the
  `deploy-to-repos` manifest.
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
# Inside LXC 101:
mount | grep /mnt/nas-cache
ls -la /mnt/nas-cache/*/                 # per-runner/per-repo cache dirs
du -sh /mnt/nas-cache                     # cache size

# In a workflow log, the "Set up build cache" step prints:
#   build cache: using NAS mount /mnt/nas-cache
#   build cache root: /mnt/nas-cache/<runner>/<repo> (HOME=/.../gha-home)
```

For the Docker build, confirm `cache-from`/`cache-to` reference
`/mnt/nas-cache/.../docker-buildx` in the `36_build-and-push-app.yml` run log,
and that `du -sh /mnt/nas-cache/.../docker-buildx` grows after the first build.
