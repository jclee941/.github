import os

os.environ["AUTO_CAST_FOR_DYNACONF"] = "false"
import json
import logging
import re
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


# loguru's own non-format kwargs that decorate the record but never act as
# str.format() arguments. We must not treat their presence as a hint that
# the caller intended named-placeholder formatting.
_LOGURU_RESERVED_KW = frozenset(
    {
        "exception",
        "record",
        "depth",
        "level",
        "colors",
        "raw",
        "capture",
        "lazy",
        "ansi",
        "catch",
        # pr_agent conventions — stuffed into ``record['extra']`` and never
        # used as positional/named template substitutions.
        "artifact",
        "artifacts",
        "extra",
        "analytics",
        "command",
        "pr_url",
        "event",
        "description",
        "suggestion",
        "error",
        "request_json",
    }
)

_PLACEHOLDER_NAME_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z_0-9]*)(?:[!:][^{}]*)?\}")


class _SafeLogger:
    """Wraps loguru to defuse a foot-gun: when a caller passes a
    pre-rendered message containing literal '{' or '}' (e.g. an f-string
    whose interpolated value contains JSON like ``{"message": ...}``)
    *together* with extra kwargs (artifact=..., extra=...), loguru runs
    ``str.format(*args, **kwargs)`` on it and raises ``KeyError`` because
    the literal braces look like placeholders.

    The wrapper escapes literal braces only when:
      - no positional ``*args`` were supplied, AND
      - no kwarg name matches any ``{name}`` placeholder actually present
        in the message

    This preserves the three legitimate loguru patterns unchanged:
      logger.error('foo: {}', e, artifact={...})       # positional
      logger.info('user {id}', id=42)                  # named-placeholder
      logger.warning('plain message', artifact={...})  # decorative kwargs
    """

    __slots__ = ("_raw",)

    def __init__(self, raw):
        self._raw = raw

    # Fall through to loguru for any non-emit attribute (level, add, opt, bind, contextualize, ...)
    def __getattr__(self, name):
        return getattr(self._raw, name)

    @staticmethod
    def _needs_escape(message, args, kwargs) -> bool:
        if args:
            return False
        if not isinstance(message, str) or ("{" not in message and "}" not in message):
            return False
        # Identify which kwargs the caller might have intended as
        # str.format() substitutions (i.e. not loguru's reserved record-decorating ones).
        format_kwargs = {k for k in kwargs if k not in _LOGURU_RESERVED_KW}
        if not format_kwargs:
            return True
        placeholders = set(_PLACEHOLDER_NAME_RE.findall(message))
        # If any placeholder name corresponds to a non-reserved kwarg, the
        # caller wants real formatting — leave the message alone.
        return placeholders.isdisjoint(format_kwargs)

    def _emit(self, level: str, message, *args, **kwargs):
        if self._needs_escape(message, args, kwargs):
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
        if self._needs_escape(message, args, kwargs):
            message = message.replace("{", "{{").replace("}", "}}")
        self._raw.opt(depth=2).log(lvl, message, *args, **kwargs)


_safe_logger = _SafeLogger(logger)


def get_logger(*args, **kwargs):
    return _safe_logger
