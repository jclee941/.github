from __future__ import annotations

from typing import cast

import requests
from pytest import MonkeyPatch

from jclee_bot import downstream_ci_runs
from jclee_bot.downstream_ci_runs import WorkflowRef


class _JsonResponse:
    _payload: object

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        return None


def test_workflow_refs_paginates_workflow_inventory(monkeypatch: MonkeyPatch) -> None:
    pages: list[int] = []

    def fake_get(*_: object, **kwargs: object) -> _JsonResponse:
        params = kwargs["params"]
        assert isinstance(params, dict)
        params = cast(dict[str, object], params)
        page_param = params["page"]
        assert isinstance(page_param, int | str)
        page = int(page_param)
        pages.append(page)
        if page == 1:
            return _JsonResponse(
                {"workflows": [{"id": workflow_id, "name": f"Workflow {workflow_id}"} for workflow_id in range(1, 101)]}
            )
        return _JsonResponse({"workflows": [{"id": 101, "name": "Workflow 101"}]})

    monkeypatch.setattr(requests, "get", fake_get)

    refs = downstream_ci_runs.workflow_refs(token="tok", repo_full_name="jclee941/tmux")

    assert pages == [1, 2]
    assert len(refs) == 101
    assert refs[0] == WorkflowRef(id=1, name="Workflow 1")
    assert refs[-1] == WorkflowRef(id=101, name="Workflow 101")


def test_latest_workflow_snapshot_parses_default_branch_run(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(*_: object, **kwargs: object) -> _JsonResponse:
        captured.update(kwargs)
        return _JsonResponse(
            {
                "workflow_runs": [
                    {
                        "id": "42",
                        "head_sha": "abcdef1234567890abcdef1234567890abcdef12",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://github.com/jclee941/tmux/actions/runs/42",
                        "pull_requests": [{"number": "7"}],
                    }
                ]
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)

    snapshot = downstream_ci_runs.latest_workflow_snapshot(
        token="tok",
        repo_full_name="jclee941/tmux",
        workflow=WorkflowRef(id=9, name="CI"),
        branch="master",
    )

    assert captured["params"] == {"per_page": 1, "branch": "master"}
    assert snapshot is not None
    assert snapshot.key == "9"
    assert snapshot.status == "completed"
    assert snapshot.run.name == "CI"
    assert snapshot.run.run_id == 42
    assert snapshot.run.pr_number == 7
    assert snapshot.run.run_url == "https://github.com/jclee941/tmux/actions/runs/42"
