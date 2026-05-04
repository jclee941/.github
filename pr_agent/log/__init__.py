import os

os.environ["AUTO_CAST_FOR_DYNACONF"] = "false"
import json
import logging
import sys
from enum import Enum

from loguru import logger

from pr_agent.config_loader import get_settings


class LoggingFormat(str, Enum):
    CONSOLE = "CONSOLE"
    JSON = "JSON"


def json_format(record: dict) -> str:
    return record["message"]


def analytics_filter(record: dict) -> bool:
    return record.get("extra", {}).get("analytics", False)


def inv_analytics_filter(record: dict) -> bool:
    return not record.get("extra", {}).get("analytics", False)


def setup_logger(level: str = "INFO", fmt: LoggingFormat = LoggingFormat.CONSOLE):
    level: int = logging.getLevelName(level.upper())
    if type(level) is not int:
        level = logging.INFO

    if fmt == LoggingFormat.JSON and os.getenv("LOG_SANE", "0").lower() == "0":  # better debugging github_app
        logger.remove(None)
        logger.add(
            sys.stdout,
            filter=inv_analytics_filter,
            level=level,
            format="{message}",
            colorize=False,
            serialize=True,
        )
    elif fmt == LoggingFormat.CONSOLE:  # does not print the 'extra' fields
        logger.remove(None)
        logger.add(sys.stdout, level=level, colorize=True, filter=inv_analytics_filter)

    log_folder = get_settings().get("CONFIG.ANALYTICS_FOLDER", "")
    if log_folder:
        pid = os.getpid()
        log_file = os.path.join(log_folder, f"pr-agent.{pid}.log")
        logger.add(
            log_file,
            filter=analytics_filter,
            level=level,
            format="{message}",
            colorize=False,
            serialize=True,
        )

    return logger


class _SafeLogger:
    """Wraps loguru to defuse a foot-gun: when a caller passes a
    pre-rendered message containing literal '{' or '}' (e.g. an f-string
    whose interpolated value contains JSON like ``{"message": ...}``)
    *together* with kwargs, loguru runs ``str.format(*args, **kwargs)``
    on it and raises ``KeyError`` because the literal braces look like
    placeholders.

    The wrapper escapes literal braces only when no positional template
    args are passed, preserving the canonical ``logger.error('foo: {}', e,
    artifact=...)`` pattern unchanged.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw):
        self._raw = raw

    # Fall through to loguru for any non-emit attribute (level, add, opt, ...)
    def __getattr__(self, name):
        return getattr(self._raw, name)

    def _emit(self, level: str, message, *args, **kwargs):
        if not args and isinstance(message, str):
            message = message.replace("{", "{{").replace("}", "}}")
        # depth=2 so the record's file/line still points at the caller of
        # error()/warning()/... rather than at this wrapper.
        getattr(self._raw.opt(depth=2), level)(message, *args, **kwargs)

    def trace(self, message, *args, **kwargs):
        self._emit("trace", message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self._emit("debug", message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self._emit("info", message, *args, **kwargs)

    def success(self, message, *args, **kwargs):
        self._emit("success", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._emit("warning", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._emit("error", message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        self._emit("critical", message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        self._emit("exception", message, *args, **kwargs)

    def log(self, lvl, message, *args, **kwargs):
        if not args and isinstance(message, str):
            message = message.replace("{", "{{").replace("}", "}}")
        self._raw.opt(depth=2).log(lvl, message, *args, **kwargs)


_safe_logger = _SafeLogger(logger)


def get_logger(*args, **kwargs):
    return _safe_logger
