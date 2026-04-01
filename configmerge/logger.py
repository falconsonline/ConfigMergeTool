"""
configmerge.logger
~~~~~~~~~~~~~~~~~~
Logging setup and structured log helpers.

setup_logging() is safe to call multiple times: each call creates a new
named logger with a fresh timestamped log file, so parallel/repeated
runs don't share handlers.
"""

from __future__ import annotations
import logging
import os
import sys
from datetime import datetime


def setup_logging(verbose: bool = False, log_dir: str = "logs") -> logging.Logger:
    """
    Create (or return an existing) logger named 'config-merge'.

    Each call with a fresh process (no existing handlers) creates a new
    timestamped log file.  If handlers already exist the logger is returned
    as-is so a second call within the same run doesn't open a second file.
    """
    # Use a unique logger name per run so tests don't share state
    run_ts   = datetime.now().strftime("%Y%m%d.%H%M%S.%f")[:-3]   # ms precision
    log_name = f"config-merge.{run_ts}"
    logger   = logging.getLogger(log_name)
    logger.setLevel(logging.DEBUG)

    # Guard: if somehow called twice with same name, don't re-add handlers
    if logger.handlers:
        return logger

    os.makedirs(log_dir, exist_ok=True)
    # The log_dir is already the timestamped run directory; keep filename simple.
    log_file = os.path.join(log_dir, "log_merge_config.log")

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # File handler — always DEBUG
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler — writes to stdout so output order is consistent with
    # important() which also uses print() (stdout).  INFO when verbose, WARNING
    # otherwise (WARNING ensures structured warnings are always visible).
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO if verbose else logging.WARNING)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)

    # Prevent propagation to root logger to avoid duplicate output
    logger.propagate = False

    important(f"[LOG FILE] {log_file}", logger)
    return logger


def important(msg: str, logger: logging.Logger) -> None:
    """Print to console AND write to log file regardless of verbose/log level.

    Uses print() for guaranteed console visibility, then writes directly to
    file handlers only — avoiding double-printing when the console handler is
    also at INFO level (--verbose mode).
    """
    print(msg)
    record = logging.LogRecord(
        name=logger.name, level=logging.INFO,
        pathname="", lineno=0, msg=msg, args=(), exc_info=None,
    )
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler):
            h.emit(record)


_LEVEL_MAP = {
    "ERROR":   "error",
    "WARN":    "warning",
    "WARNING": "warning",
    "INFO":    "info",
    "DEBUG":   "debug",
}


def log_structured(
    logger: logging.Logger,
    severity: str,
    ftype: str,
    action: str,
    file: str,
    element: str = "",
    message: str = "",
) -> None:
    """
    Emit a structured log line:
        [TYPE][ACTION][SEVERITY][FILE][ELEMENT] message
    """
    log_msg = f"[{ftype}][{action}][{severity}][{file}][{element}] {message}"
    level   = _LEVEL_MAP.get(severity.upper(), "debug")
    getattr(logger, level)(log_msg)
