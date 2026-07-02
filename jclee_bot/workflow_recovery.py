from __future__ import annotations

RECOVERY_TITLE_MAP = (
    ("ELK Health Check", ("ELK Health Check Failed",)),
    ("ELK Setup", ("ELK Setup Failed",)),
    (
        "Runtime Health Check",
        (
            "Bot webhook endpoint unreachable",
            "CLIProxyAPI unreachable",
            "jclee-bot not responding",
            "Runtime Health Check failed",
        ),
    ),
    ("Downstream Health Check", ("Downstream workflow failures detected", "Downstream Health Check failed")),
    ("Bot Health Monitor", ("bot-health", "Bot Health Monitor failed")),
)


def short_sha(sha: str) -> str:
    return sha[:8] if len(sha) >= 8 else sha


def recovered_ci_failure_title(*, workflow_name: str, head_sha: str) -> str:
    return f"[ci] {workflow_name} failed at {short_sha(head_sha)}"
