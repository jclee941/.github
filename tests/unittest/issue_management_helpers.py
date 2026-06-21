from __future__ import annotations

import hashlib
import hmac
from typing import TypedDict


class LabelCall(TypedDict):
    token: str
    repo_full_name: str
    issue_number: int
    labels: list[str]


class RemoveCall(TypedDict):
    token: str
    repo_full_name: str
    issue_number: int
    label: str


def issue_payload(
    *,
    action: str = "opened",
    title: str = "Bug: crash in coverage workflow",
    body: str | None = "Please add tests for this error.",
    labels: list[dict[str, str]] | None = None,
    state: str = "open",
) -> dict[str, object]:
    return {
        "action": action,
        "installation": {"id": 42},
        "repository": {"full_name": "jclee941/propose"},
        "issue": {
            "number": 7,
            "title": title,
            "body": body,
            "state": state,
            "labels": labels or [],
        },
        "sender": {"login": "octocat", "id": 1},
    }


def signature(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
