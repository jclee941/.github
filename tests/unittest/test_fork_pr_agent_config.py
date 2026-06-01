"""
Test suite for .pr_agent.toml fork-specific configuration.

Verifies that the hard fork of qodo-ai/pr-agent has correct configuration
for the CLIProxyAPI-based LLM backend.
"""

import pathlib
import tomllib


class TestForkPrAgentConfig:
    """Tests for fork-specific .pr_agent.toml configuration."""

    @staticmethod
    def get_toml_path() -> pathlib.Path:
        """Return path to .pr_agent.toml."""
        return pathlib.Path(__file__).parent.parent.parent / ".pr_agent.toml"

    @staticmethod
    def get_configuration_toml_path() -> pathlib.Path:
        """Return path to pr_agent/settings/configuration.toml."""
        return (
            pathlib.Path(__file__).parent.parent.parent
            / "pr_agent"
            / "settings"
            / "configuration.toml"
        )

    def test_pr_agent_toml_exists(self):
        """Test that .pr_agent.toml exists."""
        path = self.get_toml_path()
        assert path.exists(), f".pr_agent.toml not found at {path}"

    def test_custom_model_max_tokens_is_128000(self):
        """Test that [config].custom_model_max_tokens == 128000."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "config" in data, "Missing [config] section in .pr_agent.toml"
        custom_max_tokens = data["config"].get("custom_model_max_tokens")
        assert custom_max_tokens == 128000, (
            f"Expected [config].custom_model_max_tokens = 128000, "
            f"got {custom_max_tokens}"
        )

    def test_response_language_is_ko(self):
        """Test that [config].response_language == 'ko'."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "config" in data, "Missing [config] section in .pr_agent.toml"
        response_lang = data["config"].get("response_language")
        assert response_lang == "ko", (
            f"Expected [config].response_language = 'ko', got {response_lang}"
        )

    def test_model_is_kimi_k2_6(self):
        """Test that [config].model == 'kimi-k2.6'."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "config" in data, "Missing [config] section in .pr_agent.toml"
        model = data["config"].get("model")
        assert model == "kimi-k2.6", (
            f"Expected [config].model = 'kimi-k2.6', got {model}"
        )

    def test_fallback_models_are_kimi_excluded(self):
        """Test that fallback_models == ['minimax-m2.7', 'gpt-5.5'] (Kimi excluded)."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "config" in data, "Missing [config] section in .pr_agent.toml"
        fallback_models = data["config"].get("fallback_models", [])

        assert fallback_models == ["minimax-m2.7", "gpt-5.5"], (
            f"Expected fallback_models == ['minimax-m2.7', 'gpt-5.5'], got {fallback_models}"
        )
        assert "kimi-k2.5" not in fallback_models, (
            f"kimi-k2.5 must be excluded from fallback_models, got {fallback_models}"
        )

    def test_configuration_toml_was_edited_for_fork(self):
        """Test that pr_agent/settings/configuration.toml was edited for the fork."""
        path = self.get_configuration_toml_path()
        assert path.exists(), (
            f"pr_agent/settings/configuration.toml not found at {path}"
        )

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Verify that configuration.toml contains the fork's model setting
        # The fork changed model to kimi-k2.6 in configuration.toml
        assert "model=\"kimi-k2.6\"" in content or "model = \"kimi-k2.6\"" in content, (
            "configuration.toml should contain model=\"kimi-k2.6\" for fork-specific default"
        )

    def test_auto_commands_resolve_to_registered_commands(self):
        """Every command in [github_app].pr_commands / push_commands must be
        registered in command2class.

        Regression guard: c6fbb70e removed `agentic_review` from the workflow
        runner but left it in .pr_agent.toml. The GitHub App (homelab host) reads
        this file, so it silently logged \"Unknown command: agentic_review\"
        and returned False on every PR open and every push. This test fails
        if any auto-command does not resolve to a real handler.
        """
        import shlex

        from pr_agent.agent.pr_agent import command2class

        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        github_app = data.get("github_app", {})
        auto_commands = []
        for key in ("pr_commands", "push_commands"):
            auto_commands.extend(github_app.get(key, []))

        assert auto_commands, (
            "Expected [github_app].pr_commands/push_commands to be non-empty"
        )

        unresolved = []
        for raw in auto_commands:
            # mirror PRAgent._handle_request parsing: split args, strip '/'
            command = shlex.split(raw)[0].lstrip("/").lower()
            if command not in command2class:
                unresolved.append((raw, command))

        assert not unresolved, (
            "Auto-commands not registered in command2class (will silently "
            f"fail at runtime): {unresolved}. "
            f"Registered commands: {sorted(command2class.keys())}"
        )
