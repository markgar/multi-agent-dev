"""Terminal spawning helper for launching agent commands in new windows."""

import os
import shutil
import subprocess
import sys
import tempfile

from agentic_dev.utils import check_command, console, is_macos, is_windows


def build_agent_script(working_dir: str, command: str, platform: str) -> str:
    """Generate the shell script content for launching an agent.

    Pure function: returns the script text for the given platform.
    platform should be 'macos', 'windows', or 'linux'.
    Propagates COPILOT_MODEL so child terminals use the same model.
    """
    lines = ["#!/bin/bash"]
    copilot_model = os.environ.get("COPILOT_MODEL", "")
    if copilot_model:
        lines.append(f"export COPILOT_MODEL='{copilot_model}'")
    lines.append(f"cd '{working_dir}'")
    lines.append(f"agentic-dev {command}")
    if platform == "linux":
        lines.append("exec bash")
    return "\n".join(lines) + "\n"


def _spawn_macos(working_dir: str, command: str) -> None:
    """Spawn agent in a new macOS Terminal window."""
    script_content = build_agent_script(working_dir, command, "macos")
    fd, temp_script = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write(script_content)
    os.chmod(temp_script, 0o755)
    subprocess.run(
        ["osascript", "-e", f'tell application "Terminal" to do script "{temp_script}"'],
        stdout=subprocess.DEVNULL,
    )


def _resolve_windows_command(command: str) -> list[str]:
    """Build the command list for launching an agent on Windows."""
    venv_exe = os.path.join(os.path.dirname(sys.executable), "agentic-dev.exe")
    if os.path.isfile(venv_exe):
        return [venv_exe, command]
    path_exe = shutil.which("agentic-dev")
    if path_exe:
        return [path_exe, command]
    return [sys.executable, "-m", "agentic_dev", command]


def _spawn_windows(working_dir: str, command: str) -> None:
    """Spawn agent in a new Windows console."""
    cmd = _resolve_windows_command(command)
    subprocess.Popen(
        cmd,
        cwd=working_dir,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def _spawn_linux(working_dir: str, command: str) -> None:
    """Spawn agent in a new Linux terminal emulator."""
    script_content = build_agent_script(working_dir, command, "linux")
    fd, temp_script = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write(script_content)
    os.chmod(temp_script, 0o755)

    if check_command("gnome-terminal"):
        subprocess.Popen(["gnome-terminal", "--", "bash", temp_script])
    elif check_command("xterm"):
        subprocess.Popen(["xterm", "-e", f"bash {temp_script}"])
    else:
        console.print(
            f"WARNING: Could not find a terminal emulator. "
            f"Please run manually in a new terminal:\n"
            f"  cd {working_dir} && agentic-dev {command}",
            style="yellow",
        )


def spawn_agent_in_terminal(working_dir: str, command: str) -> None:
    """Launch an agent command in a new terminal window."""
    try:
        if is_macos():
            _spawn_macos(working_dir, command)
        elif is_windows():
            _spawn_windows(working_dir, command)
        else:
            _spawn_linux(working_dir, command)
    except Exception as exc:
        console.print(
            f"WARNING: Failed to spawn terminal for '{command}': {exc}\n"
            f"  Run manually: cd {working_dir} && agentic-dev {command}",
            style="yellow",
        )
