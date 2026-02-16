# Multi-Agent Flow

An autonomous development workflow using GitHub Copilot CLI. Five agents collaborate through files in a shared GitHub repo to build projects in **.NET/C#**, **Python**, or **Node.js**:

- **Planner** — creates a backlog of stories and expands them into milestones one at a time
- **Builder** — fixes bugs, addresses review items, completes one milestone per cycle
- **Reviewer** — reviews each commit for quality, fixes doc issues directly, files code issues to REVIEWS.md, plus cross-cutting milestone reviews with stale-item cleanup
- **Tester** — runs scoped tests when milestones complete, files bugs
- **Validator** — builds the app in a Docker container, runs it, and validates it against the spec

## Prerequisites

Install these one time. After each install, **close and reopen your terminal** so the PATH updates.

**Required for all projects:**

| Tool | Install (Windows) | Install (macOS) | Verify |
|---|---|---|---|
| Git | `winget install Git.Git` | `brew install git` (or Xcode CLT) | `git --version` |
| GitHub CLI | `winget install GitHub.cli` | `brew install gh` | `gh auth status` |
| Python 3 | `winget install Python.Python.3.12` | `brew install python` | `python3 --version` |
| Docker | `winget install Docker.DockerDesktop` | `brew install --cask docker` | `docker --version` |
| GitHub Copilot CLI | See GitHub Copilot CLI docs | See GitHub Copilot CLI docs | `copilot --version` |

**Install for your target language:**

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
pip install -e .
cd ..

agentic-dev go --directory hello-world --model gpt-5.3-codex \
  --description "a C# console app that prints Hello World"
```

That's it. `go` will:
1. **Bootstrap** — create the project, SPEC.md, git repo, GitHub remote, and four clones (builder/, reviewer/, tester/, validator/)
2. **Plan** — generate BACKLOG.md (story queue) and the first milestone in TASKS.md
3. **Launch reviewer** — in a new terminal window, reviewing each commit and completed milestones
4. **Launch tester** — in a new terminal window, testing each completed milestone
5. **Launch validator** — in a new terminal window, building containers and validating against the spec
6. **Start building** — in your current terminal, completing milestones one at a time

Four windows will be running. Watch the Builder work through milestones while the Reviewer, Tester, and Validator react to each commit and milestone completion. Run `agentic-dev status` anytime in the builder directory to check progress.

### Continuing with New Requirements

Come back later and add new features to the same project:

```bash
agentic-dev go --directory hello-world --model gpt-5.3-codex --spec-file new-features.md
```

The planner detects what's already built, updates the spec, and creates new milestones for the unimplemented work.

### Resuming Where You Left Off

```bash
agentic-dev go --directory hello-world --model gpt-5.3-codex
```

No spec needed — just re-evaluates the plan and continues building.

### Resuming from a Different Location

Point `--directory` at any existing project directory, even from a test harness run:

```bash
agentic-dev go --directory /path/to/runs/20260213/my-app --model gpt-5.3-codex --local
```

`go` detects the existing repo (locally via `remote.git/`, or on GitHub via `gh repo view`) and automatically clones any missing agent directories. You can resume on a fresh machine with nothing but the repo — no pre-existing `builder/`, `reviewer/`, `tester/`, or `validator/` directories needed.

### Local Mode (no GitHub)

Add `--local` to run entirely offline with a local bare git repo instead of GitHub:

```bash
agentic-dev go --directory my-project --model gpt-5.3-codex --description "..." --local
```

This skips all `gh` CLI calls and creates a bare repo at `remote.git/` inside the project directory. All git operations (push, pull, clone) work identically against it. Useful for testing, offline development, or environments without GitHub access.

---

## Examples

See [EXAMPLES.md](EXAMPLES.md) for ready-to-run commands — Hello World, REST API, and Full Stack projects in .NET, Python, and Node.js.

---

## How It Works

```
Planner ──TASKS.md──→ Builder ──git push──→ Reviewer ──REVIEWS.md──→ Builder
                         ↑                                              
                         │         Builder ──git push──→ Tester
                         │                                  │
                         │         Builder ──git push──→ Validator
                         │                                  │
                         └──────────── BUGS.md ←────────────┘
```

| From | To | Mechanism | What it says |
|---|---|---|---|
| Bootstrap | Planner | `SPEC.md` | Here's the technical decisions for how to build the project |
| Planner | Builder | `BACKLOG.md`, `TASKS.md` | Here's the next milestone to build |
| Builder | Reviewer | `git push` | I finished a commit or milestone, review it |
| Builder | Tester | `milestones.log` | A milestone is complete, test it |
| Builder | Validator | `milestones.log` | A milestone is complete, validate it in a container |
| Reviewer | Builder | `REVIEWS.md` | I found code-level issues, address these |
| Reviewer | (self) | direct commit | I found a doc issue (stale comment, inaccurate README), fixed it myself |
| Tester | Builder | `BUGS.md` | I found test failures, fix these |
| Validator | Builder | `BUGS.md` | The app failed validation in a container, fix these |
| Validator | Builder | `DEPLOY.md` | Here's what I learned about deploying this app |

See [AGENTS.md](AGENTS.md) for the exact prompts each agent receives and coordination rules.

See [USAGE.md](USAGE.md) for the full command reference, logging, troubleshooting, and more.
