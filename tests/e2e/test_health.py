"""E2E tests for monitoring and health endpoints."""


def test_health_endpoint(test_client):
    """Test the /health endpoint returns healthy status."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "version" in data
    assert "checks" in data
    assert data["checks"]["app"]["status"] == "pass"


def test_ready_endpoint(test_client):
    """Test the /ready endpoint returns ready status."""
    response = test_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"


def test_metrics_endpoint(test_client):
    """Test the /metrics endpoint returns Prometheus metrics."""
    response = test_client.get("/metrics")
    assert response.status_code == 200
    content = response.text
    assert "webhook_requests_total" in content
    assert "webhook_duration_seconds" in content
    assert "review_requests_total" in content
    assert "review_duration_seconds" in content


def test_root_endpoint(test_client):
    """Test the root / endpoint."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
