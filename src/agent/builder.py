"""Builder command: fix bugs, address reviews, complete milestones."""

import os
import time
from dataclasses import dataclass, field
from typing import Annotated

import typer

from agent.milestone import (
    count_unstarted_milestones_in_file,
    get_completed_milestones,
    get_current_milestone_progress,
    get_last_milestone_end_sha,
    get_next_eligible_story_in_file,
    has_pending_backlog_stories_in_file,
    has_unexpanded_stories_in_file,
    parse_milestones_from_text,
    record_milestone_boundary,
)
from agent.prompts import BUILDER_PROMPT
from agent.sentinel import are_agents_idle, write_builder_done
from agent.utils import has_unchecked_items, log, run_cmd, run_copilot


def register(app: typer.Typer) -> None:
    """Register builder commands on the shared app."""
    app.command()(build)


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
            if loop:
                action = _run_fix_only_cycle(state)
                if action in ("done", "limit"):
                    write_builder_done()
                    return
                continue  # action == "continue"
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
        # signal == "continue" → loop back


@dataclass
class BuildState:
    """Mutable state shared across build-loop iterations."""

    cycle_count: int = 0
    last_milestone_name: str | None = None
    milestone_retry_count: int = 0
    last_milestone_done_count: int = -1
    fix_only_cycles: int = 0
    post_completion_replans: int = 0


_MAX_MILESTONE_RETRIES = 3
_MAX_FIX_ONLY_CYCLES = 4
_MAX_POST_COMPLETION_REPLANS = 1


def _run_fix_only_cycle(state: BuildState) -> str:
    """Handle a fix-only cycle when no milestones remain.

    Returns 'done' (agents idle, checklists clean), 'limit' (too many
    fix-only cycles), or 'continue' (ran builder, loop again).
    """
    signal = _check_remaining_work(state)
    if signal == "done":
        return "done"
    state.fix_only_cycles += 1
    if state.fix_only_cycles > _MAX_FIX_ONLY_CYCLES:
        log("builder", "")
        log("builder", f"Fix-only cycle limit reached ({_MAX_FIX_ONLY_CYCLES}). "
            "Remaining items deferred. Shutting down.", style="bold yellow")
        return "limit"
    log("builder", "")
    log("builder", f"[Builder] Fixing remaining bugs/reviews "
        f"(fix-only cycle {state.fix_only_cycles}/{_MAX_FIX_ONLY_CYCLES})...",
        style="green")
    log("builder", "")
    run_copilot("builder", BUILDER_PROMPT)
    return "continue"


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


def _handle_fix_only_replan(state: BuildState) -> bool:
    """Handle re-plan when already in fix-only mode. Returns True if a new milestone was found."""
    progress = get_current_milestone_progress("TASKS.md")
    if progress:
        log("builder", "")
        log("builder", "[Milestone Planner] New milestone detected — exiting fix-only mode.", style="magenta")
        state.fix_only_cycles = 0
        state.last_milestone_done_count = progress["done"]
        state.last_milestone_name = progress["name"]
        return True
    log("builder", "")
    log("builder", "[Milestone Planner] Skipping re-plan (already in fix-only mode).", style="dim")
    return False


def _try_expand_backlog(state: BuildState) -> bool:
    """Expand the next eligible backlog story into a milestone. Returns True if a milestone was created."""
    from agent.planner import check_milestone_sizes, plan

    next_story = get_next_eligible_story_in_file("BACKLOG.md")
    if not next_story:
        log("builder", "")
        log("builder", "[Milestone Planner] WARNING: Backlog has pending stories but none are eligible (dependency deadlock).", style="bold yellow")
        return False

    log("builder", "")
    log("builder", f"[Milestone Planner] Planning next story: {next_story['name']}...", style="magenta")
    state.post_completion_replans = 0
    plan()
    check_milestone_sizes()
    return _update_state_from_replan(state)


def _try_expand_legacy_roadmap(state: BuildState) -> bool:
    """Expand the next story from a legacy TASKS.md roadmap. Returns True if a milestone was created."""
    from agent.planner import check_milestone_sizes, plan

    log("builder", "")
    log("builder", "[Milestone Planner] Expanding next story (legacy roadmap)...", style="magenta")
    state.post_completion_replans = 0
    plan()
    check_milestone_sizes()
    return _update_state_from_replan(state)


def _update_state_from_replan(state: BuildState) -> bool:
    """Check for a new milestone after re-planning and update state. Returns True if found."""
    progress = get_current_milestone_progress("TASKS.md")
    if not progress:
        log("builder", "")
        log("builder", "[Milestone Planner] WARNING: Story expansion produced no new milestones.", style="bold yellow")
        return False
    state.last_milestone_done_count = progress["done"]
    state.last_milestone_name = progress["name"]
    unstarted = count_unstarted_milestones_in_file("TASKS.md")
    if unstarted > 1:
        log("builder", f"[Milestone Planner] WARNING: {unstarted} unstarted milestones queued (expected 1).", style="bold yellow")
    return True


def _handle_backlog_expansion(state: BuildState) -> bool:
    """All milestones done and replan limit reached — try backlog or legacy stories."""
    if has_pending_backlog_stories_in_file("BACKLOG.md"):
        return _try_expand_backlog(state)
    if has_unexpanded_stories_in_file("TASKS.md"):
        return _try_expand_legacy_roadmap(state)
    log("builder", "")
    log("builder", "[Milestone Planner] Skipping re-plan (backlog empty, replan limit reached).", style="dim")
    return False


def _handle_loop_replan(state: BuildState, progress: dict | None) -> bool:
    """Handle the re-plan decision when in loop mode after cycle 1. Returns True if work remains."""
    from agent.planner import check_milestone_sizes, plan

    if state.fix_only_cycles > 0:
        return _handle_fix_only_replan(state)

    if not progress and state.post_completion_replans >= _MAX_POST_COMPLETION_REPLANS:
        return _handle_backlog_expansion(state)

    # Normal re-plan
    if not progress:
        state.post_completion_replans += 1
    log("builder", "")
    log("builder", f"[Milestone Planner] Re-evaluating task plan (cycle {state.cycle_count})...", style="magenta")
    plan()
    check_milestone_sizes()
    return _update_state_from_replan(state)


def _detect_milestone_progress(state: BuildState, loop: bool) -> bool:
    """Check milestone progress, re-plan if needed. Return False when stuck."""
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
        return True

    # New milestone or first cycle — re-plan
    state.last_milestone_done_count = current_done
    state.last_milestone_name = current_name

    if loop and state.cycle_count > 1:
        return _handle_loop_replan(state, progress)

    return True


def _record_completed_milestones(milestones_before: set) -> tuple[set, str, set]:
    """Pull latest, snapshot milestones, record boundaries for newly completed ones.

    When the builder completes multiple milestones in a single session (ignoring
    the stop-after-one instruction), we try to reconstruct per-milestone boundaries
    by scanning the git log for the commit that checked off each milestone's last task.
    """
    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    milestones_after = {
        ms["name"] for ms in get_completed_milestones("TASKS.md") if ms["all_done"]
    }
    head_after_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
    head_after = head_after_result.stdout.strip() if head_after_result.returncode == 0 else ""

    newly_completed = milestones_after - milestones_before
    if not newly_completed:
        return milestones_after, head_after, newly_completed

    if len(newly_completed) > 1:
        log(
            "builder",
            f"WARNING: Builder completed {len(newly_completed)} milestones in one session "
            f"(expected 1). Milestones: {', '.join(newly_completed)}",
            style="bold yellow",
        )

    start_sha = get_last_milestone_end_sha()

    # When only one milestone completed, use the simple path
    if len(newly_completed) == 1:
        ms_name = next(iter(newly_completed))
        record_milestone_boundary(ms_name, start_sha, head_after)
        log(
            "builder",
            f"Recorded milestone boundary: {ms_name} ({start_sha[:8]}..{head_after[:8]})",
            style="cyan",
        )
    else:
        # Multiple milestones — try to find per-milestone end commits by scanning
        # git log for TASKS.md changes and mapping them to milestone completions.
        ordered_boundaries = _find_per_milestone_boundaries(
            newly_completed, start_sha, head_after
        )
        for ms_name, ms_start, ms_end in ordered_boundaries:
            record_milestone_boundary(ms_name, ms_start, ms_end)
            log(
                "builder",
                f"Recorded milestone boundary: {ms_name} ({ms_start[:8]}..{ms_end[:8]})",
                style="cyan",
            )

    return milestones_after, head_after, newly_completed


def _find_per_milestone_boundaries(
    milestone_names: set, start_sha: str, end_sha: str,
) -> list[tuple[str, str, str]]:
    """Scan git log to assign per-milestone SHA ranges when multiple completed at once.

    Walks through each commit between start_sha and end_sha, checks the TASKS.md
    at that commit for milestone completion, and records the first commit where
    each milestone became fully checked.

    Returns [(name, start_sha, end_sha), ...] in completion order.
    Falls back to giving all milestones the same range if scanning fails.
    """
    # Get ordered commits from start to end
    result = run_cmd(
        ["git", "log", "--format=%H", "--reverse", f"{start_sha}..{end_sha}"],
        capture=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        # Fallback: all milestones get the same range
        return [(name, start_sha, end_sha) for name in milestone_names]

    commits = [c.strip() for c in result.stdout.strip().split("\n") if c.strip()]
    if not commits:
        return [(name, start_sha, end_sha) for name in milestone_names]

    remaining = set(milestone_names)
    boundaries = []
    current_start = start_sha

    for commit_sha in commits:
        if not remaining:
            break

        # Check TASKS.md at this commit to see which milestones are complete
        show_result = run_cmd(
            ["git", "show", f"{commit_sha}:TASKS.md"],
            capture=True,
        )
        if show_result.returncode != 0:
            continue

        completed_at_commit = set()
        for ms in parse_milestones_from_text(show_result.stdout):
            if ms["name"] in remaining and ms["done"] == ms["total"]:
                completed_at_commit.add(ms["name"])

        for ms_name in completed_at_commit:
            boundaries.append((ms_name, current_start, commit_sha))
            current_start = commit_sha
            remaining.discard(ms_name)

    # Any milestones we couldn't find get the full range
    for ms_name in remaining:
        boundaries.append((ms_name, start_sha, end_sha))

    return boundaries


def classify_remaining_work(bugs: int, reviews: int, tasks: int, agents_idle: bool) -> str:
    """Decide the next action based on remaining work counts and agent status.

    Pure function: returns 'done', 'reviews-only', 'waiting', or 'continue'.
    - 'done' when no work remains and agents are idle
    - 'reviews-only' when only reviews remain (no bugs/tasks) — act immediately
    - 'waiting' when no actionable work but agents are still active
    - 'continue' when bugs or tasks remain (must-fix work)
    """
    has_must_fix = bugs > 0 or tasks > 0
    if has_must_fix:
        return "continue"
    if reviews > 0:
        return "reviews-only"
    if agents_idle:
        return "done"
    return "waiting"


_AGENT_WAIT_INTERVAL = 15
_AGENT_WAIT_MAX_CYCLES = 40  # 15s * 40 = 10 minutes max wait


def _log_work_remaining(bugs: int, reviews: int, tasks: int) -> None:
    """Log which work items remain."""
    log("builder", "")
    log("builder", "Work remaining:", style="cyan")
    if bugs:
        log("builder", f" - Bugs: {bugs} unchecked", style="yellow")
    if reviews:
        log("builder", f" - Reviews: {reviews} unchecked", style="yellow")
    if tasks:
        log("builder", f" - Tasks: {tasks} unchecked", style="yellow")
    log("builder", " Starting next build cycle in 5 seconds...", style="cyan")


def _log_all_done() -> None:
    """Log the all-work-complete banner."""
    log("builder", "")
    log("builder", "======================================", style="bold green")
    log("builder", " All work complete!", style="bold green")
    log("builder", " - Bugs: Done", style="bold green")
    log("builder", " - Reviews: Done", style="bold green")
    log("builder", " - Tasks: Done", style="bold green")
    log("builder", " - Reviewer: Idle", style="bold green")
    log("builder", " - Tester: Idle", style="bold green")
    log("builder", " - Validator: Idle", style="bold green")
    log("builder", "======================================", style="bold green")


def _warn_unexpanded_stories(remaining_tasks: int) -> None:
    """Warn if backlog/roadmap has stories but no milestone tasks exist."""
    if remaining_tasks != 0:
        return
    if has_pending_backlog_stories_in_file("BACKLOG.md"):
        log("builder", "")
        log("builder", "[Planner] WARNING: Backlog has pending stories but no milestone "
            "tasks exist. Planner may have failed to expand.", style="bold yellow")
    elif has_unexpanded_stories_in_file("TASKS.md"):
        log("builder", "")
        log("builder", "[Planner] WARNING: Stories remain unexpanded but no milestone "
            "tasks exist. Planner may have failed to expand.", style="bold yellow")


def _check_remaining_work(state: BuildState) -> str:
    """Wait for agents to finish, then check work lists. Return 'done' or 'continue'."""
    wait_cycle = 0

    while wait_cycle < _AGENT_WAIT_MAX_CYCLES:
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        remaining_bugs = has_unchecked_items("BUGS.md")
        remaining_reviews = has_unchecked_items("REVIEWS.md")
        remaining_tasks = has_unchecked_items("TASKS.md")
        agents_idle = are_agents_idle()

        signal = classify_remaining_work(
            remaining_bugs, remaining_reviews, remaining_tasks, agents_idle
        )

        if signal == "continue":
            _log_work_remaining(remaining_bugs, remaining_reviews, remaining_tasks)
            time.sleep(5)
            return "continue"

        if signal == "reviews-only":
            log("builder", "")
            log("builder", f"Only reviews remain ({remaining_reviews} unchecked). "
                "One more pass, then done.", style="cyan")
            return "continue"

        if signal == "done":
            _warn_unexpanded_stories(remaining_tasks)
            _log_all_done()
            return "done"

        # signal == "waiting" — no work yet, agents still active
        wait_cycle += 1
        if wait_cycle == 1:
            log("builder", "")
            log("builder", "Waiting for reviewer/tester/validator to finish...", style="yellow")
            log("builder", "(Ctrl+C to stop)", style="dim")
        time.sleep(_AGENT_WAIT_INTERVAL)

    log("builder", "")
    log("builder", "Timed out waiting for agents. Exiting.", style="bold yellow")
    return "done"
