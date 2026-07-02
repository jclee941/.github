from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from jclee_bot import issue_maintenance
from jclee_bot.json_boundary import JsonValue

BOT_BODY_MARKER: Final = "jclee-bot에의해자동화됨"
CURRENT_CI_FAILURE_TITLE_RE: Final = re.compile(r"^\[ci\] (?P<workflow>.+) failed at (?P<short_sha>[0-9a-fA-F]{7,40})$")
FULL_SHA_RE: Final = re.compile(r"^[0-9a-fA-F]{40}$")
JSON_OBJECT_LIST_ADAPTER: Final[TypeAdapter[list[dict[str, JsonValue]]]] = TypeAdapter(list[dict[str, JsonValue]])


@dataclass(frozen=True, slots=True)
class ParsedCiFailureIssue:
    number: int
    workflow_name: str
    head_sha: str


def parsed_ci_failure_issues(*, token: str, repo_full_name: str) -> tuple[ParsedCiFailureIssue, ...]:
    issues: list[ParsedCiFailureIssue] = []
    for issue in issue_maintenance.list_open_issues(token=token, repo_full_name=repo_full_name):
        parsed = parse_ci_failure_issue(issue)
        if parsed is not None:
            issues.append(parsed)
    return tuple(issues)


def parse_ci_failure_issue(issue: dict[str, object]) -> ParsedCiFailureIssue | None:
    if isinstance(issue.get("pull_request"), dict):
        return None
    if not (_issue_has_label(issue, "ci-failure") and _issue_has_label(issue, "automated")):
        return None
    title = str(issue.get("title") or "")
    match = CURRENT_CI_FAILURE_TITLE_RE.match(title)
    if match is None:
        return None
    body = str(issue.get("body") or "")
    if BOT_BODY_MARKER not in body:
        return None
    if _body_has_pr_line(body):
        return None
    workflow_name = _body_field(body, "Workflow")
    head_sha = _body_field(body, "Commit")
    if workflow_name is None or head_sha is None:
        return None
    if FULL_SHA_RE.fullmatch(head_sha) is None:
        return None
    if workflow_name != match.group("workflow") or not head_sha.startswith(match.group("short_sha")):
        return None
    issue_number = _int_or_zero(issue.get("number"))
    if issue_number <= 0:
        return None
    return ParsedCiFailureIssue(number=issue_number, workflow_name=workflow_name, head_sha=head_sha)


def _body_field(body: str, field_name: str) -> str | None:
    prefix = f"- **{field_name}:** "
    for line in body.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return None


def _body_has_pr_line(body: str) -> bool:
    return any(line.startswith("- **PR:**") for line in body.splitlines())


def _issue_has_label(issue: dict[str, object], label: str) -> bool:
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return False
    for item in JSON_OBJECT_LIST_ADAPTER.validate_python(labels):
        if item.get("name") == label:
            return True
    return False


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
