"""Watcher commands: commit watcher, legacy reviewoncommit, and testoncommit."""

import os
import time
from datetime import datetime
from typing import Annotated

import typer

from agent.git_helpers import git_push_with_retry, is_merge_commit, is_reviewer_only_commit
from agent.milestone import (
    load_milestone_boundaries,
    load_reviewed_milestones,
    save_milestone_checkpoint,
)
from agent.prompts import (
    REVIEWER_COMMIT_PROMPT,
    REVIEWER_MILESTONE_PROMPT,
    REVIEWER_PROMPT,
    TESTER_PROMPT,
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


def _watch_loop(agent_name: str, prompt: str, label: str) -> None:
    """Shared polling loop for reviewoncommit and testoncommit."""
    log(agent_name, "======================================", style="bold yellow")
    log(agent_name, f" {label} agent watching for commits...", style="bold yellow")
    log(agent_name, " Press Ctrl+C to stop", style="bold yellow")
    log(agent_name, "======================================", style="bold yellow")
    log(agent_name, "")

    last_commit = ""

    while True:
        pull_result = run_cmd(["git", "pull", "-q"], capture=True)
        if pull_result.returncode != 0:
            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, f"[{now}] WARNING: git pull failed", style="red")
            if pull_result.stderr:
                log(agent_name, pull_result.stderr.strip(), style="red")

        head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
        current_commit = head_result.stdout.strip() if head_result.returncode == 0 else ""

        if current_commit != last_commit and last_commit != "":
            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, "")
            log(agent_name, f"[{now}] New commit detected!", style="yellow")
            log(agent_name, "")

            exit_code = run_copilot(agent_name, prompt)

            if exit_code != 0:
                now = datetime.now().strftime("%H:%M:%S")
                log(agent_name, f"[{now}] WARNING: {label} exited with errors", style="red")

            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, "")
            log(agent_name, f"[{now}] {label} complete. Watching...", style="yellow")

        last_commit = current_commit
        time.sleep(10)


def reviewoncommit():
    """Watch for new commits and review code quality (runs in a loop)."""
    _watch_loop("reviewer", REVIEWER_PROMPT, "Review")


def testoncommit():
    """Watch for new commits and auto-test (runs in a loop)."""
    _watch_loop("tester", TESTER_PROMPT, "Test run")


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


def _review_new_commits(last_sha: str, current_head: str) -> bool:
    """Review each new commit between last_sha and current_head.

    Enumerates commits, skips merges and reviewer-only commits, and invokes
    a scoped reviewer for each real commit. Saves checkpoint after each one.

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

    prev = last_sha
    for commit_sha in new_commits:
        now = datetime.now().strftime("%H:%M:%S")
        short = commit_sha[:8]

        if is_merge_commit(commit_sha):
            log("commit-watcher", f"[{now}] Skipping merge commit {short}", style="dim")
            prev = commit_sha
            save_reviewer_checkpoint(commit_sha)
            continue

        if is_reviewer_only_commit(commit_sha):
            log("commit-watcher", f"[{now}] Skipping reviewer commit {short}", style="dim")
            prev = commit_sha
            save_reviewer_checkpoint(commit_sha)
            continue

        log("commit-watcher", f"[{now}] Reviewing commit {short}...", style="cyan")

        prompt = REVIEWER_COMMIT_PROMPT.format(prev_sha=prev, commit_sha=commit_sha)
        exit_code = run_copilot("reviewer", prompt)

        if exit_code != 0:
            now = datetime.now().strftime("%H:%M:%S")
            log("commit-watcher", f"[{now}] WARNING: Review of {short} exited with errors", style="red")

        git_push_with_retry("commit-watcher")
        prev = commit_sha
        save_reviewer_checkpoint(commit_sha)

        if is_builder_done():
            now = datetime.now().strftime("%H:%M:%S")
            log("commit-watcher", f"[{now}] Builder finished. Stopping.", style="bold green")
            return True

    now = datetime.now().strftime("%H:%M:%S")
    log("commit-watcher", f"[{now}] All commits reviewed. Watching...", style="yellow")
    return False


def _check_milestone_reviews() -> None:
    """Run cross-cutting reviews for any newly completed milestones.

    Loads milestone boundaries written by the build loop and compares against
    already-reviewed milestones. Invokes a milestone-scoped reviewer for each
    unreviewed milestone and saves the checkpoint.
    """
    boundaries = load_milestone_boundaries()
    reviewed = load_reviewed_milestones()

    for boundary in boundaries:
        if boundary["name"] in reviewed:
            continue

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
                return

        last_sha = current_head if current_head else last_sha

        _check_milestone_reviews()

        time.sleep(10)
