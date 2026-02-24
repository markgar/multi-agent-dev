---
marp: true
theme: default
paginate: true
backgroundColor: #1a1a2e
color: #e0e0e0
style: |
  section {
    font-family: 'SF Pro Display', 'Segoe UI', system-ui, sans-serif;
  }
  h1, h2, h3 {
    color: #60a5fa;
  }
  code {
    background: #2d2d44;
    color: #a5d6ff;
    padding: 2px 6px;
    border-radius: 4px;
  }
  pre {
    background: #2d2d44 !important;
    border-radius: 8px;
    padding: 16px !important;
    color: #e0e0e0;
  }
  pre code {
    background: transparent;
    color: #e0e0e0;
  }
  strong {
    color: #f0f0f0;
  }
  em {
    color: #94a3b8;
  }
  a {
    color: #818cf8;
  }
  table {
    font-size: 0.85em;
  }
  th {
    background: #2d2d44;
    color: #60a5fa;
  }
  td {
    background: #1e1e36;
  }
  blockquote {
    border-left: 4px solid #60a5fa;
    background: #2d2d44;
    padding: 8px 16px;
    border-radius: 4px;
  }
  .agent-box {
    display: inline-block;
    padding: 8px 16px;
    border-radius: 8px;
    margin: 4px;
    font-weight: bold;
  }
---

<!-- _class: lead -->
<!-- _paginate: false -->

# Multi-Agent Flow

### Autonomous software development with coordinating AI agents

<br>

*Six agents. One repo. Zero human intervention.*

---

## The Problem

Building software with AI assistants today is **sequential and manual**:

- One prompt → one response → one file at a time
- Developer is the orchestrator, reviewer, and tester
- No persistent memory across sessions
- Quality degrades as projects grow — no systematic review

**What if the agents could coordinate themselves?**

---

## The Idea

Replace the single-agent loop with a **multi-agent pipeline** where each agent has a specialized role and they coordinate through a shared git repo.

```
Spec → Plan → Build → Review → Test → Validate
                ↑        |        |        |
                └────────┴────────┴────────┘
                    bugs & findings fed back
```

One command. Multiple terminal windows. Agents working in parallel.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   Orchestrator (go)                       │
│  bootstrap → plan → launch agents → build loop             │
└─────┴──────┴──────────┴─────────┴─────────┴─────────┘
      │      │          │         │         │
┌─────▼──┐ ┌──▼──┐ ┌────────▼─┐ ┌───▼───┐ ┌───▼─────┐
│ Builder │ │Commit│ │Milestone │ │Tester │ │Validat- │
│ (1..N)  │ │Watcher│ │ Reviewer │ │       │ │  or     │
└─────┬──┘ └──┬──┘ └──────┬───┘ └───┬───┘ └───┬─────┘
      │      │          │         │         │
      └──────┴──────────┴─────────┴─────────┘
                 Shared Git Repository
          (BACKLOG.md, milestones/, bugs/, reviews/)
```

Each agent runs as a **separate process** in its **own git clone**.

---

## Execution Engine

Every agent is a **GitHub Copilot CLI** call:

```bash
copilot --yolo --model claude-opus-4.6 \
  "Read the milestone file. Fix all bugs in bugs/. 
   Address findings in reviews/. Complete every task..."
```

- `--yolo` = autonomous mode, no human approval needed
- Each agent gets a **role-specific prompt** with clear rules
- Copilot reads/writes files, runs commands, commits & pushes
- The Python orchestrator handles **deterministic coordination** — milestone tracking, shutdown signals, checkpoint persistence

---

## The Six Agents

| Agent | Role | Reads | Writes |
|---|---|---|---|
| **Planner** | Decomposes requirements into stories & milestones | SPEC.md, REQUIREMENTS.md, codebase | BACKLOG.md, milestones/ |
| **Builder** | Claims stories, plans milestones, writes code | milestones/, bugs/, reviews/, DEPLOY.md, REVIEW-THEMES.md | Application code |
| **Commit Watcher** | Per-commit code review | Git diffs | finding-*.md, note-*.md |
| **Milestone Reviewer** | Cross-cutting milestone review + note filtering | Full milestone diff, note-*.md | finding-*.md, REVIEW-THEMES.md |
| **Tester** | Scoped tests on milestone completion | Changed files, existing tests | Test files, bug-*.md |
| **Validator** | Container build + acceptance testing | SPEC.md, DEPLOY.md, REQUIREMENTS.md | Dockerfile, DEPLOY.md, bug-*.md |

---

## Coordination Model

Agents coordinate through **files in git** — no message queues, no APIs, no shared memory.

| Mechanism | Purpose |
|---|---|
| `BACKLOG.md` | Story queue with optimistic locking (`[ ]` → `[~]` → `[x]`) |
| `milestones/` | One file per story — tasks, reference files, acceptance criteria |
| `bugs/` | Append-only bug reports (tester & validator → builder) |
| `reviews/` | Append-only review findings (reviewer → builder) |
| `DEPLOY.md` | Cumulative deployment knowledge (validator → builder) |
| `logs/` | Local signals — checkpoints, sentinel files, milestone log |

**Append-only directories** = no merge conflicts on concurrent writes.

---

## The Build Loop

Each builder runs an independent **claim loop**:

```
┌──────────────────────────────────────────┐
│  1. Find next eligible story in BACKLOG  │
│     (all dependencies [x], story [ ])    │
│                  ↓                       │
│  2. Claim it: [ ] → [~], commit, push   │
│     (push fails? pull & try next)        │
│                  ↓                       │
│  3. Plan milestone for this story        │
│                  ↓                       │
│  4. Fix bugs → Fix findings → Build      │
│                  ↓                       │
│  5. Mark [x], commit, push              │
│                  ↓                       │
│  6. Loop → no stories left? → Done      │
└──────────────────────────────────────────┘
```

Multiple builders run this loop **in parallel**, each claiming different stories.

---

## Parallel Builders

```
          Story Dependency Graph
     ┌──────────────────────────────┐
     │  1. Scaffolding              │
     │     ↓           ↓            │
     │  2. Members   3. Projects    │  ← Builder-1 and Builder-2
     │     ↓           ↓            │     work simultaneously
     │  4. Auditions 5. Events      │
     │     ↓           ↓            │
     │  6. Attendance               │
     │     ↓                        │
     │  7. Calendar + Notifications │
     └──────────────────────────────┘
```

- **Optimistic locking** via git push — if two builders claim the same story, the slower push fails and retries the next one
- **Minimal dependencies** — the planner keeps the graph wide for maximum parallelism
- Each builder gets its own `builder-N/` clone directory

---

## Review Signal Filtering

Two separate agents use a **two-tier system** to avoid drowning the builder in noise:

**Commit Watcher** (per-commit, in `reviewer/` clone):
- 🔴 `[bug]` / `[security]` → filed as `finding-*.md` — builder fixes immediately
- 🟡 `[cleanup]` / `[robustness]` → filed as `note-*.md` — observational only

**Milestone Reviewer** (cross-cutting, in `milestone-reviewer/` clone):
- Reads all `note-*.md` accumulated during the milestone
- **Frequency filter**: only promotes to `finding-*.md` if the pattern recurred in **2+ locations**
- One-off issues stay as notes → builder never sees them
- Cleans up stale findings already fixed in code
- Runs **tree-sitter code analysis** before review for structural quality data

*Result: builder spends fix cycles on systemic problems, not isolated nitpicks.*

---

## Positive Feedback Loops

Four mechanisms that make each milestone **better than the last**:

### 1. Deployment Knowledge Ratchet (DEPLOY.md)
Validator writes what it learned → builder reads it next session → container builds get progressively more reliable. After each milestone, a **validation summary** logs pass/fail counts by category (`[A]` milestone, `[B]` requirements, `[C]` bug verification, `[UI]` Playwright).

### 2. Review Themes (REVIEW-THEMES.md)
Reviewer maintains cumulative patterns → builder reads before coding → same class of mistake doesn't repeat

### 3. Codebase-Aware Planning
Milestone planner reads actual code → discovers emerged patterns → writes tasks that match existing conventions

### 4. Evolving Style Guide (.github/copilot-instructions.md)
Builder updates conventions as project grows → all agents read it → consistency across the entire codebase

---

## Shutdown Protocol

Graceful multi-builder shutdown with **no orphaned work**:

1. Builder finds no eligible stories → waits for downstream agents to go idle
2. Monitors `reviewer.log`, `milestone-reviewer.log`, `tester.log`, `validator.log` modification times
3. Pulls latest — checks for open bugs, open findings, unchecked tasks
4. If new work found → fix it (up to 4 cycles) → re-check
5. All clean → writes `logs/builder-N.done`
6. All builders done → all agents see it, drain remaining work, and exit
7. Crash fallback: 30 min log inactivity → assume crash → shutdown

---

## Iterative Development

The system supports **multi-session development** — come back and evolve the project:

```bash
# Session 1: Build the API
agentic-dev go --directory my-app --model claude-opus-4.6 \
  --spec-file api-spec.md

# Session 2: Add a frontend (detects existing repo, adds new stories)
agentic-dev go --directory my-app --model claude-opus-4.6 \
  --spec-file frontend-spec.md

# Session 3: Resume where it left off (no new requirements)
agentic-dev go --directory my-app --model claude-opus-4.6

# Parallel build with Playwright trace saving
agentic-dev go --directory my-app --model claude-opus-4.6 --builders 3
```

Agent directories are **disposable** — they can be deleted and re-cloned anytime. The repo and `logs/` are the persistent state.

---

## What Gets Built

From a single spec file, the system produces:

- ✅ **Working application** — builds, runs, passes tests
- ✅ **Full test suite** — unit + integration tests written by the tester
- ✅ **Docker deployment** — Dockerfile, docker-compose.yml, DEPLOY.md
- ✅ **Code review history** — every commit reviewed, findings tracked
- ✅ **Validated against spec** — three-check acceptance testing in containers
- ✅ **Playwright UI tests** — auto-detected for frontend projects, optional trace saving
- ✅ **Validation summaries** — pass/fail breakdown logged per milestone
- ✅ **Documentation** — README, copilot-instructions, deployment guide

All with **zero human intervention** from spec to deployed app.

---

## Under the Hood: Tech Stack

| Component | Technology |
|---|---|
| Orchestrator | Python, pip-installable CLI (`agentic-dev`) |
| Execution engine | GitHub Copilot CLI (`copilot --yolo`) |
| Coordination | Git (push/pull), markdown files, append-only dirs |
| Code analysis | Tree-sitter (Python, JS/TS, C#) |
| Quality gates | Deterministic structural checks + LLM review |
| Container testing | Docker, docker-compose, Playwright |
| Target languages | .NET/C#, Python, Node.js |

**~4,900 lines of Python** orchestrating **~1,200 lines of prompt templates**.

---

## Key Design Decisions

1. **Git as coordination bus** — no custom protocols, agents use tools they already understand
2. **Append-only communication** — bugs/ and reviews/ never have merge conflicts
3. **Optimistic locking for claims** — git push fails = natural retry, no distributed locks
4. **Separate clones per agent** — no file contention, each agent has its own working tree
5. **Deterministic orchestration, creative execution** — Python handles milestone tracking and shutdown; LLM handles code, reviews, tests
6. **Checkpoint persistence** — every agent can crash and resume without re-doing work
7. **Progressive planning** — one milestone at a time, reading the actual codebase, not front-loading all design

---

## Demo

```bash
agentic-dev go \
  --directory stretto \
  --model claude-opus-4.6 \
  --builders 2 \
  --spec-file stretto-spec.md
```

*Watch six terminal windows coordinate to build a multi-tenant SaaS platform from a requirements document.*

---

<!-- _class: lead -->
<!-- _paginate: false -->

# Questions?

<br>

github.com/markgar/multi-agent-dev

<br>

*"The best way to predict the future is to build it — autonomously."*
