# Refactor Tasks: Copilot-Friendly Code Guidelines

These tasks bring the codebase into alignment with the guidelines in `.github/copilot-instructions.md`. Each task is independent and can be completed one at a time.

---

## 1. ~~Move lazy imports to module level~~ ✅ Done

**Files:** `src/agent/utils.py`, `src/agent/cli.py`

`import time` appears inside `git_push_with_retry()` conditionals. `from datetime import datetime` is duplicated inside `_watch_loop()`, `commitwatch()`, and `testloop()`. Move all imports to the top of each file.

**Why:** Copilot expects imports at the top of the file. Hidden imports make dependencies invisible.

---

## 2. ~~Deduplicate milestone parsing in `utils.py`~~ ✅ Done

**File:** `src/agent/utils.py`

Three functions — `get_completed_milestones()`, `get_current_milestone_progress()`, `get_tasks_per_milestone()` — each independently parse TASKS.md with the same regex loop, just returning different shapes. Extract a shared `_parse_milestones()` helper that returns all the data, then have each public function filter/transform the result.

**Why:** Violates "consistent patterns." Three copies of the same loop are a maintenance hazard and confuse Copilot about which is canonical.

---

## 3. ~~Split `cli.py` into focused modules~~ ✅ Done

**File:** `src/agent/cli.py` (964 lines → 205 lines + 4 modules)

Broke `cli.py` into separate modules, each owning one concern.

### 3a. ~~Extract `terminal.py`~~ ✅ Done

- [x] Move `_spawn_agent_in_terminal()` into `src/agent/terminal.py` (renamed to `spawn_agent_in_terminal`)
- [x] Update imports in `cli.py`

### 3b. ~~Extract `bootstrap.py`~~ ✅ Done

- [x] Move `bootstrap()` and `_bootstrap()` into `src/agent/bootstrap.py` (renamed to `run_bootstrap`)
- [x] Register the command on the shared `app`
- [x] Update imports in `cli.py`

### 3c. ~~Extract `builder.py`~~ ✅ Done

- [x] Move `build()` and `_check_milestone_sizes()` into `src/agent/builder.py` (renamed to `check_milestone_sizes`)
- [x] Register the command on the shared `app`
- [x] Update imports in `cli.py`

### 3d. ~~Extract `watcher.py`~~ ✅ Done

- [x] Move `commitwatch()`, `_watch_loop()`, `reviewoncommit()`, `testoncommit()` into `src/agent/watcher.py`
- [x] Register commands on the shared `app`
- [x] Update imports in `cli.py`

### 3e. ~~Extract `tester.py`~~ ✅ Done

- [x] Move `testloop()` into `src/agent/tester.py`
- [x] Register the command on the shared `app`
- [x] Update imports in `cli.py`

**Result:** `cli.py` is now 205 lines (`app`, `status`, `plan`, `go`, `resume` + registration).

**Why:** 970 lines in one file violates "one concept per file" and "small functions." Copilot's context window is more effective with smaller files.

---

## 4. ~~Break down `build()` into smaller functions~~ ✅ Done

**File:** `src/agent/builder.py`

`build()` is ~180 lines (lines 70–245) with a `while True` loop that mixes 6 concerns: stuck-milestone detection, re-planning, running the builder, milestone boundary recording, reviewer drain, and remaining-work checks. Max nesting depth is 4 levels. Six mutable local variables are shared across the loop body. Four separate `write_builder_done()` exit paths must be preserved.

### 4a. ~~Add a `BuildState` dataclass~~ ✅ Done

- [x] Add `@dataclass class BuildState` at module level (after imports) with fields: `cycle_count: int`, `no_work_count: int`, `last_milestone_name: str | None`, `milestone_retry_count: int`, `last_milestone_done_count: int`
- [x] Replace the 6 scattered local variables in `build()` with a single `state = BuildState(...)` instance

### 4b. ~~Extract `_detect_milestone_progress(state, loop) → bool`~~ ✅ Done

- [x] Move the "same milestone vs new milestone" branching into `_detect_milestone_progress()`
- [x] Include the lazy `from agent.cli import plan` import inside this function (avoids circular import)
- [x] Return `False` when milestone is stuck beyond `_MAX_MILESTONE_RETRIES` (caller writes sentinel and returns)
- [x] Mutate `state` fields for retry tracking and milestone name updates
- [x] Target: ~35 lines

### 4c. ~~Extract `_record_completed_milestones(milestones_before) → tuple[set, str, set]`~~ ✅ Done

- [x] Move `git pull --rebase`, post-build milestone snapshot, `newly_completed` set diff, and `record_milestone_boundary()` calls into this function
- [x] Return `(milestones_after, head_after, newly_completed)`
- [x] Keep the git pull inside this function to preserve the ordering guarantee (pull before snapshot)
- [x] Target: ~25 lines

### 4d. ~~Extract `_wait_for_reviewer_drain(head_after)`~~ ✅ Done

- [x] Move the 2-minute reviewer polling loop into this function
- [x] Preserve the `while/else` pattern exactly (the `else` clause fires when drain expires without reviewer catching up)
- [x] Pure side-effect function (logging + sleep)
- [x] Target: ~20 lines

### 4e. ~~Extract `_check_remaining_work(state) → str`~~ ✅ Done

- [x] Move the `has_unchecked_items()` checks and no-work/idle logic into this function
- [x] Return signal string: `"done"` (all work complete), `"idle"` (no work found, keep waiting), or `"continue"` (more work, loop)
- [x] Mutate `state.no_work_count`; handle the 3-check threshold and 60s wait internally
- [x] Target: ~30 lines

### 4f. ~~Rewrite `build()` as a compact orchestration loop~~ ✅ Done

- [x] Reduce `build()` to ~50 lines: guard, `BuildState` init, and a `while True` that calls the 4 helpers in sequence
- [x] Preserve all 4 `write_builder_done()` exit paths: (1) no TASKS.md, (2) stuck milestone, (3) builder failure, (4) all-done / single-run exit

### 4g. ~~Clean up unused imports~~ ✅ Done

- [x] Remove `git_push_with_retry` and `is_builder_done` from the import list — they are imported but never used in this file

### Verification

- [x] `python -c "from agent.builder import build, check_milestone_sizes"` succeeds
- [x] `python -c "from agent.cli import app"` succeeds (no circular imports)
- [x] `python -m agent build --help` shows correct CLI registration
- [x] Grep confirms `write_builder_done()` calls are preserved (5 calls across 4 exit paths)
- [x] Run existing tests if any (`pytest`) — 0 collected, no failures

**Why:** Violates "small, single-purpose functions." The current function is hard to follow and hard for Copilot to modify safely.

---

## 5. Break down `commitwatch()` into smaller functions

**File:** `src/agent/watcher.py` (after task 3)

`commitwatch()` is ~150 lines. Extract:
- `_initialize_watcher_checkpoint()` — the startup checkpoint logic
- `_review_new_commits()` — the per-commit review loop
- `_check_milestone_reviews()` — the milestone review trigger logic

**Why:** Same rationale as task 4.

---

## 6. Break down `_bootstrap()` into smaller functions

**File:** `src/agent/bootstrap.py` (after task 3)

`_bootstrap()` is ~100 lines. Extract:
- `_resolve_description()` — spec-file vs description handling
- `_check_prerequisites()` — tool/auth prerequisite checks
- `_scaffold_project()` — the actual repo creation and cloning

**Why:** Same rationale as task 4.

---

## 7. Replace section-separator comments with module boundaries

**File:** `src/agent/utils.py`

The `# ============================================` separation comments become unnecessary once related groups of functions live in their own modules (or at least their own clearly-named sections). After task 2, review whether `utils.py` itself should be split (e.g., `git_helpers.py` for git operations, `sentinel.py` for builder-done/checkpoint logic, `milestone.py` for milestone parsing).

**Why:** "Descriptive naming over comments." Module boundaries are more informative than comment banners.

---

## Order of execution

Tasks 1 and 2 are standalone and safe to do first. Task 3 is the big structural change. Tasks 4–6 depend on task 3. Task 7 is a cleanup pass at the end.

Recommended order: **1 → 2 → 3 → 4 → 5 → 6 → 7**
