# Usage

## One Command

```bash
agentic-dev go --directory my-project --model gpt-5.3-codex \
  --description "description of what to build"
```

Or use a requirements file:

```bash
agentic-dev go --directory my-project --model gpt-5.3-codex --spec-file requirements.md
```

Or run without GitHub (local bare git repo):

```bash
agentic-dev go --directory my-project --model gpt-5.3-codex --description "..." --local
```

## Continuing with New Requirements

Come back later and add new features to the same project:

```bash
agentic-dev go --directory my-project --model gpt-5.3-codex --spec-file new-features.md
```

The planner detects what's already built, updates the spec, adds new stories to the backlog, and plans the next milestone.

## Resuming Where You Left Off

```bash
agentic-dev go --directory my-project --model gpt-5.3-codex
```

No spec needed — just re-evaluates the plan and continues building.

## Resuming from a Different Location

Point `--directory` at any existing project directory:

```bash
agentic-dev go --directory /path/to/runs/20260213/my-app --model gpt-5.3-codex --local
```

`go` detects the existing repo (locally via `remote.git/`, or on GitHub via `gh repo view`) and automatically clones any missing agent directories. You can resume on a fresh machine with nothing but the repo.

## Running Agents Individually

After `go` has created a project, you can run individual agents if needed:

```bash
cd my-project/builder
agentic-dev plan
agentic-dev build
agentic-dev build --loop

cd ../reviewer
agentic-dev commitwatch

cd ../tester
agentic-dev testloop

cd ../validator
agentic-dev validateloop
```

> **Note:** Always use `go` for new projects — it runs bootstrap, plan, and launches all agents automatically. Do not run `bootstrap` directly.

## Commands Reference

| Command | What it does | Where |
|---|---|---|
| `go --directory D --model M --description DESC` | Does everything: bootstrap, plan, launch agents, build | Once, from anywhere |
| `go --directory D --model M --spec-file F` | Same, but reads requirements from a markdown file | Once, from anywhere |
| `go --directory D --model M ... --local` | Same, but uses a local bare git repo instead of GitHub | Once, from anywhere |
| `go --directory D --model M ... --name N` | Same, but overrides the GitHub repo name (defaults to dirname) | Once, from anywhere |
| `go --directory D --model M --spec-file F` (existing) | Updates requirements, re-plans, launches agents, builds | From anywhere |
| `go --directory D --model M` (existing) | Re-plans, launches agents, resumes building | From anywhere |
| `plan` | Creates or updates BACKLOG.md and TASKS.md (one milestone at a time) | builder/, on demand |
| `build` | Fixes bugs + reviews, then completes the current milestone | builder/, repeatedly |
| `build --loop` | Loops through all milestones automatically (re-plans between each from backlog) | builder/, once |
| `commitwatch` | Polls for commits, reviews each one + milestone-level reviews | reviewer/, once |
| `testloop` | Watches for completed milestones, runs scoped tests | tester/, once |
| `validateloop` | Watches for completed milestones, builds containers, validates against spec | validator/, once |
| `reviewoncommit` | Legacy: watches for commits, reviews code quality | reviewer/, once |
| `testoncommit` | Legacy: watches for commits, runs tests, files bugs | tester/, once |
| `status` | Shows spec, tasks, reviews, and bugs at a glance | Any clone, anytime |

## About `--yolo` Mode

The GitHub Copilot CLI `--yolo` flag auto-approves every action without asking for confirmation. GitHub Copilot will create files, run commands, modify code, and push to GitHub without pausing. This is what makes the autonomous workflow possible, but it means you're trusting GitHub Copilot to do the right thing. Review the commits afterward.

## Logging

Every agent invocation is logged to an append-only file in a `logs/` directory at the project root (sibling of `builder/`, `reviewer/`, `tester/`). All console output — including status messages, warnings, and GitHub Copilot output — is duplicated to the appropriate log file.

```
myproject/
  remote.git/    ← local bare repo (only with --local)
  builder/       ← git clone
  reviewer/      ← git clone
  tester/        ← git clone
  validator/     ← git clone
  logs/          ← all agent logs + coordination signals
    bootstrap.log
    planner.log
    builder.log
    reviewer.log
    tester.log
    validator.log
    validation-*.txt       ← per-milestone PASS/FAIL test results
    orchestrator.log
    builder.done           ← shutdown signal
    reviewer.checkpoint    ← last reviewed commit SHA
    milestones.log         ← milestone SHA boundaries (append-only)
    reviewer.milestone     ← milestones already reviewed
    tester.milestone       ← milestones already tested
    validator.milestone    ← milestones already validated
```

Each log entry includes a timestamp, a prompt preview, the full output, and the exit code. The `logs/` directory is outside the git repos so logs are never committed. The `validation-*.txt` files contain structured PASS/FAIL lines for each test the validator ran per milestone.

To follow a log in real time:

```bash
tail -f logs/builder.log
```

## What Could Go Wrong

| Scenario | What happens | Mitigation |
|---|---|---|
| GitHub Copilot generates bad code | Tests fail, tester files bugs, builder tries to fix them | Review commits periodically — don't let it run unattended forever |
| Both agents edit BUGS.md at the same time | Push fails due to conflict | All prompts include `git pull --rebase` before pushing |
| Tester starts a server and doesn't stop it | Port stays bound, next test run fails | GitHub Copilot is prompted to stop it, but if it doesn't, kill the process manually |
| Validator container won't build | Validator files bug, builder fixes Dockerfile next cycle | Check DEPLOY.md for known issues; ensure Docker is running |
| Orphaned Docker containers | Port conflicts or resource waste | Validator cleans up before/after each run; run `docker ps` to check |
| Bootstrap creates wrong project structure | Tasks reference files that don't exist | Edit SPEC.md to clarify requirements, then run `plan` |
| GitHub Copilot enters an infinite fix loop | Builder and tester keep passing bugs back and forth | Stop all agents, review BUGS.md and the code, fix the root cause |
| Reviewer creates endless review items | Builder fixes reviews, reviewer reviews the fix commits, repeat | The reviewer fixes [doc] issues directly and only files [code] items. Milestone reviews clean up stale/resolved items. The builder caps fix-only cycles and treats remaining reviews as best-effort after bugs and tasks are done. |

## Troubleshooting

| Problem | Fix |
|---|---|
| `gh` not recognized | Close and reopen terminal after install |
| `copilot` not recognized | Install GitHub Copilot CLI and ensure it's on your PATH |
| Agents conflict on files | Make sure each runs in its own clone directory |
| Watchers don't detect commits | Builder must `push`, not just `commit` |
| `ModuleNotFoundError: typer` | Run `pip install .` from the multi-agent-dev directory |
| `agentic-dev` not recognized | Run `pip install .` and reopen your terminal |
| `python3` not found | Install Python 3.8+ and ensure it's on your PATH |
