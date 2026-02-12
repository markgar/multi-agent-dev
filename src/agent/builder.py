"""Builder command: fix bugs, address reviews, complete milestones."""

import os
import time
from typing import Annotated

import typer

from agent.prompts import BUILDER_PROMPT, PLANNER_SPLIT_PROMPT
from agent.utils import (
    get_completed_milestones,
    get_current_milestone_progress,
    get_last_milestone_end_sha,
    get_tasks_per_milestone,
    git_push_with_retry,
    has_unchecked_items,
    is_builder_done,
    load_reviewer_checkpoint,
    log,
    record_milestone_boundary,
    run_cmd,
    run_copilot,
    write_builder_done,
)


_MAX_TASKS_PER_MILESTONE = 5


def register(app: typer.Typer) -> None:
    """Register builder commands on the shared app."""
    app.command()(build)


def check_milestone_sizes() -> None:
    """If any uncompleted milestone exceeds the task limit, ask the planner to split it."""
    oversized = [
        ms for ms in get_tasks_per_milestone("TASKS.md")
        if ms["task_count"] > _MAX_TASKS_PER_MILESTONE
    ]
    for ms in oversized:
        log(
            "planner",
            f"Milestone '{ms['name']}' has {ms['task_count']} tasks (max {_MAX_TASKS_PER_MILESTONE}). "
            f"Asking planner to split it...",
            style="yellow",
        )
        prompt = PLANNER_SPLIT_PROMPT.format(
            milestone_name=ms["name"],
            task_count=ms["task_count"],
        )
        run_copilot("planner", prompt)

    # Verify once — if still oversized after one attempt, log a warning and proceed
    if oversized:
        still_oversized = [
            ms for ms in get_tasks_per_milestone("TASKS.md")
            if ms["task_count"] > _MAX_TASKS_PER_MILESTONE
        ]
        for ms in still_oversized:
            log(
                "planner",
                f"WARNING: Milestone '{ms['name']}' still has {ms['task_count']} tasks after split attempt.",
                style="red",
            )


def build(
    loop: Annotated[bool, typer.Option(help="Run continuously until all work is done")] = False,
):
    """Fix bugs, address reviews, then complete the current milestone. One milestone per cycle."""
    # Import here to avoid circular import — plan lives in cli.py
    from agent.cli import plan

    if not os.path.exists("TASKS.md"):
        log("builder", "No TASKS.md found. Run 'plan' first to generate tasks.", style="yellow")
        write_builder_done()
        return

    cycle_count = 0
    no_work_count = 0
    last_milestone_name = None
    milestone_retry_count = 0
    last_milestone_done_count = -1
    _MAX_MILESTONE_RETRIES = 3

    while True:
        cycle_count += 1

        # Decide whether to re-plan or retry the current milestone
        progress = get_current_milestone_progress("TASKS.md")
        if progress and last_milestone_name == progress["name"]:
            # Same milestone as last cycle — partial completion
            if progress["done"] <= last_milestone_done_count:
                # No forward progress — increment retry counter
                milestone_retry_count += 1
                if milestone_retry_count >= _MAX_MILESTONE_RETRIES:
                    log("builder", "")
                    log("builder", "======================================", style="bold red")
                    log(
                        "builder",
                        f" Milestone '{progress['name']}' stuck after {_MAX_MILESTONE_RETRIES} retries",
                        style="bold red",
                    )
                    log("builder", "======================================", style="bold red")
                    write_builder_done()
                    return
            else:
                # Made progress — reset retry counter
                milestone_retry_count = 0

            last_milestone_done_count = progress["done"]
            log("builder", "")
            log(
                "builder",
                f"[Builder] Resuming incomplete milestone '{progress['name']}' "
                f"({progress['done']}/{progress['total']} tasks done, "
                f"attempt {milestone_retry_count + 1})...",
                style="yellow",
            )
        else:
            # New milestone or first cycle — re-plan
            milestone_retry_count = 0
            last_milestone_done_count = progress["done"] if progress else -1
            last_milestone_name = progress["name"] if progress else None

            if loop and cycle_count > 1:
                log("builder", "")
                log("builder", f"[Planner] Re-evaluating task plan (cycle {cycle_count})...", style="magenta")
                plan()
                check_milestone_sizes()

        # Snapshot completed milestones before the builder runs
        milestones_before = {
            ms["name"] for ms in get_completed_milestones("TASKS.md") if ms["all_done"]
        }

        log("builder", "")
        log("builder", "[Builder] Starting work (completing current milestone)...", style="green")
        log("builder", "")

        exit_code = run_copilot("builder", BUILDER_PROMPT)

        if exit_code != 0:
            log("builder", "")
            log("builder", "======================================", style="bold red")
            log("builder", " Builder failed! Check errors above", style="bold red")
            log("builder", "======================================", style="bold red")
            write_builder_done()
            return

        # Snapshot milestone state and HEAD after the builder runs
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)
        milestones_after = {
            ms["name"] for ms in get_completed_milestones("TASKS.md") if ms["all_done"]
        }
        head_after_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
        head_after = head_after_result.stdout.strip() if head_after_result.returncode == 0 else ""

        # Record SHA boundaries for any newly completed milestones
        newly_completed = milestones_after - milestones_before
        if newly_completed:
            # Get the start SHA before recording (previous milestone's end, or bootstrap commit)
            start_sha = get_last_milestone_end_sha()
            for ms_name in newly_completed:
                record_milestone_boundary(ms_name, start_sha, head_after)
                log(
                    "builder",
                    f"Recorded milestone boundary: {ms_name} ({start_sha[:8]}..{head_after[:8]})",
                    style="cyan",
                )

        # --- Reviewer drain window ---
        # Wait up to 2 minutes for the reviewer to catch up to our latest commit.
        # This ensures review findings land in REVIEWS.md before re-planning.
        if newly_completed and loop:
            reviewer_checkpoint = load_reviewer_checkpoint()
            if reviewer_checkpoint and reviewer_checkpoint != head_after:
                log("builder", "")
                log(
                    "builder",
                    "Waiting for reviewer to catch up (up to 2 minutes)...",
                    style="yellow",
                )
                drain_deadline = time.time() + 120  # 2 minutes
                while time.time() < drain_deadline:
                    time.sleep(10)
                    reviewer_checkpoint = load_reviewer_checkpoint()
                    if reviewer_checkpoint == head_after:
                        log("builder", "Reviewer caught up.", style="green")
                        break
                else:
                    log(
                        "builder",
                        "Drain window expired. Proceeding.",
                        style="yellow",
                    )

        log("builder", "")
        log("builder", "======================================", style="bold cyan")
        log("builder", " Milestone complete!", style="bold cyan")
        log("builder", "======================================", style="bold cyan")

        if not loop:
            write_builder_done()
            break

        remaining_bugs = has_unchecked_items("BUGS.md")
        remaining_reviews = has_unchecked_items("REVIEWS.md")
        remaining_tasks = has_unchecked_items("TASKS.md")

        if not remaining_bugs and not remaining_reviews and not remaining_tasks:
            no_work_count += 1

            if no_work_count >= 3:
                log("builder", "")
                log("builder", "======================================", style="bold green")
                log("builder", " All work complete!", style="bold green")
                log("builder", " - Bugs: Done", style="bold green")
                log("builder", " - Reviews: Done", style="bold green")
                log("builder", " - Tasks: Done", style="bold green")
                log("builder", "======================================", style="bold green")
                write_builder_done()
                break
            else:
                log("builder", "")
                log("builder", f"No work found (check {no_work_count}/3)", style="yellow")
                log("builder", "Waiting 1 minute in case reviewer/tester are working...", style="yellow")
                log("builder", "(Ctrl+C to stop)", style="dim")
                time.sleep(60)
                continue

        no_work_count = 0

        log("builder", "")
        log("builder", "Work remaining:", style="cyan")
        if remaining_bugs:
            log("builder", f" - Bugs: {remaining_bugs} unchecked", style="yellow")
        if remaining_reviews:
            log("builder", f" - Reviews: {remaining_reviews} unchecked", style="yellow")
        if remaining_tasks:
            log("builder", f" - Tasks: {remaining_tasks} unchecked", style="yellow")
        log("builder", " Starting next milestone in 5 seconds... (Ctrl+C to stop)", style="cyan")
        time.sleep(5)
