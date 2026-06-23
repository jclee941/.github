from __future__ import annotations

import codecs
import json
import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]


def normalize_llm_readme_response(text: str) -> str:
    if not text:
        return text
    s = text
    s = re.sub(r"<(think|thinking)\b[^>]*>.*?</\1>", "", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"^```[a-zA-Z0-9]*\s*\n", "", s.strip())
    s = re.sub(r"\n```\s*$", "", s).strip()
    if s.startswith("{") and '"content"' in s:
        s = _unwrap_json_content(s)
    fence = re.match(r"^```[a-zA-Z0-9]*\s*\n(.*)\n```\s*$", s, flags=re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    s = re.sub(r"\[(!\[[^\]]*\]\([^)]*\))\]\(#\)", r"\1", s)
    return _strip_generator_meta_notes(s)


def _strip_generator_meta_notes(text: str) -> str:
    lines: list[str] = []
    skipping_note = False
    for line in text.splitlines():
        if skipping_note:
            if not line.strip():
                skipping_note = False
            continue

        normalized = line.lstrip("> ").lower()
        is_note = normalized.startswith(("note:", "참고:", "주의:"))
        mentions_generator_context = any(
            marker in normalized
            for marker in (
                "i noticed",
                "existing readme",
                "stale jclee-bot",
                "automation-policy boilerplate",
                "previous generator",
                "regenerated",
            )
        )
        if is_note and mentions_generator_context:
            skipping_note = True
            continue
        if "i noticed" in normalized and ("readme" in normalized or "jclee-bot" in normalized):
            skipping_note = True
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _unwrap_json_content(s: str) -> str:
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and isinstance(obj.get("content"), str):
            return obj["content"].strip()
    except (json.JSONDecodeError, ValueError):
        mcontent = re.search(r'"content"\s*:\s*"', s)
        if mcontent:
            body = re.sub(r'"\s*\}\s*$', "", s[mcontent.end():])
            try:
                return json.loads('"' + body + '"').strip()
            except (json.JSONDecodeError, ValueError):
                return codecs.decode(body.encode(), "unicode_escape", errors="ignore").strip()
    return s


def sanitize_links(text: str) -> str:
    canonical = "https://github.com/jclee941/.github"
    url_re = re.compile(
        r"https?://(?:www\.)?github\.com/jclee941/([A-Za-z0-9._-]+)(?:/[^\s)\]>\"']*)?"
    )
    known_repos = _known_jclee_repos()

    def _replace(m: re.Match[str]) -> str:
        repo = m.group(1)
        if repo in known_repos:
            return m.group(0)
        return canonical

    return url_re.sub(_replace, text)


def _known_jclee_repos() -> set[str]:
    inventory = _REPO_ROOT / "config" / "repos.yaml"
    try:
        payload = yaml.safe_load(inventory.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {".github"}
    if not isinstance(payload, dict):
        return {".github"}
    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        return {".github"}
    repos = {".github"}
    for repo in repositories:
        if not isinstance(repo, dict):
            continue
        name = repo.get("name")
        if repo.get("visibility") != "public":
            continue
        if isinstance(name, str):
            repos.add(name)
    return repos


def redact_private_ips(text: str) -> str:
    ip_re = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(:\d+)?\b")

    def _is_private(o1: int, o2: int, o3: int, o4: int) -> bool:
        if any(o > 255 for o in (o1, o2, o3, o4)):
            return False
        return o1 == 10 or (o1 == 172 and 16 <= o2 <= 31) or (o1 == 192 and o2 == 168)

    def _replace(m: re.Match[str]) -> str:
        octets = tuple(int(m.group(i)) for i in range(1, 5))
        if not _is_private(*octets):
            return m.group(0)
        return f"<homelab-host>{m.group(5) or ''}"

    return ip_re.sub(_replace, text)
