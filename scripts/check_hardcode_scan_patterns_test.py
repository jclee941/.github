#!/usr/bin/env python3
"""Regression tests for the embedded secret/IP patterns in
.github/workflows/35_auto-hardcode-scan.yml.

The Auto Hardcode Scan workflow embeds its detection regexes inline (it has no
importable module). These tests extract the live HIGH_SIGNAL_PATTERNS from the
workflow and pin the behavior that previously caused recurring scheduled
failures:
  - sentinel/boolean literals (SECRET: "false") must NOT be flagged
  - short values (< 8 chars) must NOT be flagged
  - real-looking secrets/api keys MUST still be flagged (gate preserved)

If someone edits the workflow regex and reintroduces the false-positive that
failed every scheduled run, these tests fail.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/35_auto-hardcode-scan.yml"


def _load_scan_source() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            run = step.get("run", "") or ""
            if "HIGH_SIGNAL_PATTERNS" in run:
                return run
    raise AssertionError("could not find the hardcode-scan run step")


def _extract_high_signal_patterns() -> dict[str, re.Pattern]:
    """Build the HIGH_SIGNAL_PATTERNS dict by executing just that assignment
    from the embedded Python (safe: only `re` is available). YAML block
    scalars strip common indentation, so the parsed source is already
    dedented."""
    src = _load_scan_source()
    # Match from `HIGH_SIGNAL_PATTERNS = {` to a line that is exactly `}`.
    m = re.search(r"^HIGH_SIGNAL_PATTERNS\s*=\s*\{.*?^\}", src, re.DOTALL | re.MULTILINE)
    assert m, "HIGH_SIGNAL_PATTERNS block not found"
    namespace: dict = {"re": re}
    exec(m.group(0), namespace)  # noqa: S102 - trusted, repo-local workflow source
    return namespace["HIGH_SIGNAL_PATTERNS"]


@pytest.fixture(scope="module")
def patterns() -> dict[str, re.Pattern]:
    return _extract_high_signal_patterns()


def _matches(patterns: dict[str, re.Pattern], text: str) -> bool:
    return any(p.search(text) for p in patterns.values())


class TestSecretSentinelExclusion:
    @pytest.mark.parametrize("text", [
        'SECRET: "false"',
        'SECRET: "true"',
        'token: "null"',
        'password: "no"',
        'pwd = "1"',
    ])
    def test_sentinels_not_flagged(self, patterns, text):
        assert not _matches(patterns, text), f"sentinel should be ignored: {text}"

    @pytest.mark.parametrize("text", [
        'token: "short"',     # 5 chars < 8
        'secret = "abc"',     # 3 chars
    ])
    def test_short_values_not_flagged(self, patterns, text):
        assert not _matches(patterns, text), f"short value should be ignored: {text}"


class TestSecretGatePreserved:
    @pytest.mark.parametrize("text", [
        'password = "hunter2longpw"',
        'token: "ghp_0123456789abcdefghij"',
        'api_key="sk-abcdef0123456789xyz"',
        'SECRET = "s3cr3t-value-here"',
    ])
    def test_real_secrets_still_flagged(self, patterns, text):
        assert _matches(patterns, text), f"real secret must be flagged: {text}"

    def test_env_var_reference_not_flagged(self, patterns):
        # ${VAR} references are not baked-in literals.
        assert not _matches(patterns, 'secret: "${SECRET_TOKEN}"')


class TestScanUniverse:
    def test_scan_walks_git_tracked_files(self):
        # The scan must use `git ls-files` (committed-secret universe), not a
        # raw filesystem walk that would scan gitignored debris (.env, .omo).
        src = _load_scan_source()
        assert "git" in src and "ls-files" in src, "scan must use git ls-files"
        assert 'Path(".").rglob' not in src, "scan must not rglob the whole tree"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
