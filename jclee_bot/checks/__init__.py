"""App-owned static checks reported via the GitHub Checks API.

Each check is a pure function ``run(...) -> CheckResult`` so it is trivially
unit-testable without network or a GitHub installation token. The webhook
wrapper (``jclee_bot.app``) collects the changed-file/diff context and maps each
CheckResult onto a GitHub Check Run.
"""
from __future__ import annotations

from dataclasses import dataclass

VALID_CONCLUSIONS = frozenset({"success", "failure", "neutral"})


@dataclass(frozen=True)
class CheckResult:
    """Result of a single App-owned check, mapped to a GitHub Check Run."""

    name: str
    conclusion: str
    title: str
    summary: str

    def __post_init__(self) -> None:
        if self.conclusion not in VALID_CONCLUSIONS:
            raise ValueError(
                f"conclusion must be one of {sorted(VALID_CONCLUSIONS)}, got {self.conclusion!r}"
            )


from jclee_bot.checks import (  # noqa: E402  (re-export for convenience)
    actionlint_check,
    docs_policy,
    pr_metadata,
    secret_scan,
)

__all__ = [
    "CheckResult",
    "VALID_CONCLUSIONS",
    "actionlint_check",
    "docs_policy",
    "pr_metadata",
    "secret_scan",
]
