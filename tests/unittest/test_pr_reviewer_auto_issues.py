from unittest.mock import MagicMock, patch

import pytest

from jclee_bot.review_engine.tools.pr_reviewer import PRReviewer


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
        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings", return_value=FakeSettings()):
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
        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_get:
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

    def test_fingerprint_ignores_title_changes(self):
        """Dedup marker must be stable when only the LLM-generated title changes.

        Regression: the fingerprint included finding['title'], which the LLM
        rewords between re-reviews of the same finding, producing a new marker
        and a DUPLICATE GitHub issue. The marker must depend only on structural
        position (repo|file|start_line|end_line).
        """
        reviewer = make_reviewer({})
        reviewer.git_provider.find_open_issue_by_marker.return_value = None
        reviewer.git_provider.create_issue.return_value = MagicMock(number=1)

        first = {
            "category": "bug",
            "severity": "high",
            "title": "[Review][Bug] Original wording",
            "content": "Test content",
            "file": "src/test.py",
            "start_line": 10,
            "end_line": 20,
        }
        second = {**first, "title": "[Review][Bug] Completely reworded by model"}

        reviewer._create_single_issue(first, ["jclee-bot", "review-finding"])
        first_marker = reviewer.git_provider.find_open_issue_by_marker.call_args_list[0].args[0]

        reviewer._create_single_issue(second, ["jclee-bot", "review-finding"])
        second_marker = reviewer.git_provider.find_open_issue_by_marker.call_args_list[1].args[0]

        assert first_marker == second_marker, (
            "Dedup marker changed when only the title changed; "
            f"{first_marker!r} != {second_marker!r}"
        )

    def test_fingerprint_changes_with_position(self):
        """Different structural position must produce a different marker."""
        reviewer = make_reviewer({})
        reviewer.git_provider.find_open_issue_by_marker.return_value = None
        reviewer.git_provider.create_issue.return_value = MagicMock(number=1)

        base = {
            "category": "bug",
            "severity": "high",
            "title": "[Review][Bug] Same title",
            "content": "Test content",
            "file": "src/test.py",
            "start_line": 10,
            "end_line": 20,
        }
        other = {**base, "start_line": 99, "end_line": 105}

        reviewer._create_single_issue(base, ["jclee-bot", "review-finding"])
        m1 = reviewer.git_provider.find_open_issue_by_marker.call_args_list[0].args[0]

        reviewer._create_single_issue(other, ["jclee-bot", "review-finding"])
        m2 = reviewer.git_provider.find_open_issue_by_marker.call_args_list[1].args[0]

        assert m1 != m2, f"Marker should differ for different positions; {m1!r} == {m2!r}"

    def test_fingerprint_differs_for_different_category_same_position(self):
        """Two distinct findings on the same span must NOT collide.

        Regression guard (Oracle): a position-only fingerprint collapsed a
        security finding and a bug finding at the same lines into one marker,
        so the second was wrongly skipped as a duplicate.
        """
        reviewer = make_reviewer({})
        reviewer.git_provider.find_open_issue_by_marker.return_value = None
        reviewer.git_provider.create_issue.return_value = MagicMock(number=1)

        sec = {
            "category": "security",
            "severity": "critical",
            "title": "[Review][Security] SQLi",
            "content": "SQL injection via string concat",
            "file": "src/db.py",
            "start_line": 10,
            "end_line": 20,
        }
        bug = {
            "category": "bug",
            "severity": "high",
            "title": "[Review][Bug] Off-by-one",
            "content": "Loop bound is wrong",
            "file": "src/db.py",
            "start_line": 10,
            "end_line": 20,
        }

        reviewer._create_single_issue(sec, ["jclee-bot", "review-finding"])
        m_sec = reviewer.git_provider.find_open_issue_by_marker.call_args_list[0].args[0]
        reviewer._create_single_issue(bug, ["jclee-bot", "review-finding"])
        m_bug = reviewer.git_provider.find_open_issue_by_marker.call_args_list[1].args[0]

        assert m_sec != m_bug, (
            "Distinct findings (different category) at the same span collided; "
            f"{m_sec!r} == {m_bug!r}"
        )

    def test_fingerprint_differs_for_repo_level_findings_with_no_location(self):
        """Repo-level findings (file='', start=0, end=0) must not all collide."""
        reviewer = make_reviewer({})
        reviewer.git_provider.find_open_issue_by_marker.return_value = None
        reviewer.git_provider.create_issue.return_value = MagicMock(number=1)

        f1 = {
            "category": "security",
            "severity": "critical",
            "title": "[Review][Security] A",
            "content": "Missing auth check on admin endpoint",
            "file": "",
            "start_line": 0,
            "end_line": 0,
        }
        f2 = {
            "category": "security",
            "severity": "critical",
            "title": "[Review][Security] B",
            "content": "Secrets logged in plaintext",
            "file": "",
            "start_line": 0,
            "end_line": 0,
        }

        reviewer._create_single_issue(f1, ["jclee-bot", "review-finding"])
        m1 = reviewer.git_provider.find_open_issue_by_marker.call_args_list[0].args[0]
        reviewer._create_single_issue(f2, ["jclee-bot", "review-finding"])
        m2 = reviewer.git_provider.find_open_issue_by_marker.call_args_list[1].args[0]

        assert m1 != m2, (
            "Distinct repo-level findings collided into one marker; "
            f"{m1!r} == {m2!r}"
        )


class TestCreateIssuesForReviewFindings:
    """Test suite for _create_issues_for_review_findings."""

    @pytest.fixture(autouse=True)
    def patch_settings(self):
        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings", return_value=FakeSettings()):
            yield

    def test_disabled_noops(self):
        reviewer = make_reviewer({})
        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_get:
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


class TestParseIncremental:
    """Test suite for parse_incremental argument parsing."""

    def make_reviewer(self, review_data=None):
        reviewer = object.__new__(PRReviewer)
        reviewer.review_data = review_data or {}
        reviewer.git_provider = MagicMock()
        reviewer.git_provider.repo = "jclee941/test-repo"
        reviewer.git_provider.get_pr_url.return_value = "https://github.com/jclee941/test-repo/pull/123"
        return reviewer

    def test_no_args_returns_false(self):
        reviewer = self.make_reviewer()
        result = reviewer.parse_incremental([])
        assert result.is_incremental is False

    def test_empty_args_returns_false(self):
        reviewer = self.make_reviewer()
        result = reviewer.parse_incremental([""])
        assert result.is_incremental is False

    def test_minus_i_flag_returns_true(self):
        reviewer = self.make_reviewer()
        result = reviewer.parse_incremental(["-i"])
        assert result.is_incremental is True

    def test_multiple_args_with_minus_i_still_true(self):
        reviewer = self.make_reviewer()
        result = reviewer.parse_incremental(["-i", "--pr_url=https://github.com/..."])
        assert result.is_incremental is True

    def test_non_minus_i_arg_returns_false(self):
        reviewer = self.make_reviewer()
        result = reviewer.parse_incremental(["--pr_url=https://github.com/..."])
        assert result.is_incremental is False

    def test_returns_incremental_pr_object(self):
        reviewer = self.make_reviewer()
        result = reviewer.parse_incremental(["-i"])
        assert result.__class__.__name__ == "IncrementalPR"


def _make_incremental_settings(minimal_commits=1, minimal_minutes=5, require_all=False):
    """Factory for incremental review settings."""
    class S:
        class pr_reviewer:
            minimal_commits_for_incremental_review = minimal_commits
            minimal_minutes_for_incremental_review = minimal_minutes
            require_all_thresholds_for_incremental_review = require_all
        class config:
            git_provider = "github"
    return S


class TestCanRunIncrementalReview:
    """Test suite for _can_run_incremental_review gatekeeping."""

    def make_reviewer(self):
        reviewer = object.__new__(PRReviewer)
        reviewer.review_data = {}
        reviewer.git_provider = MagicMock()
        reviewer.git_provider.repo = "jclee941/test-repo"
        reviewer.git_provider.get_pr_url.return_value = "https://github.com/jclee941/test-repo/pull/123"
        reviewer.is_auto = True
        reviewer.pr_url = "https://github.com/jclee941/test-repo/pull/123"
        return reviewer

    def test_returns_false_if_auto_and_no_new_commits(self):
        reviewer = self.make_reviewer()
        reviewer.incremental = MagicMock()
        reviewer.incremental.first_new_commit_sha = None
        reviewer.incremental.commits_range = []
        reviewer.incremental.last_seen_commit = None

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value = _make_incremental_settings()
            result = reviewer._can_run_incremental_review()
        assert result is False

    def test_returns_false_if_git_provider_lacks_incremental_commits(self):
        reviewer = self.make_reviewer()
        reviewer.incremental = MagicMock()
        reviewer.incremental.first_new_commit_sha = "abc123"
        reviewer.incremental.commits_range = ["abc123"]
        reviewer.incremental.last_seen_commit = None

        del reviewer.git_provider.get_incremental_commits  # method not present

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value = _make_incremental_settings()
            result = reviewer._can_run_incremental_review()
        assert result is False

    def test_returns_false_if_not_enough_commits(self):
        reviewer = self.make_reviewer()
        reviewer.incremental = MagicMock()
        reviewer.incremental.first_new_commit_sha = "abc123"
        reviewer.incremental.commits_range = ["abc123"]  # 1 commit, threshold is 2
        reviewer.incremental.last_seen_commit = None

        reviewer.git_provider.get_incremental_commits = MagicMock()

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value = _make_incremental_settings(minimal_commits=2, require_all=True)
            result = reviewer._can_run_incremental_review()
        assert result is False

    def test_returns_true_when_thresholds_pass(self):
        import datetime as dt_module
        reviewer = self.make_reviewer()
        reviewer.incremental = MagicMock()
        reviewer.incremental.first_new_commit_sha = "abc123"
        reviewer.incremental.commits_range = ["abc123", "def456"]  # 2 commits, threshold is 1
        reviewer.incremental.last_seen_commit = MagicMock()
        reviewer.incremental.last_seen_commit.commit.author.date = dt_module.datetime(2020, 1, 1)  # very old

        reviewer.git_provider.get_incremental_commits = MagicMock()

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value = _make_incremental_settings()
            result = reviewer._can_run_incremental_review()
        assert result is True


class TestSetReviewLabels:
    """Test suite for set_review_labels parsing."""

    def make_reviewer(self):
        reviewer = object.__new__(PRReviewer)
        reviewer.review_data = {}
        reviewer.git_provider = MagicMock()
        reviewer.git_provider.repo = "jclee941/test-repo"
        reviewer.git_provider.get_pr_url.return_value = "https://github.com/jclee941/test-repo/pull/123"
        return reviewer

    def test_disabled_publish_output_noops(self):
        reviewer = self.make_reviewer()
        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value.config.publish_output = False
            reviewer.set_review_labels({})

    def test_effort_label_extracted_from_string(self):
        reviewer = self.make_reviewer()
        reviewer.git_provider.get_pr_labels.return_value = []

        data = {"review": {"estimated_effort_to_review_[1-5]": "3, 4, or 5"}}

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value.config.publish_output = True
            mock_settings.return_value.pr_reviewer.require_estimate_effort_to_review = True
            mock_settings.return_value.pr_reviewer.enable_review_labels_effort = True
            mock_settings.return_value.pr_reviewer.require_security_review = False
            mock_settings.return_value.pr_reviewer.enable_review_labels_security = False

            reviewer.set_review_labels(data)

        # Verify publish_labels was called with effort label
        call_args = reviewer.git_provider.publish_labels.call_args
        assert call_args is not None
        labels = call_args[0][0]
        assert "Review effort 3/5" in labels

    def test_effort_label_extracted_from_int(self):
        reviewer = self.make_reviewer()
        reviewer.git_provider.get_pr_labels.return_value = []

        data = {"review": {"estimated_effort_to_review_[1-5]": 2}}

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value.config.publish_output = True
            mock_settings.return_value.pr_reviewer.require_estimate_effort_to_review = True
            mock_settings.return_value.pr_reviewer.enable_review_labels_effort = True
            mock_settings.return_value.pr_reviewer.require_security_review = False
            mock_settings.return_value.pr_reviewer.enable_review_labels_security = False

            reviewer.set_review_labels(data)

        call_args = reviewer.git_provider.publish_labels.call_args
        labels = call_args[0][0]
        assert "Review effort 2/5" in labels

    def test_security_concern_label_added(self):
        reviewer = self.make_reviewer()
        reviewer.git_provider.get_pr_labels.return_value = []

        data = {"review": {"estimated_effort_to_review_[1-5]": "1", "security_concerns": "yes there are security concerns"}}

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value.config.publish_output = True
            mock_settings.return_value.pr_reviewer.require_estimate_effort_to_review = True
            mock_settings.return_value.pr_reviewer.enable_review_labels_effort = True
            mock_settings.return_value.pr_reviewer.require_security_review = True
            mock_settings.return_value.pr_reviewer.enable_review_labels_security = True

            reviewer.set_review_labels(data)

        call_args = reviewer.git_provider.publish_labels.call_args
        labels = call_args[0][0]
        assert "Possible security concern" in labels

    def test_invalid_effort_value_noops(self):
        reviewer = self.make_reviewer()
        reviewer.git_provider.get_pr_labels.return_value = []

        data = {"review": {"estimated_effort_to_review_[1-5]": "not-a-number"}}

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value.config.publish_output = True
            mock_settings.return_value.pr_reviewer.require_estimate_effort_to_review = True
            mock_settings.return_value.pr_reviewer.enable_review_labels_effort = True
            mock_settings.return_value.pr_reviewer.require_security_review = False
            mock_settings.return_value.pr_reviewer.enable_review_labels_security = False

            reviewer.set_review_labels(data)

        reviewer.git_provider.publish_labels.assert_not_called()

    def test_effort_out_of_range_noops(self):
        reviewer = self.make_reviewer()
        reviewer.git_provider.get_pr_labels.return_value = []

        data = {"review": {"estimated_effort_to_review_[1-5]": 99}}

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value.config.publish_output = True
            mock_settings.return_value.pr_reviewer.require_estimate_effort_to_review = True
            mock_settings.return_value.pr_reviewer.enable_review_labels_effort = True
            mock_settings.return_value.pr_reviewer.require_security_review = False
            mock_settings.return_value.pr_reviewer.enable_review_labels_security = False

            reviewer.set_review_labels(data)

        reviewer.git_provider.publish_labels.assert_not_called()

    def test_existing_labels_preserved(self):
        reviewer = self.make_reviewer()
        reviewer.git_provider.get_pr_labels.return_value = ["wip", "Review effort 2/5"]

        data = {"review": {"estimated_effort_to_review_[1-5]": "3"}}

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value.config.publish_output = True
            mock_settings.return_value.pr_reviewer.require_estimate_effort_to_review = True
            mock_settings.return_value.pr_reviewer.enable_review_labels_effort = True
            mock_settings.return_value.pr_reviewer.require_security_review = False
            mock_settings.return_value.pr_reviewer.enable_review_labels_security = False

            reviewer.set_review_labels(data)

        call_args = reviewer.git_provider.publish_labels.call_args
        labels = call_args[0][0]
        # wip is preserved, new effort replaces old effort
        assert "wip" in labels
        assert "Review effort 3/5" in labels


class TestAutoApproveLogic:
    """Test suite for auto_approve_logic."""

    def make_reviewer(self):
        reviewer = object.__new__(PRReviewer)
        reviewer.review_data = {}
        reviewer.git_provider = MagicMock()
        reviewer.git_provider.repo = "jclee941/test-repo"
        reviewer.git_provider.get_pr_url.return_value = "https://github.com/jclee941/test-repo/pull/123"
        return reviewer

    def test_enabled_calls_auto_approve(self):
        reviewer = self.make_reviewer()
        reviewer.git_provider.auto_approve.return_value = True

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value.config.enable_auto_approval = True

            reviewer.auto_approve_logic()

        reviewer.git_provider.auto_approve.assert_called_once()
        reviewer.git_provider.publish_comment.assert_called()

    def test_disabled_posts_disabled_message(self):
        reviewer = self.make_reviewer()

        with patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings") as mock_settings:
            mock_settings.return_value.config.enable_auto_approval = False

            reviewer.auto_approve_logic()

        reviewer.git_provider.auto_approve.assert_not_called()
        # Should post a comment about disabled option
        reviewer.git_provider.publish_comment.assert_called_once()
        call_args = reviewer.git_provider.publish_comment.call_args[0][0]
        assert "disabled" in call_args.lower()


class TestSchemaMismatchGuards:
    """Defensive guards for malformed LLM responses (gpt-5.5 returned plain string)."""

    def _make_stub(self, review_data):
        stub = MagicMock()
        stub.review_data = review_data
        stub._record_schema_mismatch = PRReviewer._record_schema_mismatch.__get__(stub)
        return stub

    def test_extract_findings_returns_empty_when_review_data_is_string(self):
        """LLM returned plain prose instead of structured dict."""
        stub = self._make_stub("plain prose response from gpt-5.5")
        findings = PRReviewer._extract_auto_issue_findings(stub)
        assert findings == []

    def test_extract_findings_returns_empty_when_review_section_is_string(self):
        """data['review'] is a string instead of nested dict."""
        stub = self._make_stub({"review": "unstructured text"})
        findings = PRReviewer._extract_auto_issue_findings(stub)
        assert findings == []

    def test_extract_findings_returns_empty_when_review_data_is_none(self):
        """review_data attribute defaults / never set."""
        stub = MagicMock()
        stub.review_data = None
        stub._record_schema_mismatch = PRReviewer._record_schema_mismatch.__get__(stub)
        findings = PRReviewer._extract_auto_issue_findings(stub)
        assert findings == []

    @patch("jclee_bot.review_engine.tools.pr_reviewer.get_settings")
    def test_schema_mismatch_records_metric(self, mock_settings):
        """_record_schema_mismatch increments LLM_FAILURES_TOTAL with reason='schema_mismatch'."""
        mock_settings.return_value.get.return_value = "kimi-k2.6"
        from jclee_bot.review_engine.servers.monitoring import LLM_FAILURES_TOTAL
        before = sum(1 for k in LLM_FAILURES_TOTAL._metrics if k[0] == "schema_mismatch")
        stub = MagicMock()
        PRReviewer._record_schema_mismatch(stub, "review", "some string value")
        after_keys = [k for k in LLM_FAILURES_TOTAL._metrics if k[0] == "schema_mismatch"]
        assert len(after_keys) >= before
        assert any("schema_mismatch" == k[0] for k in after_keys)


class TestLoadYamlSchemaGuard:
    """load_yaml must coerce non-dict scalars to {} so callers don't crash."""

    def test_plain_string_returns_empty_dict(self):
        from jclee_bot.review_engine.algo.utils import load_yaml
        result = load_yaml("just plain text no structure")
        assert isinstance(result, dict)
        assert result == {}

    def test_integer_scalar_returns_empty_dict(self):
        from jclee_bot.review_engine.algo.utils import load_yaml
        result = load_yaml("42")
        assert isinstance(result, dict)
        assert result == {}

    def test_valid_dict_passes_through(self):
        from jclee_bot.review_engine.algo.utils import load_yaml
        result = load_yaml("foo: bar\nbaz: 42")
        assert result == {"foo": "bar", "baz": 42}
