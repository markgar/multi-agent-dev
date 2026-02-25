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


# ============================================
# Branch isolation helpers
# ============================================


def ensure_on_main(agent_name: str) -> None:
    """Ensure the working directory is on the main branch.

    Called at the start of each builder loop iteration to handle crash recovery —
    if the builder restarted while on a feature branch, this returns to main.
    Also cleans up any stale local feature branches from prior runs.
    """
    result = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
    current_branch = result.stdout.strip() if result.returncode == 0 else ""
    if current_branch != "main":
        log(agent_name, f"On branch '{current_branch}', switching to main...", style="yellow")
        run_cmd(["git", "checkout", "main"], quiet=True)

    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    # Clean up stale local feature branches (builder-*/milestone-*)
    branch_result = run_cmd(
        ["git", "branch", "--list", "builder-*/milestone-*"],
        capture=True,
    )
    if branch_result.returncode == 0 and branch_result.stdout.strip():
        for line in branch_result.stdout.strip().split("\n"):
            branch = line.strip().lstrip("* ")
            if branch:
                run_cmd(["git", "branch", "-D", branch], quiet=True)
                log(agent_name, f"Cleaned up stale branch: {branch}", style="yellow")


def create_milestone_branch(builder_id: int, milestone_name: str, agent_name: str) -> str:
    """Create a feature branch for a milestone and set upstream tracking.

    Must be called while on main. Creates builder-{id}/{milestone_name} branch,
    pushes it to origin with tracking set. Returns the branch name.
    """
    branch_name = f"builder-{builder_id}/{milestone_name}"

    result = run_cmd(["git", "checkout", "-b", branch_name], capture=True)
    if result.returncode != 0:
        log(agent_name, f"Failed to create branch {branch_name}", style="red")
        return ""

    push_result = run_cmd(
        ["git", "push", "-u", "origin", branch_name],
        capture=True,
    )
    if push_result.returncode != 0:
        log(agent_name, f"Failed to push branch {branch_name} to origin", style="red")
        # Stay on the branch — local work can still proceed
        # The LLM will need to push manually on first commit

    log(agent_name, f"Created branch: {branch_name}", style="cyan")
    return branch_name


def merge_milestone_to_main(
    branch_name: str, milestone_name: str, agent_name: str, max_attempts: int = 5,
) -> str:
    """Merge a milestone branch to main with a tagged merge commit.

    Flow per attempt:
    1. git checkout main
    2. git pull --rebase
    3. git merge --no-ff {branch} -m "[builder] Merge {milestone_name}"
    4. git tag {milestone_name} HEAD
    5. git push origin main --tags
    On push failure: reset to origin/main, delete local tag, retry.
    On merge conflict: abort merge, pull, retry.

    Returns the merge commit SHA on success, empty string on failure.
    """
    for attempt in range(1, max_attempts + 1):
        run_cmd(["git", "checkout", "main"], quiet=True)
        pull = run_cmd(["git", "pull", "--rebase", "-q"], capture=True)
        if pull.returncode != 0:
            run_cmd(["git", "rebase", "--abort"], quiet=True)
            run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        merge_result = run_cmd(
            ["git", "merge", "--no-ff", branch_name, "-m",
             f"[builder] Merge {milestone_name}"],
            capture=True,
        )
        if merge_result.returncode != 0:
            log(
                agent_name,
                f"Merge conflict (attempt {attempt}/{max_attempts}), retrying...",
                style="yellow",
            )
            run_cmd(["git", "merge", "--abort"], quiet=True)
            if attempt < max_attempts:
                time.sleep(5)
            continue

        # Tag the merge commit
        run_cmd(["git", "tag", milestone_name, "HEAD"], quiet=True)

        push_result = run_cmd(
            ["git", "push", "origin", "main", "--tags"],
            capture=True,
        )
        if push_result.returncode == 0:
            sha_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
            merge_sha = sha_result.stdout.strip() if sha_result.returncode == 0 else ""
            log(
                agent_name,
                f"Merged {branch_name} to main (tag: {milestone_name}, sha: {merge_sha[:8]})",
                style="bold cyan",
            )
            return merge_sha

        # Push failed — another agent pushed to main. Reset and retry.
        log(
            agent_name,
            f"Push rejected after merge (attempt {attempt}/{max_attempts}), resetting...",
            style="yellow",
        )
        run_cmd(["git", "tag", "-d", milestone_name], quiet=True)
        run_cmd(["git", "reset", "--hard", "origin/main"], quiet=True)
        if attempt < max_attempts:
            time.sleep(5)

    log(agent_name, f"Failed to merge {branch_name} after {max_attempts} attempts.", style="red")
    return ""


def delete_milestone_branch(branch_name: str, agent_name: str) -> None:
    """Delete a milestone branch locally and from origin.

    Best-effort — swallows failures since the branch may already be gone
    (e.g. from a prior cleanup or manual deletion).
    """
    run_cmd(["git", "branch", "-d", branch_name], quiet=True)
    run_cmd(["git", "push", "origin", "--delete", branch_name], quiet=True)
    log(agent_name, f"Deleted branch: {branch_name}", style="cyan")
