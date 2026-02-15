"""Core utility functions: logging, command execution, platform detection."""

import contextlib
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Generator
from datetime import datetime

from rich.console import Console

console = Console()


@contextlib.contextmanager
def pushd(path: str) -> Generator[None, None, None]:
    """Context manager that changes to a directory and restores on exit."""
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


_AGENT_DIRS = {"builder", "reviewer", "tester", "validator", "watcher"}


def find_project_root(cwd: str) -> str:
    """Determine the project root from a working directory path.

    Pure function: if cwd ends in an agent directory name, returns the parent.
    Otherwise returns cwd itself.
    """
    if os.path.basename(cwd) in _AGENT_DIRS:
        return os.path.dirname(cwd)
    return cwd


def resolve_logs_dir() -> str:
    """Find the project root logs directory, creating it if needed."""
    project_root = find_project_root(os.getcwd())
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


def _write_line_to_log(f, line: str) -> None:
    """Write a single line to a log file handle, silently ignoring errors."""
    try:
        f.write(line)
        f.flush()
    except Exception:
        pass


def _stream_process_output(proc: subprocess.Popen, log_file: str) -> None:
    """Stream subprocess stdout to both the console and a log file."""
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                _write_line_to_log(f, line)
    except Exception:
        pass


def _resolve_copilot_cmd() -> list[str]:
    """Resolve the copilot CLI command for the current platform.

    On Windows, the VS Code Copilot CLI installs a .BAT wrapper that chains
    through PowerShell before launching the real .EXE. Piping stdout through
    cmd→powershell→exe breaks subprocess output capture. We bypass the wrapper
    by resolving copilot.exe directly first.
    """
    if sys.platform == "win32":
        # Prefer the real .exe — avoids BAT→PowerShell→EXE chain that breaks
        # stdout piping in subprocess.Popen(stdout=PIPE).
        exe = shutil.which("copilot.exe")
        if exe and exe.lower().endswith(".exe"):
            return [exe]
        # Fallback: resolve bare "copilot" and handle .bat/.cmd wrappers.
        exe = shutil.which("copilot")
        if exe and exe.lower().endswith((".bat", ".cmd")):
            return ["cmd", "/c", exe]
        if exe:
            return [exe]
    else:
        exe = shutil.which("copilot")
        if exe:
            return [exe]
    return ["copilot"]


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
        _resolve_copilot_cmd() + ["--yolo", "-p", prompt],
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


def count_unchecked_items(content: str) -> int:
    """Count unchecked checkbox items ([ ]) in markdown content.

    Pure function: takes text, returns count.
    """
    return len(re.findall(r"\[ \]", content))


def has_unchecked_items(filepath: str) -> int:
    """Count unchecked checkbox items ([ ]) in a file. Returns 0 if file doesn't exist."""
    if not os.path.exists(filepath):
        return 0
    with open(filepath, "r", encoding="utf-8") as f:
        return count_unchecked_items(f.read())
