"""Legacy watcher commands: reviewoncommit and testoncommit.

These are the original per-commit watchers that use a simple polling loop.
They are not launched by 'go' or 'resume' but remain available for manual use.
"""

import time
from datetime import datetime

from agent.prompts import REVIEWER_PROMPT, TESTER_PROMPT
from agent.utils import log, run_cmd, run_copilot


def _watch_loop(agent_name: str, prompt: str, label: str) -> None:
    """Shared polling loop for reviewoncommit and testoncommit."""
    log(agent_name, "======================================", style="bold yellow")
    log(agent_name, f" {label} agent watching for commits...", style="bold yellow")
    log(agent_name, " Press Ctrl+C to stop", style="bold yellow")
    log(agent_name, "======================================", style="bold yellow")
    log(agent_name, "")

    last_commit = ""

    while True:
        pull_result = run_cmd(["git", "pull", "-q"], capture=True)
        if pull_result.returncode != 0:
            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, f"[{now}] WARNING: git pull failed", style="red")
            if pull_result.stderr:
                log(agent_name, pull_result.stderr.strip(), style="red")

        head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
        current_commit = head_result.stdout.strip() if head_result.returncode == 0 else ""

        if current_commit != last_commit and last_commit != "":
            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, "")
            log(agent_name, f"[{now}] New commit detected!", style="yellow")
            log(agent_name, "")

            exit_code = run_copilot(agent_name, prompt)

            if exit_code != 0:
                now = datetime.now().strftime("%H:%M:%S")
                log(agent_name, f"[{now}] WARNING: {label} exited with errors", style="red")

            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, "")
            log(agent_name, f"[{now}] {label} complete. Watching...", style="yellow")

        last_commit = current_commit
        time.sleep(10)


def reviewoncommit():
    """Watch for new commits and review code quality (runs in a loop)."""
    _watch_loop("reviewer", REVIEWER_PROMPT, "Review")


def testoncommit():
    """Watch for new commits and auto-test (runs in a loop)."""
    _watch_loop("tester", TESTER_PROMPT, "Test run")
