"""Git operation helpers: push with retry, commit classification."""

import time

from agentic_dev.utils import log, run_cmd


def git_push_with_retry(agent_name: str = "", max_attempts: int = 3, backoff: int = 5) -> bool:
    """Run git pull --rebase && git push with retry on conflict.

    If the rebase conflicts, aborts it, waits, and retries.
    Returns True if push eventually succeeded, False if all attempts failed.
    """
    for attempt in range(1, max_attempts + 1):
        pull_result = run_cmd(["git", "pull", "--rebase"], capture=True)
        if pull_result.returncode != 0:
            # Rebase conflict — abort and retry
            run_cmd(["git", "rebase", "--abort"], quiet=True)
            if agent_name:
                log(
                    agent_name,
                    f"Rebase conflict (attempt {attempt}/{max_attempts}), retrying in {backoff}s...",
                    style="yellow",
                )
            if attempt < max_attempts:
                time.sleep(backoff)
                continue
            else:
                if agent_name:
                    log(agent_name, "Push failed after all retry attempts.", style="red")
                return False

        push_result = run_cmd(["git", "push"], capture=True)
        if push_result.returncode == 0:
            return True

        # Push rejected (e.g. non-fast-forward) — retry the whole pull+push
        if agent_name:
            log(
                agent_name,
                f"Push rejected (attempt {attempt}/{max_attempts}), retrying in {backoff}s...",
                style="yellow",
            )
        if attempt < max_attempts:
            time.sleep(backoff)

    if agent_name:
        log(agent_name, "Push failed after all retry attempts.", style="red")
    return False


SKIP_ONLY_FILES = {"TASKS.md", "BACKLOG.md"}

# Paths under these directories are coordination-only (reviews/, bugs/, milestones/)
_COORDINATION_DIRS = ("reviews/", "bugs/")


def is_reviewer_only_files(file_list: list[str]) -> bool:
    """Check if every file in the list is a reviews/ directory file.

    Pure function: returns True if the commit should be skipped because it
    only touches the reviewer's own output directory.
    """
    return len(file_list) > 0 and all(f.startswith("reviews/") for f in file_list)


def is_coordination_only_files(file_list: list[str]) -> bool:
    """Check if every file in the list is a coordination file.

    Coordination files: TASKS.md, BACKLOG.md, any file under reviews/, bugs/,
    or milestones/. Pure function: returns True if the commit should be skipped
    because it only touches coordination files with no code changes.
    """
    if not file_list:
        return False
    for f in file_list:
        if f in SKIP_ONLY_FILES:
            continue
        if any(f.startswith(d) for d in _COORDINATION_DIRS):
            continue
        if f.startswith("milestones/") and f.endswith(".md"):
            continue
        return False
    return True


def is_reviewer_only_commit(commit_sha: str) -> bool:
    """Check if a commit only touches REVIEWS.md (i.e. the reviewer's own commit)."""
    result = run_cmd(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
        capture=True,
    )
    if result.returncode != 0:
        return False
    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return is_reviewer_only_files(files)


def is_coordination_only_commit(commit_sha: str) -> bool:
    """Check if a commit only touches coordination files (TASKS.md, REVIEWS.md, BUGS.md)."""
    result = run_cmd(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
        capture=True,
    )
    if result.returncode != 0:
        return False
    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return is_coordination_only_files(files)


def is_merge_commit(commit_sha: str) -> bool:
    """Check if a commit is a merge commit (has more than one parent)."""
    result = run_cmd(
        ["git", "rev-parse", f"{commit_sha}^2"],
        capture=True,
    )
    return result.returncode == 0
