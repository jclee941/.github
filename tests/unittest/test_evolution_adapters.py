"""Tests for scripts/evolution/adapters.py.

Adapters map upstream pr_agent tool OUTPUT (plain dicts/lists) into evolution
models WITHOUT importing or modifying the upstream pr_agent tree. This is the
fork-owned integration boundary (D1) and the upstream-key compatibility fix (D2).
"""

from __future__ import annotations

import hashlib

from scripts.evolution.adapters import (
    findings_from_review_data,
    suggestions_from_improve_data,
)
from scripts.evolution.fingerprint import finding_identity


def _upstream_fp(repo, file, start, end, category, content):
    ch = hashlib.sha256(str(content).encode()).hexdigest()[:8]
    marker = f"{repo}|{file}|{start}|{end}|{category}|{ch}"
    return hashlib.sha256(marker.encode()).hexdigest()[:16]


class TestFindingsFromReviewData:
    def test_security_concern_finding(self):
        # Mirrors pr_reviewer._extract_auto_issue_findings security_concerns path.
        review_data = {
            "review": {
                "security_concerns": "SQL injection: user input reaches query",
                "key_issues_to_review": [],
            }
        }
        findings = findings_from_review_data(review_data)
        assert len(findings) == 1
        assert findings[0].category == "security"
        assert findings[0].severity == "critical"
        assert findings[0].file_path == ""

    def test_key_issue_uses_upstream_file_key(self):
        # Upstream emits "file" (and relevant_file). Adapter must read it so the
        # fingerprint matches the upstream marker (D2).
        review_data = {
            "review": {
                "security_concerns": "",
                "key_issues_to_review": [
                    {
                        "issue_header": "SQL Injection",
                        "issue_content": "Query construction is vulnerable",
                        "relevant_file": "src/db.py",
                        "start_line": 10,
                        "end_line": 15,
                    }
                ],
            }
        }
        findings = findings_from_review_data(review_data)
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "security"
        assert f.file_path == "src/db.py"
        assert f.start_line == 10
        assert f.end_line == 15
        # fingerprint must match the upstream marker computed with file=src/db.py
        fp = finding_identity("repo", f).fingerprint
        assert fp == _upstream_fp("repo", "src/db.py", 10, 15, "security", f.content)

    def test_accepts_prebuilt_findings_with_file_key(self):
        # If given the already-extracted finding dicts (which use "file"), adapter
        # must honor the "file" key, not silently drop it.
        finding_dicts = [
            {"category": "bug", "severity": "high", "title": "t",
             "content": "c", "file": "core/x.py", "start_line": 5, "end_line": 6}
        ]
        findings = findings_from_review_data({"findings": finding_dicts})
        assert findings[0].file_path == "core/x.py"
        assert findings[0].start_line == 5

    def test_bug_classification_from_keywords(self):
        review_data = {
            "review": {
                "security_concerns": "",
                "key_issues_to_review": [
                    {"issue_header": "Crash", "issue_content": "this crashes on empty input",
                     "relevant_file": "a.py", "start_line": 1, "end_line": 1}
                ],
            }
        }
        findings = findings_from_review_data(review_data)
        assert findings[0].category == "bug"

    def test_non_dict_review_data_returns_empty(self):
        assert findings_from_review_data("not a dict") == []
        assert findings_from_review_data({"review": "garbage"}) == []

    def test_no_findings_when_no_concerns(self):
        review_data = {"review": {"security_concerns": "none", "key_issues_to_review": []}}
        assert findings_from_review_data(review_data) == []


class TestSuggestionsFromImproveData:
    def test_maps_code_suggestions(self):
        improve_data = {
            "code_suggestions": [
                {
                    "relevant_file": "a.py",
                    "label": "performance",
                    "one_sentence_summary": "use a set for membership test",
                    "existing_code": "if x in mylist:",
                    "improved_code": "if x in myset:",
                    "relevant_lines_start": 10,
                    "relevant_lines_end": 12,
                    "score": 8,
                }
            ]
        }
        suggestions = suggestions_from_improve_data("repo", improve_data)
        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.category == "performance"
        assert s.label == "performance"
        assert s.score == 8.0
        assert s.file_path == "a.py"
        assert s.start_line == 10
        assert s.end_line == 12
        assert s.suggestion_id  # deterministic id assigned

    def test_accepts_plain_list(self):
        suggestions = suggestions_from_improve_data("repo", [
            {"relevant_file": "b.py", "label": "style", "one_sentence_summary": "f-string",
             "score": 4, "relevant_lines_start": 1, "relevant_lines_end": 1}
        ])
        assert suggestions[0].label == "style"

    def test_missing_score_defaults_zero(self):
        suggestions = suggestions_from_improve_data("repo", [
            {"relevant_file": "b.py", "label": "x", "one_sentence_summary": "t"}
        ])
        assert suggestions[0].score == 0.0

    def test_non_dict_returns_empty(self):
        assert suggestions_from_improve_data("repo", "garbage") == []

    def test_deterministic_id_is_stable(self):
        data = [{"relevant_file": "b.py", "label": "x", "one_sentence_summary": "same",
                 "score": 5, "relevant_lines_start": 1, "relevant_lines_end": 2}]
        a = suggestions_from_improve_data("repo", list(data))[0]
        b = suggestions_from_improve_data("repo", list(data))[0]
        assert a.suggestion_id == b.suggestion_id
