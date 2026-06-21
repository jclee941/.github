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

    def test_custom_model_max_tokens_matches_cliproxy_limit(self):
        """Test that [config].custom_model_max_tokens matches the CLIProxy edge limit."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "config" in data, "Missing [config] section in .pr_agent.toml"
        custom_max_tokens = data["config"].get("custom_model_max_tokens")
        assert custom_max_tokens == 128000, (
            f"Expected [config].custom_model_max_tokens = 128000, got {custom_max_tokens}"
        )

    def test_max_model_tokens_matches_cliproxy_limit(self):
        """Test that [config].max_model_tokens matches the CLIProxy edge limit."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "config" in data, "Missing [config] section in .pr_agent.toml"
        max_model_tokens = data["config"].get("max_model_tokens")
        assert max_model_tokens == 128000, (
            f"Expected [config].max_model_tokens = 128000, got {max_model_tokens}"
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

    def test_model_is_gpt55(self):
        """Test that [config].model == 'gpt-5.5' via CLIProxyAPI."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "config" in data, "Missing [config] section in .pr_agent.toml"
        model = data["config"].get("model")
        assert model == "gpt-5.5", (
            f"Expected [config].model = 'gpt-5.5', got {model}"
        )

    def test_api_base_is_cliproxy(self):
        """Test that [openai].api_base points at CLIProxyAPI."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "openai" in data, "Missing [openai] section in .pr_agent.toml"
        api_base = data["openai"].get("api_base")
        assert api_base == "https://cliproxy.jclee.me/v1", (
            f"Expected [openai].api_base = 'https://cliproxy.jclee.me/v1', got {api_base}"
        )

    def test_provider_base_fallbacks_are_disabled(self):
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "openai" in data, "Missing [openai] section in .pr_agent.toml"
        assert data["openai"].get("api_base_fallbacks") == []

    def test_fallback_models_are_canonical_cliproxy_chain(self):
        """Test that fallback_models use the canonical CLIProxy model chain."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "config" in data, "Missing [config] section in .pr_agent.toml"
        fallback_models = data["config"].get("fallback_models", [])

        assert fallback_models == ["minimax-m3"], (
            f"Expected fallback_models == ['minimax-m3'], got {fallback_models}"
        )

    def test_configuration_toml_was_edited_for_fork(self):
        """Test that pr_agent/settings/configuration.toml was edited for the fork."""
        path = self.get_configuration_toml_path()
        assert path.exists(), (
            f"pr_agent/settings/configuration.toml not found at {path}"
        )

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "model=\"gpt-5.5\"" in content or "model = \"gpt-5.5\"" in content, (
            "configuration.toml should contain model=\"gpt-5.5\" for fork-specific default"
        )

    def test_push_trigger_second_review_model_is_fork_configured(self):
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        github_app = data.get("github_app", {})
        assert github_app.get("push_trigger_second_review_model") == "gpt-5.5"

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
