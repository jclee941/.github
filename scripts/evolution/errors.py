"""Domain exceptions for the evolution package."""

from __future__ import annotations


class EvolutionError(Exception):
    """Base class for all evolution-package errors."""


class ValidationError(EvolutionError):
    """Raised when input data fails domain validation."""


class FingerprintCollisionError(EvolutionError):
    """Raised when two distinct findings share a short fingerprint.

    The short (16-hex) fingerprint matches upstream pr-agent markers, so a
    collision means the same ``(repo, fingerprint)`` row maps to a different
    full (64-hex) digest. We refuse to merge distinct findings.
    """

    def __init__(self, repo: str, fingerprint: str) -> None:
        self.repo = repo
        self.fingerprint = fingerprint
        super().__init__(
            f"fingerprint collision for repo={repo!r} fingerprint={fingerprint!r}: "
            "short fingerprint matches an existing finding with a different full digest"
        )


class DuplicateOutcomeError(EvolutionError):
    """Raised when a suggestion outcome is recorded twice with a conflicting result."""

    def __init__(self, repo: str, suggestion_id: str, existing: str, attempted: str) -> None:
        self.repo = repo
        self.suggestion_id = suggestion_id
        self.existing = existing
        self.attempted = attempted
        super().__init__(
            f"conflicting outcome for repo={repo!r} suggestion_id={suggestion_id!r}: "
            f"already recorded {existing!r}, attempted {attempted!r}"
        )
