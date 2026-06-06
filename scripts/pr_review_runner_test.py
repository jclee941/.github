#!/usr/bin/env python3
"""Tests for scripts/pr_review_runner.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pr_review_runner import (
    PRMeta,
    check_silent_failures,
    decide_commands,
    fetch_pr_meta,
    main,
    run_commands,
)


class TestParsePRUrl:
    def test_valid_url(self):
        from pr_review_runner import _parse_pr_url
        assert _parse_pr_url("https://github.com/jclee941/.github/pull/42") == ("jclee941/.github", 42)

    def test_invalid_url_raises(self):
        from pr_review_runner import _parse_pr_url
        with pytest.raises(ValueError, match="Cannot parse PR URL"):
            _parse_pr_url("not-a-url")


class TestFetchPRMeta:
    @patch("pr_review_runner.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "additions": 10,
                "deletions": 5,
                "files": [{"path": "foo.py"}, {"path": "bar.md"}],
                "title": "feat: add foo",
                "author": {"login": "dependabot[bot]"},
            }),
        )
        meta = fetch_pr_meta("https://github.com/jclee941/.github/pull/1")
        assert meta.number == 1
        assert meta.author == "dependabot[bot]"
        assert meta.title == "feat: add foo"
        assert meta.additions == 10
        assert meta.deletions == 5
        assert meta.files == ["foo.py", "bar.md"]
        assert meta.loc == 15

    @patch("pr_review_runner.subprocess.run")
    def test_failure_returns_empty_meta(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        meta = fetch_pr_meta("https://github.com/jclee941/.github/pull/1")
        assert meta.author == ""
        assert meta.title == ""
        assert meta.loc == 0


class TestDecideCommands:
    def test_bot_author(self):
        meta = PRMeta(1, "dependabot[bot]", "bump foo", 10, 5, ["go.mod"])
        cmds, reason = decide_commands(meta)
        assert cmds == ["review"]
        assert reason == "bot author"

    def test_docs_only(self):
        meta = PRMeta(1, "user", "docs: update readme", 10, 5, ["README.md", "docs/guide.md"])
        cmds, reason = decide_commands(meta)
        assert cmds == ["describe"]
        assert reason == "docs-only diff"

    def test_mixed_files_not_docs_only(self):
        meta = PRMeta(1, "user", "docs: update", 10, 5, ["README.md", "main.py"])
        cmds, _ = decide_commands(meta)
        assert cmds != ["describe"]

    def test_feat_title(self):
        meta = PRMeta(1, "user", "feat(auth): add login", 100, 50, ["auth.py"])
        cmds, reason = decide_commands(meta)
        assert cmds == ["describe", "review"]
        assert reason == "feat/fix/refactor PR"

    def test_small_pr(self):
        meta = PRMeta(1, "user", "fix typo", 10, 5, ["main.py"])
        cmds, reason = decide_commands(meta)
        assert cmds == ["review"]
        assert reason == "small PR (<50 LOC)"

    def test_large_pr(self):
        meta = PRMeta(1, "user", "big refactor", 800, 300, ["main.py"])
        cmds, reason = decide_commands(meta)
        assert cmds == ["describe", "review"]
        assert reason == "large PR (>1000 LOC)"

    def test_default(self):
        meta = PRMeta(1, "user", "chore: update", 100, 100, ["main.py"])
        cmds, reason = decide_commands(meta)
        assert cmds == ["describe", "review"]
        assert reason == "default"


class TestRunCommands:
    @patch("pr_review_runner.subprocess.run")
    def test_success(self, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
        log = tmp_path / "pr-agent.log"
        status = run_commands("https://github.com/jclee941/.github/pull/1", ["review"], log)
        assert status == 0
        assert "ok" in log.read_text()

    @patch("pr_review_runner.subprocess.run")
    def test_failure_stops_early(self, mock_run, tmp_path: Path):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="ok\n"),
            MagicMock(returncode=1, stdout="error\n"),
        ]
        log = tmp_path / "pr-agent.log"
        status = run_commands("https://github.com/jclee941/.github/pull/1", ["review", "improve"], log)
        assert status == 1
        assert "error" in log.read_text()
        assert mock_run.call_count == 2


class TestCheckSilentFailures:
    def test_detects_fatal(self, tmp_path: Path):
        log = tmp_path / "pr-agent.log"
        log.write_text("Failed to generate prediction with any model\n")
        assert check_silent_failures(log) is True

    def test_ignores_noop(self, tmp_path: Path):
        log = tmp_path / "pr-agent.log"
        log.write_text("Empty diff for PR: 42\n")
        assert check_silent_failures(log) is False

    def test_ignores_fatal_when_noop_present(self, tmp_path: Path):
        log = tmp_path / "pr-agent.log"
        log.write_text("Empty diff for PR: 42\nFailed to generate prediction with any model\n")
        assert check_silent_failures(log) is True

    def test_no_fatal(self, tmp_path: Path):
        log = tmp_path / "pr-agent.log"
        log.write_text("Everything is fine\n")
        assert check_silent_failures(log) is False


class TestMain:
    @patch("pr_review_runner.fetch_pr_meta")
    @patch("pr_review_runner.run_commands")
    @patch("pr_review_runner.check_silent_failures")
    def test_success(self, mock_silent, mock_run, mock_fetch, tmp_path: Path):
        mock_fetch.return_value = PRMeta(1, "user", "feat: add foo", 10, 5, ["foo.py"])
        mock_run.return_value = 0
        mock_silent.return_value = False
        log = tmp_path / "pr-agent.log"
        assert main(["https://github.com/jclee941/.github/pull/1", "--log", str(log)]) == 0

    @patch("pr_review_runner.fetch_pr_meta")
    @patch("pr_review_runner.run_commands")
    def test_command_failure(self, mock_run, mock_fetch, tmp_path: Path):
        mock_fetch.return_value = PRMeta(1, "user", "feat: add foo", 10, 5, ["foo.py"])
        mock_run.return_value = 1
        log = tmp_path / "pr-agent.log"
        assert main(["https://github.com/jclee941/.github/pull/1", "--log", str(log)]) == 1

    @patch("pr_review_runner.fetch_pr_meta")
    @patch("pr_review_runner.run_commands")
    @patch("pr_review_runner.check_silent_failures")
    def test_silent_failure(self, mock_silent, mock_run, mock_fetch, tmp_path: Path):
        mock_fetch.return_value = PRMeta(1, "user", "feat: add foo", 10, 5, ["foo.py"])
        mock_run.return_value = 0
        mock_silent.return_value = True
        log = tmp_path / "pr-agent.log"
        assert main(["https://github.com/jclee941/.github/pull/1", "--log", str(log)]) == 1

    @patch("pr_review_runner.fetch_pr_meta")
    @patch("pr_review_runner.run_commands")
    @patch("pr_review_runner.check_silent_failures")
    def test_bot_author_runs_only_review(self, mock_silent, mock_run, mock_fetch, tmp_path: Path):
        mock_fetch.return_value = PRMeta(1, "dependabot[bot]", "bump", 10, 5, ["go.mod"])
        mock_run.return_value = 0
        mock_silent.return_value = False
        log = tmp_path / "pr-agent.log"
        main(["https://github.com/jclee941/.github/pull/1", "--log", str(log)])
        _, call_args, _ = mock_run.mock_calls[0]
        assert call_args[1] == ["review"]


class TestDecideCommandsWithLLM:
    """DP-16: LLM-first command selection with deterministic fallback."""

    def test_llm_success_used(self):
        meta = PRMeta(number=1, author="alice", title="feat: x",
                      additions=10, deletions=0, files=["a.py"])
        from pr_review_runner import decide_commands_with_llm
        with patch("pr_review_runner._llm_command", return_value=(["describe", "review"], "llm")):
            cmds, reason = decide_commands_with_llm(meta)
        assert cmds == ["describe", "review"]
        assert "llm" in reason.lower()

    def test_llm_failure_falls_back_to_deterministic(self):
        meta = PRMeta(number=1, author="bot[bot]", title="x",
                      additions=10, deletions=0, files=["a.py"])
        from pr_review_runner import decide_commands_with_llm
        with patch("pr_review_runner._llm_command", return_value=(None, "fallback")):
            cmds, reason = decide_commands_with_llm(meta)
        # bot author -> deterministic ['review']
        assert cmds == ["review"]

    def test_llm_invalid_command_falls_back(self):
        meta = PRMeta(number=1, author="alice", title="fix: y",
                      additions=5, deletions=0, files=["a.py"])
        from pr_review_runner import decide_commands_with_llm
        # LLM returns a command not in the valid set -> ignore, fall back
        with patch("pr_review_runner._llm_command", return_value=(["frobnicate"], "llm")):
            cmds, reason = decide_commands_with_llm(meta)
        assert cmds == ["describe", "review"]  # feat/fix/refactor deterministic
