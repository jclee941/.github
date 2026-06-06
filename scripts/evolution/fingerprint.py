"""Deterministic fingerprinting for findings and suggestions.

The finding fingerprint is intentionally byte-for-byte compatible with the
upstream ``pr_agent/tools/pr_reviewer.py`` issue marker so that regression
history aligns with the GitHub issues the reviewer already creates:

    content_hash = sha256(str(content)).hexdigest()[:8]
    marker_input = f"{repo}|{file}|{start_line}|{end_line}|{category}|{content_hash}"
    fingerprint  = sha256(marker_input).hexdigest()[:16]

We additionally store the full 64-hex digest of the same ``marker_input`` so
improbable short-fingerprint collisions can be detected instead of silently
merging distinct findings.
"""

from __future__ import annotations

import hashlib

from scripts.evolution.errors import ValidationError
from scripts.evolution.models import FindingIdentity, ReviewFinding, Suggestion


def normalize_text(value: object) -> str:
    """Whitespace-normalize ``value`` deterministically.

    Collapses any run of whitespace to a single space and strips the ends.
    Does NOT lowercase (case can be meaningful, e.g. in code). Non-strings are
    converted with ``str()`` first. Used for debugging/search columns only --
    never for the upstream-compatible fingerprint.
    """
    return " ".join(str(value).split())


def _validate_finding(repo: str, finding: ReviewFinding) -> None:
    if not repo or not repo.strip():
        raise ValidationError("repo is required")
    if not finding.category or not finding.category.strip():
        raise ValidationError("finding.category is required")
    if finding.start_line < 0 or finding.end_line < 0:
        raise ValidationError("line numbers must be non-negative")
    if finding.end_line and finding.end_line < finding.start_line:
        raise ValidationError("end_line must be >= start_line (or 0 when unset)")


def finding_identity(repo: str, finding: ReviewFinding) -> FindingIdentity:
    """Compute the upstream-compatible identity for a review finding."""
    _validate_finding(repo, finding)

    content = str(finding.content)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]

    file_path = finding.file_path or ""
    start_line = finding.start_line or 0
    end_line = finding.end_line or 0
    category = finding.category or ""

    marker_input = (
        f"{repo}|{file_path}|{start_line}|{end_line}|{category}|{content_hash}"
    )
    digest = hashlib.sha256(marker_input.encode("utf-8")).hexdigest()

    return FindingIdentity(
        fingerprint=digest[:16],
        fingerprint_full=digest,
        marker_input=marker_input,
        normalized_content=normalize_text(content),
    )


def suggestion_fingerprint(repo: str, suggestion: Suggestion) -> str:
    """Stable 64-hex identity for a suggestion.

    Identity is defined by repo + location + category + normalized text. The
    transient ``suggestion_id`` and ``score`` are excluded so the same logical
    suggestion fingerprints identically across re-runs.
    """
    if not repo or not repo.strip():
        raise ValidationError("repo is required")

    normalized = normalize_text(suggestion.text)
    key = (
        f"{repo}|{suggestion.file_path or ''}|{suggestion.start_line or 0}"
        f"|{suggestion.end_line or 0}|{(suggestion.category or '').strip().lower()}"
        f"|{normalized}"
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
