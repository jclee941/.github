from __future__ import annotations

from typing import Any

from jclee_bot import issue_commands, native_health_checks
from jclee_bot.native_health_checks import ALL_CHECKS, CheckName, HealthResult
from jclee_bot.payload_parsing import repo_full_name_from_payload

AUTOMATION_MARKER = "jclee-bot에의해자동화됨"


def _parse_checks(value: Any) -> list[CheckName]:
    raw = value if isinstance(value, list) else [value] if value else list(ALL_CHECKS)
    checks: list[CheckName] = []
    for item in raw:
        normalized = str(item).strip().lower().replace("-", "_")
        if normalized in ALL_CHECKS and normalized not in checks:
            checks.append(normalized)  # type: ignore[arg-type]
    return checks or list(ALL_CHECKS)


def _body(result: HealthResult) -> str:
    detail_lines = [f"- **{key}:** {value}" for key, value in sorted(result.details.items()) if value]
    return "\n".join(
        ["## Native jclee-bot Health", "", result.summary, "", *detail_lines, "", f"_{AUTOMATION_MARKER}._"]
    )


def _commands(results: list[HealthResult]) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for result in results:
        if result.status == "healthy":
            commands.append(
                {
                    "type": "close_matching_issues",
                    "labels": list(result.labels),
                    "title_contains": result.issue_title,
                    "comment": f"Resolved by native jclee-bot health: {result.summary}\n\n_{AUTOMATION_MARKER}._",
                }
            )
        else:
            commands.append(
                {
                    "type": "upsert_issue",
                    "title": result.issue_title,
                    "body": _body(result),
                    "labels": list(result.labels),
                    "update_body": True,
                }
            )
    return commands


def _run_check(check: CheckName, token: str, payload: dict[str, Any]) -> HealthResult:
    match check:
        case "elk_setup":
            return native_health_checks.check_elk_setup(payload)
        case "elk_health":
            return native_health_checks.check_elk_health(payload)
        case "runtime_health":
            return native_health_checks.check_runtime_health(payload)
        case "bot_health":
            return native_health_checks.check_bot_health(token, payload)
    raise AssertionError(f"unsupported native health check: {check}")


def run_native_health(*, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    repo_full_name = repo_full_name_from_payload(payload)
    dry_run = bool(payload.get("dry_run", False))
    if not repo_full_name:
        return {"dry_run": dry_run, "actions": [], "error": "repository is required"}
    requested_checks = _parse_checks(payload.get("checks") or payload.get("check"))
    results = [_run_check(check, token, payload) for check in requested_checks]
    issue_result = issue_commands.run_issue_commands(
        token=token,
        payload={"repository": repo_full_name, "dry_run": dry_run, "commands": _commands(results)},
    )
    return {
        "dry_run": dry_run,
        "repository": repo_full_name,
        "checks": [{"name": r.name, "status": r.status, "summary": r.summary} for r in results],
        "actions": issue_result.get("actions", []),
    }
