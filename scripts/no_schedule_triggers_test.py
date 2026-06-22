#!/usr/bin/env python3
"""Guard: no workflow may use a `schedule` (cron) trigger.

GitOps automation is event-driven; periodic crons were removed in favor of
event triggers + workflow_dispatch. This test fails if any cron reappears and
ensures every workflow remains runnable (has at least one trigger).
"""
from __future__ import annotations

import glob
import os

import yaml


def _load_on(path):
    d = yaml.safe_load(open(path, encoding="utf-8"))
    # PyYAML parses bare `on:` as the boolean key True
    return d.get("on", d.get(True)) if isinstance(d, dict) else None


def test_no_schedule_triggers_anywhere():
    offenders = []
    for wf in sorted(glob.glob(".github/workflows/*.yml")):
        on = _load_on(wf)
        if isinstance(on, dict) and "schedule" in on:
            offenders.append(os.path.basename(wf))
    assert not offenders, f"workflows still using cron schedule: {offenders}"


def test_every_workflow_is_runnable():
    """Every workflow must keep at least one trigger after de-cron."""
    bad = []
    for wf in sorted(glob.glob(".github/workflows/*.yml")):
        on = _load_on(wf)
        if on is None:
            bad.append((os.path.basename(wf), "no 'on:' block"))
            continue
        if isinstance(on, str):
            triggers = [on]
        elif isinstance(on, list):
            triggers = on
        elif isinstance(on, dict):
            triggers = list(on.keys())
        else:
            triggers = []
        if not triggers:
            bad.append((os.path.basename(wf), "no triggers"))
    assert not bad, f"workflows with no runnable trigger: {bad}"


def test_no_dead_schedule_conditionals():
    """No workflow may gate logic on event_name == 'schedule' once crons are gone
    (such a branch would be permanently dead)."""
    import re
    dead = []
    # Catch ==, != and the event.schedule variants — any of these is dead once cron is gone.
    pat = re.compile(r"event_name\s*(==|!=)\s*['\"]schedule['\"]|event\.schedule\s*==")
    for wf in sorted(glob.glob(".github/workflows/*.yml")):
        for i, line in enumerate(open(wf, encoding="utf-8"), 1):
            if pat.search(line):
                dead.append(f"{os.path.basename(wf)}:{i}")
    assert not dead, f"dead schedule conditionals remain: {dead}"


def test_no_residual_schedule_wording_in_comments():
    """After cron removal, workflow comments must not still claim scheduled/daily
    behavior — stale wording misleads maintainers about how automation fires."""
    import re
    stale = []
    pat = re.compile(
        r"daily sweep|run on schedule|runs on schedule|scheduled sweep|schedule is handled|schedule events?",
        re.IGNORECASE,
    )
    for wf in sorted(glob.glob(".github/workflows/*.yml")):
        for i, line in enumerate(open(wf, encoding="utf-8"), 1):
            if pat.search(line):
                stale.append(f"{os.path.basename(wf)}:{i}")
    assert not stale, f"residual schedule wording in comments: {stale}"


_REUSABLE: set[str] = set()

# 40_repo-review-batch is intentionally manual-only: it runs LLM reviews across
# many repos and is gated to workflow_dispatch to keep token spend explicit
# (see its header comment). Event-driving it would cause runaway cost.
#
# The GitOps workflows below are manual-only deprecation markers. Their former
# branch/PR/merge behavior is owned by the jclee-bot GitHub App webhook path.
_MANUAL_ONLY_EXEMPT = {
    "01_branch-to-pr.yml",
    "12_dependabot-auto-merge.yml",
    "13_pr-auto-merge.yml",
    "40_repo-review-batch.yml",
}


def test_no_workflow_is_manual_dispatch_only():
    """Every non-reusable workflow must react to a REAL webhook event, not just
    manual workflow_dispatch. GitOps automation is webhook-event-driven; a
    workflow whose only trigger is workflow_dispatch is effectively dead
    automation (must be manually run).
    """
    manual_only = []
    for wf in sorted(glob.glob(".github/workflows/*.yml")):
        base = os.path.basename(wf)
        on = _load_on(wf)
        if not isinstance(on, dict):
            continue
        keys = set(on.keys())
        # reusable workflows are invoked via workflow_call (a real event)
        if "workflow_call" in keys:
            continue
        if any(base.startswith(p) for p in _REUSABLE):
            continue
        if base in _MANUAL_ONLY_EXEMPT:
            continue
        real_events = keys - {"workflow_dispatch"}
        if not real_events:
            manual_only.append(base)
    assert not manual_only, (
        "workflows with ONLY workflow_dispatch (no webhook event trigger): "
        f"{manual_only}"
    )
