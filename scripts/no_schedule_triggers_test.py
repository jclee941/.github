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
    pat = re.compile(r"event_name\s*==\s*'schedule'|event\.schedule\s*==")
    for wf in sorted(glob.glob(".github/workflows/*.yml")):
        for i, line in enumerate(open(wf, encoding="utf-8"), 1):
            if pat.search(line):
                dead.append(f"{os.path.basename(wf)}:{i}")
    assert not dead, f"dead schedule conditionals remain: {dead}"
