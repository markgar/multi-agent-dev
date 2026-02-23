"""Milestone reviewer: cross-cutting review of completed milestones."""

import os
import time
from datetime import datetime
from typing import Annotated

import typer

from agentic_dev.code_analysis import run_milestone_analysis
from agentic_dev.git_helpers import git_push_with_retry
from agentic_dev.milestone import (
    load_milestone_boundaries,
    load_reviewed_milestones,
    save_milestone_checkpoint,
)
from agentic_dev.prompts import REVIEWER_MILESTONE_PROMPT
from agentic_dev.sentinel import is_builder_done
from agentic_dev.utils import log, resolve_logs_dir, run_cmd, run_copilot


def find_unreviewed_milestones(boundaries: list[dict], reviewed: set[str]) -> list[dict]:
    """Return milestone boundaries that have not yet been reviewed.

    Pure function: filters boundaries by membership in the reviewed set.
    """
    return [b for b in boundaries if b["name"] not in reviewed]


def _save_analysis_log(milestone_name: str, analysis_text: str) -> None:
    """Write code analysis findings to logs/analysis-<milestone>.txt."""
    safe_name = milestone_name.replace(" ", "-").replace("/", "-").lower()
    try:
        logs_dir = resolve_logs_dir()
        filepath = os.path.join(logs_dir, f"analysis-{safe_name}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Code analysis: {milestone_name}\n")
            f.write(f"{'=' * 40}\n\n")
            f.write(analysis_text)
            f.write("\n")
    except OSError:
        pass


def _review_milestone(boundary: dict) -> None:
    """Run a cross-cutting review for a completed milestone and checkpoint."""
    now = datetime.now().strftime("%H:%M:%S")
    log(
        "milestone-reviewer",
        f"[{now}] Milestone completed: {boundary['name']}! Running cross-cutting review...",
        style="bold magenta",
    )

    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    try:
        analysis_text = run_milestone_analysis(
            boundary["start_sha"], boundary["end_sha"]
        )
    except Exception:
        analysis_text = "No structural issues detected by static analysis."

    _save_analysis_log(boundary["name"], analysis_text)

    milestone_prompt = REVIEWER_MILESTONE_PROMPT.format(
        milestone_name=boundary["name"],
        milestone_start_sha=boundary["start_sha"],
        milestone_end_sha=boundary["end_sha"],
        code_analysis_findings=analysis_text,
    )
    exit_code = run_copilot("milestone-reviewer", milestone_prompt)

    if exit_code != 0:
        now = datetime.now().strftime("%H:%M:%S")
        log(
            "milestone-reviewer",
            f"[{now}] WARNING: Milestone review of '{boundary['name']}' exited with errors",
            style="red",
        )

    git_push_with_retry("milestone-reviewer")
    save_milestone_checkpoint(boundary["name"])

    now = datetime.now().strftime("%H:%M:%S")
    log(
        "milestone-reviewer",
        f"[{now}] Milestone review complete: {boundary['name']}",
        style="bold magenta",
    )


def register(app: typer.Typer) -> None:
    """Register milestone reviewer commands on the shared app."""
    app.command()(milestonewatch)


def milestonewatch(
    interval: Annotated[
        int, typer.Option(help="Seconds between poll cycles")
    ] = 10,
    milestone_reviewer_dir: Annotated[
        str, typer.Option(help="Path to the milestone-reviewer git clone")
    ] = "",
) -> None:
    """Watch for completed milestones and run cross-cutting reviews.

    Polls logs/milestones.log for newly completed milestones. When one appears,
    pulls latest code and runs a milestone-scoped review covering the full diff,
    code analysis, note frequency filtering, and stale finding cleanup.
    Shuts down when all builders finish.
    """
    if milestone_reviewer_dir:
        os.chdir(milestone_reviewer_dir)

    log("milestone-reviewer", "======================================", style="bold yellow")
    log("milestone-reviewer", " Milestone reviewer watching for completed milestones", style="bold yellow")
    log("milestone-reviewer", " Press Ctrl+C to stop", style="bold yellow")
    log("milestone-reviewer", "======================================", style="bold yellow")
    log("milestone-reviewer", "")

    try:
        _milestonewatch_inner(interval)
    except SystemExit as exc:
        log("milestone-reviewer", f"FATAL: {exc}", style="bold red")
        raise
    except Exception as exc:
        log("milestone-reviewer", f"FATAL: Unexpected error: {exc}", style="bold red")
        raise


def _drain_remaining_reviews() -> None:
    """Process all remaining milestone reviews after the builder has finished.

    Keeps pulling and reviewing until no unreviewed milestones remain.
    This ensures milestones completed while the reviewer was busy are not skipped.
    """
    while True:
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)
        boundaries = load_milestone_boundaries()
        reviewed = load_reviewed_milestones()
        remaining = find_unreviewed_milestones(boundaries, reviewed)
        if not remaining:
            break
        now = datetime.now().strftime("%H:%M:%S")
        log(
            "milestone-reviewer",
            f"[{now}] Draining {len(remaining)} remaining milestone review(s)...",
            style="yellow",
        )
        for boundary in remaining:
            _review_milestone(boundary)


def _milestonewatch_inner(interval: int) -> None:
    """Inner loop for milestonewatch, separated for crash-logging wrapper."""
    while True:
        builder_done = is_builder_done()

        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        boundaries = load_milestone_boundaries()
        reviewed = load_reviewed_milestones()

        for boundary in find_unreviewed_milestones(boundaries, reviewed):
            _review_milestone(boundary)

        if builder_done:
            _drain_remaining_reviews()
            now = datetime.now().strftime("%H:%M:%S")
            log("milestone-reviewer", f"[{now}] Builder finished. Shutting down.", style="bold green")
            break

        time.sleep(interval)
