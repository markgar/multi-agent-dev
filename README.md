# Multi-Agent Flow

An autonomous development workflow using GitHub Copilot CLI. Six agents collaborate through files in a shared GitHub repo to build projects in **.NET/C#**, **Python**, or **Node.js**:

- **Planner** — creates a backlog of stories and expands them into milestones one at a time
- **Builder** — fixes bugs, addresses review items, completes one milestone per cycle
- **Commit Watcher** — reviews each commit for quality, fixes doc issues directly, files code issues as GitHub Issues
- **Milestone Reviewer** — cross-cutting milestone reviews with frequency-filtered findings and stale-item cleanup
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
| Copilot CLI (coding agent) | See [Copilot coding agent on CLI](https://docs.github.com/en/copilot/using-github-copilot/using-the-github-copilot-agent-for-the-cli) | Same | `copilot --version` |

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
1. **Bootstrap** — create the project, SPEC.md, git repo, GitHub remote, and agent clones (builder-1/, reviewer-1/, milestone-reviewer/, tester/, validator/)
2. **Plan** — generate BACKLOG.md (story queue)
3. **Launch commit watcher** — in a new terminal window, reviewing each commit
4. **Launch milestone reviewer** — in a new terminal window, cross-cutting reviews when milestones complete
5. **Launch tester** — in a new terminal window, testing each completed milestone
6. **Launch validator** — in a new terminal window, building containers and validating against the spec
7. **Start building** — in your current terminal, completing milestones one at a time

Multiple windows will be running. Watch the Builder work through milestones while the Reviewer, Tester, and Validator react to each commit and milestone completion. Run `agentic-dev status` anytime in a builder directory to check progress.

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
agentic-dev go --directory /path/to/runs/20260213/my-app --model gpt-5.3-codex
```

`go` detects the existing repo on GitHub via `gh repo view` and automatically clones any missing agent directories. You can resume on a fresh machine with nothing but the repo — no pre-existing `builder-1/`, `reviewer-1/`, `tester/`, or `validator/` directories needed.

### GitHub Org

Create the repo under a GitHub organization instead of your personal account:

```bash
agentic-dev go --directory my-project --model gpt-5.3-codex --org my-org --description "..."
```

### Per-Agent Model Overrides

Use different models for different agents:

```bash
agentic-dev go --directory my-project --model claude-opus-4.6 \
  --builder-model gpt-5.3-codex \
  --planner-model claude-sonnet-4.6 \
  --description "..."
```

Available overrides: `--builder-model`, `--reviewer-model`, `--milestone-reviewer-model`, `--tester-model`, `--validator-model`, `--planner-model`, `--backlog-model`. Each defaults to `--model` when not specified.

---

## Examples

See [EXAMPLES.md](EXAMPLES.md) for ready-to-run commands — Hello World, REST API, and Full Stack projects in .NET, Python, and Node.js.

---

## How It Works

```
Planner ──milestones/──→ Builder ──git push──→ Reviewer ──GitHub Issues──→ Builder
                           ↑                                              
                           │         Builder ──git push──→ Tester
                           │                                  │
                           │         Builder ──git push──→ Validator
                           │                                  │
                           └───── GitHub Issues ───────────┘
```

| From | To | Mechanism | What it says |
|---|---|---|---|
| Bootstrap | Planner | `SPEC.md` | Here's the technical decisions for how to build the project |
| Planner | Builder | `BACKLOG.md`, `milestones/` | Here's the next milestone to build |
| Builder | Reviewer | `git push` | I finished a commit or milestone, review it |
| Builder | Tester | `milestones.log` | A milestone is complete, test it |
| Builder | Validator | `milestones.log` | A milestone is complete, validate it in a container |
| Reviewer | Builder | GitHub Issues (`finding`) | I found code-level issues, address these |
| Milestone Reviewer | Builder | GitHub Issues (`finding`) | Recurring patterns promoted from notes |
| Reviewer | (self) | direct commit | I found a doc issue (stale comment, inaccurate README), fixed it myself |
| Tester | Builder | GitHub Issues | I found test failures, fix these |
| Validator | Builder | GitHub Issues | The app failed validation in a container, fix these |
| Validator | Builder | `DEPLOY.md` | Here's what I learned about deploying this app |

### Positive Feedback Loops

The system is designed around cumulative knowledge — each milestone makes subsequent milestones more reliable:

- **Deployment knowledge (DEPLOY.md):** The validator writes everything it learns about building and running the app (Dockerfile config, env vars, ports, startup sequence, gotchas). The builder reads it to stay compatible. Each milestone's validation inherits all prior knowledge, so deployments get more reliable over time.
- **Review signal filtering (notes → findings):** Per-commit reviews file [bug]/[security] issues immediately but file [cleanup]/[robustness] issues as observational notes. The milestone review then evaluates notes for recurring patterns — only issues that appear in 2+ locations get promoted to findings for the builder. This means the builder spends time on systemic problems, not one-off nitpicks.
- **Review themes (REVIEW-THEMES.md):** The reviewer maintains a rolling summary of the highest-impact recurring patterns. The builder reads it to avoid repeating the same class of mistake across milestones.
- **Codebase-aware planning:** The milestone planner reads the actual codebase before expanding the next story — it matches existing patterns (base classes, naming conventions, DI wiring) rather than planning in a vacuum.
- **Copilot instructions (.github/copilot-instructions.md):** The builder updates this style guide as the project structure evolves. Future builder sessions read it, so coding conventions stay consistent as the project grows.

See [AGENTS.md](AGENTS.md) for the exact prompts each agent receives and coordination rules.

See [USAGE.md](USAGE.md) for the full command reference, logging, troubleshooting, and more.
