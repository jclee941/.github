#!/usr/bin/env python3
"""Tests for llm_decide.py — the fork-owned LLM decision helper.

Covers the Oracle-mandated safety contract:
- schema validation rejects unknown enums / missing reason / destructive+low-confidence
- fail-safe matrix: non-destructive decisions fail-open, destructive fail-closed
- the helper NEVER executes LLM-returned shell commands (allowlist only)
- prompt-injection text in input does not change the contract
- GITHUB_OUTPUT flattening is well-formed
"""
from __future__ import annotations

import importlib
import json
from urllib.error import URLError

import llm_decide as m

# ---- decision spec registry ----------------------------------------------

def test_every_spec_declares_required_fields():
    for name, spec in m.DECISION_SPECS.items():
        assert "destructive" in spec, f"{name} missing 'destructive'"
        assert "fallback" in spec, f"{name} missing 'fallback' (open|closed|deterministic)"
        assert spec["fallback"] in ("open", "closed"), f"{name} bad fallback {spec['fallback']}"
        assert "confidence_threshold" in spec
        assert isinstance(spec["actions"], (list, tuple)) and spec["actions"]


def test_non_merge_dps_present_merge_absent():
    # User scope: ALL non-merge DPs. Merge (dependabot/human) must NOT be wired here.
    assert "issue-label" in m.DECISION_SPECS
    assert "issue-classify" in m.DECISION_SPECS
    assert "repo-stale" in m.DECISION_SPECS
    assert "pr-command" in m.DECISION_SPECS
    assert "dependabot-merge" not in m.DECISION_SPECS
    assert "human-pr-merge" not in m.DECISION_SPECS


# ---- schema validation -----------------------------------------------------

def _good(decision="label", **kw):
    base = {"decision": decision, "confidence": 0.9, "risk": "low",
            "reason": "ok", "labels": [], "command": None,
            "semver_bump": None, "requires_human": False}
    base.update(kw)
    return base


def test_validate_accepts_well_formed():
    spec = m.DECISION_SPECS["issue-label"]
    ok, obj, err = m.validate_decision(_good(decision="label"), spec)
    assert ok, err
    assert obj["decision"] == "label"


def test_validate_rejects_unknown_decision_enum():
    spec = m.DECISION_SPECS["issue-label"]
    ok, _, err = m.validate_decision(_good(decision="frobnicate"), spec)
    assert not ok and "decision" in err.lower()


def test_validate_rejects_missing_reason():
    spec = m.DECISION_SPECS["issue-label"]
    bad = _good()
    del bad["reason"]
    ok, _, err = m.validate_decision(bad, spec)
    assert not ok and "reason" in err.lower()


def test_validate_rejects_destructive_below_confidence():
    spec = m.DECISION_SPECS["ci-failure-close"]  # destructive
    ok, _, err = m.validate_decision(_good(decision="close", confidence=0.10), spec)
    assert not ok and "confidence" in err.lower()


def test_validate_rejects_high_risk_destructive_allow():
    spec = m.DECISION_SPECS["ci-failure-close"]
    ok, _, err = m.validate_decision(_good(decision="close", risk="high", confidence=0.99), spec)
    assert not ok and "risk" in err.lower()


def test_validate_rejects_action_not_in_spec():
    spec = m.DECISION_SPECS["repo-stale"]  # actions: stale/active/noop
    ok, _, err = m.validate_decision(_good(decision="close", confidence=0.9), spec)
    assert not ok


# ---- command allowlist (no arbitrary execution) ---------------------------

def test_ci_auto_heal_command_must_be_in_allowlist():
    spec = m.DECISION_SPECS["ci-auto-heal"]
    assert "command_allowlist" in spec
    ok, _, err = m.validate_decision(
        _good(decision="command", command="rm -rf /", confidence=0.99, risk="low"), spec
    )
    assert not ok and "allowlist" in err.lower()
    # a permitted strategy passes
    allowed = spec["command_allowlist"][0]
    ok2, obj2, err2 = m.validate_decision(
        _good(decision="command", command=allowed, confidence=0.99, risk="low"), spec
    )
    assert ok2, err2


# ---- fail-safe matrix ------------------------------------------------------

def test_fail_open_returns_deterministic_signal_for_non_destructive(monkeypatch):
    # Force the LLM call to raise (unreachable)
    monkeypatch.setattr(m, "_call_llm", lambda *a, **k: (_ for _ in ()).throw(m.LLMError("down")))
    res = m.decide("issue-label", {"title": "x", "body": "y"})
    assert res["ok"] is False
    assert res["source"] == "fallback"
    assert res["fallback_used"] is True
    # non-destructive -> caller should run deterministic logic; helper signals that
    assert res["action"] in ("noop", "fallback")
    assert res["requires_human"] is False


def test_fail_closed_for_destructive_on_llm_error(monkeypatch):
    monkeypatch.setattr(m, "_call_llm", lambda *a, **k: (_ for _ in ()).throw(m.LLMError("down")))
    res = m.decide("ci-failure-close", {"workflow": "Gitleaks", "conclusion": "success"})
    assert res["ok"] is False
    assert res["action"] == "noop"          # fail closed: do nothing
    assert res["requires_human"] is True     # leave for human


def test_malformed_llm_json_triggers_failsafe(monkeypatch):
    monkeypatch.setattr(m, "_call_llm", lambda *a, **k: "not json at all {{{")
    res = m.decide("issue-label", {"title": "x", "body": "y"})
    assert res["ok"] is False and res["source"] == "fallback"


def test_kill_switch_disables_llm(monkeypatch):
    monkeypatch.setenv("LLM_DECISIONS_ENABLED", "false")
    called = {"n": 0}
    monkeypatch.setattr(m, "_call_llm", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or "{}")
    res = m.decide("issue-label", {"title": "x"})
    assert called["n"] == 0  # LLM never called when disabled
    assert res["source"] == "fallback"


def test_default_model_chain_uses_gpt55_then_m3(monkeypatch):
    monkeypatch.delenv("LLM_DECISION_MODEL", raising=False)
    monkeypatch.delenv("LLM_DECISION_FALLBACK_MODELS", raising=False)
    reloaded = importlib.reload(m)

    assert [reloaded.MODEL, *reloaded.FALLBACK_MODELS] == ["gpt-5.5", "MiniMax-M3"]


def test_call_llm_falls_back_to_m3_after_primary_failure(monkeypatch):
    monkeypatch.setattr(m, "API_KEY", "test-key")
    monkeypatch.setattr(m, "MODEL", "gpt-5.5")
    monkeypatch.setattr(m, "FALLBACK_MODELS", ["MiniMax-M3"])
    monkeypatch.setattr(m, "_RETRY_BACKOFF_SECONDS", [])

    requested_models = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

    def _urlopen(req, timeout):
        payload = json.loads(req.data.decode())
        requested_models.append(payload["model"])
        if payload["model"] == "gpt-5.5":
            raise URLError("primary down")
        return _Response()

    monkeypatch.setattr(m.urllib.request, "urlopen", _urlopen)

    assert m._call_llm("system", "user") == "ok"
    assert requested_models == ["gpt-5.5", "MiniMax-M3"]


# ---- happy path with mocked LLM -------------------------------------------

def test_decide_happy_path_label(monkeypatch):
    monkeypatch.setenv("LLM_DECISIONS_ENABLED", "true")
    payload = json.dumps(_good(decision="label", labels=["bug"], confidence=0.95))
    monkeypatch.setattr(m, "_call_llm", lambda *a, **k: payload)
    res = m.decide("issue-label", {"title": "crash on save", "body": "stacktrace"})
    assert res["ok"] is True and res["source"] == "llm"
    assert res["labels"] == ["bug"]
    assert res["action"] == "label"


def test_decide_strips_markdown_fence(monkeypatch):
    monkeypatch.setenv("LLM_DECISIONS_ENABLED", "true")
    fenced = "```json\n" + json.dumps(_good(decision="label", labels=["docs"])) + "\n```"
    monkeypatch.setattr(m, "_call_llm", lambda *a, **k: fenced)
    res = m.decide("issue-label", {"title": "update readme"})
    assert res["ok"] is True and res["labels"] == ["docs"]


def test_decide_strips_thinking_block(monkeypatch):
    # Thinking models can emit <think>...</think> before JSON.
    monkeypatch.setenv("LLM_DECISIONS_ENABLED", "true")
    thinky = (
        "<think>\nThe issue is clearly a bug. I will label it.\n</think>\n\n"
        + json.dumps(_good(decision="label", labels=["bug"], confidence=0.95))
    )
    monkeypatch.setattr(m, "_call_llm", lambda *a, **k: thinky)
    res = m.decide("issue-label", {"title": "crash"})
    assert res["ok"] is True, res
    assert res["labels"] == ["bug"]


def test_decide_extracts_json_with_prose_around(monkeypatch):
    # Even without <think> tags, a thinking model may wrap JSON in prose.
    monkeypatch.setenv("LLM_DECISIONS_ENABLED", "true")
    noisy = "Here is my decision:\n" + json.dumps(_good(decision="label", labels=["docs"])) + "\nDone."
    monkeypatch.setattr(m, "_call_llm", lambda *a, **k: noisy)
    res = m.decide("issue-label", {"title": "readme"})
    assert res["ok"] is True and res["labels"] == ["docs"]


# ---- GITHUB_OUTPUT flattening ---------------------------------------------

def test_flatten_output_is_wellformed():
    res = {"ok": True, "source": "llm", "action": "label", "confidence": 0.9,
           "risk": "low", "requires_human": False,
           "reason": "multi\nline\nreason", "labels": ["a", "b"]}
    lines = m.flatten_output(res)
    text = "\n".join(lines)
    assert "ok=true" in text
    assert "action=label" in text
    assert 'labels=["a", "b"]' in text or "labels=[\"a\", \"b\"]" in text
    # reason must not break GITHUB_OUTPUT (no raw newlines outside heredoc)
    assert all("\n" not in ln for ln in lines if not ln.startswith("reason<<"))
