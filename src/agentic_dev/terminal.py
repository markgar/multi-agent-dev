"""Terminal spawning helper for launching agent commands in new windows."""

import os
import shutil
import subprocess
import sys
import tempfile

from agentic_dev.utils import check_command, console, is_macos, is_windows


def build_agent_script(working_dir: str, command: str, platform: str, model: str = "") -> str:
    """Generate the shell script content for launching an agent.

    Pure function: returns the script text for the given platform.
    platform should be 'macos', 'windows', or 'linux'.
    When *model* is provided it is used; otherwise COPILOT_MODEL from the
    current environment is propagated to the child terminal.
    """
    lines = ["#!/bin/bash"]
    copilot_model = model or os.environ.get("COPILOT_MODEL", "")
    if copilot_model:
        lines.append(f"export COPILOT_MODEL='{copilot_model}'")
    lines.append(f"cd '{working_dir}'")
    lines.append(f"agentic-dev {command}")
    if platform == "linux":
        lines.append("exec bash")
    return "\n".join(lines) + "\n"


def _spawn_macos(working_dir: str, command: str, model: str = "") -> None:
    """Spawn agent in a new macOS Terminal window."""
    script_content = build_agent_script(working_dir, command, "macos", model=model)
    fd, temp_script = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write(script_content)
    os.chmod(temp_script, 0o755)
    subprocess.run(
        ["osascript", "-e", f'tell application "Terminal" to do script "{temp_script}"'],
        stdout=subprocess.DEVNULL,
    )


def _resolve_windows_command(command: str) -> list[str]:
    """Build the command list for launching an agent on Windows.

    Splits the command string so flags like '--loop --builder-id 1' become
    separate arguments in the subprocess call.
    """
    parts = command.split()
    venv_exe = os.path.join(os.path.dirname(sys.executable), "agentic-dev.exe")
    if os.path.isfile(venv_exe):
        return [venv_exe] + parts
    path_exe = shutil.which("agentic-dev")
    if path_exe:
        return [path_exe] + parts
    return [sys.executable, "-m", "agentic_dev"] + parts


def _spawn_windows(working_dir: str, command: str, model: str = "") -> None:
    """Spawn agent in a new Windows console.

    When *model* is provided it overrides the inherited COPILOT_MODEL.
    Otherwise the parent environment value is propagated.
    """
    cmd = _resolve_windows_command(command)
    env = os.environ.copy()
    copilot_model = model or os.environ.get("COPILOT_MODEL", "")
    if copilot_model:
        env["COPILOT_MODEL"] = copilot_model
    subprocess.Popen(
        cmd,
        cwd=working_dir,
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def _spawn_linux(working_dir: str, command: str, model: str = "") -> None:
    """Spawn agent in a new Linux terminal emulator."""
    script_content = build_agent_script(working_dir, command, "linux", model=model)
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


def spawn_agent_in_terminal(working_dir: str, command: str, model: str = "") -> None:
    """Launch an agent command in a new terminal window.

    When *model* is provided the child terminal's COPILOT_MODEL is set to
    that value, overriding the parent environment.  When omitted the parent
    environment value is inherited as before.
    """
    try:
        if is_macos():
            _spawn_macos(working_dir, command, model=model)
        elif is_windows():
            _spawn_windows(working_dir, command, model=model)
        else:
            _spawn_linux(working_dir, command, model=model)
    except Exception as exc:
        console.print(
            f"WARNING: Failed to spawn terminal for '{command}': {exc}\n"
            f"  Run manually: cd {working_dir} && agentic-dev {command}",
            style="yellow",
        )
