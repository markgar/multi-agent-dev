# Copilot Instructions

## About this codebase

This software is entirely written by GitHub Copilot. The code is structured to be readable, modifiable, and extendable by Copilot (and other LLM-based agents). Every design decision should reinforce that.

### Meta-context: this project builds other projects

This is a **meta-tool** — a multi-agent orchestrator that creates, plans, builds, reviews, tests, and validates *other* software projects. Almost every reference to project artifacts in the source code refers to files inside **target projects** (the projects this tool generates), not to this project itself.

Key distinctions:

- **`copilot-instructions.md` in the source code** — `_generate_copilot_instructions()`, `COPILOT_INSTRUCTIONS_TEMPLATE`, and prompt references to `.github/copilot-instructions.md` all deal with a file generated *inside target project repos* for the builder agent to follow. They are not self-referential to this file.
- **`SPEC.md`, `BACKLOG.md`, `milestones/`, `DEPLOY.md`, `REVIEW-THEMES.md`** — planning and coordination artifacts that exist *inside target project repos*. This project does not have these files itself.
- **`bugs/`, `reviews/`** — append-only directories created *inside target project clones* for cross-agent communication. They are not part of this project's directory structure.
- **`builder/`, `reviewer/`, `milestone-reviewer/`, `tester/`, `validator/`** — separate git clone directories of the *target project*, one per agent. These are working copies created at runtime, not subdirectories of this project.
- **Prompt templates in `src/agentic_dev/prompts/`** — instructions sent to Copilot CLI agents operating *on the target project*. They reference target-project files and conventions, not this project's internals.

When editing this codebase, keep this two-level structure in mind: the Python code here is orchestration logic; the prompts and templates describe work that happens in a *different* repo.

### Guidelines for Copilot-friendly code

- **Flat, explicit control flow.** Prefer straightforward if/else and early returns over deeply nested logic, complex inheritance hierarchies, or metaprogramming. Every function should be understandable from its source alone.
- **Small, single-purpose functions.** Keep functions short (ideally under ~40 lines). Each function does one thing with a clear name that describes it. This gives Copilot better context boundaries.
- **Descriptive naming over comments.** Variable and function names should make intent obvious. Use comments only when *why* isn't clear from the code — never to explain *what*.
- **Colocate related logic.** Keep constants, helpers, and the code that uses them close together (or in the same small file). Avoid scattering related pieces across many modules — Copilot works best when relevant context is nearby.
- **Consistent patterns.** When multiple functions do similar things, structure them identically. Consistent shape lets Copilot reliably extend the pattern.
- **No magic.** Avoid decorators that hide behavior, dynamic attribute access, implicit registration, or monkey-patching. Everything should be traceable by reading the code top-to-bottom.
- **Simple string templates for prompts.** Keep LLM prompts as plain format strings with named placeholders. No template engines, no runtime assembly — just `.format()` or f-strings.
- **Graceful error handling.** Wrap I/O and subprocess calls in try/except. Never let a transient failure crash the orchestration loop. Log the error and continue.
- **Minimal dependencies.** Only add a dependency when it provides substantial value. Fewer deps mean less surface area for Copilot to misunderstand.
- **One concept per file.** Each module owns a single concern. Don't mix unrelated responsibilities in the same file.
- **Design for testability.** Separate pure decision logic from I/O and subprocess calls so core functions can be tested without mocking. Pass dependencies as arguments rather than hard-coding them inside functions when practical. Keep side-effect-free helpers (parsing, validation, data transforms) in their own functions so they can be unit tested directly.

## Project structure

- **Source code lives in `src/agentic_dev/`** — this is the only directory to edit.
- **`tests/`** contains unit tests and the end-to-end test harness (`tests/harness/`).
- **`docs/`** contains rubrics for evaluating planner output quality (`backlog-planner-rubric.md`, `planner-quality-rubric.md`). These are specifications used by the automated backlog checker.
- **`build/`** is a stale setuptools artifact. Delete it if present; use `pip install -e .` for development.
- **`pyproject.toml`** defines the package. The project uses a `src/` layout with the package name `agentic_dev`.

## Key files

- `src/agentic_dev/cli.py` — App definition and command registration: `status`, `--version`.
- `src/agentic_dev/orchestrator.py` — The `go` command: project detection, agent launching, copilot-instructions generation.
- `src/agentic_dev/bootstrap.py` — Project scaffolding: repo creation, cloning reviewer/milestone-reviewer/tester/validator copies.
- `src/agentic_dev/planner.py` — Backlog planner and milestone planner: `plan` command, `check_milestone_sizes()` helper.
- `src/agentic_dev/builder.py` — Build loop: milestone completion, retry logic.
- `src/agentic_dev/watcher.py` — Commit watcher: branch-attached per-builder reviews and legacy main-polling mode.
- `src/agentic_dev/milestone_reviewer.py` — Milestone reviewer: cross-cutting milestone reviews with code analysis and note frequency filtering.
- `src/agentic_dev/tester.py` — Test loop: milestone-triggered testing.
- `src/agentic_dev/validator.py` — Validator loop: milestone-triggered container build and acceptance testing.
- `src/agentic_dev/terminal.py` — Terminal spawning helper for launching agents in new windows.
- `src/agentic_dev/prompts/` — All LLM prompt templates (one file per agent). Constants only, no logic.
- `src/agentic_dev/utils.py` — Core helpers: logging, command execution, platform detection.
- `src/agentic_dev/git_helpers.py` — Git operations: push with retry, commit classification, branch detection.
- `src/agentic_dev/sentinel.py` — Builder-done sentinel, agent-idle detection, per-builder reviewer checkpoints, and branch-review-head merge gate signals.
- `src/agentic_dev/milestone.py` — Milestone parsing, boundary tracking, and per-agent milestone checkpoints.
- `src/agentic_dev/config.py` — Language/stack configurations and thresholds for tree-sitter code analysis.
- `src/agentic_dev/backlog_checker.py` — Backlog quality gate: deterministic structural checks (A1-A4) and LLM quality review (C1-C7) on BACKLOG.md and milestone files. Also runs story ordering checks for parallel builder throughput.
- `src/agentic_dev/code_analysis.py` — Tree-sitter code analysis for target projects: structural checks across Python, JS/TS, and C#. Invoked by the milestone reviewer during milestone reviews.
- `src/agentic_dev/version.py` — Package version and git-based build info for the `--version` flag.
- `src/agentic_dev/legacy_watchers.py` — Deprecated `reviewoncommit` and `testoncommit` commands (not used by `go`).

## Architecture

This is a multi-agent orchestrator that uses GitHub Copilot CLI (`copilot --yolo`) as the execution engine. Agents (builder, planner, commit watcher, milestone reviewer, tester, validator) run as separate processes in separate git clones of the same repo. They coordinate through:

- **Markdown files** (`BACKLOG.md`, `milestones/`, `bugs/`, `reviews/`, `DEPLOY.md`, `REVIEW-THEMES.md`) — shared state via git push/pull.
- **Log files** (`logs/`) — local coordination signals like `builder.done`, `reviewer.checkpoint`, `milestone-reviewer.log`, `milestones.log`, `validator.milestone`.

The build loop (Python code in `builder.py`) handles deterministic orchestration — milestone boundary tracking, SHA recording, shutdown signals. The LLM agents handle creative work — writing code, reviewing diffs, writing tests.

## Testing conventions

- **Tests live in `tests/`** mirroring `src/agentic_dev/` — e.g. `tests/test_milestone.py` tests `agentic_dev.milestone`.
- **Use pytest.** No unittest classes. Plain functions with descriptive names.
- **Test the contract, not the implementation.** A test should describe expected behavior in terms a user would understand — not mirror the code's internal branching. If the test would break when you refactor internals without changing behavior, it's too tightly coupled.
- **Name tests as behavioral expectations.** `test_stuck_milestone_stops_after_three_retries` not `test_update_milestone_retry_state_returns_true`. The test name should read like a requirement.
- **Use realistic inputs.** Feed a real-looking milestone file with multiple tasks, not a minimal one-line synthetic string. Edge cases should be things that could actually happen — corrupted log lines, empty files, milestones with zero tasks.
- **Prefer regression tests.** When a bug is found, write the test that would have caught it before fixing it. This is the highest-value test you can write.
- **Don't test I/O wrappers.** Functions that just read a file and call a pure helper don't need their own tests — test the pure helper directly. Functions that just call subprocess don't need unit tests — they're validated by integration/end-to-end runs.
- **No mocking unless unavoidable.** The pure functions extracted for testability exist specifically so you don't need mocks. If you find yourself mocking, consider whether you should be testing a different function.

## Test harness

End-to-end tests run via `tests/harness/run_test.sh` using `--local` mode. See AGENTS.md § "Test harness" for full options (`--model`, `--name`, `--spec-file`, `--resume`). Run output lands in `tests/harness/runs/<timestamp>/<project-name>/` with subdirectories for each agent clone and a `logs/` directory capturing all prompts, output, and results.

When asked to run or monitor the harness, do NOT run it in a background terminal. Have the user run it in a visible terminal and monitor progress by reading log files (`builder.log`, `orchestrator.log`, `reviewer.log`, `tester.log`) in the run's `logs/` directory.

## Conventions

- Agent prompts are append-only format strings in `prompts/`. Use `.format()` for interpolation.
- All file I/O helpers in `utils.py` wrap operations in try/except and never crash the workflow over I/O errors.
- `resolve_logs_dir()` finds the project-root `logs/` directory regardless of which clone (builder/reviewer/milestone-reviewer/tester/validator) the code is running in.
