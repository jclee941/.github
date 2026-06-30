from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, BackgroundTasks, Request, Response

from jclee_bot import repo_standardization
from jclee_bot.json_boundary import JsonObject
from jclee_bot.payload_parsing import json_payload_or_error
from jclee_bot.repository_metadata_endpoint import METADATA_OWNER, parse_repo_metadata_owner

router = APIRouter()


@router.post("/api/v1/repo_standardization")
async def repo_standardization_webhook(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
) -> JsonObject:
    expected = os.environ.get("REPO_STANDARDIZATION_TOKEN") or os.environ.get("REPO_METADATA_TOKEN", "")
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
    return handle_repo_standardization_request(
        app_id=app_id,
        private_key=private_key,
        payload=payload,
        response=response,
        background_tasks=background_tasks,
    )


def handle_repo_standardization_request(
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
        repo_names = payload.get("repos")
    except ValueError as exc:
        response.status_code = 400
        return {"error": str(exc)}

    if payload.get("background", False):
        background_tasks.add_task(
            repo_standardization.run_app_repo_standardization_safely,
            app_id=app_id,
            private_key=private_key,
            owner=owner,
            dry_run=dry_run,
            repo_names=repo_names,
        )
        return {"accepted": True, "dry_run": dry_run, "owner": METADATA_OWNER}

    result = repo_standardization.run_app_repo_standardization_safely(
        app_id=app_id,
        private_key=private_key,
        owner=owner,
        dry_run=dry_run,
        repo_names=repo_names,
    )
    summary = result.get("summary")
    if isinstance(summary, dict) and summary.get("status") == "failed":
        response.status_code = 500
    if result.get("error"):
        response.status_code = 500
    return result


def _bearer_token_ok(expected: str, authorization: str | None) -> bool:
    if not expected or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected, authorization.removeprefix("Bearer ").strip())
