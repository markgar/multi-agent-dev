"""Builder-done sentinel and reviewer checkpoint persistence."""

import glob
import os
import re
from datetime import datetime

from agentic_dev.utils import resolve_logs_dir

_BUILDER_DONE_FILE = "builder.done"
_BUILDER_LOG_FILE = "builder.log"
_STALE_LOG_TIMEOUT_MINUTES = 30
_BUILDER_ID_RE = re.compile(r"^builder-(\d+)\.(done|log)$")
_REVIEWER_CHECKPOINT_FILE = "reviewer.checkpoint"
_REVIEWER_LOG_FILE = "reviewer.log"
_TESTER_LOG_FILE = "tester.log"
_VALIDATOR_LOG_FILE = "validator.log"
_AGENT_IDLE_SECONDS = 120


def write_builder_done(builder_id: int = 1) -> None:
    """Write logs/builder-{builder_id}.done sentinel."""
    try:
        logs_dir = resolve_logs_dir()
        sentinel = os.path.join(logs_dir, f"builder-{builder_id}.done")
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
    except Exception:
        pass


def clear_builder_done(num_builders: int = 1) -> None:
    """Remove all builder-N.done sentinels for N in 1..num_builders.

    Also removes the legacy builder.done sentinel if it exists.
    """
    try:
        logs_dir = resolve_logs_dir()
        # Remove numbered sentinels
        for i in range(1, num_builders + 1):
            sentinel = os.path.join(logs_dir, f"builder-{i}.done")
            if os.path.exists(sentinel):
                os.remove(sentinel)
        # Remove legacy sentinel
        legacy = os.path.join(logs_dir, _BUILDER_DONE_FILE)
        if os.path.exists(legacy):
            os.remove(legacy)
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


def check_all_builders_done_status(
    builder_logs: list[str],
    builder_dones: set[str],
    log_ages: dict[str, float],
    timeout_minutes: float,
) -> bool:
    """Determine if all builders should be considered done.

    Pure function. Returns True when at least one builder log exists AND every
    builder log has a matching done sentinel or is stale (age >= timeout).
    """
    if not builder_logs:
        return False
    for log_name in builder_logs:
        done_name = log_name.replace(".log", ".done")
        if done_name in builder_dones:
            continue
        age = log_ages.get(log_name, 0.0)
        if age >= timeout_minutes:
            continue
        return False
    return True


def is_builder_done() -> bool:
    """Check if ALL builders have finished.

    Discovery-based: lists logs/builder-*.log to find active builders,
    then checks each has a matching builder-*.done sentinel.

    Returns True if:
      1. At least one builder-N.log exists AND every builder-N.log has
         a matching builder-N.done sentinel, OR
      2. All builder-N.log files are stale (30+ minutes without writes).

    Also handles the legacy single builder.done / builder.log files.
    """
    try:
        logs_dir = resolve_logs_dir()
        now = datetime.now().timestamp()

        # Discover builder log files (builder-N.log pattern)
        all_files = os.listdir(logs_dir)
        builder_logs = []
        builder_dones: set[str] = set()
        log_ages: dict[str, float] = {}

        for fname in all_files:
            m = _BUILDER_ID_RE.match(fname)
            if m:
                if m.group(2) == "log":
                    builder_logs.append(fname)
                    path = os.path.join(logs_dir, fname)
                    mtime = os.path.getmtime(path)
                    log_ages[fname] = (now - mtime) / 60
                elif m.group(2) == "done":
                    builder_dones.add(fname)

        # If numbered builders exist, use multi-builder logic
        if builder_logs:
            return check_all_builders_done_status(
                builder_logs, builder_dones, log_ages, _STALE_LOG_TIMEOUT_MINUTES
            )

        # Legacy fallback: single builder.done / builder.log
        sentinel_exists = os.path.exists(os.path.join(logs_dir, _BUILDER_DONE_FILE))
        builder_log = os.path.join(logs_dir, _BUILDER_LOG_FILE)
        log_exists = os.path.exists(builder_log)
        log_age_minutes = 0.0
        if log_exists:
            mtime = os.path.getmtime(builder_log)
            log_age_minutes = (now - mtime) / 60

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
