"""Regression tests for pr_agent.log._SafeLogger.

The wrapper exists to prevent loguru from interpreting literal '{'/'}'
in pre-rendered f-string messages as template placeholders when extra
kwargs are passed (artifact=, extra=, ...).

Production trigger that motivated the wrapper: GithubException for 404
has __str__ like:
    404 {"message": "Not Found", ...}
Logged as:
    logger.error(f"Error: {e}", artifact={"traceback": ...})
which used to raise KeyError('"message"') in loguru._logger._log when it
called message.format(*args, **kwargs).
"""

from __future__ import annotations

import io
import json

import pytest


def _fresh_logger():
    """Reload pr_agent.log so tests can attach a clean sink."""
    import importlib

    from loguru import logger

    logger.remove()
    import pr_agent.log as log_mod

    importlib.reload(log_mod)
    return log_mod, logger


def _attach_serialized_sink(loguru_logger):
    buf = io.StringIO()
    sink_id = loguru_logger.add(buf, level="DEBUG", format="{message}", serialize=True)
    return buf, sink_id


def _records(buf: io.StringIO):
    return [json.loads(line)["record"] for line in buf.getvalue().splitlines() if line]


@pytest.fixture
def safe_logger():
    log_mod, loguru_logger = _fresh_logger()
    buf, sink_id = _attach_serialized_sink(loguru_logger)
    try:
        yield log_mod.get_logger(), buf
    finally:
        loguru_logger.remove(sink_id)


class _GhEx(Exception):
    def __str__(self) -> str:
        return '404 {"message": "Not Found", "documentation_url": "...", "status": "404"}'


def test_fstring_with_kwargs_does_not_raise(safe_logger):
    """The exact production bug: f-string with brace-bearing exception + artifact kwarg."""
    logger, buf = safe_logger
    e = _GhEx()
    # Must not raise KeyError('"message"').
    logger.error(f"Error getting main issue: {e}", artifact={"traceback": "..."})
    records = _records(buf)
    assert len(records) == 1, "exactly one record should be emitted"
    assert records[0]["level"]["name"] == "ERROR"
    assert "Not Found" in records[0]["message"]
    assert '{"message": "Not Found"' in records[0]["message"], (
        "literal braces from the exception payload must survive the safe-format pass"
    )


def test_placeholder_pattern_still_works(safe_logger):
    """Idiomatic loguru pattern with {} and positional args must remain unchanged."""
    logger, buf = safe_logger
    e = _GhEx()
    logger.error("Error: {}", e, artifact={"traceback": "..."})
    records = _records(buf)
    assert len(records) == 1
    assert "Not Found" in records[0]["message"]


def test_plain_message_passthrough(safe_logger):
    """Messages without braces or args must be emitted verbatim."""
    logger, buf = safe_logger
    logger.info("plain status message")
    records = _records(buf)
    assert records[0]["message"] == "plain status message"


def test_caller_metadata_preserved(safe_logger):
    """opt(depth=2) means file/line should point at THIS test, not the wrapper."""
    logger, buf = safe_logger
    logger.warning("caller-metadata-test")
    rec = _records(buf)[0]
    assert rec["file"]["name"].endswith("test_log_safe_logger.py"), f"caller file lost; got {rec['file']}"


def test_exception_method(safe_logger):
    """logger.exception must also handle brace-bearing strings."""
    logger, buf = safe_logger
    try:
        raise _GhEx()
    except Exception as e:  # pragma: no cover - control flow only
        logger.exception(f"Failed: {e}", artifact={"k": "v"})
    rec = _records(buf)[0]
    assert rec["level"]["name"] == "ERROR"  # loguru maps exception -> ERROR level
    assert "Not Found" in rec["message"]


def test_brace_in_kwargs_value_safe(safe_logger):
    """Kwargs values themselves containing braces should never be re-formatted into the message."""
    logger, buf = safe_logger
    logger.error(
        f"Failed to publish: {_GhEx()}",
        artifact={"payload": '{"foo": "bar"}'},
    )
    rec = _records(buf)[0]
    assert "Not Found" in rec["message"]
    # artifact survives in extra
    assert rec["extra"]["artifact"]["payload"] == '{"foo": "bar"}'


def test_named_placeholder_with_kwargs_formats_correctly(safe_logger):
    """Loguru's idiomatic named-placeholder pattern must NOT be escaped."""
    logger, buf = safe_logger
    logger.info("user {id}", id=42)
    rec = _records(buf)[0]
    assert rec["message"] == "user 42", f"named placeholder regression — expected 'user 42', got: {rec['message']!r}"


def test_multiple_named_placeholders(safe_logger):
    """Multiple named placeholders + matching kwargs all interpolate."""
    logger, buf = safe_logger
    logger.info("user {user_id} action {action}", user_id=42, action="login")
    rec = _records(buf)[0]
    assert rec["message"] == "user 42 action login", rec["message"]


def test_plain_message_with_decorative_kwargs_only(safe_logger):
    """Reserved kwargs (artifact, extra, ...) alone must not flip escape on
    when the message has no braces."""
    logger, buf = safe_logger
    logger.warning("plain message", artifact={"data": "x"})
    rec = _records(buf)[0]
    assert rec["message"] == "plain message"
    assert rec["extra"]["artifact"]["data"] == "x"


def test_named_placeholder_with_format_spec(safe_logger):
    """Named placeholder with format spec like {n:.2f}."""
    logger, buf = safe_logger
    logger.info("value {n:.2f}", n=3.14159)
    rec = _records(buf)[0]
    assert rec["message"] == "value 3.14", rec["message"]
