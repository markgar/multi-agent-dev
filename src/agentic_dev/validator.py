"""Validator command: watch for completed milestones, build containers, and run acceptance tests."""

import glob
import os
import shutil
import time
from datetime import datetime
from typing import Annotated

import typer

from agentic_dev.git_helpers import git_push_with_retry
from agentic_dev.milestone import (
    load_milestone_boundaries,
    load_reviewed_milestones,
    save_milestone_checkpoint,
)
from agentic_dev.prompts import VALIDATOR_MILESTONE_PROMPT, VALIDATOR_PLAYWRIGHT_SECTION
from agentic_dev.sentinel import is_builder_done
from agentic_dev.utils import log, run_cmd, run_copilot, resolve_logs_dir


_VALIDATOR_MILESTONE_CHECKPOINT = "validator.milestone"

_FRONTEND_EXTENSIONS = ("*.tsx", "*.jsx", "*.vue", "*.svelte")
_FRONTEND_KEYWORDS = (
    "frontend", "react", "vue", "angular", "svelte", "next.js", "nuxt",
    "vite", "webpack", "tailwind", "UI ", "user interface", "single-page",
    "SPA", "pages should render", "web app", "dashboard",
)


def detect_has_frontend(repo_dir: str) -> bool:
    """Return True if the repo appears to contain a frontend/UI component.

    Checks three signals:
    1. A package.json exists (root or one level deep).
    2. Frontend-framework source files exist (tsx, jsx, vue, svelte).
    3. SPEC.md contains frontend-related keywords.

    Pure-ish function: only reads the filesystem, no side effects.
    """
    # Signal 1: package.json at root or one directory deep
    if os.path.isfile(os.path.join(repo_dir, "package.json")):
        return True
    if glob.glob(os.path.join(repo_dir, "*/package.json")):
        return True

    # Signal 2: frontend framework source files (search up to 4 levels deep)
    for ext in _FRONTEND_EXTENSIONS:
        pattern = os.path.join(repo_dir, "**", ext)
        if glob.glob(pattern, recursive=True):
            return True

    # Signal 3: SPEC.md mentions frontend keywords
    spec_path = os.path.join(repo_dir, "SPEC.md")
    if os.path.isfile(spec_path):
        try:
            content = open(spec_path, encoding="utf-8").read().lower()
            for keyword in _FRONTEND_KEYWORDS:
                if keyword.lower() in content:
                    return True
        except OSError:
            pass

    return False


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


def _validate_milestone(boundary: dict) -> None:
    """Build a container, validate at the milestone's end SHA, and checkpoint."""
    now = datetime.now().strftime("%H:%M:%S")
    log(
        "validator",
        f"[{now}] Milestone completed: {boundary['name']}! "
        "Building container and validating...",
        style="bold cyan",
    )

    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)
    run_cmd(["git", "checkout", boundary["end_sha"]], quiet=True)
    _cleanup_containers()

    has_frontend = detect_has_frontend(".")
    ui_instructions = VALIDATOR_PLAYWRIGHT_SECTION if has_frontend else ""

    prompt = VALIDATOR_MILESTONE_PROMPT.format(
        milestone_name=boundary["name"],
        milestone_start_sha=boundary["start_sha"],
        milestone_end_sha=boundary["end_sha"],
        ui_testing_instructions=ui_instructions,
    )
    exit_code = run_copilot("validator", prompt)

    _copy_validation_results(boundary["name"])
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
    run_cmd(["git", "checkout", "-"], quiet=True)


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
) -> None:
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

    try:
        _validateloop_inner(interval)
    except SystemExit as exc:
        log("validator", f"FATAL: {exc}", style="bold red")
        raise
    except Exception as exc:
        log("validator", f"FATAL: Unexpected error: {exc}", style="bold red")
        raise


def _validateloop_inner(interval: int) -> None:
    """Inner loop for validateloop, separated for crash-logging wrapper."""
    while True:
        # Check if the builder has finished
        builder_done = is_builder_done()

        # Pull latest so we see new milestones.log entries
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        # Check for newly completed milestones
        boundaries = load_milestone_boundaries()
        validated = load_reviewed_milestones(checkpoint_file=_VALIDATOR_MILESTONE_CHECKPOINT)

        for boundary in find_unvalidated_milestones(boundaries, validated):
            _validate_milestone(boundary)

        if builder_done:
            now = datetime.now().strftime("%H:%M:%S")
            log("validator", f"[{now}] Builder finished. Shutting down.", style="bold green")
            break

        time.sleep(interval)
