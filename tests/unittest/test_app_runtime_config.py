from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_app_image_writes_health_build_number() -> None:
    text = (REPO_ROOT / "Dockerfile.github_app").read_text(encoding="utf-8")

    assert "ARG APP_VERSION=" in text
    assert "printf '%s\\n' \"${APP_VERSION}\" > jclee_bot/review_engine/build_number.txt" in text
    assert 'APP_VERSION="${APP_VERSION}"' in text
    assert 'GIT_SHA="${VCS_REF}"' in text


def test_build_workflow_passes_git_sha_to_app_image() -> None:
    text = (
        REPO_ROOT / ".github" / "workflows" / "36_build-and-push-app.yml"
    ).read_text(encoding="utf-8")

    assert "build-args:" in text
    assert "APP_VERSION=${{ github.sha }}" in text
    assert "VCS_REF=${{ github.sha }}" in text
    assert "- 'scripts/**'" in text


def test_compose_exposes_cliproxy_runtime_routing_env() -> None:
    text = (REPO_ROOT / "docker-compose.github_app.yml").read_text(encoding="utf-8")

    for required in [
        "CLIPROXY_API_KEY:",
        "OPENAI_BASE_URL: http://cliproxyapi:8317/v1",
        "CLIPROXY_MANAGEMENT_URL:",
        "CLIPROXY_MANAGEMENT_KEY:",
        "CLIPROXY_DYNAMIC_ROUTING:",
        "CLIPROXY_ROUTE_FAILURE_THRESHOLD:",
        "CLIPROXY_ROUTE_FAILURE_RATIO:",
        "CLIPROXY_ROUTE_RECENT_SUCCESS_LIMIT:",
    ]:
        assert required in text
