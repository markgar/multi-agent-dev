---
marp: true
theme: default
paginate: true
backgroundColor: #1a1a2e
color: #e0e0e0
style: |
  section {
    font-family: 'SF Pro Display', 'Segoe UI', system-ui, sans-serif;
    font-size: 24px;
    padding: 30px 40px;
  }
  h1 {
    color: #60a5fa;
    font-size: 1.6em;
  }
  h2 {
    color: #60a5fa;
    font-size: 1.3em;
    margin-bottom: 0.3em;
  }
  h3 {
    color: #60a5fa;
    font-size: 1.1em;
  }
  code {
    background: #2d2d44;
    color: #a5d6ff;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
  }
  pre {
    background: #2d2d44 !important;
    border-radius: 8px;
    padding: 12px !important;
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
    font-size: 0.76em;
    line-height: 1.3;
  }
  th {
    background: #2d2d44;
    color: #60a5fa;
    padding: 4px 8px;
    white-space: nowrap;
  }
  td:first-child {
    white-space: nowrap;
  }
  td {
    background: #1e1e36;
    padding: 4px 8px;
  }
  blockquote {
    border-left: 4px solid #60a5fa;
    background: #2d2d44;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 0.9em;
  }
  p {
    margin: 0.4em 0;
  }
---

<!-- _class: lead -->
<!-- _paginate: false -->

# Multi-Agent Dev

### One spec in, working software out

<br>

*Seven agents. One repo. Zero human intervention.*

---

## Orchestrator

| | |
|---|---|
| **Mission** | Single entry point (`go`) — detects project state, bootstraps or resumes, launches all agents, waits for completion |
| **Triggered by** | User runs `agentic-dev go --spec-file spec.md` |
| **Runs from** | Parent directory (creates/manages all agent clone directories) |
| **Reads** | CLI flags, repo state (GitHub via `gh repo view`) |
| **Writes** | Agent clone directories, `logs/` directory, stale sentinel cleanup |
| **Talks to** | **Planner** (invokes directly before launching agents) · **All agents** (spawns each in its own terminal window) |
| **Writes code** | No — pure coordination |
| **Shutdown** | Polls `logs/builder-N.done` every 15s; exits when all builders report done |

**Launch order:** Reviewers → Milestone Reviewer → Tester → Validator → Builders

---

## Planner

| | |
|---|---|
| **Mission** | Decompose requirements into an ordered story queue, then expand one story at a time into a detailed milestone with tasks, reference files, and acceptance criteria |
| **Triggered by** | Orchestrator calls it before build starts (backlog creation) · Builder calls it between milestones (milestone expansion) |
| **Runs from** | `builder-1/` clone (invoked by orchestrator/builder, not a standalone process) |
| **Reads** | `REQUIREMENTS.md`, `SPEC.md`, `BACKLOG.md`, `milestones/`, the actual codebase |
| **Writes** | `BACKLOG.md` (story queue), `milestones/milestone-NN.md` (task files), `SPEC.md` (updates for new requirements) |
| **Talks to** | **Orchestrator** (called by it on fresh projects) · **Builder** (called by it between milestones) · **Backlog Checker** (orchestrator runs quality gate after initial plan) |
| **Writes code** | No — planning only |
| **Key detail** | Plans **one milestone per invocation**. Reads codebase to match emerged patterns. Two-step initial plan: create backlog, then separate completeness check. |

---

## Builder

| | |
|---|---|
| **Mission** | Claim stories, write application code, fix bugs and review findings — the only agent that writes production code |
| **Triggered by** | Orchestrator spawns it at startup; runs a continuous claim loop |
| **Runs from** | `builder-N/` clone (one per builder, supports 1..N in parallel) |
| **Reads** | `BACKLOG.md`, `milestones/`, `DEPLOY.md`, `REVIEW-THEMES.md`, `.github/copilot-instructions.md`, `SPEC.md`, GitHub Issues (bugs, findings) |
| **Writes** | Application code, `.github/copilot-instructions.md` updates, `.gitignore` updates |
| **Talks to** | **Planner** (calls it to expand next story) · **Commit Watcher** (reads its findings) · **Milestone Reviewer** (reads its findings + themes) · **Tester** (reads its bugs) · **Validator** (reads its bugs + DEPLOY.md) |
| **Writes code** | Yes — the **only** agent that writes production code |
| **Key detail** | Builds on feature branches (`builder-N/milestone-NN`), merges to main with `--no-ff`. Multi-builder: last builder is a dedicated issue fixer (`--role issue`); milestone builders skip issue fixing entirely. Single builder fixes issues inline between milestones. |

---

## Commit Watcher

| | |
|---|---|
| **Mission** | Review every commit for quality issues **before it merges to main** — the first line of code review |
| **Triggered by** | Polls every 10s for new commits on the builder's feature branch |
| **Runs from** | `reviewer-N/` clone (one per builder, branch-attached) |
| **Reads** | Builder's feature branch commits (diffs) |
| **Writes** | GitHub Issues with `--label finding` for [bug]/[security] issues · GitHub Issues with `--label note` for [cleanup]/[robustness] issues |
| **Talks to** | **Builder** (files findings the builder must fix) · **Milestone Reviewer** (notes feed the frequency filter) |
| **Writes code** | No — [doc] fixes only (comments, README). Never changes application logic. |
| **Key detail** | Severity split: critical issues → GitHub Issues with `finding` label (builder acts immediately), minor issues → GitHub Issues with `note` label (milestone reviewer evaluates later). Checkpoints saved to `logs/reviewer-N.branch-checkpoint`. |

---

## Milestone Reviewer

| | |
|---|---|
| **Mission** | Run a cross-cutting review of the full milestone diff — catch what per-commit reviews miss: inconsistent patterns, API mismatches, duplicated logic, architectural problems |
| **Triggered by** | Milestone completes (polls `logs/milestones.log` every 10s) |
| **Runs from** | `milestone-reviewer/` clone (single instance) |
| **Reads** | Full milestone diff, all `note`-labeled GitHub Issues from commit watchers, tree-sitter code analysis results |
| **Writes** | Promotes `note` → `finding` (via `gh issue edit`), closes stale findings, updates `REVIEW-THEMES.md` (cumulative lessons learned) |
| **Talks to** | **Builder** (files findings, updates themes the builder reads) · **Commit Watcher** (consumes its notes as input) |
| **Writes code** | No — [doc] fixes only. Never changes application logic or DEPLOY.md. |
| **Key detail** | **Frequency filter** — [cleanup]/[robustness] notes only promoted to findings if the pattern recurs in 2+ locations. One-off issues stay as notes. Runs tree-sitter structural analysis before review. |

---

## Tester

| | |
|---|---|
| **Mission** | Write and run tests scoped to each completed milestone — prioritize integration tests over unit tests, catch regressions across features |
| **Triggered by** | Milestone completes (polls `logs/milestones.log` every 10s) |
| **Runs from** | `tester/` clone (single instance) |
| **Reads** | `SPEC.md`, `milestones/` (current milestone), milestone diff (`--name-only`), existing test files |
| **Writes** | New test files, GitHub Issues with `--label bug` for failures |
| **Talks to** | **Builder** (files bugs the builder must fix before next milestone) |
| **Writes code** | Tests only — never writes application code |
| **Key detail** | Max 20 new tests per run. Does **not** start the app or test live endpoints — that's the Validator. More milestones completed → more integration tests → catches cross-feature regressions. |

---

## Validator

| | |
|---|---|
| **Mission** | Build the app in Docker, start it, and verify it works — the final acceptance gate for each milestone |
| **Triggered by** | Milestone completes (polls `logs/milestones.log` every 10s) |
| **Runs from** | `validator/` clone (single instance) |
| **Reads** | `SPEC.md`, `DEPLOY.md`, `REQUIREMENTS.md`, `BACKLOG.md`, `milestones/` (current), GitHub Issues (for fixed-bug re-testing) |
| **Writes** | GitHub Issues with `--label bug` (with `[missing-requirement]` or `[UI]` prefix), `DEPLOY.md`, `Dockerfile`, `docker-compose.yml`, Playwright tests (if frontend), `validation-results.txt` |
| **Talks to** | **Builder** (files bugs, maintains DEPLOY.md the builder reads for compatibility) |
| **Writes code** | Deployment config + Playwright tests only — never writes application code |
| **Key detail** | Three checks per milestone: **(A)** milestone acceptance, **(B)** requirements coverage, **(C)** fixed-bug verification. Auto-detects frontends → adds Playwright. DEPLOY.md creates a **ratchet effect** — each run inherits all prior deployment knowledge. Containers left running for browsing. |

---

<!-- _class: lead -->
<!-- _paginate: false -->

# Questions?

<br>

github.com/markgar/multi-agent-dev
