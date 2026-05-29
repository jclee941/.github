"""Monitoring and observability for the GitHub App.

Provides Prometheus metrics, health checks, and ELK-ready log enrichment.
"""

import time
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from pr_agent.config_loader import get_settings

# Build number for health endpoint
_build_number_path = Path(__file__).parent.parent / "build_number.txt"
build_number = _build_number_path.read_text().strip() if _build_number_path.exists() else "unknown"

monitoring_router = APIRouter()

# Prometheus metrics
WEBHOOK_REQUESTS_TOTAL = Counter(
    "webhook_requests_total",
    "Total number of webhook requests received",
    ["event", "action"],
)
WEBHOOK_DURATION_SECONDS = Histogram(
    "webhook_duration_seconds",
    "Time spent processing webhook requests",
    ["event"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
REVIEW_REQUESTS_TOTAL = Counter(
    "review_requests_total",
    "Total number of review commands executed",
    ["command"],
)
REVIEW_DURATION_SECONDS = Histogram(
    "review_duration_seconds",
    "Time spent executing review commands",
    ["command"],
    buckets=[1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)
LLM_FAILURES_TOTAL = Counter(
    "llm_failures_total",
    "Total number of LLM call failures categorized by reason",
    ["reason", "model"],
)
WEBHOOK_FAILURES_TOTAL = Counter(
    "webhook_failures_total",
    "Total number of webhook handler failures (exceptions in handle_request)",
    ["event", "action", "exception_type"],
)


def record_llm_failure(reason: str, model: str) -> None:
    """Record an LLM call failure.

    reason: one of 'rate_limit', 'timeout', 'connect', 'api_error', 'schema_mismatch', 'provider_fallback', 'unknown'
    model: the model name (e.g. 'kimi-k2.6')
    """
    LLM_FAILURES_TOTAL.labels(
        reason=reason or "unknown",
        model=model or "unknown",
    ).inc()


def record_webhook_start(event: str, action: str) -> float:
    """Record the start of a webhook request. Returns the start time."""
    WEBHOOK_REQUESTS_TOTAL.labels(event=event or "unknown", action=action).inc()
    return time.time()


def record_webhook_end(event: str, start_time: float) -> None:
    """Record the end of a webhook request."""
    WEBHOOK_DURATION_SECONDS.labels(event=event or "unknown").observe(time.time() - start_time)


def record_review_start(command: str) -> float:
    """Record the start of a review command. Returns the start time."""
    REVIEW_REQUESTS_TOTAL.labels(command=command).inc()
    return time.time()


def record_review_end(command: str, start_time: float) -> None:
    """Record the end of a review command."""
    REVIEW_DURATION_SECONDS.labels(command=command).observe(time.time() - start_time)


def record_webhook_failure(event: str, action: str, exception_type: str) -> None:
    """Record a webhook handler failure with the exception class name."""
    WEBHOOK_FAILURES_TOTAL.labels(
        event=event or "unknown",
        action=action or "unknown",
        exception_type=exception_type or "unknown",
    ).inc()


@monitoring_router.get("/health")
async def health_check():
    """
    Health check endpoint for Docker and load balancers.
    Returns detailed health status including LLM API connectivity.
    """
    health = {
        "status": "healthy",
        "version": build_number,
        "checks": {
            "app": {"status": "pass"},
        },
    }

    # Check LLM API connectivity (lightweight)
    try:
        api_base = get_settings().get("OPENAI.API_BASE", "")
        if api_base:
            # Quick connectivity check without auth
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try /v1/models endpoint (OpenAI-compatible)
                models_url = api_base.rstrip("/") + "/models"
                response = await client.get(models_url)
                if response.status_code in (200, 401):
                    health["checks"]["llm_api"] = {"status": "pass"}
                else:
                    health["checks"]["llm_api"] = {
                        "status": "warn",
                        "detail": f"Unexpected status: {response.status_code}",
                    }
        else:
            health["checks"]["llm_api"] = {"status": "warn", "detail": "API base not configured"}
    except Exception as e:
        health["checks"]["llm_api"] = {"status": "fail", "detail": str(e)}
        health["status"] = "degraded"

    return health


@monitoring_router.get("/ready")
async def readiness_check():
    """
    Readiness probe for Kubernetes or orchestrators.
    Returns 200 when the app is ready to accept traffic.
    """
    return {"status": "ready"}


@monitoring_router.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    Exposes webhook and review metrics for scraping.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
