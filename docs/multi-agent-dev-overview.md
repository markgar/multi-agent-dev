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

<div style="text-align:center; margin: 24px 0">
<div style="display:flex; justify-content:center; gap:8px; flex-wrap:wrap; margin-bottom:8px">
  <div style="background:#2d2d44; padding:8px 14px; border-radius:6px; border:1px solid #60a5fa; font-weight:bold">Spec</div>
  <div style="color:#60a5fa; align-self:center">→</div>
  <div style="background:#2d2d44; padding:8px 14px; border-radius:6px; border:1px solid #60a5fa; font-weight:bold">Plan</div>
  <div style="color:#60a5fa; align-self:center">→</div>
  <div style="background:#2d2d44; padding:8px 14px; border-radius:6px; border:1px solid #60a5fa; font-weight:bold">Build</div>
  <div style="color:#60a5fa; align-self:center">→</div>
  <div style="background:#2d2d44; padding:8px 14px; border-radius:6px; border:1px solid #60a5fa; font-weight:bold">Review</div>
  <div style="color:#60a5fa; align-self:center">→</div>
  <div style="background:#2d2d44; padding:8px 14px; border-radius:6px; border:1px solid #60a5fa; font-weight:bold">Test</div>
  <div style="color:#60a5fa; align-self:center">→</div>
  <div style="background:#2d2d44; padding:8px 14px; border-radius:6px; border:1px solid #60a5fa; font-weight:bold">Validate</div>
</div>
<div style="color:#818cf8; font-size:0.85em">↺ bugs &amp; findings fed back to Builder</div>
</div>

One command. Multiple terminal windows. Agents working in parallel.

---

## Architecture Overview

<div style="text-align:center; margin:16px 0">
  <div style="background:#2d2d44; border:2px solid #60a5fa; border-radius:10px; padding:12px 20px; margin:0 auto 16px; max-width:600px">
    <div style="font-weight:bold; font-size:1.1em; color:#60a5fa">Orchestrator (go)</div>
    <div style="font-size:0.85em; color:#94a3b8">bootstrap → plan → launch agents → build loop</div>
  </div>
  <div style="color:#60a5fa; font-size:1.2em; margin-bottom:8px">▼ &nbsp;&nbsp;&nbsp; ▼ &nbsp;&nbsp;&nbsp; ▼ &nbsp;&nbsp;&nbsp; ▼ &nbsp;&nbsp;&nbsp; ▼</div>
  <div style="display:flex; justify-content:center; gap:10px; flex-wrap:wrap; margin-bottom:16px">
    <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 14px; min-width:90px"><strong>Builder</strong><br><span style="font-size:0.8em; color:#94a3b8">(1..N)</span></div>
    <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 14px; min-width:90px"><strong>Commit<br>Watcher</strong></div>
    <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 14px; min-width:90px"><strong>Milestone<br>Reviewer</strong></div>
    <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 14px; min-width:90px"><strong>Tester</strong></div>
    <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 14px; min-width:90px"><strong>Validator</strong></div>
  </div>
  <div style="color:#60a5fa; font-size:1.2em; margin-bottom:8px">▼ &nbsp;&nbsp;&nbsp; ▼ &nbsp;&nbsp;&nbsp; ▼ &nbsp;&nbsp;&nbsp; ▼ &nbsp;&nbsp;&nbsp; ▼</div>
  <div style="background:#2d2d44; border:2px solid #818cf8; border-radius:10px; padding:10px 20px; margin:0 auto; max-width:600px">
    <div style="font-weight:bold; color:#818cf8">Shared Git Repository</div>
    <div style="font-size:0.85em; color:#94a3b8">BACKLOG.md · milestones/ · bugs/ · reviews/</div>
  </div>
</div>

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

<!-- _class: default -->
<style scoped>table { font-size: 0.78em; } td, th { padding: 6px 10px; }</style>

## The Six Agents

| Agent | Role | Writes |
|---|---|---|
| **Planner** | Decomposes requirements into stories & milestones | BACKLOG.md, milestones/ |
| **Builder** | Claims stories, writes code, fixes bugs & findings | Application code |
| **Commit Watcher** | Reviews every commit for quality issues | finding-*.md, note-*.md |
| **Milestone Reviewer** | Cross-cutting review + note frequency filtering | finding-*.md, REVIEW-THEMES.md |
| **Tester** | Scoped tests on milestone completion | Test files, bug-*.md |
| **Validator** | Container build + acceptance testing | Dockerfile, DEPLOY.md, bug-*.md |

---

## Agent: Planner

<div style="display:flex; gap:20px; margin:12px 0">
<div style="flex:1">

**What it does**
Decomposes requirements into an ordered story queue (BACKLOG.md) with dependency annotations, then expands one story at a time into a detailed milestone file with tasks, reference files, and acceptance criteria.

**Trigger**
- Fresh project → creates BACKLOG.md + completeness check
- Between milestones → expands next eligible story

**Output**
`BACKLOG.md` · `milestones/milestone-NN.md` · SPEC.md updates

</div>
<div style="flex:1">

**How it feeds the Builder**
- BACKLOG.md tells the builder **what to claim next**
- Milestone files give the builder a **task-by-task work plan** with reference files to read and acceptance criteria to meet
- Dependency annotations control **which stories are eligible** — the builder only claims stories whose deps are all `[x]`

</div>
</div>

<div style="text-align:center; margin-top:8px; color:#94a3b8; font-size:0.85em">
Planner reads the actual codebase before planning → tasks match existing patterns
</div>

---

## Agent: Builder

<div style="display:flex; gap:20px; margin:12px 0">
<div style="flex:1">

**What it does**
Claims stories from BACKLOG.md via optimistic locking, fixes all open bugs and review findings, then completes every task in the milestone file — committing after each task.

**Trigger**
- Launched by orchestrator at startup
- Runs a continuous claim loop until no eligible stories remain

**Output**
Application code · Bug fixes · Finding resolutions · Updated `.github/copilot-instructions.md`

</div>
<div style="flex:1">

**How other agents feed it**
| Source | Mechanism |
|---|---|
| Planner | Milestone file (task list) |
| Commit Watcher | `finding-*.md` in reviews/ |
| Milestone Reviewer | `finding-*.md` in reviews/ |
| Tester | `bug-*.md` in bugs/ |
| Validator | `bug-*.md` in bugs/ + DEPLOY.md |

Builder fixes **all open bugs and findings before** starting milestone tasks.

</div>
</div>

---

## Agent: Commit Watcher

<div style="display:flex; gap:20px; margin:12px 0">
<div style="flex:1">

**What it does**
Polls for new commits every 10 seconds. Reviews each commit's diff for code quality issues. Batches multiple commits into a single review when they accumulate.

**Trigger**
- New commit(s) detected on main
- Skips merge commits and its own review-only commits

**Output**
- 🔴 `finding-*.md` for `[bug]` / `[security]` issues
- 🟡 `note-*.md` for `[cleanup]` / `[robustness]` issues

</div>
<div style="flex:1">

**How it feeds the Builder**
- `finding-*.md` files appear in `reviews/` — builder reads and fixes them **before** starting any milestone task
- `note-*.md` files are **not seen by the builder** directly — they feed the Milestone Reviewer instead
- Checkpoint in `logs/reviewer.checkpoint` ensures no commit is ever missed

</div>
</div>

<div style="text-align:center; margin-top:8px; color:#94a3b8; font-size:0.85em">
Severity split ensures critical issues reach the builder fast; low-severity issues are filtered by the Milestone Reviewer
</div>

---

## Agent: Milestone Reviewer

<div style="display:flex; gap:20px; margin:12px 0">
<div style="flex:1">

**What it does**
Runs a cross-cutting review of the entire milestone's diff when all tasks are checked. Catches issues per-commit reviews miss: inconsistent patterns, API mismatches, duplicated logic across commits. Runs tree-sitter code analysis for structural quality data.

**Trigger**
- Milestone completed (all tasks checked in milestone file)
- Polls `logs/milestones.log` every 10 seconds

**Output**
- `finding-*.md` — promoted from recurring notes or new cross-cutting issues
- `resolved-*.md` — cleans up stale findings already fixed
- `REVIEW-THEMES.md` — cumulative patterns for future sessions

</div>
<div style="flex:1">

**How it feeds the Builder**
- Applies **frequency filter** to `note-*.md` from per-commit reviews:
  - [bug]/[security] → always promoted to `finding-*.md`
  - [cleanup]/[robustness] → only if pattern recurs in **2+ locations**
- Builder reads `finding-*.md` and fixes before next milestone
- Builder reads `REVIEW-THEMES.md` to **avoid repeating** the same class of mistake
- `resolved-*.md` files **remove stale items** from the builder's work list

</div>
</div>

---

## Agent: Tester

<div style="display:flex; gap:20px; margin:12px 0">
<div style="flex:1">

**What it does**
Runs scoped tests when a milestone completes. Writes new tests for the milestone's changed files, prioritizing integration tests over unit tests. Runs the full test suite to catch regressions.

**Trigger**
- Milestone completed (detected via `logs/milestones.log`)
- Polls every 10 seconds

**Output**
- New test files (unit + integration)
- `bug-*.md` in `bugs/` for any test failures
- At most 20 new tests per run

</div>
<div style="flex:1">

**How it feeds the Builder**
- `bug-*.md` files appear in `bugs/` — builder reads and fixes them **before** starting any milestone task
- Each bug file includes: what failed, steps to reproduce, and which milestone caused it
- Does **not** start the app or test live endpoints — that's the Validator's job
- More milestones completed → more integration tests → catches cross-feature regressions

</div>
</div>

<div style="text-align:center; margin-top:8px; color:#94a3b8; font-size:0.85em">
Tester focuses on the test suite; Validator focuses on runtime behavior in containers
</div>

---

## Agent: Validator

<div style="display:flex; gap:20px; margin:12px 0">
<div style="flex:1">

**What it does**
Builds the app in Docker, starts it, and runs three checks:
- **(A)** Milestone validation — tests the `> **Validates:**` block
- **(B)** Requirements coverage — cross-references REQUIREMENTS.md
- **(C)** Fixed bug verification — re-tests `bug-*.md` with `fixed-*.md`

Auto-detects frontends and adds **Playwright UI tests**.

**Trigger**
- Milestone completed (detected via `logs/milestones.log`)

</div>
<div style="flex:1">

**Output**
- `bug-*.md` in `bugs/` (with `[missing-requirement]` or `[UI]` prefixes)
- `DEPLOY.md` — cumulative deployment knowledge
- `Dockerfile` / `docker-compose.yml`
- `validation-results.txt` → copied to `logs/`

**How it feeds the Builder**
- `bug-*.md` → builder fixes before next milestone
- `DEPLOY.md` → builder reads to stay **compatible** with deployment (env vars, ports, startup)
- Containers left running → app browsable at `localhost:<port>`

</div>
</div>

<div style="text-align:center; margin-top:8px; color:#94a3b8; font-size:0.85em">
Each milestone's validation inherits all deployment knowledge from prior runs — a ratchet effect
</div>

---

## Coordination Model

Agents coordinate through **files in git** — no message queues, no APIs, no shared memory.

| Mechanism | Purpose |
|---|---|
| `BACKLOG.md` | Story queue with optimistic locking (`[ ]` → `[N]` → `[x]`) |
| `milestones/` | One file per story — tasks, reference files, acceptance criteria |
| `bugs/` | Append-only bug reports (tester & validator → builder) |
| `reviews/` | Append-only review findings (reviewer → builder) |
| `DEPLOY.md` | Cumulative deployment knowledge (validator → builder) |
| `logs/` | Local signals — checkpoints, sentinel files, milestone log |

**Append-only directories** = no merge conflicts on concurrent writes.

---

## The Build Loop

Each builder runs an independent **claim loop**:

<div style="margin:16px auto; max-width:480px">
  <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 16px; margin-bottom:4px"><strong>1.</strong> Find next eligible story in BACKLOG <span style="color:#94a3b8; font-size:0.85em">(deps [x], story [ ])</span></div>
  <div style="text-align:center; color:#60a5fa">▼</div>
  <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 16px; margin-bottom:4px"><strong>2.</strong> Claim it: [ ] → [N], commit, push <span style="color:#94a3b8; font-size:0.85em">(push fails? try next)</span></div>
  <div style="text-align:center; color:#60a5fa">▼</div>
  <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 16px; margin-bottom:4px"><strong>3.</strong> Plan milestone for this story</div>
  <div style="text-align:center; color:#60a5fa">▼</div>
  <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 16px; margin-bottom:4px"><strong>4.</strong> Fix bugs → Fix findings → Build</div>
  <div style="text-align:center; color:#60a5fa">▼</div>
  <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 16px; margin-bottom:4px"><strong>5.</strong> Mark [x], commit, push</div>
  <div style="text-align:center; color:#60a5fa">▼</div>
  <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:8px; padding:10px 16px"><strong>6.</strong> Loop → no stories left? → <span style="color:#60a5fa">Done</span></div>
</div>

Multiple builders run this loop **in parallel**, each claiming different stories.

---

## Parallel Builders

<div style="text-align:center; margin:16px 0">
  <div style="font-weight:bold; color:#60a5fa; margin-bottom:8px">Story Dependency Graph</div>
  <div style="display:flex; flex-direction:column; align-items:center; gap:4px">
    <div style="background:#2d2d44; border:1px solid #60a5fa; border-radius:6px; padding:6px 20px">1. Scaffolding</div>
    <div style="display:flex; gap:4px; color:#60a5fa"><span>↙</span><span>&nbsp;&nbsp;&nbsp;&nbsp;</span><span>↘</span></div>
    <div style="display:flex; gap:16px">
      <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:6px; padding:6px 16px">2. Members</div>
      <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:6px; padding:6px 16px">3. Projects</div>
    </div>
    <div style="display:flex; gap:4px; color:#60a5fa"><span>↓</span><span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span><span>↓</span></div>
    <div style="display:flex; gap:16px">
      <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:6px; padding:6px 16px">4. Auditions</div>
      <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:6px; padding:6px 16px">5. Events</div>
    </div>
    <div style="color:#60a5fa">↘ &nbsp;&nbsp;&nbsp;&nbsp; ↙</div>
    <div style="background:#2d2d44; border:1px solid #818cf8; border-radius:6px; padding:6px 20px">6. Attendance</div>
    <div style="color:#60a5fa">↓</div>
    <div style="background:#2d2d44; border:1px solid #60a5fa; border-radius:6px; padding:6px 20px">7. Calendar + Notifications</div>
  </div>
  <div style="color:#94a3b8; font-size:0.8em; margin-top:8px">Builder-1 and Builder-2 work simultaneously on independent branches</div>
</div>

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
