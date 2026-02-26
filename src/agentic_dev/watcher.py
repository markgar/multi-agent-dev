"""Watcher commands: branch-attached reviewer for per-commit code reviews."""

import os
import time
from datetime import datetime
from typing import Annotated

import typer

from agentic_dev.git_helpers import (
    detect_builder_branch,
    get_branch_head_sha,
    git_push_with_retry,
    is_coordination_only_commit,
    is_merge_commit,
    is_reviewer_only_commit,
)
from agentic_dev.prompts import (
    REVIEWER_BRANCH_BATCH_PROMPT,
    REVIEWER_BRANCH_COMMIT_PROMPT,
)
from agentic_dev.sentinel import (
    is_builder_done,
    load_reviewer_checkpoint,
    save_branch_review_head,
    save_reviewer_checkpoint,
)
from agentic_dev.utils import log, resolve_logs_dir, run_cmd, run_copilot


def register(app: typer.Typer) -> None:
    """Register watcher commands on the shared app."""
    app.command()(commitwatch)


def _should_skip_commit(commit_sha: str) -> str | None:
    """Return a skip reason if the commit should not be reviewed, or None to review it."""
    if is_merge_commit(commit_sha):
        # Skip merge commits UNLESS they are milestone merges (which should be reviewed)
        msg_result = run_cmd(
            ["git", "log", "-1", "--format=%s", commit_sha],
            capture=True,
        )
        msg = msg_result.stdout.strip() if msg_result.returncode == 0 else ""
        if "[builder] Merge milestone-" in msg:
            return None  # Don't skip — review this milestone merge
        return "merge commit"
    if is_reviewer_only_commit(commit_sha):
        return "reviewer commit"
    if is_coordination_only_commit(commit_sha):
        return "coordination-only commit"
    return None


def _partition_commits(commits: list[str], last_sha: str) -> tuple[list[str], str]:
    """Split commits into reviewable ones and advance past skippable ones.

    Returns (reviewable_shas, effective_base_sha). The effective_base_sha is
    the last skipped commit before the first reviewable one (or last_sha if
    the first commit is reviewable). Skippable commits at the end are logged
    and checkpointed but excluded from the reviewable list.
    """
    reviewable = []
    base_sha = last_sha

    for commit_sha in commits:
        skip_reason = _should_skip_commit(commit_sha)
        if skip_reason:
            now = datetime.now().strftime("%H:%M:%S")
            log("commit-watcher", f"[{now}] Skipping {skip_reason} {commit_sha[:8]}", style="dim")
            save_reviewer_checkpoint(commit_sha)
            if not reviewable:
                base_sha = commit_sha
        else:
            reviewable.append(commit_sha)

    return reviewable, base_sha


def _extract_milestone_label(branch_name: str) -> str:
    """Extract the milestone label from a feature branch name.

    Branch format: 'builder-N/milestone-NN' or 'builder-N/milestone-NNa'.
    Returns e.g. 'milestone-01' or 'milestone-08a'. Falls back to the part
    after the slash if the format doesn't match the expected pattern.
    """
    if "/" in branch_name:
        return branch_name.split("/", 1)[1]
    return branch_name


def _review_branch_single_commit(prev_sha: str, commit_sha: str, branch_name: str, builder_id: int) -> int:
    """Review a single commit on a feature branch. Returns copilot exit code."""
    milestone_label = _extract_milestone_label(branch_name)
    prompt = REVIEWER_BRANCH_COMMIT_PROMPT.format(
        prev_sha=prev_sha, commit_sha=commit_sha, branch_name=branch_name,
        milestone_label=milestone_label,
    )
    return run_copilot(f"reviewer-{builder_id}", prompt)


def _review_branch_batch(base_sha: str, reviewable: list[str], branch_name: str, builder_id: int) -> int:
    """Review multiple commits on a feature branch as a batch. Returns copilot exit code."""
    head_sha = reviewable[-1]
    milestone_label = _extract_milestone_label(branch_name)
    prompt = REVIEWER_BRANCH_BATCH_PROMPT.format(
        commit_count=len(reviewable),
        base_sha=base_sha,
        head_sha=head_sha,
        branch_name=branch_name,
        milestone_label=milestone_label,
    )
    return run_copilot(f"reviewer-{builder_id}", prompt)


def _review_branch_commits(
    last_sha: str, current_head: str, branch_name: str, builder_id: int,
) -> str:
    """Review new commits on a feature branch.

    Returns the new last_sha (the last reviewed commit SHA).
    Uses the same partition/skip logic as main-branch reviews.
    """
    log_result = run_cmd(
        ["git", "log", f"{last_sha}..{current_head}", "--format=%H", "--reverse"],
        capture=True,
    )
    new_commits = [
        sha.strip()
        for sha in log_result.stdout.strip().split("\n")
        if sha.strip()
    ]

    agent_name = f"reviewer-{builder_id}"
    now = datetime.now().strftime("%H:%M:%S")
    log(agent_name, "")
    log(agent_name, f"[{now}] {len(new_commits)} new commit(s) on {branch_name}", style="yellow")

    reviewable, base_sha = _partition_commits(new_commits, last_sha)

    if not reviewable:
        now = datetime.now().strftime("%H:%M:%S")
        log(agent_name, f"[{now}] No reviewable commits. Watching branch...", style="yellow")
        return current_head

    if len(reviewable) == 1:
        commit_sha = reviewable[0]
        now = datetime.now().strftime("%H:%M:%S")
        log(agent_name, f"[{now}] Reviewing commit {commit_sha[:8]} on {branch_name}...", style="cyan")
        exit_code = _review_branch_single_commit(base_sha, commit_sha, branch_name, builder_id)
    else:
        head_sha = reviewable[-1]
        now = datetime.now().strftime("%H:%M:%S")
        log(
            agent_name,
            f"[{now}] Reviewing {len(reviewable)} commits as batch on {branch_name} "
            f"({base_sha[:8]}..{head_sha[:8]})...",
            style="cyan",
        )
        exit_code = _review_branch_batch(base_sha, reviewable, branch_name, builder_id)

    if exit_code != 0:
        now = datetime.now().strftime("%H:%M:%S")
        log(agent_name, f"[{now}] WARNING: Branch review exited with errors", style="red")

    git_push_with_retry(agent_name)
    last_reviewed = reviewable[-1]
    save_reviewer_checkpoint(last_reviewed, builder_id)
    return last_reviewed


def _watch_builder_branch(builder_id: int, branch_name: str) -> None:
    """Watch a builder's feature branch and review commits, staying on main.

    The reviewer stays on main throughout — it fetches branch commits and
    reviews them via SHA-based diffs. Findings are committed and pushed to
    main so they are never orphaned when the builder merges/deletes the branch.
    """
    agent_name = f"reviewer-{builder_id}"
    log(agent_name, f"Watching branch: {branch_name} (reviewing from main)", style="cyan")

    # Ensure we're on main with latest
    run_cmd(["git", "checkout", "main"], quiet=True)
    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    # Fetch the branch so we have its objects
    run_cmd(["git", "fetch", "origin", branch_name], quiet=True)

    # Determine starting point: checkpoint or branch base
    last_sha = load_reviewer_checkpoint(builder_id)
    if not last_sha:
        # First time seeing this branch — start from the merge-base with main
        base_result = run_cmd(
            ["git", "merge-base", "main", f"origin/{branch_name}"],
            capture=True,
        )
        last_sha = base_result.stdout.strip() if base_result.returncode == 0 else ""
        if last_sha:
            save_reviewer_checkpoint(last_sha, builder_id)
            log(agent_name, f"Branch base: {last_sha[:8]}", style="cyan")

    while True:
        if is_builder_done():
            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, f"[{now}] Builder finished. Stopping branch watch.", style="bold green")
            return

        # Check if branch still exists on remote
        branch_check = detect_builder_branch(builder_id)
        if not branch_check or branch_check != branch_name:
            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, f"[{now}] Branch {branch_name} no longer on remote (merged or deleted).", style="cyan")
            break

        # Fetch latest commits on the branch (stay on main)
        run_cmd(["git", "fetch", "origin", branch_name], quiet=True)

        # Read the remote branch head via the fetched ref
        head_result = run_cmd(
            ["git", "rev-parse", f"origin/{branch_name}"], capture=True,
        )
        current_head = head_result.stdout.strip() if head_result.returncode == 0 else ""

        if current_head and current_head != last_sha and last_sha:
            last_sha = _review_branch_commits(last_sha, current_head, branch_name, builder_id)
            # Signal merge readiness
            save_branch_review_head(builder_id, branch_name, last_sha)
        elif current_head and last_sha:
            # No new commits — still signal that we've reviewed up to HEAD
            save_branch_review_head(builder_id, branch_name, last_sha)

        time.sleep(10)

    # Branch disappeared — pull main to pick up the merged code
    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)


def _branchwatch_loop(builder_id: int) -> None:
    """Main loop for branch-attached reviewer mode.

    Polls for the builder's feature branch. When one appears, attaches to it
    and reviews commits. When the branch disappears (merged), waits for the
    next one. Shuts down when the builder is done.
    """
    agent_name = f"reviewer-{builder_id}"
    log(agent_name, f"Watching for builder-{builder_id} branches...", style="yellow")

    while True:
        if is_builder_done():
            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, "")
            log(agent_name, f"[{now}] Builder finished. Shutting down.", style="bold green")
            break

        # Poll for a builder branch
        branch_name = detect_builder_branch(builder_id)
        if branch_name:
            # Clear any stale checkpoint from a previous branch
            save_reviewer_checkpoint("", builder_id)
            _watch_builder_branch(builder_id, branch_name)
        else:
            time.sleep(10)


def commitwatch(
    reviewer_dir: Annotated[
        str, typer.Option(help="Path to the reviewer git clone")
    ] = "",
    builder_id: Annotated[
        int, typer.Option(help="Builder ID to follow")
    ] = 1,
) -> None:
    """Watch for new commits on a builder's feature branch and review them.

    Runs in branch-attached mode: watches builder-N's feature branch,
    reviews commits there, and signals merge readiness.

    Shuts down automatically when the builder finishes.
    """
    if reviewer_dir:
        os.chdir(reviewer_dir)

    if builder_id < 1:
        raise typer.BadParameter("builder-id must be >= 1")

    agent_name = f"reviewer-{builder_id}"

    log(agent_name, "======================================", style="bold yellow")
    log(agent_name, f" Branch-attached reviewer (builder-{builder_id})", style="bold yellow")
    log(agent_name, " Press Ctrl+C to stop", style="bold yellow")
    log(agent_name, "======================================", style="bold yellow")
    log(agent_name, "")

    try:
        _branchwatch_loop(builder_id)
    except SystemExit as exc:
        log(agent_name, f"FATAL: {exc}", style="bold red")
        raise
    except Exception as exc:
        log(agent_name, f"FATAL: Unexpected error: {exc}", style="bold red")
        raise
