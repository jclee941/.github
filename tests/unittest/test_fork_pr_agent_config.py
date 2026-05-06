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

    def test_fallback_models_contains_kimi_k2_5_and_minimax_m2_7(self):
        """Test that fallback_models contains 'kimi-k2.5' and 'minimax-m2.7'."""
        path = self.get_toml_path()
        with open(path, "rb") as f:
            data = tomllib.load(f)

        assert "config" in data, "Missing [config] section in .pr_agent.toml"
        fallback_models = data["config"].get("fallback_models", [])

        assert "kimi-k2.5" in fallback_models, (
            f"Expected 'kimi-k2.5' in fallback_models, got {fallback_models}"
        )
        assert "minimax-m2.7" in fallback_models, (
            f"Expected 'minimax-m2.7' in fallback_models, got {fallback_models}"
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
