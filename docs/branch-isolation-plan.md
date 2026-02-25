# Branch Isolation Implementation Plan

## Problem

All agents push directly to `main`. This causes three categories of leakage:

1. **Dirty main.** Builders push after every task (per the prompt: "After each commit, run git pull --rebase and push"). Builder-1 pushes tasks 1-3 of milestone-05; the validator starts milestone-04 validation, does `git pull`, and sees half of milestone-05.

2. **SHA contamination.** `_record_completed_milestone()` in `builder.py` does `git pull --rebase` then `git rev-parse HEAD`. Between the LLM's last push and this pull, other agents may have pushed. The recorded `end_sha` includes their commits. Downstream agents (validator, tester, milestone reviewer) operate on a polluted SHA range.

3. **Cherry-pick loss.** The validator creates artifacts (Dockerfile, DEPLOY.md, bugs/) on a detached HEAD, returns to main, and cherry-picks. If main has moved, cherry-pick conflicts silently drop the commits — deployment knowledge is lost.

## Solution

Per-builder branches. Builders work on `builder-N/milestone-NN` branches and push per-task there. Main only receives completed milestones via `--no-ff` merge. Each merge is tagged `milestone-NN`. Works identically with bare repos and GitHub — branches and tags are pure git.

### New builder loop flow

Current:
```
[main] claim → plan → run_copilot → _record_completed_milestone → mark_story_completed
```

New:
```
[main] ensure_on_main → claim → plan → CREATE BRANCH → run_copilot → MERGE TO MAIN → record_boundary → DELETE BRANCH → mark_story_completed
```

The branch is created *after* planning (so the milestone file lands on main where all agents see it) and merged *before* recording the boundary (so the merge commit is the clean SHA).

---

## Step 1: Add branch + tag helpers to `git_helpers.py`

**File:** `src/agentic_dev/git_helpers.py`

Add four new functions after `git_push_with_retry()`:

### `ensure_on_main(agent_name)`

Safety helper called at the top of each loop iteration. Ensures the builder starts each claim cycle on main regardless of prior state (crash recovery).

```python
def ensure_on_main(agent_name: str) -> None:
    """Ensure the working directory is on the main branch.

    Called at the start of each builder loop iteration to handle crash recovery —
    if the builder restarted while on a feature branch, this returns to main.
    Also cleans up any stale local feature branches from prior runs.
    """
    # Switch to main if not already there
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
```

### `create_milestone_branch(builder_id, milestone_name, agent_name)`

Creates a feature branch from current main and sets upstream tracking so the LLM's `git push` routes to the branch automatically.

```python
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
```

### `merge_milestone_to_main(branch_name, milestone_name, agent_name, max_attempts=5)`

The core merge function. Switches to main, merges the branch with `--no-ff`, tags the merge commit, and pushes. Retries on race conditions.

```python
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
```

### `delete_milestone_branch(branch_name, agent_name)`

Cleanup after successful merge. Swallows failures — branch may already be gone.

```python
def delete_milestone_branch(branch_name: str, agent_name: str) -> None:
    """Delete a milestone branch locally and from origin.

    Best-effort — swallows failures since the branch may already be gone
    (e.g. from a prior cleanup or manual deletion).
    """
    run_cmd(["git", "branch", "-d", branch_name], quiet=True)
    run_cmd(["git", "push", "origin", "--delete", branch_name], quiet=True)
    log(agent_name, f"Deleted branch: {branch_name}", style="cyan")
```

**Note:** Add `import time` at the top of `git_helpers.py` (already imported in the existing file — verify).

---

## Step 2: Modify the builder loop in `builder.py`

**File:** `src/agentic_dev/builder.py`

### 2a. Add imports

Add to the imports at the top of the file:

```python
from agentic_dev.git_helpers import (
    create_milestone_branch,
    delete_milestone_branch,
    ensure_on_main,
    git_push_with_retry,
    merge_milestone_to_main,
)
```

(Currently only `git_push_with_retry` is imported from git_helpers.)

### 2b. Add `ensure_on_main` at the top of the loop

At the start of the `while True` loop (~L501), before `claim_next_story()`:

```python
    while True:
        state.cycle_count += 1
        ensure_on_main(agent_name)  # <-- ADD THIS

        story = claim_next_story(agent_name, builder_id)
```

This handles crash recovery — if the builder restarted while on a branch, it returns to main.

### 2c. Wrap each milestone build in branch create/merge

Current code (~L555-590):

```python
        for milestone_file in new_milestones:
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

            _record_completed_milestone(milestone_file, agent_name)

            log(agent_name, "")
            log(agent_name, "======================================", style="bold cyan")
            log(agent_name, " Milestone complete!", style="bold cyan")
            log(agent_name, "======================================", style="bold cyan")

        if build_failed:
            write_builder_done(builder_id)
            return
```

New code:

```python
        for milestone_file in new_milestones:
            milestone_basename = os.path.splitext(os.path.basename(milestone_file))[0]

            # Create feature branch for this milestone
            branch_name = create_milestone_branch(builder_id, milestone_basename, agent_name)
            if not branch_name:
                build_failed = True
                break

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
                ensure_on_main(agent_name)
                build_failed = True
                break

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
            unclaim_story(story["number"], agent_name)
            write_builder_done(builder_id)
            return
```

### 2d. Update `_record_completed_milestone()` signature

Current (~L326-352):

```python
def _record_completed_milestone(
    milestone_file: str, agent_name: str,
) -> None:
    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    ms = parse_milestone_file(milestone_file)
    if not ms or not ms["all_done"]:
        log(agent_name, "WARNING: Milestone does not appear complete after build.", style="bold yellow")
        return

    start_sha = get_last_milestone_end_sha()
    head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
    head_sha = head_result.stdout.strip() if head_result.returncode == 0 else ""

    record_milestone_boundary(ms["name"], start_sha, head_sha)
```

New:

```python
def _record_completed_milestone(
    milestone_file: str, agent_name: str, merge_sha: str = "",
) -> None:
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
```

When `merge_sha` is provided (loop mode with branches), skips the `git pull --rebase` and uses the merge commit directly. When omitted (legacy non-loop mode), preserves existing behavior.

---

## Step 3: Update the builder prompt in `prompts/builder.py`

**File:** `src/agentic_dev/prompts/builder.py`

Add after the existing context scoping paragraph (after the `"COMMIT MESSAGE FORMAT:..."` line):

```
"BRANCH WORKFLOW: You are working on a feature branch. Do not switch branches, "
"checkout main, or create new branches — the orchestration system manages the "
"branch lifecycle. Just commit and push to your current branch as instructed.\n\n"
```

No change to the push instructions at the end of the prompt. The existing "After each commit, run git pull --rebase and push" works correctly because `create_milestone_branch` sets upstream tracking, so `git push` routes to the feature branch.

---

## Step 4: Update the commit watcher in `watcher.py`

**File:** `src/agentic_dev/watcher.py`

With branches, builder per-task commits no longer appear on main — only merge commits do. The watcher currently skips merge commits (via `is_merge_commit()` in `_should_skip_commit()`). Change this to not skip milestone merge commits.

In `_should_skip_commit()`, update the merge commit check. Instead of unconditionally skipping all merges, check the commit message:

```python
    # Skip merge commits UNLESS they are milestone merges (which should be reviewed)
    if is_merge_commit(commit_sha):
        msg_result = run_cmd(
            ["git", "log", "-1", "--format=%s", commit_sha],
            capture=True,
        )
        msg = msg_result.stdout.strip() if msg_result.returncode == 0 else ""
        if "[builder] Merge milestone-" in msg:
            return None  # Don't skip — review this milestone merge
        return "merge commit"
```

This lets the watcher review the full milestone diff (the merge commit's diff against main) as a single review. The watcher's existing batch review code path handles large diffs.

---

## Step 5: No changes needed

These files require **no modifications**:

- **`validator.py`** — Keeps the detached-HEAD + cherry-pick flow. With clean main (no intermediate builder commits), cherry-pick failures become much rarer. The end_sha in milestones.log is now a merge commit on main, so `git checkout {end_sha}` is always valid.
- **`prompts/validator.py`** — "Do NOT run git push" remains correct for the detached-HEAD flow.
- **`tester.py`** — Already operates on main using milestone SHAs from milestones.log. Those SHAs are now clean merge commits. No change.
- **`milestone_reviewer.py`** — Same as tester. SHAs are clean.
- **`milestone.py`** — `record_milestone_boundary()` and `get_last_milestone_end_sha()` are file-based, no git assumptions.
- **`sentinel.py`** — Entirely filesystem-based. No git.
- **`orchestrator.py`** — Launches agents. No branch awareness needed.
- **`bootstrap.py`** — Creates clones pointing to origin. All clones track main. No change.
- **`planner.py`** — The planner is called by the builder *before* branching (on main), so milestone files and BACKLOG.md land on main where all agents see them. No change.

---

## Step 6: Update documentation in `AGENTS.md`

Update the Builder section to describe the branch model:

> **Branch isolation:** Each milestone is built on a feature branch (`builder-N/milestone-NN`). The builder creates the branch after planning (so milestone files land on main), pushes per-task commits to the branch, and merges to main with `--no-ff` when complete. The merge commit is tagged `milestone-NN` and recorded in `logs/milestones.log`. All other agents only see main, which contains only completed milestones.

Update the Commit Watcher section:

> **Merge commit reviews:** With branch isolation, per-task builder commits no longer appear on main. The watcher reviews milestone merge commits (full milestone diff) when they land. This provides fast [bug]/[security] feedback at merge time, complementing the milestone reviewer's deeper analysis.

Update the Agent Coordination Rules:

> **Branch model:** Builders push code to per-milestone feature branches, never directly to main. Coordination artifacts (BACKLOG.md claims/completions, milestone files from the planner) are committed on main before branching. Main receives completed milestones via `--no-ff` merge commits, each tagged `milestone-NN`.

---

## Key design decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Branch naming | `builder-N/milestone-NN` | Namespaced per builder; matches milestone file naming |
| Merge strategy | `--no-ff` always | Guarantees a merge commit exists for clean SHA boundaries |
| Tags | `milestone-NN` on merge commit | Pure git feature, aids debugging, visible in `git log --decorate` and GitHub UI |
| Planner timing | Runs on main, before branching | Milestone files and BACKLOG.md are coordination artifacts all agents need |
| Commit watcher | Reviews merge commits on main | Preserves fast [bug]/[security] feedback; reviews full milestone diff |
| Fix-only cycles | Stay on main, no branch | Post-completion fixes are small targeted pushes; no milestone-level isolation needed |
| Non-loop mode | Unchanged, no branches | Backward compatible |
| Validator | Unchanged (detached-HEAD + cherry-pick) | Cherry-pick failures become rare with clean main; not worth refactoring |

## Verification

After implementation, validate with the test harness:

1. `--builders 2` run: `git log --oneline --graph --decorate` should show only merge commits + coordination commits on main (no per-task builder commits)
2. `git tag -l` should show `milestone-01`, `milestone-02`, etc.
3. `logs/milestones.log` entries: every `end_sha` should match a tagged merge commit
4. Kill a builder mid-milestone: branch exists on remote (`git branch -r`), main is clean, resume works
5. Validator logs: no "cherry-pick" warnings
6. `--local` mode (bare repo): branches and tags push successfully to `remote.git/`
7. GitHub remote: branches and tags appear in GitHub UI
