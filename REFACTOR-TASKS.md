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

## 5. ~~Break down `commitwatch()` into smaller functions~~ ✅ Done

**File:** `src/agent/watcher.py`

`commitwatch()` is 123 lines (lines 91–267) with max nesting depth of 4 levels. It mixes 3 concerns: checkpoint initialization, per-commit reviewing, and milestone reviewing. Only 1 mutable local (`last_sha`) persists across loop iterations — no dataclass needed (unlike task 4). Two exit paths: (1) `break` when builder done at top of loop, (2) `return` when builder finishes mid-commit-review. Legacy `_watch_loop`, `reviewoncommit`, `testoncommit` are unrelated and stay untouched.

### 5a. ~~Extract `_initialize_watcher_checkpoint() → str`~~ ✅ Done

- [x] Move lines 109–122 into a standalone function
- [x] Handle both "restored from disk" and "first run, seed from HEAD" paths
- [x] Return the initial `last_sha` string
- [x] Target: ~15 lines

### 5b. ~~Extract `_review_new_commits(last_sha, current_head) → bool`~~ ✅ Done

- [x] Move lines 142–220 (the `if current_head != last_sha` block) into a standalone function
- [x] Parameters: `last_sha` (range start), `current_head` (range end)
- [x] Return `True` if builder finished mid-review (caller should `return`), `False` otherwise
- [x] Contains commit enumeration, skip logic (merge/reviewer-only), per-commit reviewer invocation, `git_push_with_retry()`, and checkpoint saves
- [x] Keep `prev` variable local to this function
- [x] Mid-loop `is_builder_done()` → `return True` (caller exits)
- [x] Target: ~55 lines

### 5c. ~~Extract `_check_milestone_reviews() → None`~~ ✅ Done

- [x] Move lines 224–265 into a standalone function
- [x] Pure side-effect: load boundaries, run reviewer for unreviewed milestones, save checkpoints
- [x] No return value — no shutdown signal originates here
- [x] Target: ~25 lines

### 5d. ~~Rewrite `commitwatch()` as compact orchestration loop~~ ✅ Done

- [x] Reduce `commitwatch()` to ~40 lines: guard, chdir, banner, checkpoint init, then `while True` calling helpers in sequence
- [x] Preserve both exit paths: (1) `break` at top of loop when builder done, (2) `return` when `_review_new_commits()` returns `True`
- [x] `last_sha = current_head` update stays in main loop (runs regardless of whether new commits existed)
- [x] Git pull + failure logging (6 lines) stays inline — too small to justify extraction

### Verification

- [x] `python -c "from agent.watcher import commitwatch"` succeeds
- [x] `python -c "from agent.cli import app"` succeeds (no circular imports)
- [x] `python -m agent commitwatch --help` shows correct CLI registration
- [x] Grep confirms both `is_builder_done()` exit paths preserved (1 `break` + 1 `return`)
- [x] Legacy `_watch_loop`, `reviewoncommit`, `testoncommit` unchanged
- [x] `pytest` — no failures

**Why:** Same rationale as task 4.

---

## 6. ~~Break down `run_bootstrap()` into smaller functions~~ ✅ Done

**File:** `src/agent/bootstrap.py`

`run_bootstrap()` is ~115 lines (L54–192) mixing 5 concerns: input resolution, language validation, prerequisite checks, project scaffolding, and repo cloning. Max nesting depth is 3 levels. Only 2 computed values (`description`, `gh_user`) flow between sections — no dataclass needed.

**Key constraint:** `os.chdir()` on L158 is a persistent side effect that the caller `go()` in `cli.py` depends on (it checks for `builder/` at the new cwd). This must be preserved.

### 6a. ~~Extract `_resolve_description(description, spec_file) → str`~~ ✅ Done

- [x] Move lines 62–78 into a standalone function
- [x] Handle mutual exclusion of `--description` and `--spec-file`
- [x] Read and validate spec file contents when `spec_file` is provided
- [x] Raise `typer.Exit(1)` on validation errors (matching existing behavior)
- [x] Return the validated description string
- [x] Target: ~20 lines

### 6b. ~~Extract `_check_prerequisites(language) → str | None`~~ ✅ Done

- [x] Move lines 99–141 into a standalone function
- [x] Include GitHub user lookup (`gh api user`), core tool checks (`git`, `gh`, `copilot`), `gh auth status`, and language-specific prerequisite checks from `LANGUAGE_CONFIGS`
- [x] Return `gh_user` string on success, `None` on any failure
- [x] Print per-tool success/failure messages with platform-specific install instructions
- [x] Target: ~45 lines

### 6c. ~~Extract `_scaffold_project(name, description, gh_user, language) → bool`~~ ✅ Done

- [x] Move lines 147–192 into a standalone function
- [x] Include repo existence check, directory creation, `os.chdir()`, REQUIREMENTS.md writing, Copilot execution, reviewer/tester cloning, success/failure logging
- [x] Preserve the `os.chdir(parent_dir)` side effect so `go()` finds `builder/` at the new cwd
- [x] Return `True` on success, `False` on failure
- [x] Target: ~45 lines

### 6d. ~~Rewrite `run_bootstrap()` as compact orchestration~~ ✅ Done

- [x] Reduce `run_bootstrap()` to ~30 lines: `_resolve_description()` → language validation (5 lines inline) → safety warning for multi-agent-dev dir (10 lines inline, too interactive to extract) → `_check_prerequisites()` → status message (3 lines inline) → `_scaffold_project()`
- [x] Preserve all exit paths: 4 `typer.Exit(1)` raises for input errors + 7 bare `return`s for runtime failures
- [x] Language validation stays inline (raises `typer.Exit(1)`, different exit strategy than bare `return`s in prerequisites)
- [x] Safety warning stays inline (interactive `typer.prompt()`, only 10 lines)

### Verification

- [x] `python -c "from agent.bootstrap import run_bootstrap"` succeeds
- [x] `python -c "from agent.cli import app"` succeeds (no circular imports)
- [x] `python -m agent go --help` shows correct CLI registration
- [x] `pytest` — no failures

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
