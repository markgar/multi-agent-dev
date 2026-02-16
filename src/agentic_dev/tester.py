"""Tester command: watch for completed milestones and run scoped tests."""

import os
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
from agentic_dev.prompts import TESTER_MILESTONE_PROMPT
from agentic_dev.sentinel import is_builder_done
from agentic_dev.utils import log, run_cmd, run_copilot


_TESTER_MILESTONE_CHECKPOINT = "tester.milestone"


def find_untested_milestones(boundaries: list[dict], tested: set[str]) -> list[dict]:
    """Return milestone boundaries that have not yet been tested.

    Pure function: filters boundaries by membership in the tested set.
    """
    return [b for b in boundaries if b["name"] not in tested]


def _test_milestone(boundary: dict) -> None:
    """Run scoped tests for a completed milestone and checkpoint."""
    now = datetime.now().strftime("%H:%M:%S")
    log(
        "tester",
        f"[{now}] Milestone completed: {boundary['name']}! Running scoped tests...",
        style="bold cyan",
    )

    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    prompt = TESTER_MILESTONE_PROMPT.format(
        milestone_name=boundary["name"],
        milestone_start_sha=boundary["start_sha"],
        milestone_end_sha=boundary["end_sha"],
    )
    exit_code = run_copilot("tester", prompt)
    git_push_with_retry("tester")

    now = datetime.now().strftime("%H:%M:%S")
    if exit_code != 0:
        log("tester", f"[{now}] WARNING: Test run exited with errors", style="red")
    else:
        log("tester", f"[{now}] Milestone test complete: {boundary['name']}", style="yellow")

    save_milestone_checkpoint(
        boundary["name"],
        checkpoint_file=_TESTER_MILESTONE_CHECKPOINT,
    )


def register(app: typer.Typer) -> None:
    """Register tester commands on the shared app."""
    app.command()(testloop)


def testloop(
    interval: Annotated[
        int, typer.Option(help="Seconds between poll cycles (not test runs)")
    ] = 10,
    tester_dir: Annotated[
        str, typer.Option(help="Path to the tester git clone")
    ] = "",
) -> None:
    """Watch for completed milestones and run scoped tests against each one.

    Polls logs/milestones.log for newly completed milestones. When one appears,
    pulls latest code and runs the tester scoped to the milestone's changed files.
    Runs a final full test pass when the builder finishes, then shuts down.
    """
    if tester_dir:
        os.chdir(tester_dir)

    log("tester", "======================================", style="bold yellow")
    log("tester", " Tester watching for completed milestones", style="bold yellow")
    log("tester", " Press Ctrl+C to stop", style="bold yellow")
    log("tester", "======================================", style="bold yellow")
    log("tester", "")

    try:
        _testloop_inner(interval)
    except SystemExit as exc:
        log("tester", f"FATAL: {exc}", style="bold red")
        raise
    except Exception as exc:
        log("tester", f"FATAL: Unexpected error: {exc}", style="bold red")
        raise


def _testloop_inner(interval: int) -> None:
    """Inner loop for testloop, separated for crash-logging wrapper."""
    while True:
        # Check if the builder has finished
        builder_done = is_builder_done()

        # Pull latest so we see new milestones.log entries
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        # Check for newly completed milestones
        boundaries = load_milestone_boundaries()
        tested = load_reviewed_milestones(checkpoint_file=_TESTER_MILESTONE_CHECKPOINT)

        for boundary in find_untested_milestones(boundaries, tested):
            _test_milestone(boundary)

        if builder_done:
            now = datetime.now().strftime("%H:%M:%S")
            log("tester", f"[{now}] Builder finished. Shutting down.", style="bold green")
            break

        time.sleep(interval)
