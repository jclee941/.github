import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import jclee_bot.review_engine.servers.github_app as github_app
from jclee_bot.review_engine.identity_providers.identity_provider import Eligibility


def make_push_body(before="old-sha", after="new-sha", draft=False, state="open", created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:01:00Z"):
    return {
        "before": before,
        "after": after,
        "pull_request": {
            "url": "https://api.github.com/repos/jclee941/test/pulls/1",
            "state": state,
            "draft": draft,
            "created_at": created_at,
            "updated_at": updated_at,
            "merge_commit_sha": "merge-sha",
        },
    }


class FakeGithubAppSettings:
    handle_push_trigger = True
    push_trigger_ignore_merge_commits = True
    push_trigger_pending_tasks_backlog = True
    push_trigger_pending_tasks_ttl = 300


class FakeSettings:
    github_app = FakeGithubAppSettings()

    def get(self, key, default=None):
        return default


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset module-level globals before each test."""
    github_app._duplicate_push_triggers.clear()
    github_app._pending_task_duplicate_push_conditions.clear()
    yield
    github_app._duplicate_push_triggers.clear()
    github_app._pending_task_duplicate_push_conditions.clear()


class TestCheckPullRequestEvent:
    """Test suite for _check_pull_request_event draft fix."""

    def test_defaults_missing_draft_to_false(self):
        body = make_push_body()
        del body["pull_request"]["draft"]
        log_context = {}
        pr, api_url = github_app._check_pull_request_event("opened", body, log_context)
        assert pr == body["pull_request"]
        assert api_url == "https://api.github.com/repos/jclee941/test/pulls/1"

    def test_rejects_draft_true(self):
        body = make_push_body(draft=True)
        log_context = {}
        result = github_app._check_pull_request_event("opened", body, log_context)
        assert result == ({}, "")

    def test_rejects_closed_pr(self):
        body = make_push_body(state="closed")
        log_context = {}
        result = github_app._check_pull_request_event("opened", body, log_context)
        assert result == ({}, "")

    def test_rejects_synchronize_initial_duplicate(self):
        body = make_push_body(created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z")
        log_context = {}
        result = github_app._check_pull_request_event("synchronize", body, log_context)
        assert result == ({}, "")


class TestHandlePushTrigger:
    """Test suite for handle_push_trigger_for_new_commits."""

    @pytest.fixture
    def fake_settings(self):
        return FakeSettings()

    @pytest.fixture
    def mock_agent(self):
        return MagicMock()

    @pytest.fixture
    def mock_log_context(self):
        return {"request_id": "test-req"}

    @pytest.mark.asyncio
    async def test_invokes_push_commands_and_minimax_subprocess(self, fake_settings, mock_agent, mock_log_context):
        body = make_push_body()

        with patch.object(github_app, "apply_repo_settings"), \
             patch.object(github_app, "get_settings", return_value=fake_settings), \
             patch.object(github_app, "get_identity_provider") as mock_idp, \
             patch.object(github_app, "_perform_auto_commands_github", new_callable=AsyncMock) as mock_perform, \
             patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_subprocess:

            mock_idp.return_value.verify_eligibility.return_value = Eligibility.ELIGIBLE

            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            mock_subprocess.return_value = proc

            await github_app.handle_push_trigger_for_new_commits(
                body, "push", "sender", "sender-id", "synchronize", mock_log_context, mock_agent
            )

            mock_perform.assert_awaited_once()
            assert mock_perform.call_args[0][0] == "push_commands"

            mock_subprocess.assert_awaited_once()
            args = mock_subprocess.call_args[0]
            assert args[0] == sys.executable
            assert args[1] == "-m"
            assert args[2] == "jclee_bot.review_engine.cli"
            assert args[3] == "--pr_url"
            assert args[4] == "https://api.github.com/repos/jclee941/test/pulls/1"
            assert args[5] == "review"

            env = mock_subprocess.call_args[1]["env"]
            assert env["CONFIG.MODEL"] == "gpt-5.5"
            assert env["CONFIG.FALLBACK_MODELS"] == "[]"
            assert env["CONFIG.CUSTOM_MODEL_MAX_TOKENS"] == "128000"

    @pytest.mark.asyncio
    async def test_skips_when_before_equals_after(self, fake_settings, mock_agent, mock_log_context):
        body = make_push_body(before="same-sha", after="same-sha")

        with patch.object(github_app, "apply_repo_settings"), \
             patch.object(github_app, "get_settings", return_value=fake_settings), \
             patch.object(github_app, "_perform_auto_commands_github", new_callable=AsyncMock) as mock_perform, \
             patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_subprocess:

            await github_app.handle_push_trigger_for_new_commits(
                body, "push", "sender", "sender-id", "synchronize", mock_log_context, mock_agent
            )

            mock_perform.assert_not_awaited()
            mock_subprocess.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_merge_commit(self, fake_settings, mock_agent, mock_log_context):
        body = make_push_body(after="merge-sha")

        with patch.object(github_app, "apply_repo_settings"), \
             patch.object(github_app, "get_settings", return_value=fake_settings), \
             patch.object(github_app, "_perform_auto_commands_github", new_callable=AsyncMock) as mock_perform, \
             patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_subprocess:

            await github_app.handle_push_trigger_for_new_commits(
                body, "push", "sender", "sender-id", "synchronize", mock_log_context, mock_agent
            )

            mock_perform.assert_not_awaited()
            mock_subprocess.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self, fake_settings, mock_agent, mock_log_context):
        body = make_push_body()
        fake_settings.github_app.handle_push_trigger = False

        with patch.object(github_app, "apply_repo_settings"), \
             patch.object(github_app, "get_settings", return_value=fake_settings), \
             patch.object(github_app, "_perform_auto_commands_github", new_callable=AsyncMock) as mock_perform:

            await github_app.handle_push_trigger_for_new_commits(
                body, "push", "sender", "sender-id", "synchronize", mock_log_context, mock_agent
            )

            mock_perform.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_not_eligible(self, fake_settings, mock_agent, mock_log_context):
        body = make_push_body()

        with patch.object(github_app, "apply_repo_settings"), \
             patch.object(github_app, "get_settings", return_value=fake_settings), \
             patch.object(github_app, "get_identity_provider") as mock_idp, \
             patch.object(github_app, "_perform_auto_commands_github", new_callable=AsyncMock) as mock_perform:

            mock_idp.return_value.verify_eligibility.return_value = Eligibility.NOT_ELIGIBLE

            await github_app.handle_push_trigger_for_new_commits(
                body, "push", "sender", "sender-id", "synchronize", mock_log_context, mock_agent
            )

            mock_perform.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_soft_fails_minimax_nonzero_exit(self, fake_settings, mock_agent, mock_log_context):
        body = make_push_body()

        with patch.object(github_app, "apply_repo_settings"), \
             patch.object(github_app, "get_settings", return_value=fake_settings), \
             patch.object(github_app, "get_identity_provider") as mock_idp, \
             patch.object(github_app, "_perform_auto_commands_github", new_callable=AsyncMock), \
             patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_subprocess:

            mock_idp.return_value.verify_eligibility.return_value = Eligibility.ELIGIBLE

            proc = MagicMock()
            proc.returncode = 1
            proc.communicate = AsyncMock(return_value=(b"", b"error output"))
            mock_subprocess.return_value = proc

            # Should not raise despite nonzero exit
            await github_app.handle_push_trigger_for_new_commits(
                body, "push", "sender", "sender-id", "synchronize", mock_log_context, mock_agent
            )

    @pytest.mark.asyncio
    async def test_soft_fails_minimax_subprocess_exception(self, fake_settings, mock_agent, mock_log_context):
        body = make_push_body()

        with patch.object(github_app, "apply_repo_settings"), \
             patch.object(github_app, "get_settings", return_value=fake_settings), \
             patch.object(github_app, "get_identity_provider") as mock_idp, \
             patch.object(github_app, "_perform_auto_commands_github", new_callable=AsyncMock), \
             patch("asyncio.create_subprocess_exec", side_effect=RuntimeError("boom")):

            mock_idp.return_value.verify_eligibility.return_value = Eligibility.ELIGIBLE

            # Should not raise despite subprocess exception
            await github_app.handle_push_trigger_for_new_commits(
                body, "push", "sender", "sender-id", "synchronize", mock_log_context, mock_agent
            )


class TestShouldProcessPrLogic:
    """Test suite for should_process_pr_logic gatekeeping."""

    @pytest.fixture
    def fake_settings(self):
        return FakeSettings()

    def _make_body(
        self,
        repo="jclee941/test",
        sender="alice",
        title="Feature: add login",
        labels=None,
        source_branch="feat/login",
        target_branch="main",
    ):
        body = {
            "sender": {"login": sender},
            "repository": {"full_name": repo},
            "pull_request": {
                "title": title,
                "labels": [{"name": label} for label in (labels or [])],
                "head": {"ref": source_branch},
                "base": {"ref": target_branch},
            },
        }
        return body

    def test_passes_by_default(self, fake_settings):
        body = self._make_body()
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is True

    def test_filters_by_repo_regex(self, fake_settings):
        fake_settings.get = lambda key, default=None: {
            "CONFIG.IGNORE_REPOSITORIES": [r"jclee941/secret.*"],
        }.get(key, default)

        body = self._make_body(repo="jclee941/secret-repo")
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is False

    def test_passes_non_matching_repo(self, fake_settings):
        fake_settings.get = lambda key, default=None: {
            "CONFIG.IGNORE_REPOSITORIES": [r"jclee941/secret.*"],
        }.get(key, default)

        body = self._make_body(repo="jclee941/public-repo")
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is True

    def test_filters_by_user_regex(self, fake_settings):
        fake_settings.get = lambda key, default=None: {
            "CONFIG.IGNORE_PR_AUTHORS": [r"^bot-.*"],
        }.get(key, default)

        body = self._make_body(sender="bot-alice")
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is False

    def test_filters_by_title_regex(self, fake_settings):
        fake_settings.get = lambda key, default=None: {
            "CONFIG.IGNORE_PR_TITLE": [r"\[Auto\].*"],
        }.get(key, default)

        body = self._make_body(title="[Auto] Bump version")
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is False

    def test_filters_by_label(self, fake_settings):
        fake_settings.get = lambda key, default=None: {
            "CONFIG.IGNORE_PR_LABELS": ["wip"],
        }.get(key, default)

        body = self._make_body(labels=["wip"])
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is False

    def test_filters_by_source_branch(self, fake_settings):
        fake_settings.get = lambda key, default=None: {
            "CONFIG.IGNORE_PR_SOURCE_BRANCHES": [r"^dependabot/.*"],
        }.get(key, default)

        body = self._make_body(source_branch="dependabot/npm/pkg-1")
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is False

    def test_filters_by_target_branch(self, fake_settings):
        fake_settings.get = lambda key, default=None: {
            "CONFIG.IGNORE_PR_TARGET_BRANCHES": [r"^release/.*"],
        }.get(key, default)

        body = self._make_body(target_branch="release/v1")
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is False

    def test_missing_pr_returns_true(self, fake_settings):
        body = {}
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is True

    def test_exception_returns_true(self, fake_settings):
        body = {"pull_request": {"title": object()}}  # unhashable causes regex to fail
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            assert github_app.should_process_pr_logic(body) is True

    def test_non_list_ignore_pr_title_converted_to_list(self, fake_settings):
        fake_settings.get = lambda key, default=None: {
            "CONFIG.IGNORE_PR_TITLE": r"\[Skip\].*",  # string, not list
        }.get(key, default)

        body = self._make_body(title="[Skip] Bypass CI")
        with patch.object(github_app, "get_settings", return_value=fake_settings):
            result = github_app.should_process_pr_logic(body)
            assert result is False


class TestCheckPullRequestEventAdditional:
    """Additional edge cases for _check_pull_request_event."""

    def test_missing_pull_request_returns_empty(self):
        body = {}
        log_context = {}
        result = github_app._check_pull_request_event("opened", body, log_context)
        assert result == ({}, "")

    def test_missing_api_url_returns_empty(self):
        body = {"pull_request": {"title": "Test"}}
        log_context = {}
        result = github_app._check_pull_request_event("opened", body, log_context)
        assert result == ({}, "")

    def test_review_requested_not_double_reviewed(self):
        body = {
            "pull_request": {
                "url": "https://api.github.com/repos/jclee941/test/pulls/1",
                "state": "open",
                "draft": False,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        }
        log_context = {}
        result = github_app._check_pull_request_event("review_requested", body, log_context)
        assert result == ({}, "")

    def test_synchronize_with_same_created_and_updated_at_skipped(self):
        body = {
            "pull_request": {
                "url": "https://api.github.com/repos/jclee941/test/pulls/1",
                "state": "open",
                "draft": False,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        }
        log_context = {}
        result = github_app._check_pull_request_event("synchronize", body, log_context)
        assert result == ({}, "")


class TestIsBotUser:
    """Test suite for is_bot_user."""

    def test_returns_false_when_ignore_bot_pr_disabled(self):
        with patch.object(
            github_app, "get_settings",
            return_value=FakeSettings()
        ):
            assert github_app.is_bot_user("pr-agent[bot]", "Bot") is False

    def test_returns_true_for_bot_when_ignore_enabled(self):
        class FakeSettingsIgnoreBot(FakeSettings):
            def get(self, key, default=None):
                if key == "GITHUB_APP.IGNORE_BOT_PR":
                    return True
                return default

        with patch.object(github_app, "get_settings", return_value=FakeSettingsIgnoreBot()):
            assert github_app.is_bot_user("dependabot[bot]", "Bot") is True

    def test_returns_false_for_non_bot_when_ignore_enabled(self):
        class FakeSettingsIgnoreBot(FakeSettings):
            def get(self, key, default=None):
                if key == "GITHUB_APP.IGNORE_BOT_PR":
                    return True
                return default

        with patch.object(github_app, "get_settings", return_value=FakeSettingsIgnoreBot()):
            assert github_app.is_bot_user("alice", "User") is False

    def test_returns_false_when_bot_name_contains_pr_agent(self):
        class FakeSettingsIgnoreBot(FakeSettings):
            def get(self, key, default=None):
                if key == "GITHUB_APP.IGNORE_BOT_PR":
                    return True
                return default

        with patch.object(github_app, "get_settings", return_value=FakeSettingsIgnoreBot()):
            # "pr-agent" in sender prevents ignoring
            assert github_app.is_bot_user("pr-agent[bot]", "Bot") is False
