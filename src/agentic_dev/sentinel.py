"""Builder-done sentinel and reviewer checkpoint persistence."""

import os
from datetime import datetime

from agentic_dev.utils import resolve_logs_dir

_BUILDER_DONE_FILE = "builder.done"
_BUILDER_LOG_FILE = "builder.log"
_STALE_LOG_TIMEOUT_MINUTES = 30
_REVIEWER_CHECKPOINT_FILE = "reviewer.checkpoint"
_REVIEWER_LOG_FILE = "reviewer.log"
_TESTER_LOG_FILE = "tester.log"
_VALIDATOR_LOG_FILE = "validator.log"
_AGENT_IDLE_SECONDS = 120


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


def check_builder_done_status(
    sentinel_exists: bool, log_exists: bool, log_age_minutes: float, timeout_minutes: float
) -> bool:
    """Determine if the builder should be considered done.

    Pure function: returns True if the sentinel exists or the log is stale.
    """
    if sentinel_exists:
        return True
    if log_exists and log_age_minutes >= timeout_minutes:
        return True
    return False


def is_builder_done() -> bool:
    """Check if the builder has finished.

    Returns True if:
      1. The sentinel file logs/builder.done exists, OR
      2. logs/builder.log exists but hasn't been modified in 30+ minutes (crash fallback).
    """
    try:
        logs_dir = resolve_logs_dir()

        sentinel_exists = os.path.exists(os.path.join(logs_dir, _BUILDER_DONE_FILE))

        builder_log = os.path.join(logs_dir, _BUILDER_LOG_FILE)
        log_exists = os.path.exists(builder_log)
        log_age_minutes = 0.0
        if log_exists:
            mtime = os.path.getmtime(builder_log)
            log_age_minutes = (datetime.now().timestamp() - mtime) / 60

        return check_builder_done_status(
            sentinel_exists, log_exists, log_age_minutes, _STALE_LOG_TIMEOUT_MINUTES
        )
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


def check_agent_idle(log_exists: bool, log_age_seconds: float, idle_threshold: float) -> bool:
    """Determine if an agent is idle based on its log age.

    Pure function: returns True if the log exists and hasn't been modified
    within idle_threshold seconds, or if the log doesn't exist (agent never started).
    """
    if not log_exists:
        return True
    return log_age_seconds >= idle_threshold


def are_agents_idle() -> bool:
    """Check if the reviewer, tester, and validator are all idle.

    Returns True when all agent logs haven't been modified within
    the idle threshold (120 seconds), meaning they're just sleeping
    in their poll loops with nothing to do.
    """
    try:
        logs_dir = resolve_logs_dir()
        now = datetime.now().timestamp()

        reviewer_log = os.path.join(logs_dir, _REVIEWER_LOG_FILE)
        reviewer_exists = os.path.exists(reviewer_log)
        reviewer_age = (now - os.path.getmtime(reviewer_log)) if reviewer_exists else 0.0

        tester_log = os.path.join(logs_dir, _TESTER_LOG_FILE)
        tester_exists = os.path.exists(tester_log)
        tester_age = (now - os.path.getmtime(tester_log)) if tester_exists else 0.0

        validator_log = os.path.join(logs_dir, _VALIDATOR_LOG_FILE)
        validator_exists = os.path.exists(validator_log)
        validator_age = (now - os.path.getmtime(validator_log)) if validator_exists else 0.0

        return (
            check_agent_idle(reviewer_exists, reviewer_age, _AGENT_IDLE_SECONDS)
            and check_agent_idle(tester_exists, tester_age, _AGENT_IDLE_SECONDS)
            and check_agent_idle(validator_exists, validator_age, _AGENT_IDLE_SECONDS)
        )
    except Exception:
        pass
    return False
