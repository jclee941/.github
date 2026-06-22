from __future__ import annotations

from collections.abc import Sequence

from jclee_bot.checks import CheckResult

NEEDS_CHECKOUT = {"jclee-bot / secret-scan", "jclee-bot / actionlint", "jclee-bot / docs-policy"}
NEEDS_CHANGED_FILES = {
    "jclee-bot / pr-metadata",
    "jclee-bot / secret-scan",
    "jclee-bot / actionlint",
    "jclee-bot / docs-policy",
}
REQUIRED_FAIL_CLOSED = {
    "jclee-bot / pr-metadata",
    "jclee-bot / secret-scan",
    "jclee-bot / actionlint",
}
REQUIRED_TOOL_SKIPPED_TITLES = {
    "jclee-bot / secret-scan": {"secret scan skipped"},
    "jclee-bot / actionlint": {"actionlint not run"},
}


def _failure_result(result: CheckResult, reasons: list[str]) -> CheckResult:
    return CheckResult(
        name=result.name,
        conclusion="failure",
        title="required check blocked",
        summary="; ".join(reasons) + " - required check could not verify real PR content.",
    )


def _required_tool_skipped(result: CheckResult) -> bool:
    return (
        result.conclusion == "neutral"
        and result.title in REQUIRED_TOOL_SKIPPED_TITLES.get(result.name, set())
    )


def neutralize_on_missing_context(
    results: Sequence[CheckResult],
    *,
    files_ok: bool,
    checkout_ok: bool,
) -> list[CheckResult]:
    out: list[CheckResult] = []
    for result in results:
        if result.conclusion == "failure":
            out.append(result)
            continue
        if (
            result.name == "jclee-bot / actionlint"
            and result.title == "no workflow changes"
            and files_ok
        ):
            out.append(result)
            continue
        missing: list[str] = []
        if result.name in NEEDS_CHECKOUT and not checkout_ok:
            missing.append("PR checkout unavailable")
        if result.name in NEEDS_CHANGED_FILES and not files_ok:
            missing.append("changed-files API unavailable")
        if _required_tool_skipped(result):
            missing.append("required check skipped")
        if missing:
            if result.name in REQUIRED_FAIL_CLOSED:
                out.append(_failure_result(result, missing))
            else:
                out.append(CheckResult(
                    name=result.name,
                    conclusion="neutral",
                    title="skipped (context unavailable)",
                    summary="; ".join(missing) + " - check could not run against real PR content.",
                ))
        else:
            out.append(result)
    return out
