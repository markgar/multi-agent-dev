# Agent Prompts

Each agent is a `copilot --yolo` call with a specific prompt. Here's exactly what each one is told to do.

---

## Bootstrap

Runs once internally when you call `go`. Do not run `bootstrap` directly — it is deprecated and will error.

> Create a directory called builder. cd into it. Initialize a git repo. Create an appropriate .gitignore for the project. Create a README.md that describes the project: `{description}`. A file called REQUIREMENTS.md already exists in this directory — it contains the original project requirements exactly as provided by the user. Do NOT modify or overwrite REQUIREMENTS.md. Use it as the primary input when writing SPEC.md. Create a SPEC.md that defines the desired end state of the project. SPEC.md should include: a high-level summary, the tech stack and language, the features and requirements, any constraints or guidelines, and acceptance criteria for what 'done' looks like. Be specific and thorough in SPEC.md — it is the source of truth that all future planning is based on. Every feature and requirement in REQUIREMENTS.md must be addressed in SPEC.md. Do NOT create a TASKS.md — task planning happens later. Commit with message 'Initial commit: project spec'. Run 'gh repo create `{user/name}` --public --source .' and push.

**Creates:** README.md, SPEC.md, REQUIREMENTS.md, git repo, GitHub remote  
**Writes code:** No

**Note:** Before Copilot runs, the CLI pre-creates `builder/REQUIREMENTS.md` containing the original prompt or spec-file content verbatim. This file is committed with the rest of the bootstrap and never modified afterward.

---

## Planner

Runs on demand via `plan`. Call it before the first `build`, or whenever you need to re-evaluate the task list.

> You are a planning-only orchestrator. You must NOT write any code or modify any source files. Your only job is to manage TASKS.md. Read REQUIREMENTS.md first — this is the original requirements document provided by the user and is the ultimate source of truth for what must be built. Then read SPEC.md to understand the desired end state. Read README.md for project context. Look at the current codebase to see what has been built so far. Read BUGS.md if it exists to see outstanding bugs. Read REVIEWS.md if it exists to see outstanding review items. Read TASKS.md if it exists to see the current plan. Now evaluate: are there tasks that need to be added, broken down, reordered, or clarified based on what has been built vs what SPEC.md requires? Cross-check against REQUIREMENTS.md to ensure no features or requirements from the original prompt have been missed or dropped. If TASKS.md does not exist, create it with a detailed numbered checkbox task list that will achieve everything in SPEC.md and REQUIREMENTS.md. Group the tasks under milestone headings using the format `## Milestone: <name>`. Each milestone is the builder's unit of work — the builder will complete one entire milestone per session, then stop so the planner can re-evaluate. Size milestones accordingly: each should be a coherent batch of work that can be completed in one pass. If a feature area is large, split it into multiple milestones (e.g. 'API endpoints: CRUD' and 'API endpoints: search and filtering'). If several small pieces are related, combine them into one milestone. Err on the side of smaller milestones — it is better to finish a milestone and start the next than to leave one half-done. Good milestones are things like 'Project scaffolding', 'Core data models', 'API endpoints', 'Authentication', 'Frontend views', 'Error handling and validation'. Aim for 3-8 tasks per milestone. A milestone is considered complete when all its checkbox tasks are checked. The reviewer uses milestone boundaries to do cross-cutting code reviews, so organize milestones around code that interacts — put related tasks together even if they touch different files. Each task should be concrete and actionable, building on the last. Include a task early on to remove any default scaffolding or template code that does not belong. Include a final task to verify everything works end to end. If TASKS.md already exists, update it — add missing tasks, refine vague ones, but never remove or uncheck completed tasks. Commit any changes to TASKS.md with message 'Update task plan', run git pull --rebase, and push. If no changes are needed, do nothing.

**Creates:** TASKS.md (first run), updates it on subsequent runs  
**Reads:** SPEC.md, README.md, REQUIREMENTS.md, codebase, TASKS.md, BUGS.md, REVIEWS.md  
**Writes code:** No

---

## Builder

Runs via `build`. Completes one milestone per cycle. Between milestones the planner re-evaluates the task list. Writes `logs/builder.done` when it exits so other agents know to shut down.

> Before starting, review README.md, SPEC.md, and TASKS.md to understand the project's purpose and plan. Only build, fix, or keep code that serves that purpose. Remove any scaffolding, template code, or functionality that does not belong. Now look at BUGS.md first. Fix ALL unfixed bugs — bugs are never deferred. Fix them one at a time — fix a bug, mark it fixed in BUGS.md, commit with a meaningful message, run git pull --rebase, and push. Then look at REVIEWS.md. Address unchecked review items one at a time — fix the issue, mark it done in REVIEWS.md, commit, pull --rebase, and push. Once all bugs and review items are fixed (or if there are none), move to TASKS.md. TASKS.md is organized into milestones (sections headed with `## Milestone: <name>`). Find the first milestone that has unchecked tasks — this is your current milestone. Complete every task in this milestone, then stop. Do not start the next milestone. Do tasks one at a time, committing and pushing each. When every task in the current milestone is checked, you are done for this session.

**Reads:** README.md, SPEC.md, TASKS.md, BUGS.md, REVIEWS.md  
**Writes code:** Yes  
**Commits:** After each bug fix, review fix, and task  
**Shutdown signal:** Writes `logs/builder.done` on exit

---

## Commit Watcher

Runs continuously via `commitwatch`, launched automatically by `go` and `resume`. Polls for new commits and spawns a scoped reviewer for each one.

**Persistent checkpoint:** The last-reviewed commit SHA is saved to `logs/reviewer.checkpoint` after each commit is processed. On restart, the watcher resumes from the checkpoint — no commits are ever missed or re-reviewed.

**Filtering:** Merge commits and the reviewer's own commits (REVIEWS.md-only changes) are automatically skipped to avoid wasted work.

For each new commit detected, the watcher enumerates all commits since the last checkpoint (`git log {last_sha}..HEAD --format=%H --reverse`) and reviews them one at a time using a commit-scoped prompt:

> You are a code reviewer. You must NOT add features or change functionality. Your only job is to review the changes in a single commit for quality issues. Read SPEC.md and TASKS.md ONLY to understand the project goals — do NOT review those files themselves. Run `git diff {prev_sha} {commit_sha}` to get the diff. This diff is your ONLY input for review — do NOT read entire source files, do NOT review code outside the diff. Focus exclusively on the added and modified lines. Look for: code duplication, unclear naming, overly complex logic, missing error handling, security issues, violations of conventions, and dead code. Only flag issues that meaningfully affect correctness, security, maintainability, or readability. Write findings to REVIEWS.md with the commit SHA. Commit with message 'Code review: {sha}', run git pull --rebase, and push.

**Milestone reviews:** When the watcher detects that all tasks under a `## Milestone:` heading in TASKS.md are checked, it triggers a cross-cutting review of the entire milestone's diff. This catches issues that per-commit reviews miss: inconsistent patterns across files, API mismatches, duplicated logic introduced across separate commits, and architectural problems in how pieces fit together. Milestone review findings are prefixed with `[Milestone: <name>]` in REVIEWS.md. Each milestone is only reviewed once (tracked in `logs/reviewer.milestone`).

> You are a code reviewer performing a milestone-level review. A milestone — '{milestone_name}' — has just been completed. Run `git diff {milestone_start_sha} {milestone_end_sha}` to see everything that changed. Review for cross-cutting concerns: inconsistent patterns, API mismatches, duplicated logic across commits, missing integration, naming inconsistencies, error handling gaps, and architectural issues. Write findings to REVIEWS.md prefixed with '[Milestone: {milestone_name}]'. Commit with message 'Milestone review: {milestone_name}', run git pull --rebase, and push.

**Trigger:** Polls every 10 seconds for new commits  
**Scope:** Per-commit diff for individual reviews; full milestone diff for milestone reviews  
**Checkpoint:** `logs/reviewer.checkpoint` (per-commit), `logs/reviewer.milestone` (per-milestone)  
**Skips:** Merge commits, reviewer's own REVIEWS.md-only commits  
**Runs from:** `reviewer/` clone  
**Shutdown:** Checks for `logs/builder.done` each cycle; exits when builder is done  
**Writes code:** No

---

## Tester

Runs on a 5-minute timer via `testloop`, launched automatically by `go` and `resume`. Tests the full repo at HEAD on each cycle.

> Read SPEC.md and TASKS.md to understand the project. Pull the latest code. Build the project. Run all existing tests. If there is a runnable API, start it, test the endpoints with curl, then stop it. Evaluate test coverage across the codebase. If there are major gaps — like no tests at all for a feature, or completely missing error handling tests — write a few focused tests to cover the most important gaps. Write at most 5 new tests per run. For any test that fails, write each failure to BUGS.md. Commit new tests and BUGS.md changes, run git pull --rebase, and push. If everything passes and no new tests are needed, do nothing.

**Trigger:** Every 5 minutes (configurable via `--interval`)  
**Scope:** Full repo at HEAD  
**Runs from:** `tester/` clone  
**Shutdown:** Checks for `logs/builder.done`; runs one final test pass, then exits  
**Writes code:** Tests only  
**Commits:** When it writes new tests or finds bugs

---

## Legacy Commands

The original `reviewoncommit` and `testoncommit` commands still exist for manual/standalone use. They use the old `_watch_loop` polling mechanism and are not launched by `go` or `resume`.

---

## Shutdown Protocol

All agents auto-shutdown when the builder finishes:

1. **Primary signal:** Builder writes `logs/builder.done` on exit (success, failure, or no-work).
2. **Crash fallback:** If `logs/builder.log` hasn't been modified in 10+ minutes, agents assume the builder crashed and shut down.
3. **Startup cleanup:** `go` and `resume` clear any stale `builder.done` sentinel before launching agents.
