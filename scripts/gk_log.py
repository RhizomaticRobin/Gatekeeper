"""Shared logging helper for Gatekeeper Python scripts.

Usage:
    from gk_log import gk_error, gk_warn, gk_info

All messages go to BOTH stderr AND the log file.
Log file: $GATEKEEPER_LOG or .claude/gatekeeper.log
Format: [ISO8601] [LEVEL] [script:line] message
"""

import os
import sys
import inspect
from datetime import datetime, timezone


_LOG_PATH = os.environ.get("GATEKEEPER_LOG", ".claude/gatekeeper.log")


def _gk_log(level: str, msg: str) -> None:
    """Write a log line to stderr and the log file."""
    frame = inspect.stack()[2]
    caller_file = os.path.basename(frame.filename)
    caller_line = frame.lineno
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] [{level}] [{caller_file}:{caller_line}] {msg}"
    print(line, file=sys.stderr)
    try:
        os.makedirs(os.path.dirname(_LOG_PATH) or ".", exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # Log file write is best-effort — stderr is primary


def gk_error(msg: str) -> None:
    """Log an ERROR to stderr and the log file."""
    _gk_log("ERROR", msg)


def gk_warn(msg: str) -> None:
    """Log a WARN to stderr and the log file."""
    _gk_log("WARN", msg)


def gk_info(msg: str) -> None:
    """Log an INFO to stderr and the log file."""
    _gk_log("INFO", msg)
