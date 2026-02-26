"""Builder-done sentinel and reviewer checkpoint persistence."""

import glob
import os
import re
from datetime import datetime

from agentic_dev.utils import resolve_logs_dir

_STALE_LOG_TIMEOUT_MINUTES = 30
_BUILDER_ID_RE = re.compile(r"^builder-(\d+)\.(done|log)$")
_REVIEWER_LOG_RE = re.compile(r"^reviewer-\d+\.log$")
_MILESTONE_REVIEWER_LOG_FILE = "milestone-reviewer.log"
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


def are_other_builders_done(exclude_builder_id: int) -> bool:
    """Check if all builders EXCEPT exclude_builder_id have finished.

    Used by the issue builder to detect when all milestone builders are done
    without waiting for its own sentinel (which hasn't been written yet).
    Returns True only when at least one other builder log exists and all
    other builder logs have matching done sentinels or are stale.
    """
    try:
        logs_dir = resolve_logs_dir()
        now = datetime.now().timestamp()
        all_files = os.listdir(logs_dir)
        builder_logs = []
        builder_dones: set[str] = set()
        log_ages: dict[str, float] = {}

        for fname in all_files:
            m = _BUILDER_ID_RE.match(fname)
            if m:
                bid = int(m.group(1))
                if bid == exclude_builder_id:
                    continue
                if m.group(2) == "log":
                    builder_logs.append(fname)
                    path = os.path.join(logs_dir, fname)
                    mtime = os.path.getmtime(path)
                    log_ages[fname] = (now - mtime) / 60
                elif m.group(2) == "done":
                    builder_dones.add(fname)

        if not builder_logs:
            return False

        return check_all_builders_done_status(
            builder_logs, builder_dones, log_ages, _STALE_LOG_TIMEOUT_MINUTES
        )
    except Exception:
        pass
    return False


def clear_builder_done(num_builders: int = 1) -> None:
    """Remove all builder-N.done sentinels for N in 1..num_builders.

    Touches builder log files to reset their mtime so stale-log detection
    doesn't falsely report builders as done before they start.
    """
    try:
        logs_dir = resolve_logs_dir()
        # Remove numbered sentinels and touch log files
        for i in range(1, num_builders + 1):
            sentinel = os.path.join(logs_dir, f"builder-{i}.done")
            if os.path.exists(sentinel):
                os.remove(sentinel)
            log_file = os.path.join(logs_dir, f"builder-{i}.log")
            if os.path.exists(log_file):
                os.utime(log_file)
    except Exception:
        pass


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

        if not builder_logs:
            return False

        return check_all_builders_done_status(
            builder_logs, builder_dones, log_ages, _STALE_LOG_TIMEOUT_MINUTES
        )
    except Exception:
        pass
    return False


def save_reviewer_checkpoint(sha: str, builder_id: int = 1) -> None:
    """Persist the last-reviewed commit SHA so the reviewer never loses its place.

    Writes to reviewer-{N}.branch-checkpoint for the given builder.
    """
    try:
        logs_dir = resolve_logs_dir()
        filename = f"reviewer-{builder_id}.branch-checkpoint"
        path = os.path.join(logs_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(sha + "\n")
    except Exception:
        pass


def load_reviewer_checkpoint(builder_id: int = 1) -> str:
    """Load the last-reviewed commit SHA. Returns empty string if none exists.

    Reads from reviewer-{N}.branch-checkpoint for the given builder.
    """
    try:
        logs_dir = resolve_logs_dir()
        filename = f"reviewer-{builder_id}.branch-checkpoint"
        path = os.path.join(logs_dir, filename)
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
    """Check if reviewers, tester, and validator are all idle.

    Discovery-based: finds all reviewer-N.log files plus milestone-reviewer,
    tester, and validator logs. Returns True when all discovered agent logs
    haven't been modified within the idle threshold (120 seconds).
    """
    try:
        logs_dir = resolve_logs_dir()
        now = datetime.now().timestamp()

        # Collect all log files to check
        logs_to_check: list[str] = []

        # Discover reviewer logs: reviewer-N.log
        all_files = os.listdir(logs_dir)
        for fname in all_files:
            if _REVIEWER_LOG_RE.match(fname):
                logs_to_check.append(fname)

        # Fixed agent logs
        for fixed_log in (_MILESTONE_REVIEWER_LOG_FILE, _TESTER_LOG_FILE, _VALIDATOR_LOG_FILE):
            logs_to_check.append(fixed_log)

        for log_name in logs_to_check:
            log_path = os.path.join(logs_dir, log_name)
            log_exists = os.path.exists(log_path)
            log_age = (now - os.path.getmtime(log_path)) if log_exists else 0.0
            if not check_agent_idle(log_exists, log_age, _AGENT_IDLE_SECONDS):
                return False

        return True
    except Exception:
        pass
    return False
