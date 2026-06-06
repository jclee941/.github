"""Tests for scripts/evolution/fingerprint.py.

Locks the finding fingerprint to be byte-for-byte compatible with the upstream
pr_agent/tools/pr_reviewer.py marker logic so regression history aligns with the
GitHub issues the reviewer already creates.
"""

from __future__ import annotations

import hashlib

import pytest

from scripts.evolution.errors import ValidationError
from scripts.evolution.fingerprint import (
    finding_identity,
    normalize_text,
    suggestion_fingerprint,
)
from scripts.evolution.models import ReviewFinding, Suggestion


def _upstream_fingerprint(repo: str, file: str, start: int, end: int, category: str, content: str) -> str:
    """Reproduce pr_reviewer._create_single_issue marker logic independently."""
    content_hash = hashlib.sha256(str(content).encode()).hexdigest()[:8]
    marker_input = f"{repo}|{file}|{start}|{end}|{category}|{content_hash}"
    return hashlib.sha256(marker_input.encode()).hexdigest()[:16]


class TestFindingIdentityUpstreamCompat:
    def test_matches_upstream_marker_exactly(self):
        repo = "jclee941/test-repo"
        finding = ReviewFinding(
            category="security",
            severity="critical",
            title="SQL injection",
            content="user input reaches query",
            file_path="src/db.py",
            start_line=10,
            end_line=15,
        )
        identity = finding_identity(repo, finding)
        expected = _upstream_fingerprint(repo, "src/db.py", 10, 15, "security", "user input reaches query")
        assert identity.fingerprint == expected
        assert len(identity.fingerprint) == 16

    def test_full_fingerprint_is_64_hex_of_same_marker(self):
        repo = "r"
        finding = ReviewFinding("bug", "high", "t", "c", "f.py", 1, 2)
        identity = finding_identity(repo, finding)
        full = hashlib.sha256(identity.marker_input.encode()).hexdigest()
        assert identity.fingerprint_full == full
        assert len(identity.fingerprint_full) == 64
        assert identity.fingerprint_full.startswith(identity.fingerprint)

    def test_same_input_same_fingerprint(self):
        f = ReviewFinding("bug", "high", "title-a", "same content", "f.py", 3, 4)
        g = ReviewFinding("bug", "high", "title-DIFFERENT", "same content", "f.py", 3, 4)
        # Title is excluded from the marker (matches upstream comment).
        assert finding_identity("repo", f).fingerprint == finding_identity("repo", g).fingerprint

    def test_different_content_different_fingerprint(self):
        f = ReviewFinding("bug", "high", "t", "content one", "f.py", 3, 4)
        g = ReviewFinding("bug", "high", "t", "content two", "f.py", 3, 4)
        assert finding_identity("repo", f).fingerprint != finding_identity("repo", g).fingerprint

    def test_different_category_different_fingerprint(self):
        f = ReviewFinding("bug", "high", "t", "c", "f.py", 3, 4)
        g = ReviewFinding("security", "high", "t", "c", "f.py", 3, 4)
        assert finding_identity("repo", f).fingerprint != finding_identity("repo", g).fingerprint

    def test_different_location_different_fingerprint(self):
        f = ReviewFinding("bug", "high", "t", "c", "f.py", 3, 4)
        g = ReviewFinding("bug", "high", "t", "c", "f.py", 30, 40)
        assert finding_identity("repo", f).fingerprint != finding_identity("repo", g).fingerprint

    def test_repo_level_finding_empty_location(self):
        # Empty file path and line 0 are valid for repo-level findings.
        finding = ReviewFinding("design", "low", "t", "global concern")
        identity = finding_identity("repo", finding)
        expected = _upstream_fingerprint("repo", "", 0, 0, "design", "global concern")
        assert identity.fingerprint == expected

    def test_normalized_content_stored_separately(self):
        finding = ReviewFinding("bug", "high", "t", "  messy   \n content  ", "f.py", 1, 2)
        identity = finding_identity("repo", finding)
        # normalized_content is for debugging/search only; must NOT change the fingerprint.
        assert identity.normalized_content == "messy content"
        expected = _upstream_fingerprint("repo", "f.py", 1, 2, "bug", "  messy   \n content  ")
        assert identity.fingerprint == expected


class TestFindingIdentityValidation:
    def test_empty_repo_raises(self):
        with pytest.raises(ValidationError):
            finding_identity("   ", ReviewFinding("bug", "high", "t", "c", "f.py", 1, 2))

    def test_missing_category_raises(self):
        with pytest.raises(ValidationError):
            finding_identity("repo", ReviewFinding("", "high", "t", "c", "f.py", 1, 2))

    def test_negative_line_raises(self):
        with pytest.raises(ValidationError):
            finding_identity("repo", ReviewFinding("bug", "high", "t", "c", "f.py", -1, 2))

    def test_end_before_start_raises(self):
        with pytest.raises(ValidationError):
            finding_identity("repo", ReviewFinding("bug", "high", "t", "c", "f.py", 10, 5))

    def test_end_line_zero_allowed_with_nonzero_start(self):
        # end_line == 0 is the "unset" sentinel and must be tolerated.
        identity = finding_identity("repo", ReviewFinding("bug", "high", "t", "c", "f.py", 10, 0))
        assert identity.fingerprint


class TestNormalizeText:
    def test_collapses_whitespace_and_strips(self):
        assert normalize_text("  a\t b\n\n c  ") == "a b c"

    def test_non_string_is_stringified(self):
        assert normalize_text(123) == "123"
        assert normalize_text(None) == "None"

    def test_does_not_lowercase(self):
        assert normalize_text("CamelCase") == "CamelCase"


class TestSuggestionFingerprint:
    def test_is_64_hex(self):
        s = Suggestion("id-1", "performance", "perf", "use a set", 7.0, "f.py", 1, 2)
        fp = suggestion_fingerprint("repo", s)
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_same_suggestion_same_fingerprint(self):
        s1 = Suggestion("id-1", "performance", "perf", "use a set", 7.0, "f.py", 1, 2)
        s2 = Suggestion("id-2", "performance", "perf", "use a set", 9.0, "f.py", 1, 2)
        # id and score are excluded; content/category/location define identity.
        assert suggestion_fingerprint("repo", s1) == suggestion_fingerprint("repo", s2)

    def test_different_text_different_fingerprint(self):
        s1 = Suggestion("id-1", "performance", "perf", "use a set", 7.0, "f.py", 1, 2)
        s2 = Suggestion("id-1", "performance", "perf", "use a dict", 7.0, "f.py", 1, 2)
        assert suggestion_fingerprint("repo", s1) != suggestion_fingerprint("repo", s2)
