# Copilot Instructions

## About this codebase

This software is entirely written by GitHub Copilot. The code is structured to be readable, modifiable, and extendable by Copilot (and other LLM-based agents). Every design decision should reinforce that.

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
- **`build/`** is a stale setuptools artifact. Delete it if present; use `pip install -e .` for development.
- **`pyproject.toml`** defines the package. The project uses a `src/` layout with the package name `agentic_dev`.

## Key files

- `src/agentic_dev/cli.py` — App definition and command registration: `status`.
- `src/agentic_dev/orchestrator.py` — The `go` command: project detection, agent launching, copilot-instructions generation.
- `src/agentic_dev/bootstrap.py` — Project scaffolding: repo creation, cloning reviewer/tester/validator copies.
- `src/agentic_dev/planner.py` — Backlog planner and milestone planner: `plan`, `check_milestone_sizes`.
- `src/agentic_dev/builder.py` — Build loop: milestone completion, retry logic.
- `src/agentic_dev/watcher.py` — Commit watcher: per-commit reviews, milestone-level reviews.
- `src/agentic_dev/tester.py` — Test loop: milestone-triggered testing.
- `src/agentic_dev/validator.py` — Validator loop: milestone-triggered container build and acceptance testing.
- `src/agentic_dev/terminal.py` — Terminal spawning helper for launching agents in new windows.
- `src/agentic_dev/prompts.py` — All LLM prompt templates. Constants only, no logic.
- `src/agentic_dev/utils.py` — Core helpers: logging, command execution, platform detection.
- `src/agentic_dev/git_helpers.py` — Git operations: push with retry, commit classification.
- `src/agentic_dev/sentinel.py` — Builder-done sentinel, agent-idle detection, and reviewer checkpoint persistence.
- `src/agentic_dev/milestone.py` — Milestone parsing, boundary tracking, and per-agent milestone checkpoints.
- `src/agentic_dev/config.py` — Language/stack configurations and prerequisites.
- `src/agentic_dev/legacy_watchers.py` — Deprecated `reviewoncommit` and `testoncommit` commands (not used by `go`).

## Architecture

This is a multi-agent orchestrator that uses GitHub Copilot CLI (`copilot --yolo`) as the execution engine. Agents (builder, planner, reviewer, tester, validator) run as separate processes in separate git clones of the same repo. They coordinate through:

- **Markdown files** (`TASKS.md`, `BUGS.md`, `REVIEWS.md`, `DEPLOY.md`) — shared state via git push/pull.
- **Log files** (`logs/`) — local coordination signals like `builder.done`, `reviewer.checkpoint`, `milestones.log`, `validator.milestone`.

The build loop (Python code in `builder.py`) handles deterministic orchestration — milestone boundary tracking, SHA recording, shutdown signals. The LLM agents handle creative work — writing code, reviewing diffs, writing tests.

## Testing conventions

- **Tests live in `tests/`** mirroring `src/agentic_dev/` — e.g. `tests/test_milestone.py` tests `agentic_dev.milestone`.
- **Use pytest.** No unittest classes. Plain functions with descriptive names.
- **Test the contract, not the implementation.** A test should describe expected behavior in terms a user would understand — not mirror the code's internal branching. If the test would break when you refactor internals without changing behavior, it's too tightly coupled.
- **Name tests as behavioral expectations.** `test_stuck_milestone_stops_after_three_retries` not `test_update_milestone_retry_state_returns_true`. The test name should read like a requirement.
- **Use realistic inputs.** Feed a real-looking TASKS.md with multiple milestones, not a minimal one-line synthetic string. Edge cases should be things that could actually happen — corrupted log lines, empty files, milestones with zero tasks.
- **Prefer regression tests.** When a bug is found, write the test that would have caught it before fixing it. This is the highest-value test you can write.
- **Don't test I/O wrappers.** Functions that just read a file and call a pure helper don't need their own tests — test the pure helper directly. Functions that just call subprocess don't need unit tests — they're validated by integration/end-to-end runs.
- **No mocking unless unavoidable.** The pure functions extracted for testability exist specifically so you don't need mocks. If you find yourself mocking, consider whether you should be testing a different function.

## Test harness (end-to-end runs)

A test harness at `tests/harness/run_test.sh` runs the full orchestration end-to-end using `--local` mode (local bare git repo, no GitHub). It handles all setup automatically.

### Running the harness

```bash
# Default: sample CLI calculator spec
./tests/harness/run_test.sh

# Custom spec
./tests/harness/run_test.sh --name hello-world --spec-file /path/to/spec.md
```

### What it does (in order)

1. Removes stale `build/` directory if present
2. Runs `pip install -e .` to install the latest source
3. Runs `pytest tests/` to catch regressions before starting
4. Creates a timestamped run directory at `tests/harness/runs/<timestamp>/`
5. Launches `agentic-dev go --local` with the given spec, language, and project name
6. Prints log locations when the run completes

### Output structure

```
tests/harness/runs/<timestamp>/
└── <project-name>/
    ├── remote.git/       ← local bare repo (replaces GitHub)
    ├── builder/          ← builder clone
    ├── reviewer/         ← reviewer clone (commitwatch terminal)
    ├── tester/           ← tester clone (testloop terminal)
    ├── validator/        ← validator clone (validateloop terminal)
    └── logs/             ← all logs for post-mortem analysis
```

### Key files for analysis

- `logs/builder.log` — every copilot invocation, prompts and output
- `logs/planner.log` — planner decisions and task list changes
- `logs/reviewer.log` — per-commit and milestone reviews
- `logs/tester.log` — test runs and bug reports
- `logs/validator.log` — container builds and acceptance test results
- `logs/validation-*.txt` — per-milestone PASS/FAIL test results from the validator
- `logs/milestones.log` — milestone boundaries (name|start_sha|end_sha)
- `logs/orchestrator.log` — high-level orchestration status

### Options

| Flag | Default | Description |
|---|---|---|
| `--name` | `test-run` | Project name (directory name) |
| `--spec-file` | `tests/harness/sample_spec_cli_calculator.md` | Path to requirements spec |
| `--resume` | `false` | Find the latest run with the given `--name`, delete agent clone directories, and resume from the repo |

### Resuming a run

```bash
# Resume with new requirements
./tests/harness/run_test.sh --name hello-world --spec-file new-features.md --resume

# Resume without new requirements
./tests/harness/run_test.sh --name hello-world --resume
```

On resume, the harness deletes `builder/`, `reviewer/`, `tester/`, `validator/` and keeps `remote.git/` and `logs/` intact. This simulates a fresh-machine resume where only the repo exists — matching production behavior against GitHub. `go` detects the existing repo, clones all agent directories from it, and continues.

### Sample spec

Sample specs are included in `tests/harness/`:
- `sample_spec_cli_calculator.md` — simple CLI calculator (single file, no dependencies)
- `sample_spec_bookstore_api.md` — REST API with CRUD, validation, and tests

Create your own spec files for different test scenarios.

### Running the harness with Copilot monitoring

When a user asks Copilot to help run the test harness, **do not run it in a background terminal**. Instead:

1. **Have the user run it themselves** in a visible terminal so they can watch the builder's Copilot output stream in real-time:
   ```bash
   ./tests/harness/run_test.sh
   ```
2. **Monitor progress by reading log files** in the latest run directory (`tests/harness/runs/<timestamp>/`). The logs capture everything — full prompts, output, diffs, commands, and costs.
3. **Check on demand** when the user asks "what's the builder doing?" or "how far along is it?" by reading `logs/builder.log`, `logs/orchestrator.log`, `logs/reviewer.log`, and `logs/tester.log`.

This gives the user visibility into the live Copilot session while Copilot retains full access to progress and results via the persistent logs.

## Conventions

- Agent prompts are append-only format strings in `prompts.py`. Use `.format()` for interpolation.
- All file I/O helpers in `utils.py` wrap operations in try/except and never crash the workflow over I/O errors.
- `resolve_logs_dir()` finds the project-root `logs/` directory regardless of which clone (builder/reviewer/tester/validator) the code is running in.
