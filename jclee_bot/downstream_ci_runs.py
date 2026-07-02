from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import requests
from pydantic import TypeAdapter

from jclee_bot import github_api_client, workflow_issue_automation
from jclee_bot.json_boundary import JsonValue, is_object_mapping, object_dict, object_list

JSON_VALUE_ADAPTER: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)
JSON_OBJECT_LIST_ADAPTER: Final[TypeAdapter[list[dict[str, JsonValue]]]] = TypeAdapter(list[dict[str, JsonValue]])


@dataclass(frozen=True, slots=True)
class WorkflowSnapshot:
    key: str
    status: str
    run: workflow_issue_automation.WorkflowRun


@dataclass(frozen=True, slots=True)
class WorkflowRef:
    id: int
    name: str


def latest_snapshots_by_workflow(snapshots: list[WorkflowSnapshot]) -> tuple[WorkflowSnapshot, ...]:
    latest: dict[str, WorkflowSnapshot] = {}
    for snapshot in snapshots:
        existing = latest.get(snapshot.key)
        if existing is None or snapshot.run.run_id > existing.run.run_id:
            latest[snapshot.key] = snapshot
    return tuple(sorted(latest.values(), key=lambda snapshot: snapshot.run.name))


def workflow_snapshots(
    *,
    token: str,
    repo_full_name: str,
    run_limit: int,
    branch: str | None = None,
) -> list[WorkflowSnapshot]:
    snapshots: list[WorkflowSnapshot] = []
    for workflow in workflow_refs(token=token, repo_full_name=repo_full_name):
        snapshot = latest_workflow_snapshot(
            token=token,
            repo_full_name=repo_full_name,
            workflow=workflow,
            branch=branch,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
        if len(snapshots) >= run_limit:
            break
    return snapshots


def workflow_refs(*, token: str, repo_full_name: str) -> tuple[WorkflowRef, ...]:
    workflows: list[WorkflowRef] = []
    page = 1
    while True:
        response = requests.get(
            f"{github_api_client.GITHUB_API}/repos/{repo_full_name}/actions/workflows",
            headers=github_api_client.headers(token),
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        response.raise_for_status()
        payload = object_dict(_response_json(response), "workflows response must be a mapping")
        raw_workflows = object_list(payload.get("workflows"), "workflows response must contain workflows")
        if not raw_workflows:
            return tuple(workflows)
        for item in raw_workflows:
            if not is_object_mapping(item):
                continue
            workflow = _workflow_ref(object_dict(item))
            if workflow is not None:
                workflows.append(workflow)
        if len(raw_workflows) < 100:
            return tuple(workflows)
        page += 1


def latest_workflow_snapshot(
    *,
    token: str,
    repo_full_name: str,
    workflow: WorkflowRef,
    branch: str | None,
) -> WorkflowSnapshot | None:
    params: dict[str, str | int] = {"per_page": 1}
    if branch:
        params["branch"] = branch
    response = requests.get(
        f"{github_api_client.GITHUB_API}/repos/{repo_full_name}/actions/workflows/{workflow.id}/runs",
        headers=github_api_client.headers(token),
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    payload = object_dict(_response_json(response), "workflow runs response must be a mapping")
    runs = object_list(payload.get("workflow_runs"), "workflow runs response must contain workflow_runs")
    for item in runs:
        if not is_object_mapping(item):
            continue
        return _workflow_snapshot(object_dict(item), workflow)
    return None


def _workflow_ref(workflow: dict[str, object]) -> WorkflowRef | None:
    workflow_id = _int_or_zero(workflow.get("id"))
    name = str(workflow.get("name") or "")
    if workflow_id <= 0 or not name:
        return None
    return WorkflowRef(id=workflow_id, name=name)


def _workflow_snapshot(run: dict[str, object], workflow: WorkflowRef) -> WorkflowSnapshot | None:
    run_id = _int_or_zero(run.get("id"))
    head_sha = str(run.get("head_sha") or "")
    if run_id <= 0 or not head_sha:
        return None
    return WorkflowSnapshot(
        key=str(workflow.id),
        status=str(run.get("status") or ""),
        run=workflow_issue_automation.WorkflowRun(
            name=workflow.name,
            head_sha=head_sha,
            run_id=run_id,
            conclusion=str(run.get("conclusion") or ""),
            pr_number=_pull_request_number(run.get("pull_requests")),
            run_url=str(run.get("html_url") or run.get("url") or ""),
        ),
    )


def _pull_request_number(value: object) -> int:
    if not isinstance(value, list) or not value:
        return 0
    pull_requests = JSON_OBJECT_LIST_ADAPTER.validate_python(value)
    first = pull_requests[0]
    return _int_or_zero(first.get("number"))


def _int_or_zero(value: object) -> int:
    if isinstance(value, bool | float):
        return 0
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return 0
    try:
        return int(value or "0")
    except (OverflowError, ValueError):
        return 0


def _response_json(response: requests.Response) -> JsonValue:
    return JSON_VALUE_ADAPTER.validate_python(response.json())
