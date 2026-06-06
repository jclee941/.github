"""Adapters from upstream pr_agent tool OUTPUT into evolution models.

This is the fork-owned integration boundary (D1): it consumes the plain
dict/list output that ``pr_agent`` tools already produce (review YAML, code
suggestions) and converts it into our models, WITHOUT importing or modifying any
``pr_agent`` code. That keeps the upstream tree merge-clean while letting real
PR-review output flow into the evolution engine.

The classification + key handling mirrors
``pr_agent/tools/pr_reviewer.py::_extract_auto_issue_findings`` so that
fingerprints produced here match the issue markers the reviewer creates (D2).
"""

from __future__ import annotations

import hashlib
from typing import SupportsInt, cast

from scripts.evolution.fingerprint import normalize_text
from scripts.evolution.models import ReviewFinding, Suggestion

# Keyword sets copied from pr_reviewer._extract_auto_issue_findings so the
# adapter classifies findings identically to the upstream tool.
_SECURITY_KEYWORDS = (
    "security", "vulnerability", "injection", "xss", "csrf", "secret",
    "credential", "auth", "authentication bypass", "rce", "remote code",
)
_BUG_KEYWORDS = (
    "bug", "incorrect", "broken", "crash", "data loss", "race condition",
    "deadlock", "exception", "error",
)
_CRITICAL_KEYWORDS = ("critical", "privilege escalation", "secret exposure")
_EMPTY_SECURITY = ("no", "none", "n/a", "")


def _int(value: object, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(cast("SupportsInt | str", value))
    except (TypeError, ValueError):
        return default


def _classify(header: str, content: str) -> tuple[str | None, str]:
    combined = f"{header} {content}".lower()
    if any(kw in combined for kw in _SECURITY_KEYWORDS):
        return "security", "critical"
    if any(kw in combined for kw in _BUG_KEYWORDS):
        severity = "critical" if ("data loss" in combined or "crash" in combined) else "high"
        return "bug", severity
    if any(kw in combined for kw in _CRITICAL_KEYWORDS):
        return "critical", "critical"
    return None, "high"


def _finding_from_dict(d: dict[str, object]) -> ReviewFinding:
    # Upstream finding dicts use the "file" key; tolerate "file_path" too.
    file_path = d.get("file", d.get("file_path", "")) or ""
    return ReviewFinding(
        category=str(d.get("category", "")),
        severity=str(d.get("severity", "high")),
        title=str(d.get("title", "")),
        content=str(d.get("content", "")),
        file_path=str(file_path),
        start_line=_int(d.get("start_line")),
        end_line=_int(d.get("end_line")),
    )


def findings_from_review_data(review_data: object) -> list[ReviewFinding]:
    """Convert pr_reviewer review output into ReviewFinding objects.

    Accepts either:
      * the raw review_data dict ({"review": {...}}), which is classified the
        same way pr_reviewer._extract_auto_issue_findings does, or
      * a dict carrying pre-extracted finding dicts under "findings".
    Non-dict / malformed input yields an empty list (defensive, like upstream).
    """
    if not isinstance(review_data, dict):
        return []

    # Pre-extracted findings path (already in the upstream finding-dict shape).
    if isinstance(review_data.get("findings"), list):
        return [_finding_from_dict(d) for d in review_data["findings"] if isinstance(d, dict)]

    review = review_data.get("review", {})
    if not isinstance(review, dict):
        return []

    findings: list[ReviewFinding] = []

    security = review.get("security_concerns", "")
    if security and str(security).strip() and str(security).strip().lower() not in _EMPTY_SECURITY:
        findings.append(
            ReviewFinding(
                category="security",
                severity="critical",
                title="[Review][Security] Security concerns detected",
                content=str(security),
                file_path="",
                start_line=0,
                end_line=0,
            )
        )

    key_issues = review.get("key_issues_to_review", [])
    if isinstance(key_issues, dict):
        key_issues = [key_issues]
    if not isinstance(key_issues, list):
        return findings

    for issue in key_issues:
        if not isinstance(issue, dict):
            continue
        header = str(issue.get("issue_header", ""))
        content = str(issue.get("issue_content", ""))
        category, severity = _classify(header, content)
        if category is None:
            continue
        findings.append(
            ReviewFinding(
                category=category,
                severity=severity,
                title=f"[Review][{category.capitalize()}] {issue.get('issue_header', 'Issue')}",
                content=str(issue.get("issue_content", "")),
                file_path=str(issue.get("relevant_file", issue.get("file", "")) or ""),
                start_line=_int(issue.get("start_line")),
                end_line=_int(issue.get("end_line")),
            )
        )

    return findings


def _suggestion_id(repo: str, d: dict[str, object]) -> str:
    """Deterministic id from repo + location + normalized summary/code."""
    parts = [
        repo,
        str(d.get("relevant_file", d.get("file", "")) or ""),
        str(d.get("relevant_lines_start", d.get("start_line", 0)) or 0),
        str(d.get("relevant_lines_end", d.get("end_line", 0)) or 0),
        str(d.get("label", "")).strip().lower(),
        normalize_text(d.get("one_sentence_summary", d.get("text", ""))),
        normalize_text(d.get("improved_code", "")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def suggestions_from_improve_data(repo: str, improve_data: object) -> list[Suggestion]:
    """Convert pr_code_suggestions output into Suggestion objects.

    Accepts either the dict ({"code_suggestions": [...]}) or a plain list of
    suggestion dicts. Non-list/dict input yields an empty list.
    """
    if isinstance(improve_data, dict):
        raw = improve_data.get("code_suggestions", [])
    elif isinstance(improve_data, list):
        raw = improve_data
    else:
        return []
    if not isinstance(raw, list):
        return []

    suggestions: list[Suggestion] = []
    for d in raw:
        if not isinstance(d, dict):
            continue
        label = str(d.get("label", "")).strip()
        summary = str(d.get("one_sentence_summary", d.get("text", "")))
        try:
            score = float(d.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0.0
        suggestions.append(
            Suggestion(
                suggestion_id=_suggestion_id(repo, d),
                category=label or "general",
                label=label,
                text=summary,
                score=score,
                file_path=str(d.get("relevant_file", d.get("file", "")) or ""),
                start_line=_int(d.get("relevant_lines_start", d.get("start_line"))),
                end_line=_int(d.get("relevant_lines_end", d.get("end_line"))),
                metadata={
                    "existing_code": d.get("existing_code", ""),
                    "improved_code": d.get("improved_code", ""),
                },
            )
        )
    return suggestions
