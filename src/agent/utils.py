"""Shared utility functions for logging, running commands, and helpers."""

import contextlib
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

from rich.console import Console

console = Console()


@contextlib.contextmanager
def pushd(path: str):
    """Context manager that changes to a directory and restores on exit."""
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def resolve_logs_dir() -> str:
    """Find the project root logs directory, creating it if needed."""
    current_dir_name = os.path.basename(os.getcwd())
    if current_dir_name in ("builder", "reviewer", "tester", "watcher"):
        project_root = os.path.dirname(os.getcwd())
    else:
        project_root = os.getcwd()
    logs_dir = os.path.join(project_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


def log(agent_name: str, message: str, style: str = "") -> None:
    """Write a message to both the console (with optional style) and the agent log file."""
    if style:
        console.print(message, style=style)
    else:
        console.print(message)

    try:
        logs_dir = resolve_logs_dir()
        log_file = os.path.join(logs_dir, f"{agent_name}.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass  # Never break the workflow over logging


def run_copilot(agent_name: str, prompt: str) -> int:
    """
    Run 'copilot --yolo -p <prompt>' with streaming output to both console and log.
    Returns the process exit code.
    """
    logs_dir = resolve_logs_dir()
    log_file = os.path.join(logs_dir, f"{agent_name}.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt_preview = prompt[:100]

    # Write header to log
    header = (
        f"\n========== [{timestamp}] {agent_name} ==========\n"
        f"Prompt: {prompt_preview}...\n"
        f"--- output ---\n"
    )
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(header)
    except Exception:
        pass

    # Run copilot with streaming tee to console + log
    proc = subprocess.Popen(
        ["copilot", "--yolo", "-p", prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line-buffered
    )

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                try:
                    f.write(line)
                except Exception:
                    pass
    except Exception:
        pass

    proc.wait()
    exit_code = proc.returncode

    # Write footer to log
    footer = f"--- end (exit: {exit_code}) ---\n"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(footer)
    except Exception:
        pass

    return exit_code


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform == "win32"


def check_command(name: str) -> bool:
    """Check if a command is available on PATH."""
    return shutil.which(name) is not None


def run_cmd(
    args: list[str], capture: bool = False, quiet: bool = False
) -> subprocess.CompletedProcess:
    """Run a shell command, optionally capturing output."""
    kwargs = {}
    if capture or quiet:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        kwargs["text"] = True
    return subprocess.run(args, **kwargs)


def git_push_with_retry(agent_name: str = "", max_attempts: int = 3, backoff: int = 5) -> bool:
    """Run git pull --rebase && git push with retry on conflict.

    If the rebase conflicts, aborts it, waits, and retries.
    Returns True if push eventually succeeded, False if all attempts failed.
    """
    for attempt in range(1, max_attempts + 1):
        pull_result = run_cmd(["git", "pull", "--rebase"], capture=True)
        if pull_result.returncode != 0:
            # Rebase conflict — abort and retry
            run_cmd(["git", "rebase", "--abort"], quiet=True)
            if agent_name:
                log(
                    agent_name,
                    f"Rebase conflict (attempt {attempt}/{max_attempts}), retrying in {backoff}s...",
                    style="yellow",
                )
            if attempt < max_attempts:
                time.sleep(backoff)
                continue
            else:
                if agent_name:
                    log(agent_name, "Push failed after all retry attempts.", style="red")
                return False

        push_result = run_cmd(["git", "push"], capture=True)
        if push_result.returncode == 0:
            return True

        # Push rejected (e.g. non-fast-forward) — retry the whole pull+push
        if agent_name:
            log(
                agent_name,
                f"Push rejected (attempt {attempt}/{max_attempts}), retrying in {backoff}s...",
                style="yellow",
            )
        if attempt < max_attempts:
            time.sleep(backoff)

    if agent_name:
        log(agent_name, "Push failed after all retry attempts.", style="red")
    return False


def has_unchecked_items(filepath: str) -> int:
    """Count unchecked checkbox items ([ ]) in a file. Returns 0 if file doesn't exist."""
    if not os.path.exists(filepath):
        return 0
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return len(re.findall(r"\[ \]", content))


# ============================================
# Builder sentinel helpers
# ============================================

_BUILDER_DONE_FILE = "builder.done"
_BUILDER_LOG_FILE = "builder.log"
_STALE_LOG_TIMEOUT_MINUTES = 10


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

        # Primary: sentinel file
        sentinel = os.path.join(logs_dir, _BUILDER_DONE_FILE)
        if os.path.exists(sentinel):
            return True

        # Fallback: stale log file (builder probably crashed)
        builder_log = os.path.join(logs_dir, _BUILDER_LOG_FILE)
        if os.path.exists(builder_log):
            mtime = os.path.getmtime(builder_log)
            age_minutes = (datetime.now().timestamp() - mtime) / 60
            if age_minutes >= _STALE_LOG_TIMEOUT_MINUTES:
                return True

    except Exception:
        pass
    return False


# ============================================
# Reviewer checkpoint helpers
# ============================================

_REVIEWER_CHECKPOINT_FILE = "reviewer.checkpoint"


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


# ============================================
# Milestone review helpers
# ============================================

_MILESTONE_CHECKPOINT_FILE = "reviewer.milestone"
_MILESTONE_LOG_FILE = "milestones.log"


# --- Shared milestone boundary log (append-only, written by build loop) ---


def record_milestone_boundary(name: str, start_sha: str, end_sha: str) -> None:
    """Append a completed milestone's SHA range to logs/milestones.log.

    This is the shared source of truth for milestone boundaries.
    Written by the build loop (deterministic code, not prompts).
    Format: name|start_sha|end_sha
    """
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, _MILESTONE_LOG_FILE)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}|{start_sha}|{end_sha}\n")
    except Exception:
        pass


def load_milestone_boundaries() -> list[dict]:
    """Load all recorded milestone boundaries from logs/milestones.log.

    Returns a list of dicts: [{"name": str, "start_sha": str, "end_sha": str}, ...]
    in the order they were recorded.
    """
    boundaries = []
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, _MILESTONE_LOG_FILE)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("|")
                    if len(parts) == 3:
                        boundaries.append({
                            "name": parts[0],
                            "start_sha": parts[1],
                            "end_sha": parts[2],
                        })
    except Exception:
        pass
    return boundaries


def get_last_milestone_end_sha() -> str:
    """Return the end SHA of the most recently completed milestone.

    Falls back to the initial bootstrap commit (root commit) if no milestones
    have been recorded yet.
    """
    boundaries = load_milestone_boundaries()
    if boundaries:
        return boundaries[-1]["end_sha"]

    # Fallback: the very first commit in the repo (bootstrap commit)
    result = run_cmd(
        ["git", "rev-list", "--max-parents=0", "HEAD"],
        capture=True,
    )
    if result.returncode == 0:
        # May return multiple roots; take the first
        lines = result.stdout.strip().split("\n")
        return lines[0].strip() if lines else ""
    return ""


# --- Per-agent milestone checkpoint files ---


def save_milestone_checkpoint(milestone_name: str, checkpoint_file: str = None) -> None:
    """Record that an agent has processed a milestone.

    Args:
        milestone_name: Name of the milestone that was processed.
        checkpoint_file: Filename for the checkpoint (defaults to reviewer.milestone).
    """
    if checkpoint_file is None:
        checkpoint_file = _MILESTONE_CHECKPOINT_FILE
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, checkpoint_file)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{milestone_name}\n")
    except Exception:
        pass


def load_reviewed_milestones(checkpoint_file: str = None) -> set[str]:
    """Return the set of milestone names an agent has already processed.

    Args:
        checkpoint_file: Filename for the checkpoint (defaults to reviewer.milestone).
    """
    if checkpoint_file is None:
        checkpoint_file = _MILESTONE_CHECKPOINT_FILE
    reviewed = set()
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, checkpoint_file)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    name = line.strip()
                    if name:
                        reviewed.add(name)
    except Exception:
        pass
    return reviewed


def _parse_milestones(tasks_path: str) -> list[dict]:
    """Parse TASKS.md and return every milestone with its task counts.

    Returns a list of dicts in document order:
        [{"name": str, "done": int, "total": int}, ...]

    A milestone section starts with '## Milestone: <name>' and contains
    checkbox lines like '- [x] ...' or '- [ ] ...'.
    """
    milestones = []
    if not os.path.exists(tasks_path):
        return milestones

    with open(tasks_path, "r", encoding="utf-8") as f:
        content = f.read()

    current_name = None
    total = 0
    done = 0

    for line in content.split("\n"):
        heading_match = re.match(r"^##\s+Milestone:\s*(.+)$", line, re.IGNORECASE)
        if heading_match:
            if current_name and total > 0:
                milestones.append({"name": current_name, "done": done, "total": total})
            current_name = heading_match.group(1).strip()
            total = 0
            done = 0
            continue

        if current_name:
            if re.search(r"\[x\]", line, re.IGNORECASE):
                total += 1
                done += 1
            elif re.search(r"\[ \]", line):
                total += 1

    if current_name and total > 0:
        milestones.append({"name": current_name, "done": done, "total": total})

    return milestones


def get_completed_milestones(tasks_path: str) -> list[dict]:
    """Return milestones with an all_done flag.

    Returns: [{"name": str, "all_done": bool}, ...]
    """
    return [
        {"name": ms["name"], "all_done": ms["done"] == ms["total"]}
        for ms in _parse_milestones(tasks_path)
    ]


def get_current_milestone_progress(tasks_path: str) -> dict | None:
    """Return progress info for the first incomplete milestone.

    Returns {"name": str, "done": int, "total": int}, or None if all complete.
    """
    for ms in _parse_milestones(tasks_path):
        if ms["done"] < ms["total"]:
            return ms
    return None


def get_tasks_per_milestone(tasks_path: str) -> list[dict]:
    """Return task counts for each uncompleted milestone.

    Returns: [{"name": str, "task_count": int}, ...]
    """
    return [
        {"name": ms["name"], "task_count": ms["total"]}
        for ms in _parse_milestones(tasks_path)
        if ms["done"] < ms["total"]
    ]


def is_reviewer_only_commit(commit_sha: str) -> bool:
    """Check if a commit only touches REVIEWS.md (i.e. the reviewer's own commit).

    Returns True if the commit should be skipped to avoid the reviewer
    reviewing its own review output.
    """
    result = run_cmd(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
        capture=True,
    )
    if result.returncode != 0:
        return False
    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return len(files) > 0 and all(f == "REVIEWS.md" for f in files)


def is_merge_commit(commit_sha: str) -> bool:
    """Check if a commit is a merge commit (has more than one parent)."""
    result = run_cmd(
        ["git", "rev-parse", f"{commit_sha}^2"],
        capture=True,
    )
    return result.returncode == 0
