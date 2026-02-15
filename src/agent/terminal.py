"""Terminal spawning helper for launching agent commands in new windows."""

import os
import shutil
import subprocess
import sys
import tempfile

from agent.utils import check_command, console, is_macos, is_windows


def build_agent_script(working_dir: str, command: str, platform: str) -> str:
    """Generate the shell script content for launching an agent.

    Pure function: returns the script text for the given platform.
    platform should be 'macos', 'windows', or 'linux'.
    """
    lines = ["#!/bin/bash"]
    lines.append(f"cd '{working_dir}'")
    lines.append(f"agentic-dev {command}")
    if platform == "linux":
        lines.append("exec bash")
    return "\n".join(lines) + "\n"


def spawn_agent_in_terminal(working_dir: str, command: str) -> None:
    """Launch an agent command in a new terminal window."""
    try:
        if is_macos():
            script_content = build_agent_script(working_dir, command, "macos")
            fd, temp_script = tempfile.mkstemp(suffix=".sh")
            with os.fdopen(fd, "w") as f:
                f.write(script_content)
            os.chmod(temp_script, 0o755)
            subprocess.run(
                ["osascript", "-e", f'tell application "Terminal" to do script "{temp_script}"'],
                stdout=subprocess.DEVNULL,
            )
        elif is_windows():
            # Prefer the agentic-dev next to the running Python (same venv),
            # fall back to PATH, then to python -m agent.
            venv_exe = os.path.join(os.path.dirname(sys.executable), "agentic-dev.exe")
            if os.path.isfile(venv_exe):
                cmd = [venv_exe, command]
            elif shutil.which("agentic-dev"):
                cmd = [shutil.which("agentic-dev"), command]
            else:
                cmd = [sys.executable, "-m", "agent", command]
            subprocess.Popen(
                cmd,
                cwd=working_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
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
    except Exception as exc:
        console.print(
            f"WARNING: Failed to spawn terminal for '{command}': {exc}\n"
            f"  Run manually: cd {working_dir} && agentic-dev {command}",
            style="yellow",
        )
