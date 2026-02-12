# Refactor Tasks: Copilot-Friendly Code Guidelines

These tasks bring the codebase into alignment with the guidelines in `.github/copilot-instructions.md`. Each task is independent and can be completed one at a time.

---

## 1. Move lazy imports to module level

**Files:** `src/agent/utils.py`, `src/agent/cli.py`

`import time` appears inside `git_push_with_retry()` conditionals. `from datetime import datetime` is duplicated inside `_watch_loop()`, `commitwatch()`, and `testloop()`. Move all imports to the top of each file.

**Why:** Copilot expects imports at the top of the file. Hidden imports make dependencies invisible.

---

## 2. Deduplicate milestone parsing in `utils.py`

**File:** `src/agent/utils.py`

Three functions — `get_completed_milestones()`, `get_current_milestone_progress()`, `get_tasks_per_milestone()` — each independently parse TASKS.md with the same regex loop, just returning different shapes. Extract a shared `_parse_milestones()` helper that returns all the data, then have each public function filter/transform the result.

**Why:** Violates "consistent patterns." Three copies of the same loop are a maintenance hazard and confuse Copilot about which is canonical.

---

## 3. Split `cli.py` into focused modules

**File:** `src/agent/cli.py` (970 lines → multiple files)

Break `cli.py` into separate modules, each owning one concern:

| New file | Responsibility | Functions moved |
|---|---|---|
| `src/agent/cli.py` | App definition, `status`, `go`, `resume` (top-level orchestration) | `app`, `status()`, `go()`, `resume()` |
| `src/agent/bootstrap.py` | Project scaffolding | `_bootstrap()` |
| `src/agent/builder.py` | Build loop | `build()`, `_check_milestone_sizes()` |
| `src/agent/watcher.py` | Commit watching and review dispatching | `commitwatch()`, `_watch_loop()`, `reviewoncommit()`, `testoncommit()` |
| `src/agent/tester.py` | Test loop | `testloop()` |
| `src/agent/terminal.py` | Terminal spawning helpers | `_spawn_agent_in_terminal()` |

Each new module registers its commands on the shared `app` from `cli.py`. Import structure stays flat.

**Why:** 970 lines in one file violates "one concept per file" and "small functions." Copilot's context window is more effective with smaller files.

---

## 4. Break down `build()` into smaller functions

**File:** `src/agent/builder.py` (after task 3)

`build()` is ~200 lines with deep nesting. Extract:
- `_run_single_build_cycle()` — the inner while-loop body
- `_detect_milestone_progress()` — the retry/re-plan decision logic
- `_record_completed_milestones()` — the post-build milestone boundary recording
- `_wait_for_reviewer_drain()` — the 2-minute reviewer drain window
- `_check_remaining_work()` — the end-of-cycle work-remaining check

Each function should be under ~40 lines with a clear name.

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
