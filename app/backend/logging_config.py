"""
Application logging configuration for console and file diagnostics.

The module centralizes logging setup for the API runtime. It keeps Docker
stdout useful while also writing persistent files under ``LOG_DIR`` so local
and swarm deployments can mount the directory for later inspection.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo


DEFAULT_LOG_DIR = "/app/logs"
DEFAULT_TIMEZONE = "Europe/Berlin"
LOG_FORMAT = "[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DAY_FORMAT = "%Y-%m-%d"
TRUTHY_VALUES = {"true", "1", "yes", "y", "on"}
SENSITIVE_FIELD_PARTS = {"authorization", "cookie", "key", "password", "secret", "token"}
SENSITIVE_TEXT_PATTERNS = (
    (re.compile(r"bot\d+:[A-Za-z0-9_-]+"), "bot***REDACTED***"),
)
STANDARD_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {
    "asctime",
    "color_message",
    "message",
}

_setup_done = False
_timezone = ZoneInfo(DEFAULT_TIMEZONE)


class UvicornStartupLabelFilter(logging.Filter):
    """
    Rewrite the displayed logger name for informational uvicorn.error records.

    Uvicorn unconditionally routes *all* lifecycle messages (startup, shutdown,
    address announcement) through the ``uvicorn.error`` logger regardless of
    their actual severity.  That makes lines like::

        [INFO] [uvicorn.error] Application startup complete.

    look like error reports.  This filter renames the logger to ``uvicorn``
    for any record below WARNING so the startup stream reads clearly.  Records
    at WARNING or above keep the original ``uvicorn.error`` name so genuine
    error context is preserved.

    The filter is attached to output handlers rather than to a logger so the
    rename is applied uniformly on every channel without changing log routing.

    Attributes:
        None beyond the base ``logging.Filter`` attributes.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Optionally rename the ``uvicorn.error`` logger on sub-WARNING records.

        Args:
            record (logging.LogRecord): The log record being evaluated.

        Returns:
            bool: Always True — this filter never drops records, only renames.
        """
        if record.name == "uvicorn.error" and record.levelno < logging.WARNING:
            record.name = "uvicorn"
        return True


def _env_var_is_truthy(name: str) -> bool:
    """
    Return whether an environment variable contains a truthy value.

    Args:
        name (str): Environment variable name to inspect.

    Returns:
        bool: True when the value is one of the supported truthy strings,
            otherwise False for missing, empty, or unrecognized values.
    """
    return os.getenv(name, "").strip().lower() in TRUTHY_VALUES


def _resolve_log_level() -> int:
    """
    Resolve the effective root logging level from environment variables.

    ``LOG_LEVEL`` takes precedence when it names a standard logging level.
    Otherwise ``DEBUG`` or ``DEBUG_ENABLED`` enables DEBUG logging, and INFO is
    used as the safe default.

    Returns:
        int: Standard library logging level constant.
    """
    configured_level = os.getenv("LOG_LEVEL", "").strip().upper()
    if configured_level:
        level = logging.getLevelName(configured_level)
        if isinstance(level, int):
            return level

    if _env_var_is_truthy("DEBUG") or _env_var_is_truthy("DEBUG_ENABLED"):
        return logging.DEBUG
    return logging.INFO


def _serialize_field(value: object) -> str:
    """
    Serialize one extra log field for key-value output.

    Args:
        value (object): Value attached to a ``logging`` record via ``extra``.

    Returns:
        str: JSON-compatible compact string representation.
    """
    sanitized_value = _redact_sensitive_text(value) if isinstance(value, str) else value
    try:
        return json.dumps(sanitized_value, ensure_ascii=True, separators=(",", ":"), default=str)
    except Exception:
        return json.dumps(_redact_sensitive_text(str(value)), ensure_ascii=True, separators=(",", ":"))


def _redact_sensitive_text(value: str) -> str:
    """
    Redact known secret-bearing text fragments from log messages.

    Args:
        value (str): Log message or field value before rendering.

    Returns:
        str: Sanitized text with supported secret patterns replaced.
    """
    sanitized = value
    for pattern, replacement in SENSITIVE_TEXT_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def _is_sensitive_field(field_name: str) -> bool:
    """
    Return whether a log field name should have its value redacted.

    Args:
        field_name (str): Name of the field attached to a log record.

    Returns:
        bool: True when the field name appears to contain credentials or other
            sensitive authentication material.
    """
    normalized = field_name.lower()
    return any(part in normalized for part in SENSITIVE_FIELD_PARTS)


class ExtraKeyValueFormatter(logging.Formatter):
    """
    Formatter that appends safe ``extra`` fields as key-value pairs.

    Attributes:
        timezone (ZoneInfo): Timezone used for timestamps.

    Side Effects:
        Reads ``logging.LogRecord`` attributes and redacts sensitive field
        values before rendering them to stdout or files.
    """

    def __init__(self, fmt: str, datefmt: str, timezone: ZoneInfo) -> None:
        """
        Initialize the formatter.

        Args:
            fmt (str): Base logging format string.
            datefmt (str): Timestamp format string.
            timezone (ZoneInfo): Timezone for rendered timestamps.

        Returns:
            None: Formatter instance is initialized in place.
        """
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.timezone = timezone

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """
        Format record creation time in the configured timezone.

        Args:
            record (logging.LogRecord): Log record being rendered.
            datefmt (str | None): Optional timestamp format override.

        Returns:
            str: Timestamp string in the configured timezone.
        """
        timestamp = datetime.fromtimestamp(record.created, tz=self.timezone)
        return timestamp.strftime(datefmt or LOG_DATE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        """
        Render one log record with appended structured fields.

        Args:
            record (logging.LogRecord): Log record containing message and
                optional ``extra`` fields.

        Returns:
            str: Fully formatted log line.
        """
        message = _redact_sensitive_text(super().format(record))
        extra_parts: list[str] = []
        for key in sorted(record.__dict__):
            if key in STANDARD_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            value = "***REDACTED***" if _is_sensitive_field(key) else record.__dict__[key]
            extra_parts.append(f"{key}={_serialize_field(value)}")
        if not extra_parts:
            return message
        return f"{message} {' '.join(extra_parts)}"


class DayBasedFileHandler(logging.Handler):
    """
    File handler that writes one log file per local day.

    Attributes:
        log_dir (str): Directory containing day-based log files.
        suffix (str): File name suffix appended after the date.
        current_day (str): Day string for the currently opened file.

    Side Effects:
        Creates the day-based log directory and appends log records to files.
    """

    def __init__(self, log_dir: str, suffix: str) -> None:
        """
        Initialize the day-based file handler.

        Args:
            log_dir (str): Base log directory.
            suffix (str): File suffix such as ``_log.txt``.

        Returns:
            None: Handler instance is initialized in place.
        """
        super().__init__()
        self.log_dir = os.path.join(log_dir, "dayBased")
        self.suffix = suffix
        self.current_day = ""
        self.current_file = None
        os.makedirs(self.log_dir, exist_ok=True)

    def _day_string(self) -> str:
        """
        Return the current day string used for file rotation.

        Returns:
            str: Current date formatted as ``YYYY-MM-DD``.
        """
        return datetime.now(_timezone).strftime(DAY_FORMAT)

    def _open_file(self, day: str) -> None:
        """
        Open the log file for one day, closing the previous file if needed.

        Args:
            day (str): Date string used in the log file name.

        Returns:
            None: Handler state is updated in place.
        """
        if self.current_file is not None:
            self.current_file.close()
        path = os.path.join(self.log_dir, f"{day}{self.suffix}")
        self.current_file = open(path, "a", encoding="utf-8")
        self.current_day = day

    def emit(self, record: logging.LogRecord) -> None:
        """
        Write one record to the current day-based file.

        Args:
            record (logging.LogRecord): Log record to append.

        Returns:
            None: Writes the formatted line to disk.
        """
        try:
            day = self._day_string()
            if day != self.current_day:
                self._open_file(day)
            if self.current_file is None:
                return
            self.current_file.write(self.format(record) + "\n")
            self.current_file.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """
        Close the active day-based file handle.

        Returns:
            None: Releases the file handle and delegates to the base handler.
        """
        if self.current_file is not None:
            self.current_file.close()
            self.current_file = None
        super().close()


def _configure_logger_hierarchy(level: int) -> None:
    """
    Route root and framework loggers through the shared handlers with
    appropriate verbosity clamping.

    Uvicorn startup lines (uvicorn.error at INFO) are kept so the API
    address and process ID remain visible. Per-request access lines
    (uvicorn.access) are suppressed at INFO because they produce a line
    per request and obscure lifecycle events; they remain visible at DEBUG.

    SQLAlchemy engine loggers echo every SQL statement at INFO when the
    SQLAlchemy ``echo`` flag is set or propagation reaches the root logger.
    They are clamped to WARNING in normal operation so the startup stream
    does not repeat every SELECT/ROLLBACK from the migration probe. DEBUG
    mode restores full SQL echo for developer inspection.

    HTTP client loggers (httpx, httpcore) can log full provider URLs
    containing credentials; they are held at WARNING unconditionally.

    Args:
        level (int): Effective root logging level resolved from environment.

    Returns:
        None: Logger hierarchy is configured in place.
    """
    for logger_name in ("uvicorn", "uvicorn.error"):
        target_logger = logging.getLogger(logger_name)
        target_logger.handlers.clear()
        target_logger.propagate = True
        target_logger.setLevel(level)

    # Suppress per-request access lines unless the operator explicitly wants
    # DEBUG output — at INFO they flood the startup stream.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = True
    access_logger.setLevel(level if level <= logging.DEBUG else logging.WARNING)

    # Clamp SQLAlchemy engine echo at WARNING in normal operation to avoid
    # duplicated SQL probe lines during startup. DEBUG restores full echo.
    sqlalchemy_level = level if level <= logging.DEBUG else logging.WARNING
    for logger_name in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy"):
        target_logger = logging.getLogger(logger_name)
        target_logger.setLevel(sqlalchemy_level)

    # HTTP client DEBUG logs can include fully expanded provider URLs with
    # credentials. Provider modules log sanitized request outcomes themselves.
    for logger_name in ("httpx", "httpcore"):
        target_logger = logging.getLogger(logger_name)
        target_logger.setLevel(logging.WARNING)


def setup_logging(log_dir: str | None = None) -> None:
    """
    Configure console and persistent file logging for the API process.

    Args:
        log_dir (str | None): Directory where log files are written. When None,
            ``LOG_DIR`` is read from the environment and then falls back to
            ``/app/logs``.

    Returns:
        None: Global logging is configured once per process.

    Side Effects:
        Creates log directories/files, clears existing root handlers, and
        redirects uvicorn loggers into the shared handler chain.
    """
    global _setup_done, _timezone
    if _setup_done:
        return
    _setup_done = True

    resolved_log_dir = log_dir or os.getenv("LOG_DIR", DEFAULT_LOG_DIR)
    os.makedirs(resolved_log_dir, exist_ok=True)

    timezone_name = os.getenv("LOG_TIMEZONE", DEFAULT_TIMEZONE)
    try:
        _timezone = ZoneInfo(timezone_name)
    except Exception:
        _timezone = ZoneInfo(DEFAULT_TIMEZONE)

    level = _resolve_log_level()
    formatter = ExtraKeyValueFormatter(LOG_FORMAT, LOG_DATE_FORMAT, _timezone)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    # Rename "uvicorn.error" → "uvicorn" on INFO/DEBUG lines so startup output
    # does not read like an error stream to developers.
    startup_label_filter = UvicornStartupLabelFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(startup_label_filter)
    root.addHandler(console_handler)

    combined_file_handler = logging.FileHandler(
        os.path.join(resolved_log_dir, "log.txt"),
        encoding="utf-8",
    )
    combined_file_handler.setLevel(level)
    combined_file_handler.setFormatter(formatter)
    combined_file_handler.addFilter(startup_label_filter)
    root.addHandler(combined_file_handler)

    error_file_handler = logging.FileHandler(
        os.path.join(resolved_log_dir, "errorlog.txt"),
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.WARNING)
    error_file_handler.setFormatter(formatter)
    root.addHandler(error_file_handler)

    day_log_handler = DayBasedFileHandler(resolved_log_dir, "_log.txt")
    day_log_handler.setLevel(level)
    day_log_handler.setFormatter(formatter)
    root.addHandler(day_log_handler)

    day_error_handler = DayBasedFileHandler(resolved_log_dir, "_errorlog.txt")
    day_error_handler.setLevel(logging.WARNING)
    day_error_handler.setFormatter(formatter)
    root.addHandler(day_error_handler)

    _configure_logger_hierarchy(level)

    logging.getLogger("backend.logging_config").info(
        "logging.initialized",
        extra={
            "log_dir": resolved_log_dir,
            "level": logging.getLevelName(level),
            "timezone": getattr(_timezone, "key", str(_timezone)),
        },
    )
