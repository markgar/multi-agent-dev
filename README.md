# Multi-Agent Flow

An autonomous development workflow using GitHub Copilot CLI. Four agents collaborate through files in a shared GitHub repo to build projects in **.NET/C#**, **Python**, or **Node.js**:

- **Planner** — creates and updates the task list from the spec
- **Builder** — fixes bugs, addresses review items, builds tasks
- **Reviewer** — watches for commits and reviews code quality
- **Tester** — watches for commits and runs tests, files bugs

## Prerequisites

Install these one time. After each install, **close and reopen your terminal** so the PATH updates.

**Required for all projects:**

| Tool | Install (Windows) | Install (macOS) | Verify |
|---|---|---|---|
| Git | `winget install Git.Git` | `brew install git` (or Xcode CLT) | `git --version` |
| GitHub CLI | `winget install GitHub.cli` | `brew install gh` | `gh auth status` |
| Python 3 | `winget install Python.Python.3.12` | `brew install python` | `python3 --version` |
| GitHub Copilot CLI | See GitHub Copilot CLI docs | See GitHub Copilot CLI docs | `copilot --version` |

**Install for your target language (`--language` option):**

| Language | Tool(s) | Install (Windows) | Install (macOS) |
|---|---|---|---|
| `dotnet` | .NET SDK | `winget install Microsoft.DotNet.SDK.9` | `brew install dotnet` |
| `python` | Python 3 | (already installed above) | (already installed above) |
| `node` | Node.js | `winget install OpenJS.NodeJS.LTS` | `brew install node` |

After installing GitHub CLI, authenticate:

```bash
gh auth login
```

---

## Quick Start

```bash
git clone https://github.com/markgar/multi-agent-dev
cd multi-agent-dev
pip install .
cd ..

agentic-dev go --name "hello-world" --language dotnet --description "a C# console app that prints Hello World"
```

That's it. `go` will:
1. **Bootstrap** — create the project, SPEC.md, git repo, GitHub remote, and three clones (builder/, reviewer/, tester/)
2. **Plan** — generate TASKS.md from the spec
3. **Launch reviewer** — in a new terminal window, watching for commits
4. **Launch tester** — in a new terminal window, watching for commits
5. **Start building** — in your current terminal, looping through tasks

Three windows will be running. Watch the Builder work through tasks while the Reviewer and Tester react to each commit. Run `agentic-dev status` anytime in the builder directory to check progress.

---

## 👋 Hello World

A minimal starter — one file, no dependencies.

**.NET/C#**
```bash
agentic-dev go --name "hello-world" --language dotnet \
  --description "a C# console app that prints Hello World"
```

**Python**
```bash
agentic-dev go --name "hello-world" --language python \
  --description "a Python CLI app that prints Hello World"
```

**Node.js**
```bash
agentic-dev go --name "hello-world" --language node \
  --description "a Node.js CLI app that prints Hello World"
```

---

## 🚀 Simple API

A REST API with CRUD endpoints, a database, and tests.

**.NET/C#**
```bash
agentic-dev go \
  --name "bookstore-api" \
  --language dotnet \
  --description "a C# ASP.NET Core Web API for a bookstore with CRUD endpoints for books (title, author, ISBN, price, genre), an in-memory Entity Framework Core database (UseInMemoryDatabase), and xUnit tests"
```

**Python**
```bash
agentic-dev go \
  --name "bookstore-api" \
  --language python \
  --description "a Python FastAPI REST API for a bookstore with CRUD endpoints for books (title, author, ISBN, price, genre), SQLite with SQLAlchemy, and pytest tests"
```

**Node.js**
```bash
agentic-dev go \
  --name "bookstore-api" \
  --language node \
  --description "a Node.js Express REST API for a bookstore with CRUD endpoints for books (title, author, ISBN, price, genre), SQLite with Sequelize, and Jest tests"
```

---

## 🏗️ Full Stack

A multi-layer application with a web front-end, API, database, and integration tests. These take longer — the Builder scaffolds multiple projects, wires everything together, and builds the UI, all while the Reviewer and Tester provide feedback on each commit.

**.NET/C#**
```bash
agentic-dev go \
  --name "todo-app" \
  --language dotnet \
  --description "a full-stack Todo application using the latest .NET SDK available on this machine. It should have three layers: (1) a Blazor web front-end for managing todos (add, complete, delete, list), (2) an ASP.NET Core Web API middle tier with RESTful endpoints for todos (id, title, isComplete), and (3) an in-memory Entity Framework Core database (UseInMemoryDatabase). Include a shared class library for the Todo model. The solution should use a single .sln file. Add xUnit integration tests that use WebApplicationFactory to test the API endpoints. Seed a few sample todos on startup."
```

**Python**
```bash
agentic-dev go \
  --name "todo-app" \
  --language python \
  --description "a full-stack Todo application with three layers: (1) a FastAPI REST API with RESTful endpoints for todos (id, title, is_complete), (2) a Jinja2-based web front-end served by FastAPI for managing todos (add, complete, delete, list), and (3) a SQLite database with SQLAlchemy ORM. Use Alembic for migrations. Include a Pydantic model for the Todo schema. Add pytest tests using httpx.AsyncClient and TestClient to test the API endpoints. Seed a few sample todos on startup."
```

**Node.js**
```bash
agentic-dev go \
  --name "todo-app" \
  --language node \
  --description "a full-stack Todo application with three layers: (1) an Express REST API with RESTful endpoints for todos (id, title, isComplete), (2) an EJS-based web front-end served by Express for managing todos (add, complete, delete, list), and (3) a SQLite database with Sequelize ORM. Include a Todo model. Add Jest tests using supertest to test the API endpoints. Seed a few sample todos on startup."
```

---

## How It Works

```
Planner ──TASKS.md──→ Builder ──git push──→ Reviewer ──REVIEWS.md──→ Builder
                         ↑                                              
                         │         Builder ──git push──→ Tester
                         │                                  │
                         └──────────── BUGS.md ←────────────┘
```

| From | To | Mechanism | What it says |
|---|---|---|---|
| Bootstrap | Planner | `SPEC.md` | Here's what the project should look like when it's done |
| Planner | Builder | `TASKS.md` | Here's what to do next |
| Builder | Reviewer | `git push` | I finished something, review it |
| Builder | Tester | `git push` | I finished something, test it |
| Reviewer | Builder | `REVIEWS.md` | I found quality issues, address these |
| Tester | Builder | `BUGS.md` | I found test failures, fix these |

### Rules

- The **Planner** runs on demand via `plan`. It reads `SPEC.md`, the codebase, `TASKS.md`, `BUGS.md`, and `REVIEWS.md`, then creates or updates the task list. It never writes code.
- The **Builder** checks `BUGS.md` first (all bugs are fixed regardless of the task target), then `REVIEWS.md`, then works through tasks. It adapts how many tasks it takes on per cycle based on complexity and milestone boundaries.
- The **Reviewer** only commits when it finds meaningful quality issues. It skips minor style nitpicks.
- The **Tester** only commits when it finds bugs or writes new tests. If everything passes, it does nothing.
- Neither the Reviewer nor Tester duplicate items already in their respective files.
- All agents run `git pull --rebase` before pushing to avoid merge conflicts.
- `SPEC.md` is the source of truth. Edit it anytime to steer the project — run `plan` to adapt the task list.

See [AGENTS.md](AGENTS.md) for the exact prompts each agent receives.

### Logging

Every agent invocation is logged to an append-only file in a `logs/` directory at the project root (sibling of `builder/`, `reviewer/`, `tester/`). All console output — including status messages, warnings, and GitHub Copilot output — is duplicated to the appropriate log file.

```
myproject/
  builder/       ← git clone
  reviewer/      ← git clone
  tester/        ← git clone
  logs/          ← all agent logs
    bootstrap.log
    planner.log
    builder.log
    reviewer.log
    tester.log
    orchestrator.log
```

Each entry includes a timestamp, a prompt preview, the full output, and the exit code. The `logs/` directory is outside the git repos so logs are never committed.

To follow a log in real time:

```bash
tail -f logs/builder.log
```

### About `--yolo` mode

The GitHub Copilot CLI `--yolo` flag auto-approves every action without asking for confirmation. GitHub Copilot will create files, run commands, modify code, and push to GitHub without pausing. This is what makes the autonomous workflow possible, but it means you're trusting GitHub Copilot to do the right thing. Review the commits afterward.

---

## Usage

### One Command

```bash
agentic-dev go --name "my-project" --language dotnet --description "description of what to build"
```

Or use a requirements file:

```bash
agentic-dev go --name "my-project" --language python --spec-file requirements.md
```

### Resuming a Previous Project

```bash
agentic-dev resume --name "my-project"
```

### Running Agents Individually

After `go` has created a project, you can run individual agents if needed:

```bash
cd my-project/builder
agentic-dev plan
agentic-dev build
agentic-dev build --numtasks 3
agentic-dev build --loop
agentic-dev build --numtasks 5 --loop

cd ../reviewer
agentic-dev commitwatch

cd ../tester
agentic-dev testloop
```

> **Note:** Always use `go` for new projects — it runs bootstrap, plan, and launches all agents automatically. Do not run `bootstrap` directly.

### Commands Reference

| Command | What it does | Where |
|---|---|---|
| `go --name N --language L --description D` | Does everything: bootstrap, plan, launch agents, build | Once, from parent dir |
| `go --name N --language L --spec-file F` | Same, but reads requirements from a markdown file | Once, from parent dir |
| `resume --name N` | Re-plans, relaunches watchers, resumes building | Once, from parent dir |
| `plan` | Creates or updates TASKS.md from SPEC.md | builder/, on demand |
| `build` | Fixes bugs + reviews, then does tasks (targets ~5, adapts to complexity) | builder/, repeatedly |
| `build --numtasks 3` | Same, but targets ~3 tasks per cycle | builder/ |
| `build --loop` | Loops through all remaining tasks automatically | builder/, once |
| `commitwatch` | Polls for commits, reviews each one for quality | reviewer/, once |
| `testloop` | Runs tests every 5 minutes, files bugs | tester/, once |
| `reviewoncommit` | Legacy: watches for commits, reviews code quality | reviewer/, once |
| `testoncommit` | Legacy: watches for commits, runs tests, files bugs | tester/, once |
| `status` | Shows spec, tasks, reviews, and bugs at a glance | Any clone, anytime |

---

## What Could Go Wrong

| Scenario | What happens | Mitigation |
|---|---|---|
| GitHub Copilot generates bad code | Tests fail, tester files bugs, builder tries to fix them | Review commits periodically — don't let it run unattended forever |
| Both agents edit BUGS.md at the same time | Push fails due to conflict | All prompts include `git pull --rebase` before pushing |
| Tester starts a server and doesn't stop it | Port stays bound, next test run fails | GitHub Copilot is prompted to stop it, but if it doesn't, kill the process manually |
| Bootstrap creates wrong project structure | Tasks reference files that don't exist | Edit SPEC.md to clarify requirements, then run `plan` |
| GitHub Copilot enters an infinite fix loop | Builder and tester keep passing bugs back and forth | Stop all agents, review BUGS.md and the code, fix the root cause |

---

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
