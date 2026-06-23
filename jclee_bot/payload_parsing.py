from __future__ import annotations

import json
from typing import Any

from fastapi import Response


def json_payload_or_error(raw: bytes, response: Response) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        response.status_code = 400
        return None
    if not isinstance(payload, dict):
        response.status_code = 400
        return None
    return payload


def repo_full_name_from_payload(payload: dict[str, Any]) -> str:
    repository = payload.get("repository")
    if isinstance(repository, dict):
        return str(repository.get("full_name") or "")
    if isinstance(repository, str):
        return repository
    return ""


def default_branch_from_payload(payload: dict[str, Any]) -> str:
    default_branch = payload.get("default_branch")
    if isinstance(default_branch, str) and default_branch:
        return default_branch
    repository = payload.get("repository")
    if isinstance(repository, dict):
        repo_default = repository.get("default_branch")
        if isinstance(repo_default, str) and repo_default:
            return repo_default
    return "master"
