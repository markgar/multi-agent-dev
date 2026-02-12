# Code Review Tasks

Actionable items from the Copilot-friendly code guidelines analysis.

---

## Medium Priority

- [x] **Split `run_copilot()` into sub-functions** — `src/agent/utils.py` (lines 59–111, 52 lines)
  - Guideline: #2 Small, single-purpose functions
  - Extract `_write_log_header()`, `_stream_process_output()`, `_write_log_footer()` from the monolithic function.

- [x] **Extract shared launch logic from `go()` and `resume()`** — `src/agent/cli.py` (lines 92–186)
  - Guideline: #2 Small functions, #5 Consistent patterns
  - Both commands duplicate ~20 lines of watcher/tester spawning and build invocation. Extract into a `_launch_watchers_and_build()` helper.

- [x] **Split `_review_new_commits()` into smaller pieces** — `src/agent/watcher.py` (lines 118–165, 47 lines)
  - Guideline: #2 Small functions
  - The commit skip logic (merge check, reviewer-only check) could be a separate `_should_skip_commit()` helper.

## Low Priority

- [x] **Add try/except to `spawn_agent_in_terminal()`** — `src/agent/terminal.py` (lines 14–46)
  - Guideline: #8 Graceful error handling
  - Subprocess calls (`osascript`, `gnome-terminal`, `xterm`) are not wrapped. An unhandled exception here could crash the orchestrator.

- [x] **Separate legacy watcher commands from active code** — `src/agent/watcher.py` (lines 37–76)
  - Guideline: #10 One concept per file
  - `_watch_loop`, `reviewoncommit`, and `testoncommit` are deprecated legacy commands mixed in with the active `commitwatch` system. Move to a separate file or remove entirely.
