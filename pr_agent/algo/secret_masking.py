"""
Secret masking for all downstream outputs (logs, LLM prompts, PR comments, webhook responses).

Design goals:
- Single source of truth: every outgoing string from pr-agent passes through ``mask_text``.
- Two complementary strategies:
    1. **Known-value redaction**: pull live secret values from ``get_settings()`` and replace
       every occurrence verbatim. Catches user-specific tokens that no regex would match.
    2. **Pattern redaction**: regex for well-known secret shapes (GitHub PAT, AWS keys,
       JWT, Bearer headers, OpenAI/Anthropic/Slack keys, PEM blocks, etc.).
- Recursive ``mask_obj`` for nested dict/list payloads (loguru ``artifact=``,
  ``publish_inline_comments`` list-of-dicts, JSON webhook responses, ...).
- Idempotent: running mask_text on already-masked output is a no-op.
- Opt-out via ``config.mask_secrets_in_output`` setting (default ON).
- Fast: compiled regexes; secret-value set cached per call site via the caller.
"""
from __future__ import annotations

import os as _os
import re
from typing import Any, Iterable

REDACTION = "***REDACTED***"

# Setting paths whose VALUES are known to be secrets. Used to pull live secret
# values from get_settings() so they're masked even if they don't match any regex.
# Format: (section, key). Section is matched case-insensitively against Dynaconf
# top-level sections.
_SECRET_SETTING_PATHS: tuple[tuple[str, str], ...] = (
    ("openai", "key"),
    ("openai", "api_key"),
    ("openai", "api_base"),
    ("pinecone", "api_key"),
    ("qdrant", "api_key"),
    ("anthropic", "key"),
    ("anthropic", "api_key"),
    ("cohere", "key"),
    ("replicate", "key"),
    ("groq", "key"),
    ("xai", "key"),
    ("huggingface", "key"),
    ("ollama", "api_key"),
    ("google_ai_studio", "gemini_api_key"),
    ("vertexai", "vertex_project"),
    ("github", "user_token"),
    ("github", "private_key"),
    ("github", "webhook_secret"),
    ("github_action_config", "github_token"),
    ("gitlab", "personal_access_token"),
    ("gitlab", "shared_secret"),
    ("gitea", "personal_access_token"),
    ("gitea", "webhook_secret"),
    ("bitbucket", "bearer_token"),
    ("bitbucket", "basic_token"),
    ("bitbucket_server", "bearer_token"),
    ("bitbucket_server", "webhook_secret"),
    ("bitbucket_server", "app_key"),
    ("azure_devops", "pat"),
    ("azure_devops_server", "webhook_username"),
    ("azure_devops_server", "webhook_password"),
    ("deepseek", "key"),
    ("deepinfra", "key"),
    ("azure_ad", "client_id"),
    ("azure_ad", "client_secret"),
    ("azure_ad", "tenant_id"),
    ("openrouter", "key"),
    ("aws", "AWS_ACCESS_KEY_ID"),
    ("aws", "AWS_SECRET_ACCESS_KEY"),
    ("aws_secrets_manager", "secret_arn"),
    ("litellm", "extra_headers"),
)

# Substring hints inside any setting key. If a key contains any of these
# tokens we treat its value as a secret regardless of section.
_SECRET_KEY_HINTS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "private_key",
    "client_secret",
    "access_key",
    "auth",
)

# Generic patterns for secrets that may appear inline in code, diffs, or text
# even when they aren't in our config. Each entry is (name, compiled regex).
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # AWS Access Key IDs
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA|AIDA|AGPA|AIPA|ANPA|ANVA|AROA)[0-9A-Z]{16}\b")),
    # AWS Secret Access Key heuristic (base64-ish, 40 chars)
    ("aws_secret_access_key",
     re.compile(r"(?i)aws(.{0,20})?(secret|access)[_-]?key[\"'\s:=]+[\"']?([A-Za-z0-9/+=]{40})[\"']?")),
    # GitHub tokens
    ("github_token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("github_fine_grained_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("github_app_jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_.+/=-]{20,}\b")),
    # GitLab personal access tokens
    ("gitlab_pat", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b")),
    # Slack
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    # Stripe
    ("stripe_key", re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{20,}\b")),
    # OpenAI keys
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}\b")),
    # Anthropic keys
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    # Google API keys
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    # Generic Bearer token in HTTP-ish context (mask the secret after "Bearer ")
    ("bearer_token",
     re.compile(r"(?i)\b(authorization|bearer)\s*[:=]\s*\"?(?:Bearer\s+)?([A-Za-z0-9_\-\.=]{20,})\"?")),
    # PEM private key blocks
    ("pem_private_key",
     re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |DSA |EC |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----")),
    # Generic JWT
    ("jwt",
     re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    # Connection strings with embedded user:password@host
    # Covers postgres, postgresql, mysql, mongodb, mongodb+srv, redis, rediss, amqp, amqps, ftp, sftp, ssh, etc.
    ("url_credentials",
     re.compile(r"(?i)\b([a-z][a-z0-9+\-.]*?)://([^:/@\s]+):([^@\s/]+)@")),
    # Azure storage account connection strings (AccountKey=...)
    ("azure_storage_conn",
     re.compile(r"(?i)\bAccountKey\s*=\s*([A-Za-z0-9+/=]{40,})")),
    # Azure Service Bus / Event Hubs SAS
    ("azure_sas",
     re.compile(r"(?i)\bSharedAccessKey\s*=\s*([A-Za-z0-9+/=]{20,})")),
    # Generic KEY=value style secrets in env / .env / shell-export dumps. The KEY must contain
    # one of token|secret|password|api_key|access_key|private_key (case-insensitive). The value
    # is anything non-whitespace of length >= 12 (filters out empty / short placeholders).
    ("env_var_secret",
     re.compile(
         r"\b([A-Z][A-Z0-9_]*?(?:TOKEN|SECRET|PASSWORD|PASSWD|KEY))\s*[:=]\s*['\"]?([^\s'\"`<>${}()\[\];,]{12,})['\"]?")),
    # GitHub App installation tokens (ghs_ already covered) but also short app jwt are caught above.
    # Twilio Account SID / Auth Token
    ("twilio_sid", re.compile(r"\bAC[0-9a-fA-F]{32}\b")),
    ("twilio_token", re.compile(r"(?i)\btwilio[_-]?auth[_-]?token\s*[:=]\s*['\"]?([0-9a-fA-F]{32})['\"]?")),
    # SendGrid
    ("sendgrid_key", re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b")),
    # Mailgun
    ("mailgun_key", re.compile(r"\bkey-[a-f0-9]{32}\b")),
    # Heroku
    ("heroku_key", re.compile(r"\b[hH]eroku[_-]?api[_-]?key\s*[:=]\s*['\"]?([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})['\"]?")),
    # NPM access token
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36,}\b")),
    # PyPI token
    ("pypi_token", re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{20,}\b")),
    # Docker registry tokens
    ("docker_pat", re.compile(r"\bdckr_pat_[A-Za-z0-9_\-]{20,}\b")),
    # ngrok auth tokens
    ("ngrok_token", re.compile(r"\b[0-9a-zA-Z]{20,}_[0-9a-zA-Z]{20,}\b")),
    # Discord bot token
    ("discord_token", re.compile(r"\b[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27,}\b")),
    # Telegram bot token
    ("telegram_token", re.compile(r"\b\d{9,10}:AA[A-Za-z0-9_\-]{32,}\b")),
    # Square access token
    ("square_token", re.compile(r"\bsq0(?:atp|csp)-[0-9A-Za-z\-_]{22,}\b")),
    # Generic Basic-Auth header (mask base64 payload)
    ("basic_auth",
     re.compile(r"(?i)\b(authorization)\s*[:=]\s*['\"]?Basic\s+([A-Za-z0-9+/=]{16,})['\"]?")),
]


# Env-var escape hatches for environments that don't want to pay the cost of
# loading pr_agent.config_loader (e.g. the standalone scan script). Setting
# PR_AGENT_MASK_SECRETS=0 disables masking entirely; setting
# PR_AGENT_MASK_SECRETS_SKIP_CONFIG=1 keeps regex masking on but skips the
# Dynaconf-backed collect_config_secrets path (no live secret values are added).
def _enabled() -> bool:
    """Return True if masking is enabled (default ON)."""
    env = _os.environ.get("PR_AGENT_MASK_SECRETS")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "off", "")
    try:
        from pr_agent.config_loader import get_settings  # local import to avoid cycles

        return bool(get_settings().get("config.mask_secrets_in_output", True))
    except Exception:
        # If settings aren't initialized (e.g. early import), mask by default.
        return True


def _iter_settings_items(node: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    """Yield (path, value) for every leaf in a Dynaconf settings tree.

    Tolerates dicts, lists, and Dynaconf DynaBox-like objects.
    """
    if node is None:
        return
    if isinstance(node, dict):
        items = node.items()
    elif hasattr(node, "items") and callable(node.items):
        try:
            items = list(node.items())
        except Exception:
            return
    else:
        return
    for k, v in items:
        path = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, (dict,)) or (hasattr(v, "items") and callable(v.items) and not isinstance(v, str)):
            yield from _iter_settings_items(v, path)
        else:
            yield path, v


_CACHED_SECRETS: set[str] | None = None


def collect_config_secrets(*, refresh: bool = False) -> set[str]:
    """Snapshot every secret-shaped VALUE currently held in ``get_settings()``.

    Optimized: directly resolves the known ``_SECRET_SETTING_PATHS`` instead of
    walking the entire Dynaconf tree (which triggers fresh_vars on every leaf).
    Cached across calls. Pass ``refresh=True`` after rotating tokens or when a
    new settings file is loaded.
    """
    global _CACHED_SECRETS
    if _CACHED_SECRETS is not None and not refresh:
        return _CACHED_SECRETS
    secrets: set[str] = set()
    if _os.environ.get("PR_AGENT_MASK_SECRETS_SKIP_CONFIG", "").strip().lower() in ("1", "true", "yes", "on"):
        _CACHED_SECRETS = secrets
        return secrets
    try:
        from pr_agent.config_loader import get_settings

        settings = get_settings()
    except Exception:
        _CACHED_SECRETS = secrets
        return secrets

    def _stash(value):
        if isinstance(value, str):
            v = value.strip()
            if len(v) >= 6 and not _looks_like_placeholder(v):
                secrets.add(v)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str):
                    iv = item.strip()
                    if len(iv) >= 6 and not _looks_like_placeholder(iv):
                        secrets.add(iv)

    # Direct lookup of every known secret path. Each settings.get() touches at
    # most two dict layers, which is O(1) and avoids walking unrelated config.
    for section, key in _SECRET_SETTING_PATHS:
        try:
            _stash(settings.get(f"{section}.{key}"))
        except Exception:
            continue

    _CACHED_SECRETS = secrets
    return secrets


_PLACEHOLDER_RE = re.compile(r"^[<\[].*[>\]]$|^(?:xxx+|none|null|n/a|todo|tbd|change[_\-]?me)$", re.IGNORECASE)


def _looks_like_placeholder(value: str) -> bool:
    v = value.strip()
    if not v:
        return True
    if _PLACEHOLDER_RE.match(v):
        return True
    if set(v) <= {".", "x", "X", "0", " "}:
        return True
    return False


def mask_text(text: Any, extra_secrets: Iterable[str] | None = None) -> Any:
    """Mask known and pattern-detected secrets inside ``text``.

    - Non-string input is returned unchanged unless it's a container, in which
      case use :func:`mask_obj`.
    - Idempotent: if ``REDACTION`` already covers the substring, nothing happens.
    """
    if not isinstance(text, str):
        return text
    if not text or not _enabled():
        return text

    out = text

    # 1. Known config values first (exact substring replace)
    known = collect_config_secrets()
    if extra_secrets:
        known = known | {s for s in extra_secrets if isinstance(s, str) and len(s) >= 6}
    # Sort by length descending so longer secrets are replaced before any
    # shorter prefix that might appear inside another.
    for secret in sorted(known, key=len, reverse=True):
        if secret and secret in out:
            out = out.replace(secret, REDACTION)

    # 2. Regex-based generic detection. Most patterns are full-match (whole substring
    # is the secret); a few keep a label readable and only redact a capture group.
    out = _apply_patterns(out)
    return out


# Patterns whose ENTIRE match is the secret -> replace verbatim with REDACTION.
# Patterns where we want to keep a human label visible -> redact a specific
# capture group index (and leave the rest of the match intact).
_GROUP_REDACT = {
    "aws_secret_access_key": 3,
    "bearer_token": 2,
    "basic_auth": 2,
    "url_credentials": 3,   # the password between :...@
    "azure_storage_conn": 1,
    "azure_sas": 1,
    "env_var_secret": 2,    # the value, keep the KEY label readable
    "twilio_token": 1,
    "heroku_key": 1,
}


def _apply_patterns(text: str) -> str:
    for name, pattern in _PATTERNS:
        group = _GROUP_REDACT.get(name)
        if group is None:
            text = pattern.sub(REDACTION, text)
            continue

        def _sub(m: re.Match[str], _g: int = group) -> str:
            try:
                start = m.start(_g) - m.start(0)
                end = m.end(_g) - m.start(0)
            except (IndexError, re.error):
                return REDACTION
            whole = m.group(0)
            return whole[:start] + REDACTION + whole[end:]

        text = pattern.sub(_sub, text)
    return text


def mask_obj(obj: Any, extra_secrets: Iterable[str] | None = None, _depth: int = 0) -> Any:
    """Recursively mask secrets inside arbitrary JSON-ish payloads.

    Dicts, lists, tuples, sets are traversed; strings are masked via
    :func:`mask_text`; everything else is returned unchanged. Depth-bounded
    to defend against malicious cyclic structures.
    """
    if _depth > 12 or not _enabled():
        return obj
    if isinstance(obj, str):
        return mask_text(obj, extra_secrets)
    if isinstance(obj, dict):
        return {k: mask_obj(v, extra_secrets, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_obj(v, extra_secrets, _depth + 1) for v in obj]
    if isinstance(obj, tuple):
        return tuple(mask_obj(v, extra_secrets, _depth + 1) for v in obj)
    if isinstance(obj, set):
        return {mask_obj(v, extra_secrets, _depth + 1) for v in obj}
    return obj


__all__ = [
    "REDACTION",
    "collect_config_secrets",
    "mask_obj",
    "mask_text",
]
