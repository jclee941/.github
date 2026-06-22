#!/usr/bin/env python3
"""Detect hardcoded private (RFC 1918) IP addresses in Markdown documentation.

Why this exists
---------------
Documentation across this fork and managed repositories kept leaking
homelab private IPs (e.g. ``192.168.50.114:8317``) into READMEs and
architecture diagrams. Private IPs in docs are noise at best and an internal
network-map disclosure at worst. They should be written as placeholders such
as ``<homelab-host>`` / ``<homelab-elk>`` instead.

This scanner is intentionally documentation-only (``*.md``). Real config files
(``filebeat.yml``, ``docker-compose*.yml``) legitimately need addresses as
environment-variable fallbacks and are out of scope.

Detected ranges (RFC 1918 private):
  - 10.0.0.0/8
  - 172.16.0.0/12   (172.16 - 172.31 only; 172.15 / 172.32 are public)
  - 192.168.0.0/16

Explicitly ignored: loopback (127/8), 0.0.0.0, public IPs, and placeholder
tokens like ``<homelab-host>``.

Usage:
    check_private_ips.py PATH [PATH ...]

Each PATH may be a Markdown file or a directory (recursed for ``*.md``).
Exits non-zero if any private IP is found, printing ``file:line: ip``.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass

# Match any dotted-quad with optional :port, then validate the range in code.
# Using \b avoids matching inside longer numbers; we re-check octets below.
_IP_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")


def _is_private(o1: int, o2: int, o3: int, o4: int) -> bool:
    """True if the four octets fall in an RFC 1918 private range."""
    if any(o > 255 for o in (o1, o2, o3, o4)):
        return False  # not a valid IPv4 octet -> ignore
    if o1 == 10:
        return True
    if o1 == 172 and 16 <= o2 <= 31:
        return True
    if o1 == 192 and o2 == 168:
        return True
    return False


def find_private_ips(text: str) -> list[str]:
    """Return private IPs found in ``text`` (in order of appearance)."""
    hits: list[str] = []
    for m in _IP_RE.finditer(text):
        octets = tuple(int(g) for g in m.groups())
        if _is_private(*octets):
            hits.append(".".join(m.groups()))
    return hits


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    ip: str


_DEFAULT_EXCLUDES = (".venv", "node_modules", ".git", ".ruff_cache", ".mypy_cache", ".pytest_cache")


def _iter_markdown(
    paths: list[str], exclude_dirs: tuple[str, ...] | list[str] | None = None
) -> list[str]:
    """Expand the given paths to a flat list of Markdown files.

    ``exclude_dirs`` names directories (any path segment) to skip while
    recursing, e.g. vendored trees like ``.venv`` / ``node_modules``.
    """
    skip = set(_DEFAULT_EXCLUDES if exclude_dirs is None else exclude_dirs)
    files: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                # prune excluded dirs in-place so os.walk does not descend
                dirs[:] = [d for d in dirs if d not in skip]
                for name in names:
                    if name.endswith(".md"):
                        files.append(os.path.join(root, name))
        elif p.endswith(".md") and os.path.isfile(p):
            files.append(p)
    return files


def count_scanned(
    paths: list[str], exclude_dirs: tuple[str, ...] | list[str] | None = None
) -> int:
    """Return how many Markdown files would actually be scanned."""
    return len(_iter_markdown(paths, exclude_dirs))


def scan_paths(
    paths: list[str], exclude_dirs: tuple[str, ...] | list[str] | None = None
) -> list[Finding]:
    """Scan Markdown files under ``paths`` and return private-IP findings."""
    findings: list[Finding] = []
    for path in _iter_markdown(paths, exclude_dirs):
        try:
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, start=1):
                    for ip in find_private_ips(line):
                        findings.append(Finding(path=path, line=lineno, ip=ip))
        except (OSError, UnicodeDecodeError):
            continue
    return findings


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: check_private_ips.py PATH [PATH ...]", file=sys.stderr)
        return 2

    scanned = count_scanned(args)
    findings = scan_paths(args)
    if not findings:
        print(f"OK: no hardcoded private IPs found ({scanned} Markdown file(s) scanned).")
        return 0

    print("Hardcoded private IP(s) found in documentation:", file=sys.stderr)
    for f in findings:
        print(f"{f.path}:{f.line}: {f.ip}", file=sys.stderr)
    print(
        "\nReplace private IPs with placeholders "
        "(e.g. <homelab-host>, <homelab-elk>) in Markdown docs.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
