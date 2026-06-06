"""CLIProxyAPI health check — verify the service is reachable and the default model is available."""
from __future__ import annotations

import pytest
import requests

CLIPROXY_BASE_URL = "https://cliproxy.jclee.me/v1"
DEFAULT_MODEL = "gpt-5.5"

pytestmark = pytest.mark.cliproxy_health


def test_cliproxy_health(cliproxy_api_key: str) -> None:
    """Verify CLIProxyAPI /v1/models returns HTTP 200 and lists the default model."""
    response = requests.get(
        f"{CLIPROXY_BASE_URL}/models",
        headers={"Authorization": f"Bearer {cliproxy_api_key}"},
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    model_ids = [item["id"] for item in payload.get("data", [])]
    assert DEFAULT_MODEL in model_ids, (
        f"Expected '{DEFAULT_MODEL}' in model list, got: {model_ids}"
    )
