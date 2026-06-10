#!/usr/bin/env python3
"""Tests for the setup-build-cache composite action.

The self-hosted runner (LXC 101, Debian) has HOME unset and ephemeral build
caches on a small 32G rootfs. This action routes build caches (Go, pip, uv,
npm, Docker buildx) to an NFS-backed mount (/mnt/nas-cache) and gives HOME a
stable LOCAL path, only on self-hosted runners. On GitHub-hosted runners it is
a no-op so the existing actions/cache flow is unchanged.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / ".github/actions/setup-build-cache/action.yml"
DEPLOY = ROOT / "scripts/cmd/deploy-to-repos/main.go"


def _action() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def _self_hosted_run() -> str:
    """Concatenate the run: scripts of steps gated to self-hosted."""
    doc = _action()
    out = []
    for step in doc.get("runs", {}).get("steps", []):
        if "self-hosted" in str(step.get("if", "")):
            out.append(step.get("run", "") or "")
    return "\n".join(out)


def test_action_exists_and_is_composite() -> None:
    assert ACTION.exists(), f"missing composite action: {ACTION}"
    assert _action().get("runs", {}).get("using") == "composite"


def test_only_runs_on_self_hosted() -> None:
    """Every step that mutates the environment must be gated to self-hosted so
    GitHub-hosted runners keep their existing actions/cache behavior."""
    doc = _action()
    steps = doc.get("runs", {}).get("steps", [])
    assert steps, "action has no steps"
    for step in steps:
        assert "runner.environment == 'self-hosted'" in str(step.get("if", "")), (
            f"step {step.get('name')!r} is not gated to self-hosted"
        )


def test_routes_build_caches_to_nas() -> None:
    run = _self_hosted_run()
    for var in (
        "GOCACHE",
        "GOMODCACHE",
        "PIP_CACHE_DIR",
        "UV_CACHE_DIR",
        "npm_config_cache",
        "XDG_CACHE_HOME",
    ):
        assert var in run, f"{var} not exported by setup-build-cache"
    assert "/mnt/nas-cache" in run, "NAS mount path not referenced"


def test_exports_docker_buildx_cache() -> None:
    run = _self_hosted_run()
    assert "DOCKER_BUILDX_CACHE" in run, "Docker buildx cache var not exported"


def test_home_is_local_not_nas() -> None:
    """HOME must be a LOCAL path (RUNNER_TEMP), not the NAS mount, to avoid
    persisting credentials/git/ssh state and NFS locking issues."""
    run = _self_hosted_run()
    assert "HOME=" in run, "HOME not set (the unset-HOME bug must be fixed)"
    # HOME must resolve to a local path. Find the home dir definition line and
    # confirm it is rooted at RUNNER_TEMP (local), never the NAS mount.
    home_def = [
        ln for ln in run.splitlines()
        if "home_dir=" in ln.replace(" ", "")
    ]
    assert home_def, "no home_dir definition found"
    for ln in home_def:
        assert "/mnt/nas-cache" not in ln, f"HOME must not be on NAS: {ln.strip()}"
        assert "RUNNER_TEMP" in ln or "/tmp" in ln, (
            f"HOME dir must be local (RUNNER_TEMP): {ln.strip()}"
        )
    # And HOME must be exported from that local home_dir, not a NAS path.
    assert 'echo "HOME=$home_dir"' in run.replace("'", '"') or "HOME=$home_dir" in run, (
        "HOME must be exported from the local home_dir variable"
    )


def test_falls_back_when_nas_unavailable() -> None:
    """A missing/unwritable NAS mount must degrade to a local path, not hard-fail."""
    run = _self_hosted_run()
    assert "RUNNER_TEMP" in run, "no local fallback base referenced"
    # Writability check before committing to the NAS path.
    assert "-w" in run, "no writability test for the NAS mount"


def test_action_in_deploy_manifest() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert ".github/actions/setup-build-cache/action.yml" in deploy, (
        "setup-build-cache must be in extraFiles so downstream repos receive it"
    )
