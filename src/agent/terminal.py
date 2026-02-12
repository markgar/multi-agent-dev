"""Terminal spawning helper for launching agent commands in new windows."""

import os
import subprocess
import tempfile

from agent.utils import check_command, console, is_macos, is_windows


def spawn_agent_in_terminal(working_dir: str, command: str) -> None:
    """Launch an agent command in a new terminal window."""
    if is_macos():
        fd, temp_script = tempfile.mkstemp(suffix=".sh")
        with os.fdopen(fd, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f"cd '{working_dir}'\n")
            f.write(f"agentic-dev {command}\n")
        os.chmod(temp_script, 0o755)
        subprocess.run(
            ["osascript", "-e", f'tell application "Terminal" to do script "{temp_script}"'],
            stdout=subprocess.DEVNULL,
        )
    elif is_windows():
        subprocess.Popen(
            ["agentic-dev", command],
            cwd=working_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    else:
        fd, temp_script = tempfile.mkstemp(suffix=".sh")
        with os.fdopen(fd, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f"cd '{working_dir}'\n")
            f.write(f"agentic-dev {command}\n")
            f.write("exec bash\n")
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
