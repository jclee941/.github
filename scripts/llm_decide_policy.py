from __future__ import annotations

import json

VALID_RISK = ("low", "medium", "high")

DECISION_SPECS: dict[str, dict] = {
    "issue-label": {
        "actions": ["label", "noop"],
        "destructive": False,
        "fallback": "open",
        "confidence_threshold": 0.0,
        "summary": "Pick GitHub issue labels from the issue title/body.",
    },
    "issue-classify": {
        "actions": ["duplicate", "resolved", "noop"],
        "destructive": False,
        "fallback": "open",
        "confidence_threshold": 0.0,
        "summary": "Classify whether an issue is a duplicate or resolved-by-PR.",
    },
    "repo-stale": {
        "actions": ["stale", "active", "noop"],
        "destructive": False,
        "fallback": "open",
        "confidence_threshold": 0.0,
        "summary": "Decide whether a repository is stale.",
    },
    "pr-stale": {
        "actions": ["stale", "active", "noop"],
        "destructive": False,
        "fallback": "open",
        "confidence_threshold": 0.0,
        "summary": "Decide whether a pull request is stale.",
    },
    "drift": {
        "actions": ["drift", "clean", "noop"],
        "destructive": False,
        "fallback": "open",
        "confidence_threshold": 0.0,
        "summary": "Decide whether a managed file has meaningful drift.",
    },
    "ci-failure-issue": {
        "actions": ["create", "noop"],
        "destructive": False,
        "fallback": "open",
        "confidence_threshold": 0.0,
        "summary": "Decide the failure-issue title/category for a failed run.",
    },
    "pr-command": {
        "actions": ["command", "noop"],
        "destructive": False,
        "fallback": "open",
        "confidence_threshold": 0.0,
        "command_allowlist": ["review", "describe", "describe,review", "improve"],
        "summary": "Pick which pr-agent commands to run for a PR.",
    },
    "branch-to-pr": {
        "actions": ["open", "noop"],
        "destructive": False,
        "fallback": "open",
        "confidence_threshold": 0.0,
        "summary": "Decide whether a pushed branch warrants a draft PR.",
    },
    "ci-failure-close": {
        "actions": ["close", "noop"],
        "destructive": True,
        "fallback": "closed",
        "confidence_threshold": 0.75,
        "summary": "Decide whether to close a CI-failure issue after recovery.",
    },
    "bot-auto-fix": {
        "actions": ["push", "noop"],
        "destructive": True,
        "fallback": "closed",
        "confidence_threshold": 0.75,
        "summary": "Decide whether bot auto-fix changes are safe to push.",
    },
    "release-bump": {
        "actions": ["release", "noop"],
        "destructive": True,
        "fallback": "closed",
        "confidence_threshold": 0.75,
        "valid_bumps": ["major", "minor", "patch", "none"],
        "summary": "Decide the semver bump level for a release.",
    },
}

_DESTRUCTIVE_DECISIONS = {"close", "push", "release", "merge"}


class LLMError(Exception):
    pass


def validate_decision(obj, spec) -> tuple[bool, dict, str]:
    if not isinstance(obj, dict):
        return False, {}, "decision is not an object"

    decision = obj.get("decision")
    if decision not in spec["actions"]:
        return False, {}, f"decision '{decision}' not in allowed actions {spec['actions']}"

    reason = obj.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return False, {}, "missing or empty reason"

    risk = obj.get("risk", "low")
    if risk not in VALID_RISK:
        return False, {}, f"risk '{risk}' not in {VALID_RISK}"

    try:
        confidence = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        return False, {}, "confidence is not a number"
    if not (0.0 <= confidence <= 1.0):
        return False, {}, f"confidence {confidence} out of range [0,1]"

    is_destructive_action = decision in _DESTRUCTIVE_DECISIONS or spec.get("destructive", False)
    if is_destructive_action and decision != "noop":
        if confidence < spec.get("confidence_threshold", 0.75):
            return False, {}, (
                f"destructive decision '{decision}' confidence {confidence} "
                f"below threshold {spec.get('confidence_threshold')}"
            )
        if risk == "high":
            return False, {}, f"refusing high-risk destructive decision '{decision}'"

    command = obj.get("command")
    if decision == "command":
        allow = spec.get("command_allowlist", [])
        if command not in allow:
            return False, {}, f"command '{command}' not in allowlist {allow}"

    bump = obj.get("semver_bump")
    if decision == "release" and bump not in spec.get("valid_bumps", []):
        return False, {}, f"semver_bump '{bump}' not in {spec.get('valid_bumps')}"

    labels = obj.get("labels", [])
    if not isinstance(labels, list):
        return False, {}, "labels is not a list"

    normalized = {
        "decision": decision,
        "confidence": confidence,
        "risk": risk,
        "reason": reason.strip()[:500],
        "labels": [str(x) for x in labels],
        "command": command,
        "semver_bump": bump,
        "requires_human": bool(obj.get("requires_human", False)),
    }
    return True, normalized, ""


def failsafe(decision_type: str, spec: dict, reason: str) -> dict:
    if spec.get("fallback") == "closed":
        return {
            "ok": False, "source": "fallback", "decision_type": decision_type,
            "action": "noop", "confidence": 0.0, "risk": "high",
            "reason": f"fail-closed: {reason}", "labels": [],
            "command": None, "semver_bump": None,
            "requires_human": True, "fallback_used": True,
        }
    return {
        "ok": False, "source": "fallback", "decision_type": decision_type,
        "action": "fallback", "confidence": 0.0, "risk": "low",
        "reason": f"fail-open to deterministic: {reason}", "labels": [],
        "command": None, "semver_bump": None,
        "requires_human": False, "fallback_used": True,
    }


def flatten_output(res: dict) -> list[str]:
    def b(v):
        return "true" if v else "false"

    lines = [
        f"ok={b(res.get('ok'))}",
        f"source={res.get('source')}",
        f"action={res.get('action')}",
        f"confidence={res.get('confidence', 0.0)}",
        f"risk={res.get('risk', 'low')}",
        f"requires_human={b(res.get('requires_human'))}",
        f"fallback_used={b(res.get('fallback_used'))}",
        f"command={res.get('command') if res.get('command') is not None else ''}",
        f"semver_bump={res.get('semver_bump') if res.get('semver_bump') is not None else ''}",
        f"labels={json.dumps(res.get('labels', []))}",
    ]
    reason = str(res.get("reason", "")).replace("\n", " ")
    lines.append(f"reason={reason}")
    return lines
