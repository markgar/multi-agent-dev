"""Validator command: watch for completed milestones, build containers, and run acceptance tests."""

import os
import shutil
import time
from datetime import datetime
from typing import Annotated

import typer

from agent.git_helpers import git_push_with_retry
from agent.milestone import (
    load_milestone_boundaries,
    load_reviewed_milestones,
    save_milestone_checkpoint,
)
from agent.prompts import VALIDATOR_MILESTONE_PROMPT
from agent.sentinel import is_builder_done
from agent.utils import log, run_cmd, run_copilot, resolve_logs_dir


_VALIDATOR_MILESTONE_CHECKPOINT = "validator.milestone"


def find_unvalidated_milestones(boundaries: list[dict], validated: set[str]) -> list[dict]:
    """Return milestone boundaries that have not yet been validated.

    Pure function: filters boundaries by membership in the validated set.
    """
    return [b for b in boundaries if b["name"] not in validated]


def _cleanup_containers() -> None:
    """Stop and remove any containers from previous validator runs.

    Runs docker compose down if a compose file exists. Never raises.
    """
    try:
        for compose_file in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
            if os.path.exists(compose_file):
                run_cmd(["docker", "compose", "down", "--remove-orphans"], quiet=True)
                return
        # Fallback: remove containers with the 'validator-' label if any
        run_cmd(["docker", "rm", "-f", "$(docker ps -aq --filter label=validator)"], quiet=True)
    except Exception:
        pass


def _copy_validation_results(milestone_name: str) -> None:
    """Copy validation-results.txt from the working dir to logs/.

    The validator prompt asks Copilot to write this file but not commit it.
    We copy it to logs/ with the milestone name for post-run analysis.
    Silently does nothing if the file doesn't exist.
    """
    results_file = "validation-results.txt"
    if not os.path.exists(results_file):
        return
    try:
        logs_dir = resolve_logs_dir()
        safe_name = milestone_name.lower().replace(" ", "-")
        dest = os.path.join(logs_dir, f"validation-{safe_name}.txt")
        shutil.copy(results_file, dest)
        log("validator", f"Validation results saved to {dest}", style="blue")
        os.remove(results_file)
    except Exception:
        pass


def register(app: typer.Typer) -> None:
    """Register validator commands on the shared app."""
    app.command()(validateloop)


def validateloop(
    interval: Annotated[
        int, typer.Option(help="Seconds between poll cycles")
    ] = 10,
    validator_dir: Annotated[
        str, typer.Option(help="Path to the validator git clone")
    ] = "",
):
    """Watch for completed milestones, build containers, and run acceptance tests.

    Polls logs/milestones.log for newly completed milestones. When one appears,
    pulls latest code, builds the app in a Docker container, starts it, and
    validates it against SPEC.md acceptance criteria scoped to the current milestone.
    Deployment knowledge is persisted in DEPLOY.md for future runs.
    """
    if validator_dir:
        os.chdir(validator_dir)

    log("validator", "======================================", style="bold blue")
    log("validator", " Validator watching for completed milestones", style="bold blue")
    log("validator", " Press Ctrl+C to stop", style="bold blue")
    log("validator", "======================================", style="bold blue")
    log("validator", "")

    while True:
        # Check if the builder has finished
        builder_done = is_builder_done()

        # Pull latest so we see new milestones.log entries
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        # Check for newly completed milestones
        boundaries = load_milestone_boundaries()
        validated = load_reviewed_milestones(checkpoint_file=_VALIDATOR_MILESTONE_CHECKPOINT)

        for boundary in find_unvalidated_milestones(boundaries, validated):
                now = datetime.now().strftime("%H:%M:%S")
                log(
                    "validator",
                    f"[{now}] Milestone completed: {boundary['name']}! Building container and validating...",
                    style="bold cyan",
                )

                run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

                # Check out the exact milestone end SHA so we validate
                # exactly what was built at that point, not later code.
                run_cmd(["git", "checkout", boundary["end_sha"]], quiet=True)

                # Clean up any leftover containers before starting
                _cleanup_containers()

                prompt = VALIDATOR_MILESTONE_PROMPT.format(
                    milestone_name=boundary["name"],
                    milestone_start_sha=boundary["start_sha"],
                    milestone_end_sha=boundary["end_sha"],
                )
                exit_code = run_copilot("validator", prompt)

                # Copy validation results to logs if the file was created
                _copy_validation_results(boundary["name"])

                # Clean up containers after the run regardless of outcome
                _cleanup_containers()

                git_push_with_retry("validator")

                now = datetime.now().strftime("%H:%M:%S")
                if exit_code != 0:
                    log("validator", f"[{now}] WARNING: Validation run exited with errors", style="red")
                else:
                    log("validator", f"[{now}] Milestone validated: {boundary['name']}", style="blue")

                save_milestone_checkpoint(
                    boundary["name"],
                    checkpoint_file=_VALIDATOR_MILESTONE_CHECKPOINT,
                )

                # Return to the main branch after validating at a pinned SHA.
                run_cmd(["git", "checkout", "-"], quiet=True)

        if builder_done:
            now = datetime.now().strftime("%H:%M:%S")
            log("validator", f"[{now}] Builder finished. Shutting down.", style="bold green")
            break

        time.sleep(interval)
