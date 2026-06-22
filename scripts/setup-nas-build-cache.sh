#!/usr/bin/env bash
#
# setup-nas-build-cache.sh — provision NAS-backed build cache for the
# self-hosted GitHub Actions runner (Proxmox LXC).
#
# Idempotent. Run as root ON THE PROXMOX HOST (pve3) that owns the LXC.
#
# What it does:
#   1. Creates the CI cache tree on the NFS share already mounted at
#      /mnt/pve/shared (NFS <redacted-nas-ip>:/volume1/shared).
#   2. chowns it to the host-mapped UID/GID of the runner user inside the
#      unprivileged LXC (default 100000 + container-uid).
#   3. Bind-mounts that tree into the runner LXC at /mnt/nas-cache (mp0).
#   4. Verifies the runner can read/write the mount.
#
# Build caches (Go/pip/uv/npm/Docker buildx) then live on NAS via the
# .github/actions/setup-build-cache composite action. Docker data-root stays
# LOCAL (overlay2 on NFS is unsupported); only the buildx layer cache (exported
# via cache-to type=local) goes to NAS.
#
# Usage:
#   ./setup-nas-build-cache.sh [--ctid 101] [--mount /mnt/nas-cache] \
#       [--nas-cache-dir /mnt/pve/shared/ci-cache] [--uid 1000] [--apply]
#
# Without --apply it runs in DRY-RUN mode and only prints what it would do.

set -euo pipefail

CTID="101"
MOUNT_POINT="/mnt/nas-cache"
NAS_CACHE_DIR="/mnt/pve/shared/ci-cache"
RUNNER_UID="1000"          # container-side UID of the runner user
LXC_BASE_MAP="100000"      # default unprivileged LXC uid/gid base offset
APPLY="false"

while [ $# -gt 0 ]; do
  case "$1" in
    --ctid) CTID="$2"; shift 2 ;;
    --mount) MOUNT_POINT="$2"; shift 2 ;;
    --nas-cache-dir) NAS_CACHE_DIR="$2"; shift 2 ;;
    --uid) RUNNER_UID="$2"; shift 2 ;;
    --map-base) LXC_BASE_MAP="$2"; shift 2 ;;
    --apply) APPLY="true"; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

HOST_UID="$(( LXC_BASE_MAP + RUNNER_UID ))"
HOST_GID="$HOST_UID"

run() {
  if [ "$APPLY" = "true" ]; then
    echo "+ $*"
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

echo "=== NAS build cache setup ==="
echo "  LXC CTID:        $CTID"
echo "  NAS cache dir:   $NAS_CACHE_DIR (on host)"
echo "  LXC mount point: $MOUNT_POINT"
echo "  runner uid:      $RUNNER_UID (host-mapped $HOST_UID:$HOST_GID)"
echo "  mode:            $([ "$APPLY" = true ] && echo APPLY || echo DRY-RUN)"
echo

# 1. Verify the NFS share is mounted on the host.
if ! mountpoint -q "$(dirname "$NAS_CACHE_DIR")" 2>/dev/null && [ ! -d "$(dirname "$NAS_CACHE_DIR")" ]; then
  echo "::warning:: $(dirname "$NAS_CACHE_DIR") is not present; ensure the NFS storage 'shared' is mounted on this host."
fi

# 2. Create the cache tree.
for d in go-build go-mod pip uv npm xdg tmp docker-buildx docker-buildx-new home workspace; do
  run mkdir -p "$NAS_CACHE_DIR/$d"
done

# 3. Ownership: map to the runner's host-side UID/GID so the container process
#    can write. setgid bit keeps group ownership stable for shared writes.
run chown -R "$HOST_UID:$HOST_GID" "$NAS_CACHE_DIR"
run chmod -R u+rwX,g+rwX "$NAS_CACHE_DIR"
run find "$NAS_CACHE_DIR" -type d -exec chmod 2775 {} +

# 4. Add the bind mount to the LXC if not already present.
if pct config "$CTID" 2>/dev/null | grep -qE "^mp[0-9]+: .*${MOUNT_POINT}\b"; then
  echo "mount point for $MOUNT_POINT already configured on CT $CTID"
else
  # Find the next free mpN slot.
  next_mp=0
  while pct config "$CTID" 2>/dev/null | grep -qE "^mp${next_mp}:"; do
    next_mp=$(( next_mp + 1 ))
  done
  run pct set "$CTID" \
    "-mp${next_mp}" "${NAS_CACHE_DIR},mp=${MOUNT_POINT},backup=0"
  echo "NOTE: reboot the container to apply the mount: pct reboot $CTID"
fi

# 5. Verify writability from inside the container (best-effort; needs CT running).
if [ "$APPLY" = "true" ]; then
  if pct status "$CTID" 2>/dev/null | grep -q running; then
    echo "verifying write access inside CT $CTID ..."
    pct exec "$CTID" -- sh -lc \
      "mkdir -p '$MOUNT_POINT' 2>/dev/null; touch '$MOUNT_POINT/.write-test' && rm -f '$MOUNT_POINT/.write-test' && echo OK: $MOUNT_POINT writable" \
      || echo "::warning:: could not verify write access (reboot the CT if the mount was just added)"
  fi
fi

echo
echo "Done. After 'pct reboot $CTID', the runner workflows that use the"
echo ".github/actions/setup-build-cache action will route caches to $MOUNT_POINT."
