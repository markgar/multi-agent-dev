"""Builder command: claim stories, fix bugs, address reviews, complete milestones."""

import os
import re
import time
from dataclasses import dataclass
from typing import Annotated

import typer

from agentic_dev.git_helpers import git_push_with_retry
from agentic_dev.milestone import (
    get_all_milestones,
    get_completed_milestones_from_dir,
    get_last_milestone_end_sha,
    get_milestone_progress_from_file,
    get_next_eligible_story_in_file,
    has_pending_backlog_stories_in_file,
    parse_milestone_file,
    record_milestone_boundary,
)
from agentic_dev.prompts import BUILDER_PROMPT
from agentic_dev.sentinel import are_agents_idle, write_builder_done
from agentic_dev.utils import count_open_items_in_dir, count_partitioned_open_items, log, run_cmd, run_copilot


def register(app: typer.Typer) -> None:
    """Register builder commands on the shared app."""
    app.command()(build)


# ============================================
# Pure text-manipulation functions for BACKLOG.md
# ============================================

_BACKLOG_LINE_RE = re.compile(
    r"^(\d+)\.\s+\[([ xX~])\]\s+(.+?)(?:\s*<!--\s*depends:\s*[\d,\s]+\s*-->)?$"
)


def mark_story_claimed(content: str, story_number: int) -> str:
    """Replace [ ] with [~] for the given story number in backlog text.

    Pure function: returns the modified content string. Only modifies the
    first line whose number matches and whose checkbox is unclaimed ([ ]).
    """
    lines = content.split("\n")
    for i, line in enumerate(lines):
        m = _BACKLOG_LINE_RE.match(line.strip())
        if m and int(m.group(1)) == story_number and m.group(2).strip() == "":
            lines[i] = line.replace("[ ]", "[~]", 1)
            break
    return "\n".join(lines)


def mark_story_completed_text(content: str, story_number: int) -> str:
    """Replace [~] with [x] for the given story number in backlog text.

    Pure function: returns the modified content string. Only modifies the
    first line whose number matches and whose checkbox is in-progress ([~]).
    """
    lines = content.split("\n")
    for i, line in enumerate(lines):
        m = _BACKLOG_LINE_RE.match(line.strip())
        if m and int(m.group(1)) == story_number and m.group(2) == "~":
            lines[i] = line.replace("[~]", "[x]", 1)
            break
    return "\n".join(lines)


def mark_story_unclaimed_text(content: str, story_number: int) -> str:
    """Replace [~] with [ ] for the given story number in backlog text.

    Pure function: returns the modified content string. Reverts a claimed
    story back to unclaimed so another builder can pick it up.
    """
    lines = content.split("\n")
    for i, line in enumerate(lines):
        m = _BACKLOG_LINE_RE.match(line.strip())
        if m and int(m.group(1)) == story_number and m.group(2) == "~":
            lines[i] = line.replace("[~]", "[ ]", 1)
            break
    return "\n".join(lines)


# ============================================
# Git-based story claim and completion
# ============================================

_BACKLOG_FILE = "BACKLOG.md"


def claim_next_story(agent_name: str, max_attempts: int = 10) -> dict | None:
    """Claim the next eligible story from BACKLOG.md using git push as a lock.

    Flow:
    1. git pull --rebase
    2. Read BACKLOG.md, find next eligible unclaimed story
    3. Mark it in-progress ([ ] -> [~])
    4. git commit + push
    5. If push fails: pull (winner's claim arrives), go to step 2
    6. Returns the claimed story dict, or None if no eligible stories
    """
    for attempt in range(1, max_attempts + 1):
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        story = get_next_eligible_story_in_file(_BACKLOG_FILE)
        if story is None:
            return None

        # Read, modify, and write BACKLOG.md
        try:
            with open(_BACKLOG_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            new_content = mark_story_claimed(content, story["number"])
            if new_content == content:
                log(agent_name, f"WARNING: Could not mark story {story['number']} as claimed.", style="yellow")
                return None
            with open(_BACKLOG_FILE, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            log(agent_name, f"WARNING: Failed to update BACKLOG.md: {e}", style="yellow")
            return None

        # Commit and push
        run_cmd(["git", "add", _BACKLOG_FILE])
        run_cmd(["git", "commit", "-m", f"[planner] Claim story {story['number']}: {story['name']}"])

        push_result = run_cmd(["git", "push"], capture=True)
        if push_result.returncode == 0:
            log(agent_name, f"Claimed story {story['number']}: {story['name']}", style="green")
            return story

        # Push failed -- someone else claimed first. Pull and retry.
        log(
            agent_name,
            f"Claim race lost (attempt {attempt}/{max_attempts}). Pulling and retrying...",
            style="yellow",
        )
        pull_result = run_cmd(["git", "pull", "--rebase"], capture=True)
        if pull_result.returncode != 0:
            run_cmd(["git", "rebase", "--abort"], quiet=True)
            run_cmd(["git", "pull", "--rebase"], quiet=True)

    log(agent_name, f"Could not claim a story after {max_attempts} attempts.", style="bold yellow")
    return None


def mark_story_completed(story_number: int, agent_name: str, max_attempts: int = 5) -> bool:
    """Mark a claimed story as completed in BACKLOG.md ([~] -> [x]).

    Uses the same git-push-as-lock pattern as claim_next_story.
    Returns True if successfully marked, False if failed after retries.
    """
    for attempt in range(1, max_attempts + 1):
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        try:
            with open(_BACKLOG_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            new_content = mark_story_completed_text(content, story_number)
            if new_content == content:
                log(agent_name, f"WARNING: Story {story_number} not in [~] state -- may already be completed.", style="yellow")
                return True  # idempotent
            with open(_BACKLOG_FILE, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            log(agent_name, f"WARNING: Failed to update BACKLOG.md: {e}", style="yellow")
            return False

        run_cmd(["git", "add", _BACKLOG_FILE])
        run_cmd(["git", "commit", "-m", f"[builder] Complete story {story_number}"])

        push_result = run_cmd(["git", "push"], capture=True)
        if push_result.returncode == 0:
            return True

        log(
            agent_name,
            f"Push failed marking story {story_number} complete (attempt {attempt}/{max_attempts}).",
            style="yellow",
        )
        pull_result = run_cmd(["git", "pull", "--rebase"], capture=True)
        if pull_result.returncode != 0:
            run_cmd(["git", "rebase", "--abort"], quiet=True)
            run_cmd(["git", "pull", "--rebase"], quiet=True)

    log(agent_name, f"Failed to mark story {story_number} complete after {max_attempts} attempts.", style="red")
    return False


def unclaim_story(story_number: int, agent_name: str, max_attempts: int = 5) -> bool:
    """Revert a claimed story back to unclaimed in BACKLOG.md ([~] -> [ ]).

    Used when the planner fails to produce a valid milestone file, so the
    story can be retried later (possibly by another builder).
    Uses the same git-push-as-lock pattern as claim_next_story.
    Returns True if successfully unclaimed, False if failed after retries.
    """
    for attempt in range(1, max_attempts + 1):
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        try:
            with open(_BACKLOG_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            new_content = mark_story_unclaimed_text(content, story_number)
            if new_content == content:
                log(agent_name, f"WARNING: Story {story_number} not in [~] state -- cannot unclaim.", style="yellow")
                return True  # idempotent
            with open(_BACKLOG_FILE, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            log(agent_name, f"WARNING: Failed to update BACKLOG.md: {e}", style="yellow")
            return False

        run_cmd(["git", "add", _BACKLOG_FILE])
        run_cmd(["git", "commit", "-m", f"[builder] Unclaim story {story_number} (milestone planning failed)"])

        push_result = run_cmd(["git", "push"], capture=True)
        if push_result.returncode == 0:
            log(agent_name, f"Unclaimed story {story_number}.", style="yellow")
            return True

        log(
            agent_name,
            f"Push failed unclaiming story {story_number} (attempt {attempt}/{max_attempts}).",
            style="yellow",
        )
        pull_result = run_cmd(["git", "pull", "--rebase"], capture=True)
        if pull_result.returncode != 0:
            run_cmd(["git", "rebase", "--abort"], quiet=True)
            run_cmd(["git", "pull", "--rebase"], quiet=True)

    log(agent_name, f"Failed to unclaim story {story_number} after {max_attempts} attempts.", style="red")
    return False


# ============================================
# Milestone file discovery
# ============================================


def find_milestone_file_for_story(milestones_dir: str = "milestones") -> str | None:
    """Find the most recently created milestone file with unchecked tasks.

    After the planner runs, there should be a new .md file in milestones/
    that has unchecked tasks. Returns the path to that file, or None.
    """
    candidates = []
    for ms in get_all_milestones(milestones_dir):
        if not ms["all_done"]:
            path = ms["path"]
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0
            candidates.append((mtime, path))

    if not candidates:
        return None

    # Return the most recently modified incomplete milestone file
    candidates.sort(reverse=True)
    return candidates[0][1]


def _build_partition_filter(builder_id: int, num_builders: int) -> str:
    """Build the prompt text that tells this builder which bugs/findings to fix.

    When num_builders is 1, returns empty string (no filtering).
    Otherwise returns a sentence listing the assigned last digits.
    """
    if num_builders <= 1:
        return ""
    assigned = [d for d in range(10) if d % num_builders == (builder_id - 1)]
    digits_str = ", ".join(str(d) for d in assigned)
    return (
        f"You are builder {builder_id} of {num_builders}. Only fix bugs/findings "
        f"whose filename ends in one of these digits (before `.md`): {digits_str}. "
        "Skip all others — another builder will handle them. "
    )


# ============================================
# Build loop helpers
# ============================================


@dataclass
class BuildState:
    """Mutable state shared across build-loop iterations."""

    cycle_count: int = 0
    fix_only_cycles: int = 0


_MAX_FIX_ONLY_CYCLES = 4
_AGENT_WAIT_INTERVAL = 15
_AGENT_WAIT_MAX_CYCLES = 40  # 15s * 40 = 10 minutes max wait


def classify_remaining_work(bugs: int, reviews: int, tasks: int, agents_idle: bool) -> str:
    """Decide the next action based on remaining work counts and agent status.

    Pure function: returns 'done', 'reviews-only', 'waiting', or 'continue'.
    - 'done' when no work remains and agents are idle
    - 'reviews-only' when only reviews remain (no bugs/tasks) -- act immediately
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


def _record_completed_milestone(
    milestone_file: str, milestones_before: set, agent_name: str,
) -> set:
    """Pull latest, check if the milestone is now complete, record its boundary.

    Returns the updated set of completed milestone names.
    """
    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    milestones_after = {
        ms["name"] for ms in get_completed_milestones_from_dir("milestones")
    }

    newly_completed = milestones_after - milestones_before
    if not newly_completed:
        # Also check the specific milestone file directly
        ms = parse_milestone_file(milestone_file)
        if ms and ms["all_done"]:
            newly_completed = {ms["name"]}

    if not newly_completed:
        log(agent_name, "WARNING: Milestone does not appear complete after build.", style="bold yellow")
        return milestones_after

    start_sha = get_last_milestone_end_sha()
    head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
    head_sha = head_result.stdout.strip() if head_result.returncode == 0 else ""

    for ms_name in newly_completed:
        record_milestone_boundary(ms_name, start_sha, head_sha)
        log(
            agent_name,
            f"Recorded milestone boundary: {ms_name} ({start_sha[:8]}..{head_sha[:8]})",
            style="cyan",
        )

    return milestones_after


def _log_work_remaining(agent_name: str, bugs: int, reviews: int) -> None:
    """Log which work items remain."""
    log(agent_name, "")
    log(agent_name, "Work remaining:", style="cyan")
    if bugs:
        log(agent_name, f" - Bugs: {bugs} unchecked", style="yellow")
    if reviews:
        log(agent_name, f" - Reviews: {reviews} unchecked", style="yellow")
    log(agent_name, " Starting fix cycle...", style="cyan")


def _log_all_done(agent_name: str) -> None:
    """Log the all-work-complete banner."""
    log(agent_name, "")
    log(agent_name, "======================================", style="bold green")
    log(agent_name, " All work complete!", style="bold green")
    log(agent_name, " - Bugs: Done", style="bold green")
    log(agent_name, " - Reviews: Done", style="bold green")
    log(agent_name, " - Reviewer: Idle", style="bold green")
    log(agent_name, " - Tester: Idle", style="bold green")
    log(agent_name, " - Validator: Idle", style="bold green")
    log(agent_name, "======================================", style="bold green")


def _check_remaining_work(
    state: BuildState, agent_name: str, milestone_file: str,
    builder_id: int = 1, num_builders: int = 1,
) -> str:
    """Wait for agents to finish, then check work lists. Return 'done' or 'continue'."""
    wait_cycle = 0

    while wait_cycle < _AGENT_WAIT_MAX_CYCLES:
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        remaining_bugs = count_partitioned_open_items(
            "bugs", "bug-", "fixed-", builder_id, num_builders,
        )
        remaining_reviews = count_partitioned_open_items(
            "reviews", "finding-", "resolved-", builder_id, num_builders,
        )
        # Check the builder's own milestone file for unchecked tasks
        progress = get_milestone_progress_from_file(milestone_file)
        remaining_tasks = 0 if progress is None else (progress["total"] - progress["done"])
        agents_idle = are_agents_idle()

        signal = classify_remaining_work(
            remaining_bugs, remaining_reviews, remaining_tasks, agents_idle
        )

        if signal == "continue":
            _log_work_remaining(agent_name, remaining_bugs, remaining_reviews)
            time.sleep(5)
            return "continue"

        if signal == "reviews-only":
            log(agent_name, "")
            log(agent_name, f"Only reviews remain ({remaining_reviews} unchecked). "
                "One more pass, then done.", style="cyan")
            return "continue"

        if signal == "done":
            _log_all_done(agent_name)
            return "done"

        # signal == "waiting" -- no work yet, agents still active
        wait_cycle += 1
        if wait_cycle == 1:
            log(agent_name, "")
            log(agent_name, "Waiting for reviewer/tester/validator to finish...", style="yellow")
            log(agent_name, "(Ctrl+C to stop)", style="dim")
        time.sleep(_AGENT_WAIT_INTERVAL)

    log(agent_name, "")
    log(agent_name, "Timed out waiting for agents. Exiting.", style="bold yellow")
    return "done"


def _run_fix_only_cycle(
    state: BuildState, agent_name: str, milestone_file: str,
    builder_id: int = 1, num_builders: int = 1,
) -> str:
    """Handle a fix-only cycle when the milestone is complete but work remains.

    Returns 'done', 'limit', or 'continue'.
    """
    signal = _check_remaining_work(state, agent_name, milestone_file, builder_id, num_builders)
    if signal == "done":
        return "done"
    state.fix_only_cycles += 1
    if state.fix_only_cycles > _MAX_FIX_ONLY_CYCLES:
        log(agent_name, "")
        log(agent_name, f"Fix-only cycle limit reached ({_MAX_FIX_ONLY_CYCLES}). "
            "Remaining items deferred. Shutting down.", style="bold yellow")
        return "limit"
    log(agent_name, "")
    log(agent_name, f"[Builder] Fixing remaining bugs/reviews "
        f"(fix-only cycle {state.fix_only_cycles}/{_MAX_FIX_ONLY_CYCLES})...",
        style="green")
    log(agent_name, "")
    prompt = BUILDER_PROMPT.format(
        milestone_file=milestone_file,
        partition_filter=_build_partition_filter(builder_id, num_builders),
    )
    run_copilot(agent_name, prompt)
    return "continue"


# ============================================
# Main build command
# ============================================


def build(
    loop: Annotated[bool, typer.Option(help="Run continuously until all work is done")] = False,
    builder_id: Annotated[int, typer.Option(help="Builder instance number (1-based)")] = 1,
    num_builders: Annotated[int, typer.Option(help="Total number of builder instances")] = 1,
) -> None:
    """Claim stories from BACKLOG.md, fix bugs, address reviews, complete milestones.

    In loop mode: claim -> plan -> build -> complete -> repeat until all stories done.
    In non-loop mode: build a single milestone (legacy compatibility).
    """
    agent_name = f"builder-{builder_id}"
    state = BuildState()

    if not loop:
        # Non-loop mode: find the first incomplete milestone file and build it
        milestone_file = find_milestone_file_for_story("milestones")
        if not milestone_file:
            log(agent_name, "No incomplete milestone file found. Nothing to build.", style="yellow")
            write_builder_done(builder_id)
            return

        log(agent_name, "")
        log(agent_name, f"[Builder] Starting work on {milestone_file}...", style="green")
        log(agent_name, "")

        prompt = BUILDER_PROMPT.format(
            milestone_file=milestone_file,
            partition_filter=_build_partition_filter(builder_id, num_builders),
        )
        exit_code = run_copilot(agent_name, prompt)
        if exit_code != 0:
            log(agent_name, "Builder failed! Check errors above.", style="bold red")
        write_builder_done(builder_id)
        return

    # Loop mode: claim-and-build pattern
    while True:
        state.cycle_count += 1

        story = claim_next_story(agent_name)
        if story is None:
            # No eligible stories -- check if pending (dep deadlock) or truly done
            if has_pending_backlog_stories_in_file(_BACKLOG_FILE):
                log(agent_name, "")
                log(agent_name, "No eligible stories (dependency deadlock or all claimed). "
                    "Waiting for other builders...", style="yellow")
                time.sleep(30)
                if has_pending_backlog_stories_in_file(_BACKLOG_FILE):
                    continue  # retry -- another builder may complete a dep
            # All done or permanently blocked
            log(agent_name, "")
            log(agent_name, "No more stories to claim.", style="bold cyan")

            # Enter shutdown: wait for agents, fix remaining bugs/reviews
            milestone_file = find_milestone_file_for_story("milestones") or "milestones/done.md"
            signal = _check_remaining_work(state, agent_name, milestone_file, builder_id, num_builders)
            if signal == "done":
                write_builder_done(builder_id)
                return
            # Still work to do -- run fix-only cycles
            while True:
                action = _run_fix_only_cycle(state, agent_name, milestone_file, builder_id, num_builders)
                if action in ("done", "limit"):
                    write_builder_done(builder_id)
                    return

        # Plan: expand this story into a milestone file
        from agentic_dev.planner import check_milestone_sizes, plan

        # Snapshot incomplete milestones before planning so we can detect new ones
        incomplete_before = {
            ms["path"] for ms in get_all_milestones("milestones") if not ms["all_done"]
        }

        log(agent_name, "")
        log(agent_name, f"[Milestone Planner] Planning story: {story['name']}...", style="magenta")
        plan(story_name=story["name"])
        check_milestone_sizes()

        # Identify all NEW milestone files created by plan + split
        new_milestones = [
            ms["path"] for ms in get_all_milestones("milestones")
            if not ms["all_done"] and ms["path"] not in incomplete_before
        ]
        if not new_milestones:
            log(agent_name, "ERROR: Planner did not create a milestone file with checkboxes.", style="bold red")
            log(agent_name, "Unclaiming story and stopping builder.", style="bold red")
            unclaim_story(story["number"], agent_name)
            write_builder_done(builder_id)
            return

        new_milestones.sort()  # deterministic order (08a before 08b)
        if len(new_milestones) > 1:
            log(agent_name, f"Story was split into {len(new_milestones)} milestones.", style="cyan")

        # Build each milestone part sequentially
        build_failed = False
        for milestone_file in new_milestones:
            milestones_before = {
                ms["name"] for ms in get_completed_milestones_from_dir("milestones")
            }

            log(agent_name, "")
            log(agent_name, f"[Builder] Starting work on {milestone_file}...", style="green")
            log(agent_name, "")

            prompt = BUILDER_PROMPT.format(
                milestone_file=milestone_file,
                partition_filter=_build_partition_filter(builder_id, num_builders),
            )
            exit_code = run_copilot(agent_name, prompt)

            if exit_code != 0:
                log(agent_name, "")
                log(agent_name, "======================================", style="bold red")
                log(agent_name, " Builder failed! Check errors above", style="bold red")
                log(agent_name, "======================================", style="bold red")
                build_failed = True
                break

            _record_completed_milestone(milestone_file, milestones_before, agent_name)

            log(agent_name, "")
            log(agent_name, "======================================", style="bold cyan")
            log(agent_name, " Milestone complete!", style="bold cyan")
            log(agent_name, "======================================", style="bold cyan")

        if build_failed:
            write_builder_done(builder_id)
            return

        # Mark story as completed ([~] -> [x]) so downstream deps unlock
        mark_story_completed(story["number"], agent_name)

        # Loop back to claim next story
