# Agent Prompts

Each agent is a `copilot --yolo` call with a specific prompt. Here's exactly what each one is told to do.

---

## Bootstrap

Runs once internally when you call `go`. Do not run `bootstrap` directly — it is deprecated and will error.

> Create a directory called builder. cd into it. Initialize a git repo. Create an appropriate .gitignore for the project. Create a README.md that describes the project: `{description}`. A file called REQUIREMENTS.md already exists in this directory — it contains the original project requirements exactly as provided by the user. Do NOT modify or overwrite REQUIREMENTS.md. Use it as the primary input when writing SPEC.md. Create a SPEC.md that defines the desired end state of the project. SPEC.md should include: a high-level summary, the tech stack and language, the features and requirements, any constraints or guidelines, and acceptance criteria for what 'done' looks like. Be specific and thorough in SPEC.md — it is the source of truth that all future planning is based on. Every feature and requirement in REQUIREMENTS.md must be addressed in SPEC.md. Do NOT create a TASKS.md — task planning happens later. Commit with message 'Initial commit: project spec'. Run 'gh repo create `{user/name}` --public --source .' and push.

**Creates:** README.md, SPEC.md, REQUIREMENTS.md, git repo, GitHub remote  
**Writes code:** No

**Local mode (`--local`):** When `go` is called with `--local`, the bootstrap prompt replaces `gh repo create` with `git remote add origin {remote_path}` pointing to a local bare git repo. No GitHub CLI calls are made. The `--local` flag also skips the `gh` prerequisite checks and clones reviewer/tester copies from the local bare repo instead of GitHub.

**Note:** Before Copilot runs, the CLI pre-creates `builder/REQUIREMENTS.md` containing the original prompt or spec-file content verbatim. This file is committed with the rest of the bootstrap and never modified afterward.

---

## Planner

Runs on demand via `plan`. Call it before the first `build`, or whenever you need to re-evaluate the task list.

> You are a planning-only orchestrator. You must NOT write any code or modify any source files. Your only job is to manage TASKS.md. Read REQUIREMENTS.md first — this is the original requirements document provided by the user and is the ultimate source of truth for what must be built. Then read SPEC.md to understand the desired end state. Read README.md for project context. Look at the current codebase to see what has been built so far. Read BUGS.md if it exists to see outstanding bugs. Read REVIEWS.md if it exists to see outstanding review items. Read TASKS.md if it exists to see the current plan. Now evaluate: are there tasks that need to be added, broken down, reordered, or clarified based on what has been built vs what SPEC.md requires? Cross-check against REQUIREMENTS.md to ensure no features or requirements from the original prompt have been missed or dropped. If TASKS.md does not exist, create it with a detailed numbered checkbox task list that will achieve everything in SPEC.md and REQUIREMENTS.md. Group the tasks under milestone headings using the format `## Milestone: <name>`. Each milestone is the builder's unit of work — the builder will complete one entire milestone per session, then stop so the planner can re-evaluate. MILESTONE SIZING RULES (follow these strictly): Keep each milestone to at most 5 tasks. Each task should describe one logical change. If a task has 'and' connecting two distinct pieces of work, split it into two tasks. If a task requires creating something new AND integrating it elsewhere, make those separate tasks. If a feature area needs more than 5 tasks, split it into sequential milestones (e.g. 'User API: models and routes' then 'User API: validation and error handling'). If several small related pieces fit under 5 tasks, combine them into one milestone. Good milestones are things like 'Project scaffolding', 'Core data models', 'API endpoints', 'Authentication', 'Frontend views', 'Error handling and validation'. A milestone is considered complete when all its checkbox tasks are checked. The reviewer uses milestone boundaries to do cross-cutting code reviews, so organize milestones around code that interacts — put related tasks together even if they touch different files. TESTING: Do not create milestones for writing tests. A separate testing agent writes and runs tests after each milestone. Focus milestones on building features and functionality only. Include a final task to verify everything works end to end. Each task should be concrete and actionable, building on the last. Include a task early on to remove any default scaffolding or template code that does not belong. If TASKS.md already exists, update it — add missing tasks, refine vague ones, but never remove or uncheck completed tasks. Commit any changes to TASKS.md with message 'Update task plan', run git pull --rebase, and push. If no changes are needed, do nothing.

**Post-plan enforcement:** After the planner runs, the build loop checks milestone sizes. If any uncompleted milestone exceeds 5 tasks, the planner is re-invoked with a targeted split prompt. If still oversized after one retry, a warning is logged and the build proceeds.

**Creates:** TASKS.md (first run), updates it on subsequent runs  
**Reads:** SPEC.md, README.md, REQUIREMENTS.md, codebase, TASKS.md, BUGS.md, REVIEWS.md  
**Writes code:** No

---

## Copilot Instructions Generator

Runs once automatically after the first planner run (in both `go` and `resume`). Skipped if `.github/copilot-instructions.md` already exists.

> You are a documentation generator. You must NOT write any application code or modify any source files other than .github/copilot-instructions.md. Read SPEC.md to understand the tech stack, language, and architecture. Read TASKS.md to understand the planned components and milestones. Read REQUIREMENTS.md for the original project intent. Now create the file .github/copilot-instructions.md (create the .github directory if it doesn't exist). Fill in the project-specific sections (Project structure, Key files, Architecture, Conventions) based on SPEC.md and TASKS.md. Keep the coding guidelines and testing conventions sections exactly as provided in the template. Commit with message 'Add copilot instructions', run git pull --rebase, and push.

The generated file includes:
- **LLM-friendly coding guidelines** — universal rules for flat control flow, small functions, descriptive naming, no magic, etc.
- **Documentation maintenance rule** — instructs the builder to keep the instructions file updated as the project evolves.
- **Project-specific sections** — structure, key files, architecture, and conventions inferred from the plan.
- **Testing conventions** — universal rules for behavioral test naming, realistic inputs, regression tests, no mocking.

**Creates:** `.github/copilot-instructions.md`  
**Reads:** SPEC.md, TASKS.md, REQUIREMENTS.md  
**Writes code:** No

---

## Builder

Runs via `build`. Completes one milestone per cycle. Between milestones the planner re-evaluates the task list. Writes `logs/builder.done` when it exits so other agents know to shut down.

> Before starting, review README.md, SPEC.md, and TASKS.md to understand the project's purpose and plan. Read .github/copilot-instructions.md if it exists — follow its coding guidelines and conventions in all code you write. Only build, fix, or keep code that serves that purpose. Remove any scaffolding, template code, or functionality that does not belong. When completing a task that changes the project structure, key files, architecture, or conventions, update .github/copilot-instructions.md to reflect the change. Now look at BUGS.md first. Fix ALL unfixed bugs — bugs are never deferred. Fix them one at a time — fix a bug, mark it fixed in BUGS.md, commit with a meaningful message, run git pull --rebase, and push. Then look at REVIEWS.md. Address unchecked review items one at a time — fix the issue, mark it done in REVIEWS.md, commit, pull --rebase, and push. Once all bugs and review items are fixed (or if there are none), move to TASKS.md. TASKS.md is organized into milestones (sections headed with `## Milestone: <name>`). Find the first milestone that has unchecked tasks — this is your current milestone. Complete every task in this milestone, then stop. Do not start the next milestone. Do tasks one at a time. For each task: write the code AND mark it complete in TASKS.md, then commit both together in a single commit with a meaningful message. Do not make separate commits for the code and the checkbox update. After each commit, run git pull --rebase and push. When every task in the current milestone is checked, you are done for this session.

**Reads:** README.md, SPEC.md, TASKS.md, BUGS.md, REVIEWS.md, .github/copilot-instructions.md  
**Writes code:** Yes  
**Updates:** .github/copilot-instructions.md (when project structure changes)  
**Commits:** After each bug fix, review fix, and task  
**Shutdown signal:** Writes `logs/builder.done` on exit

---

## Commit Watcher

Runs continuously via `commitwatch`, launched automatically by `go` and `resume`. Polls for new commits and spawns a scoped reviewer for each one.

**Persistent checkpoint:** The last-reviewed commit SHA is saved to `logs/reviewer.checkpoint` after each commit is processed. On restart, the watcher resumes from the checkpoint — no commits are ever missed or re-reviewed.

**Filtering:** Merge commits and the reviewer's own commits (REVIEWS.md-only changes) are automatically skipped to avoid wasted work.

For each new commit detected, the watcher enumerates all commits since the last checkpoint (`git log {last_sha}..HEAD --format=%H --reverse`), filters out skippable commits (merges, reviewer-only, coordination-only), and reviews the remaining ones. If there is a single reviewable commit, it reviews that commit individually. If there are multiple reviewable commits (e.g. the builder pushed several commits while the reviewer was busy), it reviews them as a single batch using the combined diff — one Copilot call instead of N:

**Single commit prompt:**

> You are a code reviewer. You must NOT add features or change functionality. Your only job is to review the changes in a single commit for quality issues. Read SPEC.md and TASKS.md ONLY to understand the project goals — do NOT review those files themselves. Run `git diff {prev_sha} {commit_sha}` to get the diff. This diff is your ONLY input for review — do NOT read entire source files, do NOT review code outside the diff. Focus exclusively on the added and modified lines. Look for: code duplication, unclear naming, overly complex logic, missing error handling, security issues, violations of conventions, and dead code. Only flag issues that meaningfully affect correctness, security, maintainability, or readability. Write findings to REVIEWS.md with the commit SHA. Commit with message 'Code review: {sha}', run git pull --rebase, and push.

**Batched commits prompt (2+ commits):**

> You are a code reviewer. Your job is to review the combined changes from {commit_count} commits for quality issues. Read SPEC.md and TASKS.md ONLY to understand the project goals. Run `git log --oneline {base_sha}..{head_sha}` to see the commit messages. Run `git diff {base_sha} {head_sha}` to get the combined diff. This diff is your ONLY input for review. Focus exclusively on the added and modified lines. Look for: code duplication, unclear naming, overly complex logic, missing error handling, security issues, violations of conventions, and dead code. Only flag meaningful issues. Write findings to REVIEWS.md with the relevant commit SHA(s). Commit with message 'Code review: {base_sha:.8}..{head_sha:.8}', run git pull --rebase, and push.

**Milestone reviews:** When the watcher detects that all tasks under a `## Milestone:` heading in TASKS.md are checked, it triggers a cross-cutting review of the entire milestone's diff. This catches issues that per-commit reviews miss: inconsistent patterns across files, API mismatches, duplicated logic introduced across separate commits, and architectural problems in how pieces fit together. Milestone review findings are prefixed with `[Milestone: <name>]` in REVIEWS.md. Each milestone is only reviewed once (tracked in `logs/reviewer.milestone`).

> You are a code reviewer performing a milestone-level review. A milestone — '{milestone_name}' — has just been completed. Run `git diff {milestone_start_sha} {milestone_end_sha}` to see everything that changed. Review for cross-cutting concerns: inconsistent patterns, API mismatches, duplicated logic across commits, missing integration, naming inconsistencies, error handling gaps, and architectural issues. Write findings to REVIEWS.md prefixed with '[Milestone: {milestone_name}]'. Commit with message 'Milestone review: {milestone_name}', run git pull --rebase, and push.

**Trigger:** Polls every 10 seconds for new commits  
**Scope:** Per-commit diff for individual reviews; full milestone diff for milestone reviews  
**Checkpoint:** `logs/reviewer.checkpoint` (per-commit), `logs/reviewer.milestone` (per-milestone)  
**Skips:** Merge commits, coordination-only commits (TASKS.md, REVIEWS.md, BUGS.md only)  
**Runs from:** `reviewer/` clone  
**Shutdown:** Checks for `logs/builder.done` each cycle; exits when builder is done  
**Writes code:** No

---

## Tester

Milestone-triggered via `testloop`, launched automatically by `go` and `resume`. Watches `logs/milestones.log` for newly completed milestones and runs scoped tests for each one.

For each newly completed milestone:

> Read SPEC.md and TASKS.md to understand the project. A milestone — '{milestone_name}' — has just been completed. Pull the latest code with `git pull --rebase`. Run `git diff {milestone_start_sha} {milestone_end_sha} --name-only` to see which files changed in this milestone. Focus your testing on those files and the features they implement. Build the project. Run all existing tests. If there is a runnable API, start it, test the endpoints related to the changed files with curl, then stop it. Evaluate test coverage for the changed files and their related functionality. If there are major gaps — like no tests at all for a feature, or completely missing error handling tests — write focused tests to cover the most important gaps. Prioritize integration tests over unit tests. Each test should verify a distinct user-facing behavior. Do not test internal implementation details, getters/setters, or trivially obvious code. Write at most 10 new tests per run. For any test that fails, write each failure to BUGS.md. Only append new lines — never edit, reorder, or remove existing lines in BUGS.md. Commit new tests and BUGS.md changes, run git pull --rebase, and push. If the push fails, run git pull --rebase and push again (retry up to 3 times). If everything passes and no new tests are needed, do nothing.

When the builder finishes, the tester runs one final full test pass using the general tester prompt (not milestone-scoped) before shutting down.

**Trigger:** Polls `logs/milestones.log` every 10 seconds (configurable via `--interval`)  
**Scope:** Changed files per milestone; full repo for final pass  
**Checkpoint:** `logs/tester.milestone` (set of milestones already tested)  
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
