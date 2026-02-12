"""Builder command: fix bugs, address reviews, complete milestones."""

import os
import time
from dataclasses import dataclass, field
from typing import Annotated

import typer

from agent.milestone import (
    get_completed_milestones,
    get_current_milestone_progress,
    get_last_milestone_end_sha,
    get_tasks_per_milestone,
    record_milestone_boundary,
)
from agent.prompts import BUILDER_PROMPT, PLANNER_SPLIT_PROMPT
from agent.sentinel import load_reviewer_checkpoint, write_builder_done
from agent.utils import has_unchecked_items, log, run_cmd, run_copilot


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
    if not os.path.exists("TASKS.md"):
        log("builder", "No TASKS.md found. Run 'plan' first to generate tasks.", style="yellow")
        write_builder_done()
        return

    state = BuildState()

    while True:
        state.cycle_count += 1

        if not _detect_milestone_progress(state, loop):
            write_builder_done()
            return

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

        milestones_after, head_after, newly_completed = _record_completed_milestones(milestones_before)

        if newly_completed and loop:
            _wait_for_reviewer_drain(head_after)

        log("builder", "")
        log("builder", "======================================", style="bold cyan")
        log("builder", " Milestone complete!", style="bold cyan")
        log("builder", "======================================", style="bold cyan")

        if not loop:
            write_builder_done()
            break

        signal = _check_remaining_work(state)
        if signal == "done":
            write_builder_done()
            break
        elif signal == "idle":
            continue
        # signal == "continue" → loop back


@dataclass
class BuildState:
    """Mutable state shared across build-loop iterations."""

    cycle_count: int = 0
    no_work_count: int = 0
    last_milestone_name: str | None = None
    milestone_retry_count: int = 0
    last_milestone_done_count: int = -1


_MAX_MILESTONE_RETRIES = 3


def update_milestone_retry_state(
    current_name: str | None,
    current_done: int,
    last_name: str | None,
    last_done: int,
    retry_count: int,
    max_retries: int,
) -> tuple[bool, int]:
    """Determine if a milestone is stuck and update the retry count.

    Pure function: returns (is_stuck, new_retry_count).
    is_stuck is True when the same milestone has failed to make progress
    max_retries times in a row.
    """
    if current_name and current_name == last_name:
        if current_done <= last_done:
            new_count = retry_count + 1
            return (new_count >= max_retries, new_count)
        return (False, 0)
    return (False, 0)


def _detect_milestone_progress(state: BuildState, loop: bool) -> bool:
    """Check milestone progress, re-plan if needed. Return False when stuck."""
    # Import here to avoid circular import — plan lives in cli.py
    from agent.cli import plan

    progress = get_current_milestone_progress("TASKS.md")
    current_name = progress["name"] if progress else None
    current_done = progress["done"] if progress else -1

    is_stuck, new_retry_count = update_milestone_retry_state(
        current_name, current_done,
        state.last_milestone_name, state.last_milestone_done_count,
        state.milestone_retry_count, _MAX_MILESTONE_RETRIES,
    )
    state.milestone_retry_count = new_retry_count

    if is_stuck:
        log("builder", "")
        log("builder", "======================================", style="bold red")
        log(
            "builder",
            f" Milestone '{current_name}' stuck after {_MAX_MILESTONE_RETRIES} retries",
            style="bold red",
        )
        log("builder", "======================================", style="bold red")
        return False

    if progress and state.last_milestone_name == current_name:
        state.last_milestone_done_count = current_done
        log("builder", "")
        log(
            "builder",
            f"[Builder] Resuming incomplete milestone '{current_name}' "
            f"({current_done}/{progress['total']} tasks done, "
            f"attempt {state.milestone_retry_count + 1})...",
            style="yellow",
        )
    else:
        # New milestone or first cycle — re-plan
        state.last_milestone_done_count = current_done
        state.last_milestone_name = current_name

        if loop and state.cycle_count > 1:
            log("builder", "")
            log("builder", f"[Planner] Re-evaluating task plan (cycle {state.cycle_count})...", style="magenta")
            plan()
            check_milestone_sizes()

            # Re-check after re-plan: if still no milestone, nothing to do
            progress = get_current_milestone_progress("TASKS.md")
            if not progress:
                return False

    return True


def _record_completed_milestones(milestones_before: set) -> tuple[set, str, set]:
    """Pull latest, snapshot milestones, record boundaries for newly completed ones."""
    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    milestones_after = {
        ms["name"] for ms in get_completed_milestones("TASKS.md") if ms["all_done"]
    }
    head_after_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
    head_after = head_after_result.stdout.strip() if head_after_result.returncode == 0 else ""

    newly_completed = milestones_after - milestones_before
    if newly_completed:
        start_sha = get_last_milestone_end_sha()
        for ms_name in newly_completed:
            record_milestone_boundary(ms_name, start_sha, head_after)
            log(
                "builder",
                f"Recorded milestone boundary: {ms_name} ({start_sha[:8]}..{head_after[:8]})",
                style="cyan",
            )

    return milestones_after, head_after, newly_completed


def _wait_for_reviewer_drain(head_after: str) -> None:
    """Wait up to 2 minutes for the reviewer to catch up to our latest commit."""
    reviewer_checkpoint = load_reviewer_checkpoint()
    if not reviewer_checkpoint or reviewer_checkpoint == head_after:
        return

    log("builder", "")
    log("builder", "Waiting for reviewer to catch up (up to 2 minutes)...", style="yellow")

    drain_deadline = time.time() + 120
    while time.time() < drain_deadline:
        time.sleep(10)
        reviewer_checkpoint = load_reviewer_checkpoint()
        if reviewer_checkpoint == head_after:
            log("builder", "Reviewer caught up.", style="green")
            break
    else:
        log("builder", "Drain window expired. Proceeding.", style="yellow")


def classify_remaining_work(bugs: int, reviews: int, tasks: int, no_work_count: int) -> str:
    """Decide the next action based on remaining work counts.

    Pure function: returns 'done', 'idle', or 'continue'.
    - 'done' when no work remains and no_work_count >= 3
    - 'idle' when no work remains but hasn't been confirmed 3 times yet
    - 'continue' when there is remaining work
    """
    if not bugs and not reviews and not tasks:
        if no_work_count >= 3:
            return "done"
        return "idle"
    return "continue"


def _check_remaining_work(state: BuildState) -> str:
    """Check for remaining bugs, reviews, and tasks. Return 'done', 'idle', or 'continue'."""
    remaining_bugs = has_unchecked_items("BUGS.md")
    remaining_reviews = has_unchecked_items("REVIEWS.md")
    remaining_tasks = has_unchecked_items("TASKS.md")

    state.no_work_count = 0 if (remaining_bugs or remaining_reviews or remaining_tasks) else state.no_work_count + 1

    signal = classify_remaining_work(remaining_bugs, remaining_reviews, remaining_tasks, state.no_work_count)

    if signal == "done":
        log("builder", "")
        log("builder", "======================================", style="bold green")
        log("builder", " All work complete!", style="bold green")
        log("builder", " - Bugs: Done", style="bold green")
        log("builder", " - Reviews: Done", style="bold green")
        log("builder", " - Tasks: Done", style="bold green")
        log("builder", "======================================", style="bold green")
    elif signal == "idle":
        log("builder", "")
        log("builder", f"No work found (check {state.no_work_count}/3)", style="yellow")
        log("builder", "Waiting 1 minute in case reviewer/tester are working...", style="yellow")
        log("builder", "(Ctrl+C to stop)", style="dim")
        time.sleep(60)
    else:
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

    return signal
