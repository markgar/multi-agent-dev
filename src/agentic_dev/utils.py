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


_AGENT_DIRS = {"builder", "milestone-reviewer", "tester", "validator", "watcher"}
_BUILDER_DIR_RE = re.compile(r"^builder-\d+$")
_REVIEWER_DIR_RE = re.compile(r"^reviewer-\d+$")


def find_project_root(cwd: str) -> str:
    """Determine the project root from a working directory path.

    Pure function: if cwd ends in an agent directory name (including
    numbered builder dirs like builder-1 or reviewer dirs like reviewer-1),
    returns the parent. Otherwise returns cwd itself.
    """
    basename = os.path.basename(cwd)
    if basename in _AGENT_DIRS or _BUILDER_DIR_RE.match(basename) or _REVIEWER_DIR_RE.match(basename):
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


# Mapping of friendly display names to Copilot CLI model identifiers.
# The CLI expects lowercase-hyphenated names (e.g. "gpt-5.3-codex").
# Users can pass either the friendly name or the CLI name.
MODEL_NAME_MAP = {
    "GPT-5.3-Codex": "gpt-5.3-codex",
    "Claude Opus 4.6": "claude-opus-4.6",
    "Claude Opus 4.6 Fast": "claude-opus-4.6-fast",
    "Claude Sonnet 4.6": "claude-sonnet-4.6",
}

# Set of all accepted inputs (friendly names + CLI names).
ALLOWED_MODELS = set(MODEL_NAME_MAP.keys()) | set(MODEL_NAME_MAP.values())


def validate_model(model: str) -> str:
    """Validate and normalize a model name to its Copilot CLI identifier.

    Accepts either a friendly display name ('GPT-5.3-Codex') or the CLI name
    ('gpt-5.3-codex'). Returns the CLI name. Raises SystemExit with a clear
    message listing valid options if the model is not recognized.
    """
    if model in MODEL_NAME_MAP:
        return MODEL_NAME_MAP[model]
    if model in MODEL_NAME_MAP.values():
        return model
    allowed = ", ".join(sorted(MODEL_NAME_MAP.keys()))
    raise SystemExit(f"Invalid model '{model}'. Allowed models: {allowed}")
    return model


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


_AUTH_ERROR_MARKERS = [
    "No authentication information found",
    "COPILOT_GITHUB_TOKEN",
    "gh auth login",
]


def _detect_auth_failure(log_file: str) -> bool:
    """Check if the last copilot output indicates an auth token expiry.

    Reads the tail of the log file and looks for known auth error markers.
    Pure-ish function: only reads the file, no side effects.
    """
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # Read the last 2KB — auth errors appear at the very end
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 2048))
            tail = f.read()
    except Exception:
        return False
    return all(marker in tail for marker in _AUTH_ERROR_MARKERS)


def _refresh_github_auth() -> bool:
    """Attempt to refresh the GitHub auth token non-interactively.

    Tries 'gh auth refresh' which uses the stored refresh token —
    no user interaction needed if the refresh token is still valid.
    Returns True if the refresh succeeded.
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "refresh"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def _run_copilot_once(agent_name: str, prompt: str, model: str, log_file: str) -> int:
    """Run a single copilot invocation. Returns the exit code."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt_preview = prompt[:100]

    header = (
        f"\n========== [{timestamp}] {agent_name} ==========\n"
        f"Model: {model}\n"
        f"Prompt: {prompt_preview}...\n"
        f"--- output ---\n"
    )
    _write_log_entry(log_file, header)

    cmd = _resolve_copilot_cmd() + ["--allow-all-tools", "--model", model, "-p", prompt]

    proc = subprocess.Popen(
        cmd,
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


def run_copilot(agent_name: str, prompt: str, model: str = "") -> int:
    """Run 'copilot --allow-all-tools --model <model> -p <prompt>' with streaming output.

    When *model* is provided it is used directly; otherwise the value is read
    from the COPILOT_MODEL environment variable (required).
    If copilot fails with an auth error, attempts 'gh auth refresh' and retries once.
    Returns the process exit code.
    """
    if not model:
        model = os.environ.get("COPILOT_MODEL", "")
    if not model:
        raise SystemExit("COPILOT_MODEL environment variable is not set. Use --model on the go command.")

    logs_dir = resolve_logs_dir()
    log_file = os.path.join(logs_dir, f"{agent_name}.log")

    exit_code = _run_copilot_once(agent_name, prompt, model, log_file)

    if exit_code != 0 and _detect_auth_failure(log_file):
        log(agent_name, "[Auth] Token expired — attempting gh auth refresh...", style="yellow")
        if _refresh_github_auth():
            log(agent_name, "[Auth] Refresh succeeded — retrying copilot...", style="green")
            exit_code = _run_copilot_once(agent_name, prompt, model, log_file)
        else:
            log(agent_name, "[Auth] Refresh failed — cannot recover without manual login.", style="red")

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


def _extract_item_ids(filenames: list[str], prefix: str) -> set[str]:
    """Extract item IDs from filenames by stripping a prefix and .md suffix.

    Pure function: e.g. prefix='finding-' turns 'finding-20260215-120000.md'
    into '20260215-120000'.
    """
    ids = set()
    for name in filenames:
        if name.startswith(prefix) and name.endswith(".md"):
            item_id = name[len(prefix):-3]
            ids.add(item_id)
    return ids


def count_open_items_in_dir(directory: str, open_prefix: str, closed_prefix: str) -> int:
    """Count open items in a directory-based tracking system.

    An item is "open" when an open_prefix file exists without a matching
    closed_prefix file. Items are matched by stripping the prefix.

    Pure function over directory contents. Returns 0 if directory doesn't exist.
    """
    if not os.path.isdir(directory):
        return 0
    try:
        filenames = os.listdir(directory)
    except OSError:
        return 0
    open_ids = _extract_item_ids(filenames, open_prefix)
    closed_ids = _extract_item_ids(filenames, closed_prefix)
    return len(open_ids - closed_ids)


def count_partitioned_open_items(
    directory: str, open_prefix: str, closed_prefix: str,
    builder_id: int, num_builders: int,
) -> int:
    """Count open items assigned to this builder by last-digit partitioning.

    Items are partitioned across builders by the last digit of their ID
    (the timestamp portion of the filename). An item belongs to builder N
    when: last_digit % num_builders == (builder_id - 1).

    When num_builders is 1, returns the same result as count_open_items_in_dir.
    """
    if not os.path.isdir(directory):
        return 0
    try:
        filenames = os.listdir(directory)
    except OSError:
        return 0
    open_ids = _extract_item_ids(filenames, open_prefix)
    closed_ids = _extract_item_ids(filenames, closed_prefix)
    unclosed = open_ids - closed_ids
    if num_builders <= 1:
        return len(unclosed)
    return sum(
        1 for item_id in unclosed
        if item_id and item_id[-1].isdigit()
        and int(item_id[-1]) % num_builders == (builder_id - 1)
    )


def _parse_gh_issue_numbers(json_output: str) -> list[int]:
    """Extract issue numbers from gh issue list JSON output.

    Pure function: parses JSON array of objects with 'number' keys.
    Returns sorted list of issue numbers, or empty list on parse error.
    """
    import json
    try:
        issues = json.loads(json_output)
    except (json.JSONDecodeError, TypeError):
        return []
    numbers = []
    for issue in issues:
        if isinstance(issue, dict) and "number" in issue:
            numbers.append(issue["number"])
    numbers.sort()
    return numbers


def count_open_bug_issues(builder_id: int = 1, num_builders: int = 1) -> int:
    """Count open GitHub Issues labeled 'bug' assigned to this builder.

    Assignment is by issue number modulo: number % num_builders == (builder_id - 1).
    When num_builders is 1, returns total open bug issue count.
    """
    result = run_cmd(
        ["gh", "issue", "list", "--label", "bug", "--state", "open",
         "--json", "number", "--limit", "200"],
        capture=True,
    )
    if result.returncode != 0:
        return 0
    numbers = _parse_gh_issue_numbers(result.stdout)
    if num_builders <= 1:
        return len(numbers)
    return sum(
        1 for n in numbers
        if n % num_builders == (builder_id - 1)
    )


def ensure_bug_label_exists() -> None:
    """Create the 'bug' label on the GitHub repo if it doesn't already exist.

    Idempotent: silently succeeds if the label already exists.
    """
    run_cmd(
        ["gh", "label", "create", "bug", "--description", "Bug report",
         "--color", "d73a4a", "--force"],
        quiet=True,
    )
