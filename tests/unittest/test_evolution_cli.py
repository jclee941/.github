"""Tests for scripts/evolution/cli.py defensive JSON parsing.

Issue #485: the CLI reads external JSON files, so missing required fields must
raise a friendly ValueError (not a bare KeyError with an unhelpful traceback).
"""

from __future__ import annotations

import pytest

from scripts.evolution.cli import _finding_from_dict, _suggestion_from_dict


class TestFindingFromDict:
    def test_missing_category_raises_value_error(self):
        with pytest.raises(ValueError, match="category"):
            _finding_from_dict({})

    def test_valid_finding_parses(self):
        f = _finding_from_dict({"category": "bug", "title": "t"})
        assert f.category == "bug"
        assert f.title == "t"


class TestSuggestionFromDict:
    def test_missing_suggestion_id_raises_value_error(self):
        with pytest.raises(ValueError, match="suggestion_id"):
            _suggestion_from_dict({"category": "perf", "score": 1})

    def test_missing_category_raises_value_error(self):
        with pytest.raises(ValueError, match="category"):
            _suggestion_from_dict({"suggestion_id": "s1", "score": 1})

    def test_missing_score_raises_value_error(self):
        with pytest.raises(ValueError, match="score"):
            _suggestion_from_dict({"suggestion_id": "s1", "category": "perf"})

    def test_valid_suggestion_parses(self):
        s = _suggestion_from_dict(
            {"suggestion_id": "s1", "category": "perf", "score": 0.5}
        )
        assert s.suggestion_id == "s1"
        assert s.category == "perf"
        assert s.score == 0.5
