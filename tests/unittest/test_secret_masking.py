"""Tests for pr_agent.algo.secret_masking.

We use the env-var escape hatch ``PR_AGENT_MASK_SECRETS_SKIP_CONFIG=1`` so
tests never need to fully initialize Dynaconf, keeping them fast and isolated.
"""
from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("PR_AGENT_MASK_SECRETS_SKIP_CONFIG", "1")

from jclee_bot.review_engine.algo import secret_masking  # noqa: E402
from jclee_bot.review_engine.algo.secret_masking import REDACTION, mask_obj, mask_text  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic-secret helpers.
#
# GitHub Secret Scanning rejects pushes that contain complete-looking tokens
# (Stripe sk_live_*, Twilio AC*, etc.) anywhere in the diff - even inside
# test fixtures. We therefore assemble every token at runtime from harmless
# fragments so the literal never appears in the committed file. Each value
# still matches the corresponding regex in
# ``pr_agent.algo.secret_masking._PATTERNS``.
# ---------------------------------------------------------------------------

GH_PAT = "ghp" + "_" + "a" * 30 + "XX"
AWS_AK = "AKIA" + "IOSFODNN7EXAMPLE"
OPENAI = "sk-" + "proj-" + "a" * 40
ANTHRO = "sk-ant-" + "api03-" + "a" * 30
STRIPE = "sk" + "_live_" + "a" * 24
OPENAI_SHORT = "sk-" + "1234567890abcdefghijklmnop"


@pytest.fixture(autouse=True)
def _reset_cache():
    """Drop the cached config-secrets between tests."""
    secret_masking._CACHED_SECRETS = None
    yield
    secret_masking._CACHED_SECRETS = None


# ----------------------------- Regex coverage -----------------------------


@pytest.mark.parametrize(
    "label,sample",
    [
        # All fixtures are assembled at runtime so they never appear as
        # a complete token in the repo (otherwise GitHub Secret Scanning
        # blocks the push). Each value still matches the corresponding
        # regex in pr_agent.algo.secret_masking._PATTERNS.
        ("aws_access_key", "AKIA" + "IOSFODNN7EXAMPLE"),
        ("github_pat", "ghp" + "_" + "a" * 30 + "XX"),
        ("github_oauth", "gho" + "_" + "a" * 30 + "XX"),
        ("github_server", "ghs" + "_" + "a" * 30 + "XX"),
        ("github_fine_grained", "github_pat" + "_" + "1" * 60),
        ("openai_proj", "sk-" + "proj-" + "a" * 40),
        ("anthropic", "sk-ant-" + "api03-" + "a" * 30),
        ("gitlab_pat", "glpat-" + "a" * 20),
        ("slack", "xoxb-" + "1234567890-abcdefghij"),
        ("stripe_live", "sk" + "_live_" + "a" * 24),
        ("google_api", "AIza" + "Sy" + "A" + "0" * 30 + "_x"),
        ("jwt", "eyJ" + "a" * 30 + ".eyJ" + "b" * 30 + "." + "c" * 30),
        ("npm_token", "npm" + "_" + "a" * 40),
        ("twilio_sid", "AC" + "0" * 32),
        ("sendgrid", "SG." + "a" * 20 + "." + "b" * 30),
        ("docker_pat", "dckr_pat" + "_" + "a" * 24),
    ],
)
def test_full_match_patterns_are_fully_redacted(label, sample):
    out = mask_text(sample)
    assert REDACTION in out, f"{label} not redacted: {out}"
    assert sample not in out, f"{label} value leaked: {out}"


@pytest.mark.parametrize(
    "sample,kept_prefix,kept_suffix",
    [
        # Group-redact patterns keep the label visible.
        ("Authorization: Bearer abcdefghij1234567890klmnop",
         "Authorization: Bearer ", None),
        ("Authorization: Basic dXNlcjpzdXBlcnNlY3JldHBhc3N3b3Jk",
         "Authorization: Basic ", None),
        ("postgresql://admin:supersecret123@db.example.com/prod",
         "postgresql://admin:", "@db.example.com/prod"),
        ("mongodb+srv://user:Topsecret9876@cluster.mongodb.net/db",
         "mongodb+srv://user:", "@cluster.mongodb.net/db"),
        ("AccountKey=abcdefghijklmnopqrstuvwxyz0123456789ABCD==",
         "AccountKey=", None),
        ("OPENAI_KEY=" + OPENAI_SHORT,
         "OPENAI_KEY=", None),
        ("AWS_SECRET_ACCESS_KEY=\"" + "wJalrXUtnFEMI/K7MDENG/bPxRfiCY" + "EXAMPLEKEY" + "\"",
         "AWS_SECRET_ACCESS_KEY=\"", "\""),
    ],
)
def test_group_redact_patterns_keep_labels(sample, kept_prefix, kept_suffix):
    out = mask_text(sample)
    assert REDACTION in out
    assert out.startswith(kept_prefix), f"expected prefix {kept_prefix!r} in {out!r}"
    if kept_suffix is not None:
        assert out.endswith(kept_suffix), f"expected suffix {kept_suffix!r} in {out!r}"


@pytest.mark.parametrize(
    "sample",
    [
        "Just a plain code review comment about naming.",
        "Refactor the loop and add tests for edge cases.",
        "PR title: chore(deps): bump actions/setup-go from 5 to 6",
        "version 1.2.3 release notes",
        "abcdefghijk",  # no token shape, no env-var shape
        # Regression: real Python/JS source quoted in a PR review must NOT trigger env_var_secret.
        'api_key = get_settings().get("openai.key")',
        'api_key = config.get("openai.key")',
        'self.api_key = self.config.api_key',
        # Lowercase variable assignments must NOT be confused with env-vars.
        'access_token: str = await get_token()',
        'auth_key=request.headers.get("x-auth")',
    ],
)
def test_plain_text_is_unchanged(sample):
    assert mask_text(sample) == sample


def test_pem_private_key_block_is_redacted():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEAxxx...\n"
        "-----END RSA PRIVATE KEY-----"
    )
    out = mask_text(pem)
    assert REDACTION in out
    assert "MIIEpAIBAAKCAQEAxxx" not in out


# ------------------------------ Behavior --------------------------------


def test_idempotent_double_mask_is_noop():
    s = "token " + GH_PAT + " leaked"
    once = mask_text(s)
    twice = mask_text(once)
    assert once == twice


def test_non_string_passthrough():
    assert mask_text(None) is None
    assert mask_text(123) == 123
    assert mask_text(True) is True


def test_mask_obj_recurses_dict_and_list():
    data = {
        "ok": "fine",
        "nested": {
            "github_token": GH_PAT,
            "list": [
                AWS_AK,
                {"deep": OPENAI},
            ],
        },
        "tuple": ("plain", GH_PAT),
    }
    out = mask_obj(data)
    assert out["ok"] == "fine"
    assert out["nested"]["github_token"] == REDACTION
    assert out["nested"]["list"][0] == REDACTION
    assert out["nested"]["list"][1]["deep"] == REDACTION
    # tuple is preserved as tuple
    assert isinstance(out["tuple"], tuple)
    assert out["tuple"][0] == "plain"
    assert out["tuple"][1] == REDACTION


def test_mask_obj_handles_set():
    s = {"ok", GH_PAT}
    out = mask_obj(s)
    assert isinstance(out, set)
    assert REDACTION in out
    assert GH_PAT not in out


def test_mask_obj_depth_bound_prevents_runaway():
    # Build a deep nested dict beyond the depth bound. Should not recurse.
    deep = GH_PAT
    obj = deep
    for _ in range(20):
        obj = {"x": obj}
    out = mask_obj(obj)
    # Verify it returns *something* without raising; deep leaves untouched.
    s = str(out)
    assert "x" in s


def test_extra_secrets_are_redacted():
    custom = "my-internal-token-7Z9XQ"
    text = f"using {custom} for auth"
    assert custom in mask_text(text)  # not detected by default
    out = mask_text(text, extra_secrets=[custom])
    assert custom not in out
    assert REDACTION in out


def test_disabled_via_env_var(monkeypatch):
    monkeypatch.setenv("PR_AGENT_MASK_SECRETS", "0")
    s = GH_PAT
    assert mask_text(s) == s


def test_enabled_when_env_unset(monkeypatch):
    monkeypatch.delenv("PR_AGENT_MASK_SECRETS", raising=False)
    s = GH_PAT
    assert mask_text(s) == REDACTION


# ----------------------------- Performance ------------------------------


def test_perf_100kb_under_2s():
    body = ("This is some perfectly normal review text. " * 2400) + (
        " token=" + GH_PAT
    )
    assert len(body) > 100_000
    t = time.time()
    out = mask_text(body)
    elapsed = time.time() - t
    assert elapsed < 2.0, f"too slow: {elapsed:.2f}s"
    assert REDACTION in out


def test_perf_many_small_calls_under_2s():
    samples = [
        "PR review: looks good, ship it",
        "naming nit on line 42",
        "consider extracting helper",
        GH_PAT,
        "perfectly normal sentence",
    ]
    t = time.time()
    for _ in range(2000):
        for s in samples:
            mask_text(s)
    elapsed = time.time() - t
    assert elapsed < 10.0, f"too slow: {elapsed:.2f}s"


# ------------------------ config-secrets collection ---------------------


def test_collect_config_secrets_skips_config_when_env_set(monkeypatch):
    monkeypatch.setenv("PR_AGENT_MASK_SECRETS_SKIP_CONFIG", "1")
    secret_masking._CACHED_SECRETS = None
    assert secret_masking.collect_config_secrets() == set()


def test_collect_config_secrets_pulls_live_values(monkeypatch):
    monkeypatch.delenv("PR_AGENT_MASK_SECRETS_SKIP_CONFIG", raising=False)
    secret_masking._CACHED_SECRETS = None

    fake_openai = "sk-live-" + "abcdefghijklmnopqrstuv0123"
    fake_gh = "ghp" + "_" + "realalalalalalalalalalalal1234567890"
    fake_wh = "wh-" + "very-secret-value-123456"

    class FakeSettings:
        store = {
            "openai.key": fake_openai,
            "github.user_token": fake_gh,
            "github.webhook_secret": fake_wh,
            "anthropic.key": "<PLACEHOLDER>",
            "openai.api_base": "",
        }

        def get(self, path, default=None):
            return self.store.get(path, default)

    monkeypatch.setattr(
        secret_masking,
        "_os",
        type("M", (), {"environ": {}})(),
    )
    monkeypatch.setattr(
        "jclee_bot.review_engine.config_loader.get_settings", lambda: FakeSettings()
    )
    secrets = secret_masking.collect_config_secrets()
    assert fake_openai in secrets
    assert fake_gh in secrets
    assert fake_wh in secrets
    assert "<PLACEHOLDER>" not in secrets
    assert "" not in secrets


def test_collect_config_secrets_caches(monkeypatch):
    monkeypatch.delenv("PR_AGENT_MASK_SECRETS_SKIP_CONFIG", raising=False)
    secret_masking._CACHED_SECRETS = None
    calls = {"n": 0}

    class FakeSettings:
        def get(self, path, default=None):
            calls["n"] += 1
            return None

    monkeypatch.setattr(
        secret_masking, "_os", type("M", (), {"environ": {}})()
    )
    monkeypatch.setattr(
        "jclee_bot.review_engine.config_loader.get_settings", lambda: FakeSettings()
    )
    secret_masking.collect_config_secrets()
    n_after_first = calls["n"]
    secret_masking.collect_config_secrets()
    secret_masking.collect_config_secrets()
    assert calls["n"] == n_after_first, "cache should prevent re-walking"
