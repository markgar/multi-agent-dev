# Agent Prompts

Each agent is a `copilot --yolo` call with a specific prompt. Here's exactly what each one is told to do.

---

## Bootstrap

Runs once when you call `bootstrap "name" "description"`.

> Create a directory called builder. cd into it. Initialize a git repo. Create an appropriate .gitignore for the project. Create a README.md that describes the project: `{description}`. A file called REQUIREMENTS.md already exists in this directory — it contains the original project requirements exactly as provided by the user. Do NOT modify or overwrite REQUIREMENTS.md. Use it as the primary input when writing SPEC.md. Create a SPEC.md that defines the desired end state of the project. SPEC.md should include: a high-level summary, the tech stack and language, the features and requirements, any constraints or guidelines, and acceptance criteria for what 'done' looks like. Be specific and thorough in SPEC.md — it is the source of truth that all future planning is based on. Every feature and requirement in REQUIREMENTS.md must be addressed in SPEC.md. Do NOT create a TASKS.md — task planning happens later. Commit with message 'Initial commit: project spec'. Run 'gh repo create `{user/name}` --public --source .' and push.

**Creates:** README.md, SPEC.md, REQUIREMENTS.md, git repo, GitHub remote  
**Writes code:** No

**Note:** Before Copilot runs, the CLI pre-creates `builder/REQUIREMENTS.md` containing the original prompt or spec-file content verbatim. This file is committed with the rest of the bootstrap and never modified afterward.

---

## Planner

Runs on demand via `plan`. Call it before the first `build`, or whenever you need to re-evaluate the task list.

> You are a planning-only orchestrator. You must NOT write any code or modify any source files. Your only job is to manage TASKS.md. Read REQUIREMENTS.md first — this is the original requirements document provided by the user and is the ultimate source of truth for what must be built. Then read SPEC.md to understand the desired end state. Read README.md for project context. Look at the current codebase to see what has been built so far. Read BUGS.md if it exists to see outstanding bugs. Read REVIEWS.md if it exists to see outstanding review items. Read TASKS.md if it exists to see the current plan. Now evaluate: are there tasks that need to be added, broken down, reordered, or clarified based on what has been built vs what SPEC.md requires? Cross-check against REQUIREMENTS.md to ensure no features or requirements from the original prompt have been missed or dropped. If TASKS.md does not exist, create it with a detailed numbered checkbox task list that will achieve everything in SPEC.md and REQUIREMENTS.md. Each task should be concrete and actionable, building on the last. Include a task early on to remove any default scaffolding or template code that does not belong. Include a final task to verify everything works end to end. If TASKS.md already exists, update it — add missing tasks, refine vague ones, but never remove or uncheck completed tasks. Commit any changes to TASKS.md with message 'Update task plan', run git pull --rebase, and push. If no changes are needed, do nothing.

**Creates:** TASKS.md (first run), updates it on subsequent runs  
**Reads:** SPEC.md, README.md, REQUIREMENTS.md, codebase, TASKS.md, BUGS.md, REVIEWS.md  
**Writes code:** No

---

## Builder

Runs via `build`. Targets `--numtasks` tasks (default 5) per cycle but adapts based on complexity and milestones. Writes `logs/builder.done` when it exits so other agents know to shut down.

> Before starting, review README.md, SPEC.md, and TASKS.md to understand the project's purpose and plan. Only build, fix, or keep code that serves that purpose. Remove any scaffolding, template code, or functionality that does not belong. Now look at BUGS.md first. Fix ALL unfixed bugs regardless of the target — bugs are never deferred. Fix them one at a time — fix a bug, mark it fixed in BUGS.md, commit with a meaningful message, run git pull --rebase, and push. Then look at REVIEWS.md. Address unchecked review items one at a time — fix the issue, mark it done in REVIEWS.md, commit, pull --rebase, and push. Once all bugs and review items are fixed (or if there are none), move to TASKS.md. Before starting tasks, scan the upcoming unchecked tasks and assess their complexity. The target is `{numtasks}` tasks per session, but adapt: if tasks are simple, batch more (up to double the target); if a task is complex, do fewer. Look for natural milestones — if one more task finishes a logical milestone, push through even if past the target. If you just hit a major milestone and the next task starts a new area, stop early and let the planner re-evaluate. Do tasks one at a time, committing and pushing each. Stop when you've hit a good stopping point or when there is no more work.

**Reads:** README.md, SPEC.md, TASKS.md, BUGS.md, REVIEWS.md  
**Writes code:** Yes  
**Commits:** After each bug fix, review fix, and task  
**Shutdown signal:** Writes `logs/builder.done` on exit

---

## Commit Watcher

Runs continuously via `commitwatch`, launched automatically by `go` and `resume`. Polls for new commits and spawns a scoped reviewer for each one.

For each new commit detected, the watcher enumerates all commits since the last checkpoint (`git log {last_sha}..HEAD --format=%H --reverse`) and reviews them one at a time using a commit-scoped prompt:

> You are a code reviewer. You must NOT add features or change functionality. Your only job is to review the changes in a single commit for quality issues. Read SPEC.md and TASKS.md to understand the project goals. Run `git diff {prev_sha} {commit_sha}` to see exactly what changed. Review ONLY the code in this diff. Look for: code duplication, unclear naming, overly complex logic, missing error handling, security issues, violations of conventions, and dead code. Only flag issues that meaningfully affect correctness, security, maintainability, or readability. Write findings to REVIEWS.md with the commit SHA. Commit with message 'Code review: {sha}', run git pull --rebase, and push.

**Trigger:** Polls every 10 seconds for new commits  
**Scope:** Exactly one commit's diff per review  
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
