"""Shared utility functions for logging, running commands, and helpers."""

import contextlib
import os
import re
import shutil
import subprocess
import sys
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
