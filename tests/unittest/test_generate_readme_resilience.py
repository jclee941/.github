from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_readme.py"
assert SCRIPT.exists(), f"generate_readme.py not found: {SCRIPT}"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_readme", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_call_llm_raises_transient_error_after_exhausting_retries(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "API_KEY", "test-key")
    monkeypatch.setattr(mod, "MODELS", ["m1"])
    monkeypatch.setattr(mod, "_RETRY_BACKOFF_SECONDS", [0, 0])

    def fake_chat_completion(**_kwargs):
        raise ConnectionError("timeout")

    monkeypatch.setattr(mod, "cliproxy_chat_completion", fake_chat_completion)
    with pytest.raises(mod.TransientLLMError):
        mod.call_llm("sys", "user")


def test_main_degrades_gracefully_on_transient_failure(monkeypatch, tmp_path):
    mod = _load_module()
    readme = tmp_path / "README.md"
    readme.write_text("# Existing README\n\nkeep me\n", encoding="utf-8")

    def boom(repo_root):
        raise mod.TransientLLMError("all models 524")

    monkeypatch.setattr(mod, "generate_readme", boom)
    monkeypatch.setattr(mod.sys, "argv", ["generate_readme.py", "--repo", str(tmp_path)])
    rc = mod.main()
    assert rc == 0, f"transient failure must not hard-fail CI, got rc={rc}"
    assert readme.read_text(encoding="utf-8") == "# Existing README\n\nkeep me\n"
