"""Builder command: claim stories, fix bugs, address reviews, complete milestones."""

import os
import re
import time
from dataclasses import dataclass
from typing import Annotated

import typer

from agentic_dev.git_helpers import (
    create_milestone_branch,
    delete_milestone_branch,
    ensure_on_main,
    git_push_with_retry,
    merge_milestone_to_main,
)
from agentic_dev.milestone import (
    get_all_milestones,
    get_last_milestone_end_sha,
    get_milestone_progress_from_file,
    get_next_eligible_story_in_file,
    has_pending_backlog_stories_in_file,
    parse_milestone_file,
    record_milestone_boundary,
)
from agentic_dev.prompts import (
    BUILDER_FIX_ONLY_PROMPT,
    BUILDER_ISSUE_FIXING_SECTION,
    BUILDER_PROMPT,
)
from agentic_dev.sentinel import (
    are_agents_idle,
    clear_branch_review_head,
    load_branch_review_head,
    write_builder_done,
)
from agentic_dev.utils import count_open_bug_issues, count_open_finding_issues, log, run_cmd, run_copilot


def register(app: typer.Typer) -> None:
    """Register builder commands on the shared app."""
    app.command()(build)


# ============================================
# Pure text-manipulation functions for BACKLOG.md
# ============================================

_BACKLOG_LINE_RE = re.compile(
    r"^(\d+)\.\s+\[([ xX]|\d+)\]\s+(.+?)(?:\s*<!--\s*depends:\s*[\d,\s]+\s*-->)?$"
)


def mark_story_claimed(content: str, story_number: int, builder_id: int = 1) -> str:
    """Replace [ ] with [N] for the given story number in backlog text.

    Pure function: returns the modified content string. Only modifies the
    first line whose number matches and whose checkbox is unclaimed ([ ]).
    The builder_id is written into the checkbox so concurrent claims produce
    different text, causing git merge conflicts that prevent double-claims.
    """
    lines = content.split("\n")
    for i, line in enumerate(lines):
        m = _BACKLOG_LINE_RE.match(line.strip())
        if m and int(m.group(1)) == story_number and m.group(2).strip() == "":
            lines[i] = line.replace("[ ]", f"[{builder_id}]", 1)
            break
    return "\n".join(lines)


def mark_story_completed_text(content: str, story_number: int) -> str:
    """Replace [N] with [x] for the given story number in backlog text.

    Pure function: returns the modified content string. Only modifies the
    first line whose number matches and whose checkbox is in-progress ([N]).
    """
    lines = content.split("\n")
    for i, line in enumerate(lines):
        m = _BACKLOG_LINE_RE.match(line.strip())
        if m and int(m.group(1)) == story_number and m.group(2).isdigit():
            marker = m.group(2)
            lines[i] = line.replace(f"[{marker}]", "[x]", 1)
            break
    return "\n".join(lines)


def mark_story_unclaimed_text(content: str, story_number: int) -> str:
    """Replace [N] with [ ] for the given story number in backlog text.

    Pure function: returns the modified content string. Reverts a claimed
    story back to unclaimed so another builder can pick it up.
    """
    lines = content.split("\n")
    for i, line in enumerate(lines):
        m = _BACKLOG_LINE_RE.match(line.strip())
        if m and int(m.group(1)) == story_number and m.group(2).isdigit():
            marker = m.group(2)
            lines[i] = line.replace(f"[{marker}]", "[ ]", 1)
            break
    return "\n".join(lines)


# ============================================
# Git-based story claim and completion
# ============================================

_BACKLOG_FILE = "BACKLOG.md"


def claim_next_story(agent_name: str, builder_id: int = 1, max_attempts: int = 10) -> dict | None:
    """Claim the next eligible story from BACKLOG.md using git push as a lock.

    Flow:
    1. git pull --rebase
    2. Read BACKLOG.md, find next eligible unclaimed story
    3. Mark it in-progress ([ ] -> [N] where N is builder_id)
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
            new_content = mark_story_claimed(content, story["number"], builder_id)
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

        # Push failed -- another commit was pushed to the remote.
        # Reset the local claim commit so we don't read our own claim on retry.
        log(
            agent_name,
            f"Claim race lost (attempt {attempt}/{max_attempts}). Pulling and retrying...",
            style="yellow",
        )
        run_cmd(["git", "reset", "--hard", "HEAD~1"], quiet=True)
        pull_result = run_cmd(["git", "pull", "--rebase"], capture=True)
        if pull_result.returncode != 0:
            run_cmd(["git", "rebase", "--abort"], quiet=True)
            run_cmd(["git", "pull", "--rebase"], quiet=True)

    log(agent_name, f"Could not claim a story after {max_attempts} attempts.", style="bold yellow")
    return None


def mark_story_completed(story_number: int, agent_name: str, max_attempts: int = 5) -> bool:
    """Mark a claimed story as completed in BACKLOG.md ([N] -> [x]).

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
                log(agent_name, f"WARNING: Story {story_number} not in claimed state -- may already be completed.", style="yellow")
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
    """Revert a claimed story back to unclaimed in BACKLOG.md ([N] -> [ ]).

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
                log(agent_name, f"WARNING: Story {story_number} not in claimed state -- cannot unclaim.", style="yellow")
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

    Returns empty string — builders race to fix issues rather than partitioning
    by issue number. Any builder can pick up any open issue; the first to close
    it wins. Kept as a function for call-site compatibility.
    """
    return ""


# ============================================
# Orphaned milestone cleanup
# ============================================


def _cleanup_orphaned_milestones(story_number: int, agent_name: str) -> None:
    """Remove incomplete milestone files for a story after a build failure.

    When a builder fails mid-story (e.g. merge conflict), its milestone files
    remain on main with unchecked tasks. If another builder later claims the
    same story, the planner creates fresh milestones — but the old incomplete
    milestones would also be picked up by the prefix match in the build loop.
    This function deletes the orphaned files so the next builder starts clean.

    Deletes milestone files matching milestone-{NN}* that have unchecked tasks.
    Completed milestone files (all tasks checked) are left alone.
    """
    milestones_dir = "milestones"
    story_prefix = f"milestone-{story_number:02d}"

    orphans = []
    for ms in get_all_milestones(milestones_dir):
        basename = os.path.basename(ms["path"])
        if basename.startswith(story_prefix) and not ms["all_done"]:
            orphans.append(ms["path"])

    if not orphans:
        return

    for path in orphans:
        try:
            os.remove(path)
            log(agent_name, f"Removed orphaned milestone: {os.path.basename(path)}", style="yellow")
        except OSError:
            pass

    # Commit the removal so other builders see a clean state
    run_cmd(["git", "add", "-A", milestones_dir])
    run_cmd(["git", "commit", "-m",
             f"[builder] Remove orphaned milestones for story {story_number}"])
    git_push_with_retry(agent_name)


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
_REVIEWER_MERGE_TIMEOUT = 300  # 5 minutes max wait for reviewer before merge
_REVIEWER_MERGE_POLL_INTERVAL = 5  # seconds between checks


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


def _wait_for_reviewer(
    builder_id: int, branch_name: str, agent_name: str,
    timeout: int = _REVIEWER_MERGE_TIMEOUT,
) -> bool:
    """Wait for the branch-attached reviewer to catch up before merging.

    Polls the reviewer's branch-head checkpoint until the reviewed SHA matches
    the current branch HEAD. Returns True if the reviewer caught up, False on
    timeout. This is a soft gate — the caller should proceed with merge even
    on timeout (the milestone reviewer will catch remaining issues).
    """
    head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
    branch_head = head_result.stdout.strip() if head_result.returncode == 0 else ""
    if not branch_head:
        return True  # Can't determine HEAD, skip waiting

    elapsed = 0
    while elapsed < timeout:
        reviewed_branch, reviewed_sha = load_branch_review_head(builder_id)
        if reviewed_branch == branch_name and reviewed_sha == branch_head:
            log(agent_name, "Reviewer has caught up. Proceeding to merge.", style="green")
            return True
        if elapsed == 0:
            log(agent_name, "Waiting for reviewer to catch up...", style="yellow")
        time.sleep(_REVIEWER_MERGE_POLL_INTERVAL)
        elapsed += _REVIEWER_MERGE_POLL_INTERVAL

    log(agent_name, f"Reviewer did not catch up within {timeout}s. Proceeding to merge.", style="yellow")
    return False


def _record_completed_milestone(
    milestone_file: str, agent_name: str, merge_sha: str = "",
) -> None:
    """Check if this builder's milestone is complete and record its boundary.

    When merge_sha is provided (loop mode with branches), uses the merge commit
    directly. When omitted (legacy non-loop mode), pulls latest and reads HEAD.
    """
    if not merge_sha:
        # Legacy/non-loop fallback: read HEAD on main
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    ms = parse_milestone_file(milestone_file)
    if not ms or not ms["all_done"]:
        log(agent_name, "WARNING: Milestone does not appear complete after build.", style="bold yellow")
        return

    start_sha = get_last_milestone_end_sha()
    end_sha = merge_sha if merge_sha else ""
    if not end_sha:
        head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
        end_sha = head_result.stdout.strip() if head_result.returncode == 0 else ""

    record_milestone_boundary(ms["name"], start_sha, end_sha)
    log(
        agent_name,
        f"Recorded milestone boundary: {ms['name']} ({start_sha[:8]}..{end_sha[:8]})",
        style="cyan",
    )


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

        remaining_bugs = count_open_bug_issues(builder_id, num_builders)
        remaining_reviews = count_open_finding_issues(builder_id, num_builders)
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


# ============================================
# Issue builder loop
# ============================================

_ISSUE_POLL_INTERVAL = 30  # seconds between polls when no issues found


def _run_issue_builder_loop(
    agent_name: str, builder_id: int, state: BuildState,
) -> None:
    """Run the dedicated issue builder loop.

    Polls for open bugs and findings. When any exist, runs a fix-only Copilot
    session on main. When none exist, checks whether all milestone builders
    have finished (all other builder-N.done sentinels present). If so, writes
    its own sentinel and returns. Otherwise sleeps and polls again.
    """
    from agentic_dev.sentinel import are_other_builders_done

    log(agent_name, "")
    log(agent_name, "[Issue Builder] Starting dedicated issue fixing loop.", style="green")
    log(agent_name, "")

    while True:
        ensure_on_main(agent_name)
        run_cmd(["git", "pull", "--rebase"])

        bugs = count_open_bug_issues(agent_name)
        findings = count_open_finding_issues(agent_name)
        total_issues = bugs + findings

        if total_issues > 0:
            log(agent_name, "")
            log(agent_name, f"[Issue Builder] Found {bugs} bug(s) and {findings} finding(s). "
                "Fixing...", style="green")
            log(agent_name, "")
            run_copilot(agent_name, BUILDER_FIX_ONLY_PROMPT)
            state.fix_only_cycles += 1
            continue

        # No issues right now — check if milestone builders are all done
        if are_other_builders_done(builder_id):
            # All builders (including us if sentinel already written) are done.
            # Do one final check for issues that may have been filed during shutdown.
            bugs = count_open_bug_issues(agent_name)
            findings = count_open_finding_issues(agent_name)
            if bugs + findings > 0:
                log(agent_name, f"[Issue Builder] {bugs + findings} issue(s) filed during "
                    "shutdown. Fixing...", style="green")
                run_copilot(agent_name, BUILDER_FIX_ONLY_PROMPT)
                continue

            log(agent_name, "")
            log(agent_name, "[Issue Builder] All milestone builders done, no open issues. "
                "Shutting down.", style="bold green")
            write_builder_done(builder_id)
            return

        # Milestone builders still working, nothing to fix yet — wait
        log(agent_name, "[Issue Builder] No open issues. Waiting for work...", style="dim")
        time.sleep(_ISSUE_POLL_INTERVAL)


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
        issue_fixing_section=BUILDER_ISSUE_FIXING_SECTION,
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
    role: Annotated[str, typer.Option(help="Builder role: 'milestone' (claim stories) or 'issue' (fix bugs/findings)")] = "milestone",
) -> None:
    """Claim stories from BACKLOG.md, fix bugs, address reviews, complete milestones.

    In loop mode: claim -> plan -> build -> complete -> repeat until all stories done.
    In non-loop mode: build a single milestone (legacy compatibility).
    Role 'issue': dedicated issue fixer — polls for bugs/findings, never claims stories.
    """
    agent_name = f"builder-{builder_id}"
    state = BuildState()

    if role == "issue":
        _run_issue_builder_loop(agent_name, builder_id, state)
        return

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
            issue_fixing_section=BUILDER_ISSUE_FIXING_SECTION,
        )
        exit_code = run_copilot(agent_name, prompt)
        if exit_code != 0:
            log(agent_name, "Builder failed! Check errors above.", style="bold red")
        write_builder_done(builder_id)
        return

    # Milestone builders with a dedicated issue builder skip inline issue fixing.
    # When num_builders <= 1 (solo mode), the milestone builder fixes issues itself.
    has_issue_builder = num_builders > 1
    issue_section = "" if has_issue_builder else BUILDER_ISSUE_FIXING_SECTION

    # Loop mode: claim-and-build pattern
    while True:
        state.cycle_count += 1
        ensure_on_main(agent_name)

        story = claim_next_story(agent_name, builder_id)
        if story is None:
            # No eligible stories -- check if pending (dep deadlock) or truly done
            if has_pending_backlog_stories_in_file(_BACKLOG_FILE):
                log(agent_name, "")
                log(agent_name, "No eligible stories (dependency deadlock or all claimed). "
                    "Checking for bugs/findings to fix while waiting...", style="yellow")

                # Fix issues while waiting for stories to become eligible
                run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)
                remaining_bugs = count_open_bug_issues()
                remaining_reviews = count_open_finding_issues()
                if remaining_bugs > 0 or remaining_reviews > 0:
                    log(agent_name, f"Found {remaining_bugs} bug(s) and "
                        f"{remaining_reviews} finding(s). Fixing while waiting...",
                        style="cyan")
                    run_copilot(agent_name, BUILDER_FIX_ONLY_PROMPT)
                else:
                    log(agent_name, "No open issues. Waiting 30s for stories...",
                        style="dim")
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

        log(agent_name, "")
        log(agent_name, f"[Milestone Planner] Planning story: {story['name']}...", style="magenta")
        plan(story_name=story["name"])
        check_milestone_sizes()

        # Find milestone files for THIS story only (milestone-NN* pattern).
        # Using the story number avoids picking up other builders' milestones
        # that arrived via git pull during planning.
        story_prefix = f"milestone-{story['number']:02d}"
        new_milestones = [
            ms["path"] for ms in get_all_milestones("milestones")
            if not ms["all_done"] and os.path.basename(ms["path"]).startswith(story_prefix)
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
            milestone_basename = os.path.splitext(os.path.basename(milestone_file))[0]

            # Create feature branch for this milestone
            branch_name = create_milestone_branch(builder_id, milestone_basename, agent_name)
            if not branch_name:
                build_failed = True
                break

            # Clear stale reviewer signal from previous branch
            clear_branch_review_head(builder_id)

            log(agent_name, "")
            log(agent_name, f"[Builder] Starting work on {milestone_file}...", style="green")
            log(agent_name, "")

            prompt = BUILDER_PROMPT.format(
                milestone_file=milestone_file,
                issue_fixing_section=issue_section,
            )
            exit_code = run_copilot(agent_name, prompt)

            if exit_code != 0:
                log(agent_name, "")
                log(agent_name, "======================================", style="bold red")
                log(agent_name, " Builder failed! Check errors above", style="bold red")
                log(agent_name, "======================================", style="bold red")
                ensure_on_main(agent_name)
                build_failed = True
                break

            # Wait for branch-attached reviewer to catch up (soft gate)
            _wait_for_reviewer(builder_id, branch_name, agent_name)

            # Merge feature branch back to main
            merge_sha = merge_milestone_to_main(branch_name, milestone_basename, agent_name)
            if not merge_sha:
                log(agent_name, "Merge to main failed. Stopping builder.", style="bold red")
                ensure_on_main(agent_name)
                build_failed = True
                break

            _record_completed_milestone(milestone_file, agent_name, merge_sha=merge_sha)
            delete_milestone_branch(branch_name, agent_name)

            log(agent_name, "")
            log(agent_name, "======================================", style="bold cyan")
            log(agent_name, " Milestone complete!", style="bold cyan")
            log(agent_name, "======================================", style="bold cyan")

        if build_failed:
            ensure_on_main(agent_name)
            if branch_name:
                delete_milestone_branch(branch_name, agent_name)
            # Clean up orphaned milestone files so the next builder that claims
            # this story plans fresh milestones instead of inheriting stale ones.
            _cleanup_orphaned_milestones(story["number"], agent_name)
            unclaim_story(story["number"], agent_name)
            # Don't terminate — continue the claim loop to try other stories.
            log(agent_name, "Build failed for this story. Continuing to next eligible story...", style="yellow")
            continue

        # Mark story as completed ([N] -> [x]) so downstream deps unlock
        mark_story_completed(story["number"], agent_name)

        # Loop back to claim next story
