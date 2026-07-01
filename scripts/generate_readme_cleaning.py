from __future__ import annotations

import json
import re
from pathlib import Path
from typing import ClassVar, Final

import yaml
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[1]


class _ContentPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    content: str


class _RepoInventoryEntry(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    visibility: str
    name: str


class _RepoInventory(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    repositories: tuple[_RepoInventoryEntry, ...]


_REPO_INVENTORY_MODEL_READY: Final[bool | None] = _RepoInventory.model_rebuild()
_JSON_STRING_ADAPTER: Final[TypeAdapter[str]] = TypeAdapter(str)
_KNOWN_STALE_BRANDING_REPLACEMENTS: Final[tuple[tuple[str, str], ...]] = (
    ("레쥬메 모노레포 / Resume Portfolio Monorepo", "포트폴리오 자동화 워크스페이스 / Portfolio Automation Workspace"),
    ("Resume portfolio monorepo:", "Portfolio automation workspace:"),
    ("Resume Portfolio Monorepo", "Portfolio Automation Workspace"),
    ("npm 워크스페이스 모노레포", "npm 워크스페이스 빌드"),
    ("npm workspaces monorepo", "npm workspaces build"),
    ("private npm workspaces build", "private automation workspace"),
    ("이 모노레포", "이 워크스페이스"),
)
_STALE_RESUME_MONOREPO_RE: Final[re.Pattern[str]] = re.compile(
    r"\br[eé]sum[eé](?:[-\s]+(?:site|portfolio|workspace|automation|dashboard|private|npm))*[-\s]+monorepo\b",
    re.IGNORECASE,
)
_STALE_KOREAN_RESUME_MONOREPO_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:레쥬메|이력서)(?:\s+(?:포트폴리오|사이트|자동화|대시보드|워크스페이스))*\s+모노레포"
)
_NPM_WORKSPACE_MONOREPO_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnpm\s+workspaces?\s+monorepo\b",
    re.IGNORECASE,
)


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
    s = _strip_generator_meta_notes(s)
    return _repair_known_stale_branding(s)


def _repair_known_stale_branding(text: str) -> str:
    repaired = text
    for stale, replacement in _KNOWN_STALE_BRANDING_REPLACEMENTS:
        repaired = repaired.replace(stale, replacement)
    repaired = _STALE_RESUME_MONOREPO_RE.sub("Portfolio Automation Workspace", repaired)
    repaired = _STALE_KOREAN_RESUME_MONOREPO_RE.sub("포트폴리오 자동화 워크스페이스", repaired)
    repaired = _NPM_WORKSPACE_MONOREPO_RE.sub("npm workspaces build", repaired)
    repaired = re.sub(
        r"하나의\s+npm 워크스페이스 빌드로\s+통합한",
        "하나의 자동화 워크스페이스로 통합한",
        repaired,
    )
    return repaired


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
        return _ContentPayload.model_validate_json(s).content.strip()
    except (ValidationError, ValueError):
        mcontent = re.search(r'"content"\s*:\s*"', s)
        if mcontent:
            body = re.sub(r'"\s*\}\s*$', "", s[mcontent.end():])
            try:
                return _JSON_STRING_ADAPTER.validate_json('"' + body + '"').strip()
            except (json.JSONDecodeError, ValueError):
                return body.encode().decode("unicode_escape", errors="ignore").strip()
    return s


def sanitize_links(text: str) -> str:
    canonical = "https://github.com/jclee941/jclee-bot"
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
        payload = _RepoInventory.model_validate(yaml.safe_load(inventory.read_text(encoding="utf-8")))
    except (OSError, ValidationError, yaml.YAMLError):
        return {"jclee-bot"}
    repos = {"jclee-bot"}
    for repo in payload.repositories:
        if repo.visibility != "public":
            continue
        repos.add(repo.name)
    return repos


def known_jclee_repos() -> set[str]:
    return _known_jclee_repos()


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
