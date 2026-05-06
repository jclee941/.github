from unittest.mock import MagicMock, patch

import pytest

from pr_agent.tools.pr_reviewer import PRReviewer


class FakeConfig:
    model = "kimi-k2.6"


class FakePRReviewerSettings:
    def __init__(self, auto_create=True):
        self._auto_create = auto_create

    def get(self, key, default=None):
        values = {
            "auto_create_issues": self._auto_create,
            "auto_create_issue_labels": ["jclee-bot", "review-finding"],
            "auto_create_issue_security_labels": ["security", "critical"],
            "auto_create_issue_bug_labels": ["bug", "critical"],
        }
        return values.get(key, default)


class FakeSettings:
    config = FakeConfig()
    pr_reviewer = FakePRReviewerSettings()


def make_reviewer(review_data):
    reviewer = object.__new__(PRReviewer)
    reviewer.review_data = review_data
    reviewer.git_provider = MagicMock()
    reviewer.git_provider.repo = "jclee941/test-repo"
    reviewer.git_provider.get_pr_url.return_value = "https://github.com/jclee941/test-repo/pull/123"
    return reviewer


class TestExtractAutoIssueFindings:
    """Test suite for _extract_auto_issue_findings."""

    def test_extract_security_concerns(self):
        reviewer = make_reviewer({"review": {"security_concerns": "SQL injection: user input reaches query", "key_issues_to_review": []}})
        findings = reviewer._extract_auto_issue_findings()
        assert len(findings) == 1
        assert findings[0]["category"] == "security"
        assert findings[0]["severity"] == "critical"
        assert "[Review][Security]" in findings[0]["title"]

    def test_extract_classifies_security_keyword(self):
        reviewer = make_reviewer({
            "review": {
                "security_concerns": "",
                "key_issues_to_review": [{"issue_header": "SQL Injection", "issue_content": "Query construction is vulnerable", "relevant_file": "src/db.py", "start_line": 10, "end_line": 15}],
            }
        })
        findings = reviewer._extract_auto_issue_findings()
        assert len(findings) == 1
        assert findings[0]["category"] == "security"
        assert findings[0]["severity"] == "critical"
        assert findings[0]["file"] == "src/db.py"
        assert findings[0]["start_line"] == 10

    def test_extract_classifies_bug_with_crash(self):
        reviewer = make_reviewer({
            "review": {
                "security_concerns": "",
                "key_issues_to_review": [{"issue_header": "Possible Bug", "issue_content": "This crashes when input is empty"}],
            }
        })
        findings = reviewer._extract_auto_issue_findings()
        assert len(findings) == 1
        assert findings[0]["category"] == "bug"
        assert findings[0]["severity"] == "critical"

    def test_extract_classifies_bug_without_crash(self):
        reviewer = make_reviewer({
            "review": {
                "security_concerns": "",
                "key_issues_to_review": [{"issue_header": "Bug", "issue_content": "Incorrect logic in calculation"}],
            }
        })
        findings = reviewer._extract_auto_issue_findings()
        assert len(findings) == 1
        assert findings[0]["category"] == "bug"
        assert findings[0]["severity"] == "high"

    def test_extract_classifies_critical_keyword(self):
        reviewer = make_reviewer({
            "review": {
                "security_concerns": "",
                "key_issues_to_review": [{"issue_header": "Critical", "issue_content": "Privilege escalation possible"}],
            }
        })
        findings = reviewer._extract_auto_issue_findings()
        assert len(findings) == 1
        assert findings[0]["category"] == "critical"
        assert findings[0]["severity"] == "critical"

    def test_extract_skips_maintainability_issue(self):
        reviewer = make_reviewer({
            "review": {
                "security_concerns": "",
                "key_issues_to_review": [{"issue_header": "Maintainability", "issue_content": "Variable naming could be improved"}],
            }
        })
        findings = reviewer._extract_auto_issue_findings()
        assert len(findings) == 0

    def test_extract_accepts_single_dict_key_issue(self):
        reviewer = make_reviewer({
            "review": {
                "security_concerns": "",
                "key_issues_to_review": {"issue_header": "Bug", "issue_content": "Broken logic"},
            }
        })
        findings = reviewer._extract_auto_issue_findings()
        assert len(findings) == 1
        assert findings[0]["category"] == "bug"

    def test_extract_ignores_non_list_key_issues(self):
        reviewer = make_reviewer({
            "review": {
                "security_concerns": "",
                "key_issues_to_review": "No issues",
            }
        })
        findings = reviewer._extract_auto_issue_findings()
        assert len(findings) == 0


class TestCreateSingleIssue:
    """Test suite for _create_single_issue."""

    @pytest.fixture(autouse=True)
    def patch_settings(self):
        with patch("pr_agent.tools.pr_reviewer.get_settings", return_value=FakeSettings()):
            yield

    def test_create_issue_creates_fingerprint_marker_and_issue(self):
        reviewer = make_reviewer({})
        reviewer.git_provider.find_open_issue_by_marker.return_value = None
        issue = MagicMock()
        issue.number = 77
        reviewer.git_provider.create_issue.return_value = issue

        finding = {
            "category": "bug",
            "severity": "high",
            "title": "[Review][Bug] Test issue",
            "content": "Test content",
            "file": "src/test.py",
            "start_line": 10,
            "end_line": 20,
        }
        reviewer._create_single_issue(finding, ["jclee-bot", "review-finding"])

        reviewer.git_provider.find_open_issue_by_marker.assert_called_once()
        args = reviewer.git_provider.create_issue.call_args
        assert args.kwargs["title"] == "[Review][Bug] Test issue"
        body = args.kwargs["body"]
        assert "<!-- jclee-bot-review-finding:" in body
        assert "Source PR" in body
        assert "src/test.py" in body
        assert "10-20" in body
        assert "kimi-k2.6" in body

    def test_create_issue_skips_duplicate(self):
        reviewer = make_reviewer({})
        existing = MagicMock()
        existing.number = 10
        reviewer.git_provider.find_open_issue_by_marker.return_value = existing

        finding = {
            "category": "bug",
            "severity": "high",
            "title": "[Review][Bug] Test issue",
            "content": "Test content",
            "file": "",
            "start_line": 0,
            "end_line": 0,
        }
        reviewer._create_single_issue(finding, ["jclee-bot", "review-finding"])

        reviewer.git_provider.create_issue.assert_not_called()

    def test_create_issue_builds_security_labels(self):
        reviewer = make_reviewer({})
        reviewer.git_provider.find_open_issue_by_marker.return_value = None
        reviewer.git_provider.create_issue.return_value = MagicMock(number=1)

        finding = {
            "category": "security",
            "severity": "critical",
            "title": "[Review][Security] Test",
            "content": "Test",
            "file": "",
            "start_line": 0,
            "end_line": 0,
        }
        reviewer._create_single_issue(finding, ["jclee-bot", "review-finding"])

        labels = reviewer.git_provider.create_issue.call_args.kwargs["labels"]
        assert "jclee-bot" in labels
        assert "review-finding" in labels
        assert "security" in labels
        assert "critical" in labels
        assert len(labels) == len(set(labels))  # deduped

    def test_create_issue_builds_bug_labels(self):
        reviewer = make_reviewer({})
        reviewer.git_provider.find_open_issue_by_marker.return_value = None
        reviewer.git_provider.create_issue.return_value = MagicMock(number=1)

        finding = {
            "category": "bug",
            "severity": "critical",
            "title": "[Review][Bug] Test",
            "content": "Test",
            "file": "",
            "start_line": 0,
            "end_line": 0,
        }
        reviewer._create_single_issue(finding, ["jclee-bot", "review-finding"])

        labels = reviewer.git_provider.create_issue.call_args.kwargs["labels"]
        assert "bug" in labels
        assert "critical" in labels

    def test_create_issue_builds_critical_labels(self):
        reviewer = make_reviewer({})
        reviewer.git_provider.find_open_issue_by_marker.return_value = None
        reviewer.git_provider.create_issue.return_value = MagicMock(number=1)

        finding = {
            "category": "critical",
            "severity": "critical",
            "title": "[Review][Critical] Test",
            "content": "Test",
            "file": "",
            "start_line": 0,
            "end_line": 0,
        }
        reviewer._create_single_issue(finding, ["jclee-bot", "review-finding"])

        labels = reviewer.git_provider.create_issue.call_args.kwargs["labels"]
        assert "critical" in labels

    def test_create_issue_records_minimax_model_in_body(self):
        with patch("pr_agent.tools.pr_reviewer.get_settings") as mock_get:
            fake = FakeSettings()
            fake.config.model = "minimax-m2.7"
            mock_get.return_value = fake
            reviewer = make_reviewer({})
            reviewer.git_provider.find_open_issue_by_marker.return_value = None
            reviewer.git_provider.create_issue.return_value = MagicMock(number=1)

            finding = {
                "category": "bug",
                "severity": "high",
                "title": "[Review][Bug] Test",
                "content": "Test",
                "file": "",
                "start_line": 0,
                "end_line": 0,
            }
            reviewer._create_single_issue(finding, ["jclee-bot", "review-finding"])

            body = reviewer.git_provider.create_issue.call_args.kwargs["body"]
            assert "minimax-m2.7" in body


class TestCreateIssuesForReviewFindings:
    """Test suite for _create_issues_for_review_findings."""

    @pytest.fixture(autouse=True)
    def patch_settings(self):
        with patch("pr_agent.tools.pr_reviewer.get_settings", return_value=FakeSettings()):
            yield

    def test_disabled_noops(self):
        reviewer = make_reviewer({})
        with patch("pr_agent.tools.pr_reviewer.get_settings") as mock_get:
            fake = FakeSettings()
            fake.pr_reviewer = FakePRReviewerSettings(auto_create=False)
            mock_get.return_value = fake
            reviewer._create_issues_for_review_findings()
            reviewer.git_provider.ensure_labels.assert_not_called()

    def test_enabled_extracts_and_creates(self):
        reviewer = make_reviewer({})
        reviewer.git_provider.find_open_issue_by_marker.return_value = None
        reviewer.git_provider.create_issue.return_value = MagicMock(number=1)

        finding1 = {
            "category": "security",
            "severity": "critical",
            "title": "[Review][Security] Test1",
            "content": "Test1",
            "file": "",
            "start_line": 0,
            "end_line": 0,
        }
        finding2 = {
            "category": "bug",
            "severity": "high",
            "title": "[Review][Bug] Test2",
            "content": "Test2",
            "file": "",
            "start_line": 0,
            "end_line": 0,
        }

        with patch.object(reviewer, "_extract_auto_issue_findings", return_value=[finding1, finding2]):
            reviewer._create_issues_for_review_findings()

        reviewer.git_provider.ensure_labels.assert_called_once_with(["jclee-bot", "review-finding"])
        assert reviewer.git_provider.create_issue.call_count == 2

    def test_soft_fails_on_error(self):
        reviewer = make_reviewer({})
        reviewer.git_provider.ensure_labels.side_effect = RuntimeError("boom")

        # Should not raise
        reviewer._create_issues_for_review_findings()
