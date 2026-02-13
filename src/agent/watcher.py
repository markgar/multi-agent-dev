"""Watcher commands: commit watcher and milestone reviewer."""

import os
import time
from datetime import datetime
from typing import Annotated

import typer

from agent.git_helpers import (
    git_push_with_retry,
    is_coordination_only_commit,
    is_merge_commit,
    is_reviewer_only_commit,
)
from agent.milestone import (
    load_milestone_boundaries,
    load_reviewed_milestones,
    save_milestone_checkpoint,
)
from agent.legacy_watchers import reviewoncommit, testoncommit
from agent.prompts import (
    REVIEWER_BATCH_PROMPT,
    REVIEWER_COMMIT_PROMPT,
    REVIEWER_MILESTONE_PROMPT,
)
from agent.sentinel import (
    is_builder_done,
    load_reviewer_checkpoint,
    save_reviewer_checkpoint,
)
from agent.utils import log, run_cmd, run_copilot


def register(app: typer.Typer) -> None:
    """Register watcher commands on the shared app."""
    app.command()(commitwatch)
    app.command()(reviewoncommit)
    app.command()(testoncommit)


def _initialize_watcher_checkpoint() -> str:
    """Restore or seed the reviewer checkpoint.

    Returns the initial last_sha. If a checkpoint exists on disk, restores it.
    Otherwise pulls latest and seeds from HEAD.
    """
    last_sha = load_reviewer_checkpoint()
    if last_sha:
        log("commit-watcher", f"Restored checkpoint: {last_sha[:8]}", style="cyan")
        return last_sha

    # First run ever — seed at current HEAD.
    run_cmd(["git", "pull", "-q"], capture=True)
    head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
    if head_result.returncode == 0:
        last_sha = head_result.stdout.strip()
        save_reviewer_checkpoint(last_sha)
        log("commit-watcher", f"Initialized checkpoint at: {last_sha[:8]}", style="cyan")
        return last_sha

    log("commit-watcher", "WARNING: Could not determine HEAD", style="red")
    return ""


def _should_skip_commit(commit_sha: str) -> str | None:
    """Return a skip reason if the commit should not be reviewed, or None to review it."""
    if is_merge_commit(commit_sha):
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


def _review_single_commit(prev_sha: str, commit_sha: str) -> int:
    """Review a single commit. Returns the copilot exit code."""
    prompt = REVIEWER_COMMIT_PROMPT.format(prev_sha=prev_sha, commit_sha=commit_sha)
    return run_copilot("reviewer", prompt)


def _review_batch(base_sha: str, reviewable: list[str]) -> int:
    """Review multiple commits as a single combined diff. Returns the copilot exit code."""
    head_sha = reviewable[-1]
    prompt = REVIEWER_BATCH_PROMPT.format(
        commit_count=len(reviewable),
        base_sha=base_sha,
        head_sha=head_sha,
    )
    return run_copilot("reviewer", prompt)


def _review_new_commits(last_sha: str, current_head: str) -> bool:
    """Review new commits between last_sha and current_head.

    When a single reviewable commit is found, reviews it individually.
    When multiple reviewable commits are found, reviews them as a batch
    using the combined diff — one Copilot call instead of N.

    Returns True if the builder finished mid-review (caller should exit),
    False otherwise.
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

    now = datetime.now().strftime("%H:%M:%S")
    log("commit-watcher", "")
    log("commit-watcher", f"[{now}] {len(new_commits)} new commit(s) detected", style="yellow")

    reviewable, base_sha = _partition_commits(new_commits, last_sha)

    if not reviewable:
        now = datetime.now().strftime("%H:%M:%S")
        log("commit-watcher", f"[{now}] No reviewable commits. Watching...", style="yellow")
        return False

    if len(reviewable) == 1:
        commit_sha = reviewable[0]
        now = datetime.now().strftime("%H:%M:%S")
        log("commit-watcher", f"[{now}] Reviewing commit {commit_sha[:8]}...", style="cyan")
        exit_code = _review_single_commit(base_sha, commit_sha)
    else:
        head_sha = reviewable[-1]
        now = datetime.now().strftime("%H:%M:%S")
        log(
            "commit-watcher",
            f"[{now}] Reviewing {len(reviewable)} commits as batch ({base_sha[:8]}..{head_sha[:8]})...",
            style="cyan",
        )
        exit_code = _review_batch(base_sha, reviewable)

    if exit_code != 0:
        now = datetime.now().strftime("%H:%M:%S")
        log("commit-watcher", f"[{now}] WARNING: Review exited with errors", style="red")

    git_push_with_retry("commit-watcher")
    save_reviewer_checkpoint(reviewable[-1])

    if is_builder_done():
        now = datetime.now().strftime("%H:%M:%S")
        log("commit-watcher", f"[{now}] Builder finished. Stopping.", style="bold green")
        return True

    now = datetime.now().strftime("%H:%M:%S")
    log("commit-watcher", f"[{now}] All commits reviewed. Watching...", style="yellow")
    return False


def find_unreviewed_milestones(boundaries: list[dict], reviewed: set[str]) -> list[dict]:
    """Return milestone boundaries that have not yet been reviewed.

    Pure function: filters boundaries by membership in the reviewed set.
    """
    return [b for b in boundaries if b["name"] not in reviewed]


def _check_milestone_reviews() -> None:
    """Run cross-cutting reviews for any newly completed milestones.

    Loads milestone boundaries written by the build loop and compares against
    already-reviewed milestones. Invokes a milestone-scoped reviewer for each
    unreviewed milestone and saves the checkpoint.
    """
    boundaries = load_milestone_boundaries()
    reviewed = load_reviewed_milestones()

    for boundary in find_unreviewed_milestones(boundaries, reviewed):

        now = datetime.now().strftime("%H:%M:%S")
        log(
            "commit-watcher",
            f"[{now}] Milestone completed: {boundary['name']}! Running cross-cutting review...",
            style="bold magenta",
        )

        milestone_prompt = REVIEWER_MILESTONE_PROMPT.format(
            milestone_name=boundary["name"],
            milestone_start_sha=boundary["start_sha"],
            milestone_end_sha=boundary["end_sha"],
        )
        exit_code = run_copilot("reviewer", milestone_prompt)

        if exit_code != 0:
            now = datetime.now().strftime("%H:%M:%S")
            log(
                "commit-watcher",
                f"[{now}] WARNING: Milestone review of '{boundary['name']}' exited with errors",
                style="red",
            )

        git_push_with_retry("commit-watcher")
        save_milestone_checkpoint(boundary["name"])

        now = datetime.now().strftime("%H:%M:%S")
        log(
            "commit-watcher",
            f"[{now}] Milestone review complete: {boundary['name']}",
            style="bold magenta",
        )


def commitwatch(
    reviewer_dir: Annotated[
        str, typer.Option(help="Path to the reviewer git clone")
    ] = "",
):
    """Watch for new commits and spawn a per-commit code reviewer.

    Runs from the reviewer clone directory. For each new commit detected,
    invokes a reviewer agent scoped to exactly that commit's diff.
    Uses a persistent checkpoint so no commits are ever missed, even across
    restarts. Skips merge commits and the reviewer's own REVIEWS.md commits.
    Shuts down automatically when the builder finishes.
    """
    if reviewer_dir:
        os.chdir(reviewer_dir)

    log("commit-watcher", "======================================", style="bold yellow")
    log("commit-watcher", " Commit watcher started", style="bold yellow")
    log("commit-watcher", " Spawns a reviewer per commit", style="bold yellow")
    log("commit-watcher", " Press Ctrl+C to stop", style="bold yellow")
    log("commit-watcher", "======================================", style="bold yellow")
    log("commit-watcher", "")

    last_sha = _initialize_watcher_checkpoint()

    while True:
        if is_builder_done():
            # Builder is done — but finish any remaining milestone reviews first.
            # Pull latest to pick up final milestones.log entries.
            run_cmd(["git", "pull", "-q"], capture=True)
            _check_milestone_reviews()
            now = datetime.now().strftime("%H:%M:%S")
            log("commit-watcher", "")
            log("commit-watcher", f"[{now}] Builder finished. Shutting down.", style="bold green")
            break

        pull_result = run_cmd(["git", "pull", "-q"], capture=True)
        if pull_result.returncode != 0:
            now = datetime.now().strftime("%H:%M:%S")
            log("commit-watcher", f"[{now}] WARNING: git pull failed", style="red")
            if pull_result.stderr:
                log("commit-watcher", pull_result.stderr.strip(), style="red")

        head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
        current_head = head_result.stdout.strip() if head_result.returncode == 0 else ""

        if current_head and current_head != last_sha and last_sha:
            builder_finished = _review_new_commits(last_sha, current_head)
            if builder_finished:
                # Builder finished mid-review — still do final milestone reviews.
                run_cmd(["git", "pull", "-q"], capture=True)
                _check_milestone_reviews()
                return

        last_sha = current_head if current_head else last_sha

        _check_milestone_reviews()

        time.sleep(10)
