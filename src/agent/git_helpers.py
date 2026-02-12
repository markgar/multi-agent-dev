"""Git operation helpers: push with retry, commit classification."""

import time

from agent.utils import log, run_cmd


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


def is_reviewer_only_files(file_list: list[str]) -> bool:
    """Check if every file in the list is REVIEWS.md.

    Pure function: returns True if the commit should be skipped because it
    only touches the reviewer's own output file.
    """
    return len(file_list) > 0 and all(f == "REVIEWS.md" for f in file_list)


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


def is_merge_commit(commit_sha: str) -> bool:
    """Check if a commit is a merge commit (has more than one parent)."""
    result = run_cmd(
        ["git", "rev-parse", f"{commit_sha}^2"],
        capture=True,
    )
    return result.returncode == 0
