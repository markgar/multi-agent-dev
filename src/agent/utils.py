"""Core utility functions: logging, command execution, platform detection."""

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


def _write_log_entry(log_file: str, text: str) -> None:
    """Append text to a log file. Never raises."""
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def _stream_process_output(proc: subprocess.Popen, log_file: str) -> None:
    """Stream subprocess stdout to both the console and a log file."""
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


def run_copilot(agent_name: str, prompt: str) -> int:
    """Run 'copilot --yolo -p <prompt>' with streaming output to both console and log.

    Returns the process exit code.
    """
    logs_dir = resolve_logs_dir()
    log_file = os.path.join(logs_dir, f"{agent_name}.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt_preview = prompt[:100]

    header = (
        f"\n========== [{timestamp}] {agent_name} ==========\n"
        f"Prompt: {prompt_preview}...\n"
        f"--- output ---\n"
    )
    _write_log_entry(log_file, header)

    proc = subprocess.Popen(
        ["copilot", "--yolo", "-p", prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    _stream_process_output(proc, log_file)
    proc.wait()
    exit_code = proc.returncode

    _write_log_entry(log_file, f"--- end (exit: {exit_code}) ---\n")

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
