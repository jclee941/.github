#!/usr/bin/env python3
"""Tests for scripts/check_private_ips.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from check_private_ips import count_scanned, find_private_ips, scan_paths


class TestFindPrivateIps:
    def test_detects_192_168(self):
        hits = find_private_ips("backend at 192.168.50.114:8317 is primary")
        assert hits == ["192.168.50.114"]

    def test_detects_10_range(self):
        assert find_private_ips("host 10.0.0.5 here") == ["10.0.0.5"]

    def test_detects_172_16_31_range(self):
        assert find_private_ips("172.16.0.1 and 172.31.255.254") == [
            "172.16.0.1",
            "172.31.255.254",
        ]

    def test_ignores_172_public_edge(self):
        # 172.15 and 172.32 are NOT private
        assert find_private_ips("172.15.0.1 172.32.0.1") == []

    def test_ignores_public_ip(self):
        assert find_private_ips("connect to 8.8.8.8 and 1.1.1.1") == []

    def test_ignores_placeholder(self):
        assert find_private_ips("use <homelab-host>:8317 instead") == []

    def test_ignores_loopback_and_zero(self):
        assert find_private_ips("127.0.0.1 and 0.0.0.0 are fine") == []

    def test_multiple_on_one_line(self):
        hits = find_private_ips("a 192.168.1.1 b 10.1.2.3")
        assert hits == ["192.168.1.1", "10.1.2.3"]


class TestScanPaths:
    def test_flags_markdown_with_private_ip(self, tmp_path: Path):
        f = tmp_path / "README.md"
        f.write_text("CLIProxyAPI at 192.168.50.114:8317\n", encoding="utf-8")
        findings = scan_paths([str(f)])
        assert len(findings) == 1
        assert findings[0].path == str(f)
        assert findings[0].line == 1
        assert "192.168.50.114" in findings[0].ip

    def test_clean_markdown_passes(self, tmp_path: Path):
        f = tmp_path / "README.md"
        f.write_text("CLIProxyAPI at <homelab-host>:8317\n", encoding="utf-8")
        assert scan_paths([str(f)]) == []

    def test_directory_recurses_markdown_only(self, tmp_path: Path):
        (tmp_path / "doc.md").write_text("ip 10.0.0.1\n", encoding="utf-8")
        (tmp_path / "conf.yml").write_text("ip 10.0.0.2\n", encoding="utf-8")
        findings = scan_paths([str(tmp_path)])
        # only the .md file is scanned
        assert len(findings) == 1
        assert findings[0].path.endswith("doc.md")

    def test_reports_line_number(self, tmp_path: Path):
        f = tmp_path / "a.md"
        f.write_text("line1\nline2 192.168.0.9\nline3\n", encoding="utf-8")
        findings = scan_paths([str(f)])
        assert findings[0].line == 2


class TestCountScanned:
    def test_counts_existing_markdown(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("x\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("y\n", encoding="utf-8")
        assert count_scanned([str(tmp_path)]) == 2

    def test_zero_when_paths_missing(self, tmp_path: Path):
        missing = str(tmp_path / "nope.md")
        assert count_scanned([missing]) == 0

    def test_ignores_non_markdown(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("x\n", encoding="utf-8")
        (tmp_path / "c.yml").write_text("y\n", encoding="utf-8")
        assert count_scanned([str(tmp_path)]) == 1


class TestExcludeDirs:
    def test_excludes_vendored_dirs(self, tmp_path: Path):
        (tmp_path / "keep.md").write_text("10.0.0.1\n", encoding="utf-8")
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "skip.md").write_text("10.0.0.2\n", encoding="utf-8")
        findings = scan_paths([str(tmp_path)], exclude_dirs=[".venv"])
        assert len(findings) == 1
        assert findings[0].path.endswith("keep.md")

    def test_count_respects_exclude(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("x\n", encoding="utf-8")
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "b.md").write_text("y\n", encoding="utf-8")
        assert count_scanned([str(tmp_path)], exclude_dirs=["node_modules"]) == 1

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
