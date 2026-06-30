from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, BackgroundTasks, Request, Response

from jclee_bot import repository_metadata
from jclee_bot.json_boundary import JsonObject, JsonValue
from jclee_bot.payload_parsing import json_payload_or_error
from jclee_bot.readme_automation import REPO_PATTERN

METADATA_OWNER = "jclee941"
router = APIRouter()


@router.post("/api/v1/repo_metadata")
async def repo_metadata_webhook(request: Request, response: Response, background_tasks: BackgroundTasks) -> JsonObject:
    expected = os.environ.get("REPO_METADATA_TOKEN", "")
    if not _bearer_token_ok(expected, request.headers.get("Authorization")):
        response.status_code = 401
        return {"error": "invalid token"}

    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
    if not app_id or not private_key:
        response.status_code = 503
        return {"error": "github app credentials unavailable"}

    payload = json_payload_or_error(await request.body(), response)
    if payload is None:
        return {"error": "invalid json"}
    return handle_repo_metadata_request(
        app_id=app_id,
        private_key=private_key,
        payload=payload,
        response=response,
        background_tasks=background_tasks,
    )


def handle_repo_metadata_request(
    *,
    app_id: str,
    private_key: str,
    payload: JsonObject,
    response: Response,
    background_tasks: BackgroundTasks,
) -> JsonObject:
    try:
        dry_run = bool(payload.get("dry_run", False))
        owner = parse_repo_metadata_owner(payload.get("owner"))
        repo_names = parse_repo_metadata_repos(payload.get("repos"))
    except ValueError as exc:
        response.status_code = 400
        return {"error": str(exc)}

    if payload.get("background", False):
        background_tasks.add_task(
            repository_metadata.run_app_repository_metadata_safely,
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            dry_run=dry_run,
            repo_names=repo_names,
        )
        return {"accepted": True, "dry_run": dry_run, "owner": owner}

    return repository_metadata.run_app_repository_metadata_safely(
        app_id=app_id,
        private_key=private_key,
        owner=owner,
        dry_run=dry_run,
        repo_names=repo_names,
    )


def parse_repo_metadata_owner(value: JsonValue) -> str:
    if value is None or value == "":
        return METADATA_OWNER
    if not isinstance(value, str) or value != METADATA_OWNER:
        raise ValueError("owner must be jclee941")
    return value


def parse_repo_metadata_repos(value: JsonValue) -> set[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("repos must be a list")
    repos: set[str] = set()
    for repo in value:
        if not isinstance(repo, str) or not REPO_PATTERN.fullmatch(repo):
            raise ValueError("repos must contain GitHub repository names")
        repos.add(repo)
    return repos


def _bearer_token_ok(expected: str, authorization: str | None) -> bool:
    if not expected or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected, authorization.removeprefix("Bearer ").strip())
