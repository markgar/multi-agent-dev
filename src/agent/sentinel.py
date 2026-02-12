"""Builder-done sentinel and reviewer checkpoint persistence."""

import os
from datetime import datetime

from agent.utils import resolve_logs_dir

_BUILDER_DONE_FILE = "builder.done"
_BUILDER_LOG_FILE = "builder.log"
_STALE_LOG_TIMEOUT_MINUTES = 10
_REVIEWER_CHECKPOINT_FILE = "reviewer.checkpoint"


def write_builder_done() -> None:
    """Write a sentinel file indicating the builder has finished."""
    try:
        logs_dir = resolve_logs_dir()
        sentinel = os.path.join(logs_dir, _BUILDER_DONE_FILE)
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
    except Exception:
        pass


def clear_builder_done() -> None:
    """Remove the builder-done sentinel so agents don't exit prematurely."""
    try:
        logs_dir = resolve_logs_dir()
        sentinel = os.path.join(logs_dir, _BUILDER_DONE_FILE)
        if os.path.exists(sentinel):
            os.remove(sentinel)
    except Exception:
        pass


def is_builder_done() -> bool:
    """Check if the builder has finished.

    Returns True if:
      1. The sentinel file logs/builder.done exists, OR
      2. logs/builder.log exists but hasn't been modified in 10+ minutes (crash fallback).
    """
    try:
        logs_dir = resolve_logs_dir()

        sentinel = os.path.join(logs_dir, _BUILDER_DONE_FILE)
        if os.path.exists(sentinel):
            return True

        builder_log = os.path.join(logs_dir, _BUILDER_LOG_FILE)
        if os.path.exists(builder_log):
            mtime = os.path.getmtime(builder_log)
            age_minutes = (datetime.now().timestamp() - mtime) / 60
            if age_minutes >= _STALE_LOG_TIMEOUT_MINUTES:
                return True

    except Exception:
        pass
    return False


def save_reviewer_checkpoint(sha: str) -> None:
    """Persist the last-reviewed commit SHA so the reviewer never loses its place."""
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, _REVIEWER_CHECKPOINT_FILE)
        with open(path, "w", encoding="utf-8") as f:
            f.write(sha + "\n")
    except Exception:
        pass


def load_reviewer_checkpoint() -> str:
    """Load the last-reviewed commit SHA. Returns empty string if none exists."""
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, _REVIEWER_CHECKPOINT_FILE)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""
