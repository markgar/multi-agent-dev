# Multi-Builder Design: Story-Level Parallelism via Git Locking

## Problem

Currently agentic-dev has one builder agent that works through stories sequentially. We want N builders working in parallel to speed up large projects (e.g., FieldCraft has 42 stories, Stretto has 31).

## Key Design Decisions

1. **No frontend/backend split.** Any builder takes the next eligible story. The dependency graph in BACKLOG.md enforces ordering — a frontend story won't become eligible until its backend dependency is completed (`[x]`).

2. **Per-milestone task files.** TASKS.md is eliminated. The planner writes each milestone to its own file (e.g., `milestones/milestone-03-members-backend.md`). Each builder exclusively owns its milestone file — zero conflict risk on task completions.

3. **Git-based optimistic locking for story claims.** No central coordinator. The builder's Python orchestration claims a story by marking it in-progress (`[~]`) in BACKLOG.md and pushing. If two builders race, git rejects the second push. The loser pulls (winner's claim arrives), re-reads BACKLOG.md, gets the next eligible story, and claims that instead. After the milestone is fully built, the builder marks the story completed (`[x]`). Dependencies require `[x]` (completed), not `[~]` (claimed) — so a claimed-but-unfinished story does NOT unlock downstream stories.

4. **`--builders N` flag on `go`, default 1.** Backward-compatible. Single builder matches current behavior.

5. **Builder naming: `builder-1`, `builder-2`, ... `builder-N`.** Clean numbering. Affects clone dirs, log files, sentinel files, terminal labels.

6. **All builders on main with robust rebase-retry.** No feature branches. Rebase handles different-line edits (DI wiring, route registration). Extra retries absorb collision rate.

7. **Each builder calls planner independently after claiming.** Claim serializes story assignment via git push. By the time planner runs, each builder has a different story, so planner invocations write to different milestone files. No additional lock needed.

8. **Builders are spawned as terminal processes.** The orchestrator no longer runs `build(loop=True)` in-process. Instead it launches all builders in terminals (like reviewer/tester/validator) and polls for completion.

---

## Claim Flow (per builder)

```
1. git pull --rebase
2. story = get_next_eligible_story(BACKLOG.md)
3. if no story → done (all stories claimed/completed or deps blocked)
4. Mark story in-progress in BACKLOG.md ([ ] → [~])
5. git commit -m '[planner] Claim story N' && git push
6. if push fails:
     - git pull --rebase (winner's claim arrives)
     - go to step 2 (re-read, get NEXT eligible story)
7. Push succeeded → this builder owns story N
8. Planner expands story N into milestones/<name>.md
9. Builder completes the milestone
10. Mark story completed in BACKLOG.md ([~] → [x]), commit & push
11. Go to step 1
```

After a failed push, the builder does NOT retry the same story. It re-reads BACKLOG.md (which now has the winner's claim) and claims whatever's next.

**Three-state backlog:** `[ ]` = unclaimed, `[~]` = claimed/in-progress, `[x]` = completed. Dependencies require `[x]` to be satisfied — a story marked `[~]` does NOT unlock downstream stories. This prevents a frontend story from becoming eligible before its backend dependency is actually built.

---

## Backlog States

BACKLOG.md uses three states for story checkboxes:

| State | Syntax | Meaning |
|---|---|---|
| Unclaimed | `[ ]` | No builder has taken this story yet |
| In-progress | `[~]` | A builder has claimed this story and is actively building it |
| Completed | `[x]` | The story's milestone is fully built and verified |

**State transitions:**
- `[ ] → [~]` — Builder claims the story (Python orchestration, git commit + push)
- `[~] → [x]` — Builder marks it done after milestone completion (Python orchestration, git commit + push)

**Dependency resolution:** `get_next_eligible_story()` only considers `[x]` (completed) stories as satisfying dependencies. A story with `depends: 3` requires story 3 to be `[x]`, not `[~]`. This prevents a downstream story from becoming eligible while an upstream story is still being built by another builder.

**Regex impact:** `parse_backlog()` in milestone.py must recognize all three states. The current regex `\[([ x])\]` needs to become `\[([ x~])\]` and the returned dict needs a `status` field (`unclaimed`, `in_progress`, `completed`) in addition to the existing `checked` boolean. `get_next_eligible_story()` treats `[~]` as "not eligible" (same as `[x]` — already claimed) and only considers `[x]` when checking dependency satisfaction.

---

## Milestone File Format

Each file in `milestones/` is a standalone markdown file with the same structure as today's `## Milestone:` sections in TASKS.md:

```markdown
## Milestone: Members management

> **Validates:** GET /api/members returns 200 with list. POST /api/members returns 201. ...

- [ ] Create Member entity (Id, FirstName, LastName, Email, Role enum)
- [ ] Create MemberRepository implementing BaseRepository<Member>
- [ ] Create MemberService with CRUD operations
- [ ] Create MembersController with REST endpoints
```

The heading, validates block, and checkbox tasks are identical to today. The only difference is each milestone lives in its own file rather than being a section in TASKS.md.

---

## Implementation Sessions

### Session 1: Milestone File Parsing (milestone.py + tests) ✅

**Goal:** Add functions to read/parse milestone files from a `milestones/` directory. Pure additive — nothing existing changes. Old TASKS.md code paths stay intact.

**Files to modify:**
- `src/agentic_dev/milestone.py`
- `tests/test_milestone.py`

#### What exists today in milestone.py (318 lines)

Key functions that read TASKS.md:

```python
# Line 125 — Parses "## Milestone:" sections from markdown text
def parse_milestones_from_text(content: str) -> list[dict]:
    # Returns [{"name": str, "done": int, "total": int}, ...]

# Line 163 — I/O wrapper: reads TASKS.md, calls parse_milestones_from_text
def _parse_milestones(tasks_path: str) -> list[dict]:

# Line 171 — Returns milestones with all_done flag
def get_completed_milestones(tasks_path: str) -> list[dict]:
    # Returns [{"name": str, "all_done": bool}, ...]

# Line 182 — Returns first incomplete milestone
def get_current_milestone_progress(tasks_path: str) -> dict | None:
    # Returns {"name": str, "done": int, "total": int} or None

# Line 229 — Returns task counts for each uncompleted milestone
def get_tasks_per_milestone(tasks_path: str) -> list[dict]:
    # Returns [{"name": str, "task_count": int}, ...]
```

Key functions for milestones.log (already shared-state-safe):

```python
# Line 12 — Appends to logs/milestones.log
def record_milestone_boundary(name, start_sha, end_sha) -> None:

# Line 28 — Pure parser for milestone log text
def parse_milestone_log(text: str) -> list[dict]:

# Line 46 — I/O wrapper: reads milestones.log
def load_milestone_boundaries() -> list[dict]:

# Line 63 — Gets the end SHA of the last recorded milestone
def get_last_milestone_end_sha() -> str:
```

Key functions for agent checkpoints:

```python
# Line 85 — Save which milestones an agent has processed
def save_milestone_checkpoint(milestone_name, checkpoint_file) -> None:

# Line 103 — Load the set of processed milestone names
def load_reviewed_milestones(checkpoint_file=_MILESTONE_CHECKPOINT_FILE) -> set[str]:
```

Key functions for BACKLOG.md:

```python
# Line 249 — Parse BACKLOG.md into story dicts
def parse_backlog(content: str) -> list[dict]:
    # Returns [{"number": int, "name": str, "checked": bool, "status": str, "depends": [int]}, ...]
    # status is one of: "unclaimed", "in_progress", "completed"
    # checked is True for both [~] and [x] (backward compat), False for [ ]

# Line 281 — Get the first unclaimed story with all deps completed
def get_next_eligible_story(content: str) -> dict | None:
    # Returns the first story where status == "unclaimed" AND
    # all dependencies have status == "completed" (not just "in_progress")
```

**Session 1 changes to backlog functions:** Update `_BACKLOG_RE` regex from `\[([ x])\]` to `\[([ x~])\]`. Update `parse_backlog` to return a `status` field. Update `get_next_eligible_story` to:
- Skip stories with status `in_progress` or `completed` (not just `checked`)
- Only consider a dependency satisfied when its status is `completed` (not `in_progress`)

# Line 300-318 — I/O wrappers
def has_pending_backlog_stories_in_file(path) -> bool:
def get_next_eligible_story_in_file(path) -> dict | None:
```

#### New functions to add

```python
def parse_milestone_file(path: str) -> dict | None:
    """Read one milestone file and return milestone info.

    Returns {"name": str, "done": int, "total": int, "all_done": bool}
    or None if the file doesn't exist or has no tasks.

    The file format is the same as a ## Milestone: section in TASKS.md —
    a heading, optional validates block, and checkbox lines.
    """

def list_milestone_files(milestones_dir: str = "milestones") -> list[str]:
    """Return sorted list of .md file paths in the milestones/ directory.

    Returns full paths, sorted alphabetically. Returns empty list if
    the directory doesn't exist.
    """

def get_all_milestones(milestones_dir: str = "milestones") -> list[dict]:
    """Parse all milestone files and return milestone info for each.

    Returns [{"name": str, "done": int, "total": int, "all_done": bool}, ...]
    in filename-sorted order. Skips files that fail to parse.
    """

def get_completed_milestones_from_dir(milestones_dir: str = "milestones") -> list[dict]:
    """Return only completed milestones from the milestones/ directory.

    Returns [{"name": str, "all_done": True}, ...] for milestones where
    all tasks are checked.
    """

def get_milestone_progress_from_file(path: str) -> dict | None:
    """Return progress info for a single milestone file.

    Returns {"name": str, "done": int, "total": int} if the milestone
    has unchecked tasks. Returns None if all tasks are done or file
    doesn't exist.
    """

def get_tasks_per_milestone_from_dir(milestones_dir: str = "milestones") -> list[dict]:
    """Return task counts for each uncompleted milestone in the directory.

    Returns [{"name": str, "task_count": int}, ...]
    Replacement for get_tasks_per_milestone("TASKS.md").
    """
```

All of these are thin wrappers around `parse_milestones_from_text` — each milestone file has the same `## Milestone:` heading + checkbox format. The key insight is that `parse_milestones_from_text` already works on a single milestone's text because a milestone file contains exactly one `## Milestone:` section.

#### Tests to add in test_milestone.py

Use realistic milestone file content as fixtures. Test:

1. `parse_milestone_file` — file with 5 tasks (3 done, 2 remaining)
2. `parse_milestone_file` — file with all tasks done
3. `parse_milestone_file` — missing file returns None
4. `parse_milestone_file` — empty file returns None
5. `list_milestone_files` — directory with 3 .md files (verify sorted)
6. `list_milestone_files` — missing directory returns empty list
7. `list_milestone_files` — directory with non-.md files (ignored)
8. `get_all_milestones` — multiple files, mixed completion
9. `get_completed_milestones_from_dir` — filters to only completed
10. `get_milestone_progress_from_file` — incomplete milestone returns dict
11. `get_milestone_progress_from_file` — completed milestone returns None
12. `get_tasks_per_milestone_from_dir` — counts tasks for uncompleted milestones

Use `tmp_path` fixture to create real directories and files.

---

### Session 2: Planner Writes to milestones/ (prompts + planner.py) ✅

**Goal:** Change planner output from appending to TASKS.md to writing individual milestone files in `milestones/`. The builder still runs the old way — this session only changes the planning side.

**Files to modify:**
- `src/agentic_dev/prompts/planner.py`
- `src/agentic_dev/planner.py`
- `src/agentic_dev/prompts/copilot_instructions.py`

#### prompts/planner.py changes

**PLANNER_INITIAL_PROMPT** (Line 3, ~92 lines long):

Current: "Create TASKS.md with one `## Milestone:` section for that story."

Change to:
- "Create the directory `milestones/` if it doesn't exist."
- "Write the first milestone as `milestones/<slug>.md` where `<slug>` is a kebab-case slug derived from the milestone name (e.g., `milestone-01-project-scaffolding.md`)."
- "The file must start with `## Milestone: <name>`, followed by the `> **Validates:**` block, followed by task checkboxes."
- "Do NOT create TASKS.md."
- Update the commit message from '[planner] Update task plan' to '[planner] Plan milestone: <name>'

Keep everything else (story decomposition, BACKLOG.md format, task/milestone sizing rules) exactly as-is.

**PLANNER_PROMPT** (Line 107, ~111 lines long — Case B/C):

Current: "append one `## Milestone:` to TASKS.md"

Change to:
- "Write one milestone file to `milestones/<slug>.md`."
- Add a `{story_name}` placeholder: "You are expanding story '{story_name}' into a milestone."
- Remove: "3. Check it off in BACKLOG.md" — the Python orchestration does this now via the claim step.
- Change Case B step list to:
  1. "The orchestrator has already claimed this story in BACKLOG.md"
  2. "Read the codebase to understand what patterns exist"
  3. "Write one milestone file to `milestones/<slug>.md`"
  4. "Never modify existing milestone files — those belong to other builders"
- Remove TASKS.md references everywhere in Case B/C.
- Update commit message to '[planner] Plan milestone: <name>'

**PLANNER_SPLIT_PROMPT** (Line 292):

Current: "Milestone '{milestone_name}' in TASKS.md has {task_count} tasks"

Change to: "Milestone file `{milestone_file}` has {task_count} tasks, which is too many. Split it into two milestone files in `milestones/`..."

Also add `{milestone_file}` placeholder.

**BACKLOG_QUALITY_PROMPT** (Line 221):

References TASKS.md for "the first milestone." Change to: "Read the milestone files in `milestones/` to see the current milestone's tasks." Also update "CRITERION C6" references from TASKS.md to `milestones/`.

**BACKLOG_ORDERING_PROMPT** (Line 274):

No changes needed — only touches BACKLOG.md.

**PLANNER_COMPLETENESS_PROMPT** (Line 94):

No changes needed — only touches BACKLOG.md.

**BACKLOG.md checkbox semantics in planner prompts:**

The planner prompts currently document `[x]` as "planned into TASKS.md". With three-state, update the BACKLOG.md format documentation in both PLANNER_INITIAL_PROMPT and PLANNER_PROMPT:

- Change: `- \`[ ]\` = in backlog (not yet planned), \`[x]\` = planned into TASKS.md`
- To: `- \`[ ]\` = unclaimed, \`[~]\` = claimed/in-progress, \`[x]\` = completed`
- Add: "The Python orchestration manages checkbox state — do NOT check off stories yourself."

This ensures the LLM planner understands the three states even though it doesn't write them directly.

#### planner.py changes

```python
def plan(requirements_changed: bool = False, story_name: str = "") -> bool:
```

Add `story_name` parameter. When non-empty, format it into the PLANNER_PROMPT:

```python
prompt = PLANNER_PROMPT.format(story_name=story_name)
```

Add `os.makedirs("milestones", exist_ok=True)` before invoking Copilot in both the fresh and continuing paths.

**check_milestone_sizes()** at Line 91:

Current:
```python
oversized = [
    ms for ms in get_tasks_per_milestone("TASKS.md")
    if ms["task_count"] > _MAX_TASKS_PER_MILESTONE
]
```

Change to use the new milestones/ directory function:
```python
from agentic_dev.milestone import get_tasks_per_milestone_from_dir

oversized = [
    ms for ms in get_tasks_per_milestone_from_dir("milestones")
    if ms["task_count"] > _MAX_TASKS_PER_MILESTONE
]
```

Also update the PLANNER_SPLIT_PROMPT formatting to use `milestone_file` instead of the old TASKS.md reference. The planner needs to know which file to split.

#### prompts/copilot_instructions.py changes

**COPILOT_INSTRUCTIONS_PROMPT** (Line 95):

Current: "Read TASKS.md to understand the planned components and milestones."

Change to: "Read the milestone files in `milestones/` to understand the planned components and milestones."

This only affects newly generated copilot-instructions.md files — existing project repos still have whatever was generated before.

---

### Session 3: Builder Claim Loop + Multi-Builder Primitives

**Goal:** Rewrite the builder to use the claim-and-build pattern with milestone files. Add `--builder-id` option. Update sentinel for multi-builder shutdown. Update utils and git_helpers for builder-N directories.

**Files to modify:**
- `src/agentic_dev/builder.py`
- `src/agentic_dev/prompts/builder.py`
- `src/agentic_dev/sentinel.py`
- `src/agentic_dev/utils.py`
- `src/agentic_dev/git_helpers.py`
- `tests/test_builder.py`
- `tests/test_utils.py`

#### prompts/builder.py changes

**BUILDER_PROMPT** (83 lines, single string constant):

This prompt currently tells the builder to find the first incomplete milestone in TASKS.md. It needs to change so the Python orchestration tells the builder WHICH file to work on.

Add `{milestone_file}` placeholder. Change the full prompt:

**Remove these sections:**
- "move to TASKS.md. TASKS.md is organized into milestones..."
- "Find the first milestone that has unchecked tasks — this is your current milestone."
- All references to marking tasks in TASKS.md

**Replace with:**
- "Read your milestone file at `{milestone_file}`. This file contains exactly one milestone with task checkboxes."
- "Complete every task in this file, then STOP."
- "For each task: write the code AND mark it complete in `{milestone_file}`, then commit BOTH together with a meaningful message."
- "Do NOT modify any other files in `milestones/` — those belong to other builders."

Keep everything else: bugs/ and reviews/ handling, DEPLOY.md/REVIEW-THEMES.md reading, gitignore maintenance, documentation maintenance, build verification.

Also keep "Read README.md, SPEC.md" but remove "and TASKS.md" — replace with "and your milestone file at `{milestone_file}`".

#### builder.py changes

**Current structure (537 lines):**

```python
# L30 — build() function
#   L42 — while True main loop
#   L56 — get_completed_milestones("TASKS.md")
#   L60 — run_copilot("builder", BUILDER_PROMPT)
#   L76 — _record_completed_milestones(milestones_before)
#   L91 — _try_expand_next_story(state)

# L96 — BuildState dataclass
# L109 — _run_fix_only_cycle(state)
# L139 — update_milestone_retry_state (pure)
# L160 — _handle_fix_only_replan(state)
# L176 — _try_expand_backlog(state) — calls plan()
# L194 — _try_expand_legacy_roadmap(state)
# L206 — _update_state_from_replan(state)
# L222 — _handle_backlog_expansion(state)
# L234 — _try_expand_next_story(state)
# L249 — _handle_loop_replan(state, progress)
# L268 — _detect_milestone_progress(state, loop)
# L314 — _record_completed_milestones(milestones_before)
# L365 — _completed_milestones_at_commit(commit_sha, remaining)
# L381 — _find_per_milestone_boundaries(milestone_names, start_sha, end_sha)
# L421 — classify_remaining_work (pure)
# L493 — _check_remaining_work(state)
```

**New structure:**

```python
def build(
    loop: bool = False,
    builder_id: int = 1,  # NEW
) -> None:
```

The `builder_id` determines:
- Agent name for logging: `f"builder-{builder_id}"` (used in `log()` and `run_copilot()` calls)
- Sentinel file: `logs/builder-{builder_id}.done`

**New function — `claim_next_story`:**

```python
def claim_next_story(agent_name: str, max_attempts: int = 10) -> dict | None:
    """Claim the next eligible story from BACKLOG.md using git push as a lock.

    Flow:
    1. git pull --rebase
    2. Read BACKLOG.md, find next eligible unclaimed story (status == "unclaimed"
       AND all deps have status == "completed")
    3. Mark it in-progress ([ ] → [~])
    4. git commit + push
    5. If push fails: pull (winner's claim arrives), go to step 2
    6. Returns the claimed story dict, or None if no eligible stories

    The key insight: after a failed push, we do NOT retry the same story.
    We pull (which brings the winner's [~] mark), re-read BACKLOG.md,
    and get whatever is now the next eligible story.
    """
```

Implementation details:
- Read BACKLOG.md, call `get_next_eligible_story()` from milestone.py
- If None → return None (all done or deadlocked)
- Modify the line in BACKLOG.md: replace `[ ]` with `[~]` for exactly the story number
- `git add BACKLOG.md && git commit -m "[planner] Claim story N: <name>"`
- `git push` — check return code
- If push fails: `git pull --rebase` (if rebase fails, `git rebase --abort` then `git pull --rebase` again)
- Loop back to re-read BACKLOG.md and find next eligible
- After `max_attempts` failures, log warning and return None

**New function — `mark_story_completed`:**

```python
def mark_story_completed(story_number: int, agent_name: str, max_attempts: int = 5) -> bool:
    """Mark a claimed story as completed in BACKLOG.md ([~] → [x]).

    Called after the builder finishes a milestone. Uses the same
    git-push-as-lock pattern as claim_next_story.

    Returns True if successfully marked, False if failed after retries.
    """
```

Implementation details:
- `git pull --rebase`
- Read BACKLOG.md, find story N, replace `[~]` with `[x]`
- `git add BACKLOG.md && git commit -m "[builder] Complete story N: <name>"`
- `git push` — if fails, pull and retry (the story line should merge cleanly since each builder edits a different line)
- After `max_attempts` failures, log error and return False

**New function — `find_milestone_file_for_story`:**

```python
def find_milestone_file_for_story(milestones_dir: str = "milestones") -> str | None:
    """Find the milestone file that was just created by the planner.

    After the planner runs, there should be exactly one new .md file in milestones/
    that has unchecked tasks. Returns the path to that file.
    """
```

Find the most recently created file in `milestones/` that has unchecked tasks (could also compare file listing before/after planner run).

**Rewritten build loop:**

```python
def build(loop: bool = False, builder_id: int = 1) -> None:
    agent_name = f"builder-{builder_id}"

    if not loop:
        # Non-loop mode: just run one copilot cycle on whatever milestone file exists
        # (legacy compatibility, not used by multi-builder)
        ...
        return

    # Loop mode: claim-and-build
    while True:
        story = claim_next_story(agent_name)
        if not story:
            # No eligible stories — enter shutdown sequence
            signal = _check_remaining_work(state, agent_name)
            if signal == "done":
                write_builder_done(builder_id)
                return
            continue

        # Plan: expand this story into a milestone file
        plan(story_name=story["name"])
        check_milestone_sizes()

        milestone_file = find_milestone_file_for_story()
        if not milestone_file:
            log(agent_name, "WARNING: Planner did not create a milestone file.", style="yellow")
            continue

        # Build the milestone
        prompt = BUILDER_PROMPT.format(milestone_file=milestone_file)
        milestones_before = {
            ms["name"] for ms in get_completed_milestones_from_dir() if ms["all_done"]
        }

        exit_code = run_copilot(agent_name, prompt)

        if exit_code != 0:
            log(agent_name, "Builder failed!", style="bold red")
            write_builder_done(builder_id)
            return

        _record_completed_milestone(milestone_file, milestones_before, agent_name)

        # Mark story as completed ([~] → [x]) so downstream deps unlock
        mark_story_completed(story["number"], agent_name)

        # Loop back to claim next story
```

**Functions to remove or significantly simplify:**
- `_detect_milestone_progress` — no longer needed (each builder owns one milestone at a time)
- `_try_expand_next_story` — replaced by claim loop
- `_try_expand_backlog` — replaced by claim loop
- `_try_expand_legacy_roadmap` — can keep for backward compat or remove
- `_handle_loop_replan` — replaced by claim loop
- `_handle_backlog_expansion` — replaced by claim loop
- `_update_state_from_replan` — replaced by claim loop
- `_handle_fix_only_replan` — simplify
- `update_milestone_retry_state` — simplify (less relevant with single-milestone ownership)
- `_completed_milestones_at_commit` — simplify (reads TASKS.md at commit SHA)
- `_find_per_milestone_boundaries` — simplify (each builder completes exactly one milestone)

**Functions to keep but modify:**
- `_record_completed_milestones` → `_record_completed_milestone` — reads from the builder's milestone file instead of TASKS.md
- `_check_remaining_work` — change `has_unchecked_items("TASKS.md")` to check the current milestone file; add `agent_name` parameter
- `_run_fix_only_cycle` — keep but update agent_name and milestone file references
- `classify_remaining_work` — keep as-is (pure function, no TASKS.md dependency)
- `BuildState` — simplify (remove milestone-tracking fields that are no longer needed)

#### sentinel.py changes

**Current structure (147 lines):**

```python
_BUILDER_DONE_FILE = "builder.done"    # Line 8
_BUILDER_LOG_FILE = "builder.log"      # Line 9

def write_builder_done() -> None:      # Line 18 — writes logs/builder.done
def clear_builder_done() -> None:      # Line 28 — removes logs/builder.done
def is_builder_done() -> bool:         # Line 47 — checks single sentinel + stale log
def are_agents_idle() -> bool:         # Line 108 — checks reviewer/tester/validator logs
```

**Changes:**

```python
def write_builder_done(builder_id: int = 1) -> None:
    """Write logs/builder-{builder_id}.done sentinel."""

def clear_builder_done(num_builders: int = 1) -> None:
    """Remove all builder-N.done sentinels for N in 1..num_builders."""

def is_builder_done() -> bool:
    """Check if ALL builders have finished.

    Returns True if:
    1. At least one builder-N.log exists, AND every builder-N.log that exists
       has a matching builder-N.done sentinel, OR
    2. All builder-N.log files are stale (30+ minutes without writes).

    Discovery: list logs/builder-*.log to find how many builders exist.
    Then check for builder-*.done matching each one.
    """
```

The discovery-based approach means `is_builder_done()` doesn't need to know `num_builders` — it discovers active builders from their log files and checks each has a done sentinel.

Also update `check_builder_done_status` pure function to handle multi-builder or add a new pure function `check_all_builders_done_status`.

Keep `are_agents_idle()` unchanged — it checks reviewer/tester/validator, not builders.

#### utils.py changes

**Line 28:**

```python
_AGENT_DIRS = {"builder", "reviewer", "tester", "validator", "watcher"}
```

Change `find_project_root` to also recognize `builder-N` directories:

```python
import re

_AGENT_DIRS = {"builder", "reviewer", "tester", "validator", "watcher"}
_BUILDER_DIR_RE = re.compile(r"^builder-\d+$")

def find_project_root(cwd: str) -> str:
    basename = os.path.basename(cwd)
    if basename in _AGENT_DIRS or _BUILDER_DIR_RE.match(basename):
        return os.path.dirname(cwd)
    return cwd
```

No other changes in utils.py — `log()` and `run_copilot()` already use `agent_name` parameter, so passing `"builder-1"` naturally logs to `logs/builder-1.log`.

#### git_helpers.py changes

**Line 52:**

```python
SKIP_ONLY_FILES = {"TASKS.md"}
```

Update `is_coordination_only_files` to also treat `milestones/*.md` and `BACKLOG.md` as coordination files:

```python
SKIP_ONLY_FILES = {"TASKS.md", "BACKLOG.md"}

def is_coordination_only_files(file_list: list[str]) -> bool:
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
```

#### Tests

**test_builder.py — new tests:**
- `test_claim_next_story_succeeds_on_first_push` — mock git commands, verify story is returned
- `test_claim_next_story_retries_after_push_failure` — first push fails, pull succeeds, second claim works
- `test_claim_next_story_returns_none_when_no_eligible_stories`
- `test_claim_next_story_modifies_backlog_correctly` — verify the [ ] → [~] substitution is correct

Note: `claim_next_story` involves git subprocess calls, so these tests might need to be integration-style or the function should be split into a pure "modify backlog text" function (testable) and an I/O wrapper.

**Recommended split for testability:**

```python
def mark_story_claimed(content: str, story_number: int) -> str:
    """Pure function: replace [ ] with [~] for the given story number in backlog text.

    Returns the modified content string.
    """

def mark_story_completed_text(content: str, story_number: int) -> str:
    """Pure function: replace [~] with [x] for the given story number in backlog text.

    Called after a milestone is fully built. Returns the modified content string.
    """
```

These are easily unit-testable. The I/O wrappers (`claim_next_story`, `mark_story_completed`) are thin and don't need their own unit tests.

Test `mark_story_claimed`:
- Marks the correct story with `[~]`
- Doesn't modify already-claimed `[~]` or completed `[x]` stories
- Handles story with dependencies annotation
- Handles story at end of file (no trailing newline)

Test `mark_story_completed_text`:
- Changes `[~]` to `[x]` for the correct story
- Doesn't modify unclaimed `[ ]` or already-completed `[x]` stories
- Handles story with dependencies annotation

**test_builder.py — existing tests to update:**
- `classify_remaining_work` tests — keep as-is (pure function, no changes)
- `update_milestone_retry_state` tests — may be removed or simplified depending on how much that logic is kept
- `BuildState` tests — update for new field set

**test_utils.py — new tests:**
- `test_find_project_root_recognizes_builder_numbered_dirs` — `builder-1`, `builder-2`, `builder-10`
- `test_find_project_root_ignores_non_matching_dirs` — `builder-`, `builder-abc`, `builder1`

**test_utils.py — existing tests to update:**
- `is_coordination_only_files` tests — add cases for `milestones/*.md` files and BACKLOG.md

---

### Session 4: Orchestrator Multi-Launch + Wiring + Docs

**Goal:** Wire everything together. Orchestrator launches N builders as terminals. Downstream agents verified. Harness updated. Docs updated.

**Files to modify:**
- `src/agentic_dev/orchestrator.py`
- `src/agentic_dev/cli.py` (`status` command reads TASKS.md → milestones/)
- `src/agentic_dev/backlog_checker.py` (TASKS.md validation → milestones/)
- `src/agentic_dev/prompts/reviewer.py` (TASKS.md references → milestones/)
- `src/agentic_dev/prompts/tester.py` (TASKS.md references → milestones/)
- `src/agentic_dev/prompts/validator.py` (TASKS.md references → milestones/)
- `src/agentic_dev/watcher.py` (verify, minimal changes)
- `src/agentic_dev/tester.py` (verify, minimal changes)
- `src/agentic_dev/validator.py` (verify, minimal changes)
- `tests/harness/run_test.sh`
- `tests/harness/run_test.py` (if it exists as Python wrapper)
- `AGENTS.md`

#### orchestrator.py changes

**Current structure (317 lines):**

```python
# L30 — _detect_clone_source(parent_dir)
# L47 — _find_existing_repo(parent_dir, name, local)
# L68 — _clone_all_agents(parent_dir, clone_source)
#        Hardcoded: ["builder", "reviewer", "tester", "validator"]
# L82 — _pull_all_clones(parent_dir)
#        Hardcoded: ["builder", "reviewer", "tester", "validator"]
# L126 — _generate_copilot_instructions()
# L152 — _launch_agents_and_build(parent_dir, plan_label, project_name, requirements_changed)
#         Calls: plan() → spawn reviewer/tester/validator → build(loop=True)  [BLOCKING]
# L215 — _resume_existing_project(...)
#         L270: os.chdir(os.path.join(parent_dir, "builder"))
# L246 — go(directory, model, description, spec_file, local, name)
```

**Add `--builders` flag to `go()`:**

```python
def go(
    directory: ...,
    model: ...,
    description: ... = None,
    spec_file: ... = None,
    local: ... = False,
    name: ... = None,
    builders: Annotated[int, typer.Option(help="Number of parallel builders")] = 1,  # NEW
) -> None:
```

Pass `builders` through to `_launch_agents_and_build`, `_clone_all_agents`, `_pull_all_clones`, and `clear_builder_done`.

**Change `_clone_all_agents`:**

```python
def _clone_all_agents(parent_dir: str, clone_source: str, num_builders: int = 1) -> None:
    os.makedirs(parent_dir, exist_ok=True)
    agents = [f"builder-{i}" for i in range(1, num_builders + 1)] + ["reviewer", "tester", "validator"]
    for agent in agents:
        agent_dir = os.path.join(parent_dir, agent)
        if not os.path.exists(agent_dir):
            log("orchestrator", f"Cloning {agent} from existing repo...", style="cyan")
            with pushd(parent_dir):
                run_cmd(["git", "clone", clone_source, agent])
    write_workspace_readme(parent_dir)
```

**Change `_pull_all_clones`:**

```python
def _pull_all_clones(parent_dir: str, num_builders: int = 1) -> None:
    clone_source = _detect_clone_source(parent_dir)
    agents = [f"builder-{i}" for i in range(1, num_builders + 1)] + ["reviewer", "tester", "validator"]
    for agent in agents:
        # ... same logic as today but with dynamic agent list
```

**Rewrite `_launch_agents_and_build`:**

```python
def _launch_agents_and_build(
    parent_dir: str, plan_label: str, project_name: str = "",
    requirements_changed: bool = False, num_builders: int = 1,
) -> None:
    clear_builder_done(num_builders)

    # --- Initial planning (runs once, from builder-1) ---
    plan_ok = plan(requirements_changed=requirements_changed)
    if not plan_ok:
        log("orchestrator", "Planner failed — aborting.", style="bold red")
        return
    check_milestone_sizes()
    _generate_copilot_instructions()

    # --- Spawn downstream agents ---
    spawn_agent_in_terminal(os.path.join(parent_dir, "reviewer"), "commitwatch")
    spawn_agent_in_terminal(os.path.join(parent_dir, "tester"), "testloop")
    validator_cmd = f"validateloop --project-name {project_name}" if project_name else "validateloop"
    spawn_agent_in_terminal(os.path.join(parent_dir, "validator"), validator_cmd)

    # --- Spawn builders ---
    for i in range(1, num_builders + 1):
        builder_dir = os.path.join(parent_dir, f"builder-{i}")
        builder_cmd = f"build --loop --builder-id {i}"
        log("orchestrator", f"Launching builder-{i}...", style="yellow")
        spawn_agent_in_terminal(builder_dir, builder_cmd)

    # --- Poll for completion ---
    log("orchestrator", "All agents launched! Waiting for builders to complete...", style="bold green")
    _wait_for_builders()
```

**New function — `_wait_for_builders`:**

```python
def _wait_for_builders() -> None:
    """Block until all builders have finished (or stale-log timeout)."""
    while True:
        if is_builder_done():
            log("orchestrator", "All builders done. Run complete.", style="bold green")
            return
        time.sleep(15)
```

**Change CWD handling:**

Current code does `os.chdir(os.path.join(parent_dir, "builder"))` at L207 and L270. Change to `os.chdir(os.path.join(parent_dir, "builder-1"))` — the initial planning runs from builder-1's clone.

In `_bootstrap_new_project`, the bootstrap currently creates `builder/` directory. This needs to change to create `builder-1/` (or the bootstrap prompt creates `builder/` and we rename it). Simplest approach: let bootstrap create `builder/` as before, then rename it to `builder-1/` after bootstrap completes, before cloning other agents.

**Bootstrap handling:**

In `_bootstrap_new_project` at L194, after bootstrap creates `builder/`:
```python
# Rename builder/ to builder-1/ for consistency
builder_old = os.path.join(parent_dir, "builder")
builder_new = os.path.join(parent_dir, "builder-1")
if os.path.exists(builder_old) and not os.path.exists(builder_new):
    os.rename(builder_old, builder_new)
```

Then `_clone_all_agents` creates `builder-2..N` by cloning from the repo.

**Resume handling for existing `builder/` directory:**

When resuming a project that was previously built with the old single-builder layout (has `builder/` instead of `builder-1/`), the orchestrator needs to handle migration:

```python
# In _resume_existing_project or _pull_all_clones:
builder_old = os.path.join(parent_dir, "builder")
builder_new = os.path.join(parent_dir, "builder-1")
if os.path.exists(builder_old) and not os.path.exists(builder_new):
    os.rename(builder_old, builder_new)
```

This handles the case where a user starts with `--builders 1` (or the old code), then later resumes with `--builders 2`. The existing `builder/` clone becomes `builder-1/` and `builder-2/` is cloned fresh.

#### cli.py changes

The `build` command defined in builder.py with `@app.command()` already auto-registers via `builder.register(app)`. The `--builder-id` option just needs to be added to the `build()` function signature with a typer.Option annotation. No cli.py changes needed for the build command.

**`status` command (Lines 92-99):** Currently reads TASKS.md to display milestone progress. Change to:
- Read `milestones/` directory using `get_all_milestones()` from milestone.py
- Display each milestone file's progress (done/total tasks)
- Fall back message: "No milestones/ directory yet. Run 'plan' to generate it."

#### backlog_checker.py changes

`backlog_checker.py` has 7 references to TASKS.md. The main change:

- `check_first_milestone_structure()` (Line 183): Currently reads TASKS.md and validates the first milestone's structure. Change to read from `milestones/` directory — find the first (alphabetically) milestone file and validate its structure.
- `check_backlog_quality()` (Line 479): Currently reads TASKS.md via `_read_file_safe("TASKS.md")`. Change to read milestone files from `milestones/` directory.
- Update all error messages from "TASKS.md" to "milestones/".

#### Prompt changes for downstream agents

**prompts/reviewer.py** — 4 occurrences of "TASKS.md":
- Lines 115, 135, 162, 192: "Read SPEC.md and TASKS.md" → "Read SPEC.md and the milestone files in `milestones/`"
- These appear in REVIEWER_COMMIT_PROMPT, REVIEWER_BATCH_PROMPT, and REVIEWER_MILESTONE_PROMPT.

**prompts/tester.py** — 2 occurrences:
- Lines 4, 42: "Read SPEC.md and TASKS.md to understand the project" → "Read SPEC.md and the milestone files in `milestones/` to understand the project"
- These appear in TESTER_MILESTONE_PROMPT.

**prompts/validator.py** — 2 occurrences:
- Line 70: "Read TASKS.md to see which milestones are complete" → "Read the milestone files in `milestones/` to see which milestones are complete"
- Line 73: "Each milestone in TASKS.md has a `> **Validates:**` blockquote" → "Each milestone file in `milestones/` has a `> **Validates:**` blockquote"

#### Downstream agent verification

**watcher.py:** Uses `is_builder_done()` at Lines 316 and passim. Since we changed `is_builder_done()` to check all builder sentinels, no code changes needed. Just verify the watcher starts up, polls, and shuts down correctly.

**tester.py:** Same — uses `is_builder_done()` at Line 108. No changes needed.

**validator.py:** Same — uses `is_builder_done()` at its poll loop. No changes needed.

These agents discover milestones from `milestones.log` (via `load_milestone_boundaries`) which is written by the builder's `record_milestone_boundary()` call. Multiple builders each write to `milestones.log` — this is safe because:
1. Writes are single-line appends (atomic under POSIX for < 4KB)
2. Each builder completes milestones at different times (minutes apart)
3. Even without atomicity, the worst case is interleaved partial lines, which `parse_milestone_log` already handles by skipping lines that don't have exactly 3 `|`-separated parts

#### Test harness changes

**run_test.sh** — Add `--builders` flag:

```bash
# Parse --builders N
BUILDERS=1
while [[ $# -gt 0 ]]; do
    case $1 in
        --builders) BUILDERS="$2"; shift 2;;
        ...
    esac
done

# Pass to go command
agentic-dev go ... --builders "$BUILDERS"
```

**run_test.py** if it exists — add `--builders` argument passthrough.

#### AGENTS.md updates

Update these sections:
- **Builder** — describe the claim loop, `--builder-id`, milestone file ownership
- **Planner** — describe milestone file output, `{story_name}` parameter
- **Orchestrator** — describe `--builders N`, multi-builder launching, poll-for-done
- **Shutdown Protocol** — describe multi-builder sentinel detection
- **Agent Coordination Rules** — mention milestone file ownership, BACKLOG.md claim protocol
- **Iterative Development** — no fundamental changes, just mention `--builders`

---

## Current Data Flow (Single Builder)

```
go() → plan() → spawn reviewer/tester/validator → build(loop=True)  [blocking]
                                                        │
                                                        ▼
                                             ┌──── build loop ────┐
                                             │  detect progress   │
                                             │  run_copilot()     │
                                             │  record milestone  │──→ milestones.log
                                             │  plan() [inline]   │
                                             │  repeat            │
                                             └───────────────────┘
                                                        │
                                             write builder.done
                                                        │
                                      reviewer/tester/validator see → exit
```

## Target Data Flow (Multi-Builder)

```
go() → plan() [backlog only] → spawn reviewer/tester/validator
                              → spawn builder-1..N
                              → poll for builder-*.done

     ┌──── builder-1 ────┐  ┌──── builder-2 ────┐  ┌──── builder-N ────┐
     │ claim story [~]  │  │ claim story [~]  │  │ claim story [~]  │
     │ plan() [milestone]│  │ plan() [milestone]│  │ plan() [milestone]│
     │ run_copilot()     │  │ run_copilot()     │  │ run_copilot()     │
     │ record milestone  │  │ record milestone  │  │ record milestone  │
     │ complete story [x]│  │ complete story [x]│  │ complete story [x]│
     │ loop or done      │  │ loop or done      │  │ loop or done      │
     └──────────────────┘  └──────────────────┘  └──────────────────┘
            │                       │                       │
    builder-1.done          builder-2.done          builder-N.done
            └───────────────────────┼───────────────────────┘
                                    │
                      is_builder_done() returns True
                                    │
                      reviewer/tester/validator exit
```

## Conflict Risks and Mitigations

| Resource | Risk | Mitigation |
|---|---|---|
| BACKLOG.md claims | Two builders claim same story | Git push rejects loser. Loser pulls (winner's `[~]` arrives), claims next. |
| BACKLOG.md completions | Two builders mark different stories `[x]` | Different lines — git rebase handles cleanly |
| BACKLOG.md dependency race | Downstream story eligible before upstream built | Three-state prevents this: `[~]` (claimed) does NOT satisfy deps, only `[x]` (completed) does |
| Source files (DI wiring, routes) | Two builders touch same file for different features | Rebase-retry with increased attempts (5 instead of 3). Different-line edits merge. Same-line edits fail after retries — builder logs error and stops. |
| Milestone files | Two builders edit same file | Impossible — each builder exclusively owns its milestone file |
| milestones.log | Concurrent appends | POSIX atomic write for < 4KB lines. Worst case: parser skips malformed lines |
| reviews/, bugs/ | Concurrent new files | Already append-only. New files with different timestamps never conflict |
| builder-N.done | Concurrent writes | Each builder writes its own file — no shared writes |

## File Reference: What Each File Contains Today

These are the key files with current line counts and import structures. Use this as a reference when making changes.

| File | Lines | Key Imports |
|---|---|---|
| builder.py | 537 | milestone.{get_completed_milestones, get_current_milestone_progress, ...}, sentinel.write_builder_done, utils.{log, run_copilot, run_cmd}, planner.{plan, check_milestone_sizes}, prompts.BUILDER_PROMPT |
| planner.py | 128 | milestone.get_tasks_per_milestone, prompts.{PLANNER_*}, utils.{log, run_copilot}, backlog_checker.{check_backlog_quality, run_ordering_check} |
| orchestrator.py | 317 | planner.{plan, check_milestone_sizes}, builder.build, sentinel.clear_builder_done, terminal.spawn_agent_in_terminal, utils.{log, run_cmd, pushd} |
| milestone.py | 318 | utils.{resolve_logs_dir, run_cmd} |
| sentinel.py | 147 | utils.resolve_logs_dir |
| utils.py | 326 | (no internal deps) |
| git_helpers.py | 116 | utils.{log, run_cmd} |
| terminal.py | 100 | utils.{check_command, console, is_macos, is_windows} |
| cli.py | 124 | utils.console, milestone.{parse_milestones_from_text} |
| backlog_checker.py | ~500 | milestone.{parse_milestones_from_text, parse_backlog}, utils.{log, run_copilot}, prompts.BACKLOG_QUALITY_PROMPT |
| watcher.py | 341 | milestone.{load_milestone_boundaries, load_reviewed_milestones, save_milestone_checkpoint, find_unreviewed_milestones}, sentinel.is_builder_done, git_helpers.git_push_with_retry, prompts.REVIEWER_* |
| tester.py | 123 | milestone.{load_milestone_boundaries, load_reviewed_milestones, save_milestone_checkpoint}, sentinel.is_builder_done, prompts.TESTER_MILESTONE_PROMPT |
| validator.py | 332 | milestone.{load_milestone_boundaries, load_reviewed_milestones, save_milestone_checkpoint}, sentinel.is_builder_done, prompts.VALIDATOR_MILESTONE_PROMPT |
| prompts/builder.py | 83 | (constant only) |
| prompts/planner.py | 307 | (constants only) |
| prompts/reviewer.py | ~200 | (constants only) — 4 TASKS.md refs to update |
| prompts/tester.py | ~50 | (constants only) — 2 TASKS.md refs to update |
| prompts/validator.py | ~120 | (constants only) — 2 TASKS.md refs to update |
| prompts/copilot_instructions.py | 133 | (constants only) — 3 TASKS.md refs to update |

## Known Limitations

**Stale claim recovery:** If a builder crashes after claiming a story (`[~]`) but before completing it (`[x]`), that story is stuck — no other builder will claim it and the crashed builder won't finish it. On re-run, the user must manually reset the stuck story from `[~]` to `[ ]` in BACKLOG.md. A future improvement could have the orchestrator detect and reset stale claims at startup.

---

## Testing Strategy

### Existing tests to preserve
- `test_milestone.py` — all TASKS.md parsing tests (backward compat)
- `test_builder.py` — `classify_remaining_work`, `check_agent_idle`, `check_builder_done_status` pure function tests
- `test_utils.py` — `is_coordination_only_files`, `is_reviewer_only_files` tests
- `test_prompts.py` — prompt format string tests

### New pure functions to test
- `mark_story_claimed(content, story_number)` — writes `[~]` for claimed story
- `mark_story_completed_text(content, story_number)` — writes `[x]` for completed story
- `parse_backlog` with three states — `[ ]`, `[~]`, `[x]` all recognized, `status` field returned
- `get_next_eligible_story` with three states — skips `[~]` and `[x]`, deps require `[x]`
- `parse_milestone_file(path)` — single file parsing
- `list_milestone_files(dir)` — directory listing
- `get_all_milestones(dir)` — multi-file aggregation
- `check_all_builders_done_status(...)` — multi-builder sentinel logic
- `find_project_root("builder-3")` — builder-N recognition

### Tests that need updating
- `parse_backlog` tests — add `[~]` cases, verify `status` field
- `get_next_eligible_story` tests — verify `[~]` deps do not satisfy, `[x]` deps do
- Anything testing `is_coordination_only_files` — add milestones/*.md cases
- Anything testing `is_builder_done` or `check_builder_done_status` — multi-builder sentinel
