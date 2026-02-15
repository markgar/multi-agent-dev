# Agent Prompts

Each agent is a `copilot --yolo` call with a specific prompt. Here's exactly what each one is told to do.

---

## Bootstrap

Runs once internally when you call `go`. Do not run `bootstrap` directly — it is deprecated and will error.

> Create a directory called builder. cd into it. Initialize a git repo. Create an appropriate .gitignore for the project. Create a brief README.md (~15 lines) — what the project is, how to build and run it, and how to develop. Do not describe features in detail — REQUIREMENTS.md and SPEC.md cover that. A file called REQUIREMENTS.md already exists in this directory — it contains the original project requirements exactly as provided by the user. Do NOT modify or overwrite REQUIREMENTS.md. Use it as the primary input when writing SPEC.md. Create a SPEC.md that captures TECHNICAL DECISIONS only (~40-60 lines). SPEC.md should include: (1) a high-level summary, (2) the tech stack and language choices, (3) the architecture approach — layers, dependency rules, project structure, (4) cross-cutting concerns — authentication strategy, multi-tenancy approach, error handling conventions, (5) acceptance criteria at the feature level (e.g. 'members can be managed') not the field level. Do NOT include entity field definitions, API route tables, page layouts, or DTO shapes in SPEC.md — those details will be planned progressively as features are built. REQUIREMENTS.md is the authoritative source for feature details — SPEC.md captures the technical decisions for how to build them. Do NOT create a TASKS.md — task planning happens later. Commit with message '[bootstrap] Initial commit: project spec'. Run 'gh repo create `{user/name}` --public --source .' and push.

**Creates:** README.md, SPEC.md, REQUIREMENTS.md, git repo, GitHub remote  
**Writes code:** No

**Local mode (`--local`):** When `go` is called with `--local`, the bootstrap prompt replaces `gh repo create` with `git remote add origin {remote_path}` pointing to a local bare git repo. No GitHub CLI calls are made. The `--local` flag also skips the `gh` prerequisite checks and clones reviewer/tester/validator copies from the local bare repo instead of GitHub.

**Note:** Before Copilot runs, the CLI pre-creates `builder/REQUIREMENTS.md` containing the prompt or spec-file content verbatim. This file is committed with the rest of the bootstrap. In later sessions, `go` may overwrite REQUIREMENTS.md with new requirements before re-planning.

---

## Planner

Runs on demand via `plan`. Called automatically by `go` before the first build cycle, and called again by the build loop between milestones to expand the next backlog story.

The planner manages three files: **BACKLOG.md** (ordered story queue), **TASKS.md** (current and completed milestones), and **SPEC.md** (technical decisions). It plans **one milestone at a time** — never multiple milestones in a single run.

The planner uses different prompts depending on the project state:

### Initial Planning (fresh project)

When no BACKLOG.md exists, the planner runs two focused Copilot calls:

1. **Backlog creation** — Reads REQUIREMENTS.md and SPEC.md, decomposes all requirements into an ordered story queue (BACKLOG.md) with dependency annotations, checks off the first story, and writes the first milestone in TASKS.md.
2. **Completeness check** — A separate Copilot call reviews the backlog against REQUIREMENTS.md and SPEC.md. It walks through every section and subsection to verify coverage. Any gaps (missing feature stories, uncovered technical concerns like API client generation, seed data, navigation structure) are added as new stories.

This two-step approach prevents the LLM from self-validating — the completeness pass reviews with fresh eyes.

### Continuing Planning (between milestones)

When BACKLOG.md already exists, the planner determines which situation applies:

- **(B) Continuing project** — a milestone was just completed. BACKLOG.md and TASKS.md exist. Reads the codebase to understand what patterns emerged (base classes, naming conventions, dependency injection wiring). Finds the next eligible unchecked story in BACKLOG.md (all dependencies checked), checks it off, and appends one new `## Milestone:` to TASKS.md.
- **(C) Evolving project** — REQUIREMENTS.md contains features or requirements not reflected in BACKLOG.md stories or SPEC.md technical decisions. This means new requirements have been added. Updates SPEC.md to incorporate any new technical decisions. Adds new stories to BACKLOG.md for the new features. The default is additive — existing features stay in SPEC.md unless REQUIREMENTS.md explicitly asks to remove or replace them. Silence about an existing feature is not a removal request. Then proceeds to Case B logic.

In both cases, the planner looks at the actual codebase to understand what is already built — it does not rely only on checked tasks.

### BACKLOG.md

BACKLOG.md is a planner-owned, numbered, ordered story queue. Each entry:

```
N. [x] Story name <!-- depends: 1, 2 -->
```

- `[ ]` = in backlog (not yet planned), `[x]` = planned into TASKS.md
- `<!-- depends: N -->` = HTML comment listing story numbers this depends on
- The first story is always scaffolding (project structure, entry point, health endpoint)
- Stories are ordered so each builds on predecessors, preferring vertical feature slices — each story delivers one feature through all layers (entity → repository → service → API → frontend) rather than building one layer across all features.
- The builder never reads or writes BACKLOG.md — only the planner and orchestrator touch it.

### Planning Rules

- **One milestone per run.** The planner writes exactly one new `## Milestone:` section in TASKS.md each time it runs. It does not plan ahead or create multiple milestones at once.
- **Detail in task descriptions.** Instead of "Create Member entity", write "Create Member entity (Id, FirstName, LastName, Email, Role enum, IsActive, OrganizationId)". The builder should not need to cross-reference SPEC.md or REQUIREMENTS.md.
- **Task sizing.** Each task describes one logical change — one concept, one concern, one commit. If a task contains "and", "with", or a comma connecting distinct work, it is too big — split it.
- **Milestone sizing.** A well-sized milestone typically has 3-7 tasks. Under 3 suggests tasks might be too coarse. Over 8 suggests a natural split point exists.
- **Runnable after every milestone.** Each milestone must leave the app in a buildable, startable state.
- **No test or container tasks.** The tester and validator agents handle those separately.
- **Milestone acceptance context.** Each `## Milestone:` heading must be followed by a `> **Validates:**` blockquote describing what the validator should test — endpoint paths, HTTP methods, expected status codes, pages that should render, CLI commands. This is the validator's primary test plan.
- **Read the codebase first (cases B/C).** Match existing patterns — if a BaseRepository<T> exists, use it; if DTOs are records, make new DTOs records.

> **Initial planning prompt:** You are a planning-only orchestrator. Your job is to decompose a project's requirements into a complete backlog of stories, then plan the first milestone. [...story decomposition rules, task sizing, milestone sizing, detail requirements, containerization/testing exclusions...]

> **Completeness check prompt:** You are a planning quality reviewer. Your ONLY job is to verify that BACKLOG.md completely covers REQUIREMENTS.md and SPEC.md. Walk through every ## and ### heading in REQUIREMENTS.md. For each section, verify at least one story covers it. Also check SPEC.md for technical decisions that require setup work. If gaps exist, add stories. [...gap identification, renumbering rules...]

> **Continuing planning prompt:** You are a planning-only orchestrator. Your job is to manage BACKLOG.md, SPEC.md, and TASKS.md. ASSESS THE PROJECT STATE. Determine: (B) Continuing — find next eligible story, expand into milestone. (C) Evolving — update SPEC.md, add new stories, then do Case B. [...task sizing, milestone sizing, detail requirements, codebase reading...]

**Post-plan enforcement:** After the planner runs, the build loop checks milestone sizes. If any uncompleted milestone exceeds 10 tasks, the planner is re-invoked with a targeted split prompt. If still oversized after one retry, a warning is logged and the build proceeds.

**Between-milestone re-planning:** After each milestone completes, the build loop calls the planner again to expand the next backlog story. If no eligible story exists (all remaining stories have unmet dependencies), a dependency deadlock warning is logged. If the backlog is empty, the build is done.

**Creates:** BACKLOG.md (first run), TASKS.md (first run)  
**Updates:** BACKLOG.md (checks off stories), TASKS.md (appends milestones), SPEC.md (when new requirements are detected — case C)  
**Reads:** SPEC.md, REQUIREMENTS.md, BACKLOG.md, TASKS.md, codebase  
**Writes code:** No

---

## Copilot Instructions Generator

Runs once automatically after the first planner run. Skipped if `.github/copilot-instructions.md` already exists.

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

Runs via `build`. Completes one milestone per cycle, then stops. Between milestones the build loop calls the planner to expand the next backlog story. After all stories are done, waits for the reviewer, tester, and validator to go idle and verifies that all checklists are clean before writing `logs/builder.done` to signal shutdown.

> Before starting, review README.md, SPEC.md, and TASKS.md to understand the project's purpose and plan. Read .github/copilot-instructions.md if it exists — follow its coding guidelines and conventions in all code you write. Read DEPLOY.md if it exists — it contains deployment configuration and lessons learned from the validator agent. If it mentions required env vars, ports, or startup requirements, ensure your code is compatible. Do NOT modify DEPLOY.md — only the validator agent manages that file. Only build, fix, or keep code that serves that purpose. Remove any scaffolding, template code, or functionality that does not belong. After any refactoring — including review fixes — check for dead code left behind and remove it. Before your first commit in each session, review .gitignore and ensure it covers the project's current tech stack; update it when you introduce a new framework or build tool. When completing a task that changes the project structure, key files, architecture, or conventions, update .github/copilot-instructions.md to reflect the change (it is a style guide — describe file roles and coding patterns, not implementation details). Now look at BUGS.md first. Fix ALL unfixed bugs — bugs are never deferred. Then look at REVIEWS.md. Address unchecked review items one at a time. Once all bugs and review items are fixed, move to TASKS.md. Find the first milestone that has unchecked tasks — this is your current milestone. Complete every task in this milestone, then STOP IMMEDIATELY. Do not continue to the next milestone. For each task: write the code AND mark it complete in TASKS.md, then commit BOTH together in a single commit with a meaningful message. After each commit, run git pull --rebase and push. When every task in the current milestone is checked, verify the application still builds and runs. Once verified, you are done for this session.

**Reads:** README.md, SPEC.md, TASKS.md, BUGS.md, REVIEWS.md, DEPLOY.md, .github/copilot-instructions.md  
**Writes code:** Yes  
**Updates:** .github/copilot-instructions.md (when project structure changes), .gitignore (when tech stack changes)  
**Commits:** After each bug fix, review fix, and task (prefixed with `[builder]`)  
**Shutdown signal:** Waits for agents to idle, then writes `logs/builder.done`

---

## Commit Watcher

Runs continuously via `commitwatch`, launched automatically by `go`. Polls for new commits and spawns a scoped reviewer for each one.

**Persistent checkpoint:** The last-reviewed commit SHA is saved to `logs/reviewer.checkpoint` after each commit is processed. On restart, the watcher resumes from the checkpoint — no commits are ever missed or re-reviewed.

**Filtering:** Merge commits and the reviewer's own commits (REVIEWS.md-only changes) are automatically skipped to avoid wasted work.

For each new commit detected, the watcher enumerates all commits since the last checkpoint (`git log {last_sha}..HEAD --format=%H --reverse`), filters out skippable commits (merges, reviewer-only, coordination-only), and reviews the remaining ones. If there is a single reviewable commit, it reviews that commit individually. If there are multiple reviewable commits (e.g. the builder pushed several commits while the reviewer was busy), it reviews them as a single batch using the combined diff — one Copilot call instead of N:

**Single commit prompt:**

> You are a code reviewer. You must NOT add features or change functionality. Your only job is to review the changes in a single commit for quality issues. Read SPEC.md and TASKS.md ONLY to understand the project goals — do NOT review those files themselves. Run `git diff {prev_sha} {commit_sha}` to get the diff. This diff is your ONLY input for review — do NOT read entire source files, do NOT review code outside the diff. Focus exclusively on the added and modified lines. Look for: code duplication, unclear naming, overly complex logic, missing error handling, security issues, violations of conventions, and dead code. Only flag issues that meaningfully affect correctness, security, maintainability, or readability. NON-CODE ISSUES — [doc]: If you find a non-code issue — stale documentation, misleading comments, outdated DEPLOY.md bullets, inaccurate README content — fix it directly yourself instead of filing it to REVIEWS.md. Commit the fix with a descriptive message. CODE ISSUES — [code]: If you find a code-level issue that requires changing application logic, write it to REVIEWS.md with the commit SHA. Commit with message 'Code review: {sha}', run git pull --rebase, and push.

**Batched commits prompt (2+ commits):**

> You are a code reviewer. Your job is to review the combined changes from {commit_count} commits for quality issues. Read SPEC.md and TASKS.md ONLY to understand the project goals. Run `git log --oneline {base_sha}..{head_sha}` to see the commit messages. Run `git diff {base_sha} {head_sha}` to get the combined diff. This diff is your ONLY input for review. Focus exclusively on the added and modified lines. Look for: code duplication, unclear naming, overly complex logic, missing error handling, security issues, violations of conventions, and dead code. Only flag meaningful issues. NON-CODE ISSUES — [doc]: If you find a non-code issue — stale documentation, misleading comments, outdated DEPLOY.md bullets, inaccurate README content — fix it directly yourself instead of filing it to REVIEWS.md. Commit the fix with a descriptive message. CODE ISSUES — [code]: If you find a code-level issue that requires changing application logic, write it to REVIEWS.md with the relevant commit SHA(s). Commit with message 'Code review: {base_sha:.8}..{head_sha:.8}', run git pull --rebase, and push.

**Milestone reviews:** When the watcher detects that all tasks under a `## Milestone:` heading in TASKS.md are checked, it triggers a cross-cutting review of the entire milestone's diff. This catches issues that per-commit reviews miss: inconsistent patterns across files, API mismatches, duplicated logic introduced across separate commits, and architectural problems in how pieces fit together. Milestone review findings are prefixed with `[Milestone: <name>]` in REVIEWS.md. Each milestone is only reviewed once (tracked in `logs/reviewer.milestone`). The milestone reviewer also cleans up stale review items — marking already-resolved items as checked.

> You are a code reviewer performing a milestone-level review. A milestone — '{milestone_name}' — has just been completed. Run `git diff {milestone_start_sha} {milestone_end_sha}` to see everything that changed. Review for cross-cutting concerns: inconsistent patterns, API mismatches, duplicated logic across commits, missing integration, naming inconsistencies, error handling gaps, and architectural issues. STALE REVIEW CLEANUP: Before filing new items, read the existing unchecked items in REVIEWS.md. For each unchecked item, check whether the issue it describes has already been resolved in the current code. If it has, mark it as checked ([x]). Do not re-file issues that are already listed. NON-CODE ISSUES — [doc]: Fix non-code issues (stale docs, misleading comments, outdated README/DEPLOY.md) directly yourself instead of filing to REVIEWS.md. CODE ISSUES — [code]: Write code-level findings to REVIEWS.md prefixed with '[Milestone: {milestone_name}]'. Commit with message 'Milestone review: {milestone_name}', run git pull --rebase, and push.

**Trigger:** Polls every 10 seconds for new commits  
**Scope:** Per-commit diff for individual reviews; full milestone diff for milestone reviews  
**Checkpoint:** `logs/reviewer.checkpoint` (per-commit), `logs/reviewer.milestone` (per-milestone)  
**Skips:** Merge commits, coordination-only commits (TASKS.md, REVIEWS.md, BUGS.md only)  
**Runs from:** `reviewer/` clone  
**Shutdown:** Checks for `logs/builder.done` each cycle; completes any remaining milestone reviews before exiting  
**Writes code:** [doc] fixes only (comments, README, DEPLOY.md). Never changes application logic.

---

## Tester

Milestone-triggered via `testloop`, launched automatically by `go`. Watches `logs/milestones.log` for newly completed milestones and runs scoped tests for each one.

For each newly completed milestone:

> Read SPEC.md and TASKS.md to understand the project. A milestone — '{milestone_name}' — has just been completed. Pull the latest code with `git pull --rebase`. Run `git diff {milestone_start_sha} {milestone_end_sha} --name-only` to see which files changed in this milestone. Focus your testing on those files and the features they implement. Build the project. Run all existing tests. Evaluate test coverage for the changed files and their related functionality. If there are major gaps — like no tests at all for a feature, or completely missing error handling tests — write focused tests to cover the most important gaps. Prioritize integration tests over unit tests. Each test should verify a distinct user-facing behavior. Do not test internal implementation details, getters/setters, or trivially obvious code. Write at most 10 new tests per run. Do NOT start the application, start servers, or test live endpoints — a separate validator agent handles runtime testing in containers. Focus exclusively on running the test suite. For any test that fails, write each failure to BUGS.md. Only append new lines — never edit, reorder, or remove existing lines in BUGS.md. Commit new tests and BUGS.md changes, run git pull --rebase, and push. If the push fails, run git pull --rebase and push again (retry up to 3 times). If everything passes and no new tests are needed, do nothing.

When the builder finishes, the tester sees `logs/builder.done` and exits.

**Trigger:** Polls `logs/milestones.log` every 10 seconds (configurable via `--interval`)  
**Scope:** Changed files per milestone  
**Checkpoint:** `logs/tester.milestone` (set of milestones already tested)  
**Runs from:** `tester/` clone  
**Shutdown:** Checks for `logs/builder.done`; exits when builder is done  
**Writes code:** Tests only  
**Commits:** When it writes new tests or finds bugs

---

## Validator

Milestone-triggered via `validateloop`, launched automatically by `go`. Watches `logs/milestones.log` for newly completed milestones and validates the application in a Docker container.

For each newly completed milestone:

> You are a deployment validator. Your job is to build the application in a Docker container, run it, and verify it works against the acceptance criteria in SPEC.md. FIRST: Read DEPLOY.md if it exists — it contains everything previous runs learned about building and deploying this application. Follow its instructions for Dockerfile configuration, environment variables, port mappings, startup sequence, and known gotchas. Read SPEC.md for acceptance criteria. Read TASKS.md to see which milestones are complete — you should test all requirements that should be working up to and including milestone '{milestone_name}'. First stop and remove any running containers from previous runs. If no Dockerfile exists, create one appropriate for the project's tech stack. Build the container. Start it. Wait for the app to be healthy. Test every SPEC.md requirement that should be working at this point — for milestone 1, just confirm the app starts and responds; for later milestones, test accumulated functionality. Tear down containers after testing. Report failures to BUGS.md. Update DEPLOY.md with everything learned about deploying this application. Commit and push.

**Milestone SHA checkout:** Before validating, the validator checks out the exact commit at the milestone's end SHA (`git checkout {end_sha}`). This ensures each milestone is tested against exactly the code that existed when it was completed, not code from later milestones. After validation, it returns to the main branch.

**Persistent deployment knowledge:** The validator reads DEPLOY.md at the start of each run and updates it at the end. This creates a ratchet effect — each milestone's validation run gets more reliable because it inherits knowledge from all prior runs. DEPLOY.md captures: Dockerfile configuration, required environment variables, port mappings, docker-compose service setup, startup sequence, health check details, and known gotchas. The builder also reads DEPLOY.md to stay compatible with deployment requirements.

**Validation results log:** After each milestone, the validator writes `validation-results.txt` in the repo root (not committed). The Python orchestration copies it to `logs/validation-<milestone-name>.txt` for post-run analysis. Each line is `PASS` or `FAIL` with a description of what was tested (container build, startup, endpoints, error cases).

When the builder finishes, the validator sees `logs/builder.done` and exits.

**Trigger:** Polls `logs/milestones.log` every 10 seconds (configurable via `--interval`)  
**Scope:** All SPEC.md requirements that should work at the current milestone  
**Checkpoint:** `logs/validator.milestone` (set of milestones already validated)  
**Runs from:** `validator/` clone  
**Shutdown:** Checks for `logs/builder.done`; exits when builder is done  
**Writes code:** Dockerfile, docker-compose.yml (if needed), DEPLOY.md  
**Commits:** When it creates/updates deployment files, finds bugs, or updates DEPLOY.md

---

## Agent Coordination Rules

- **Commit message tagging:** Every agent prefixes its commit messages with its name in brackets — `[builder]`, `[reviewer]`, `[tester]`, `[validator]`, `[planner]`, `[bootstrap]`. This makes it easy to see who did what in `git log`.
- The **Planner** runs on demand via `plan`. It assesses project state (fresh / continuing / evolving), manages BACKLOG.md (story queue with dependency tracking), updates SPEC.md if new requirements are detected, then creates or updates the task list one milestone at a time. It never writes application code.
- The **Builder** checks `BUGS.md` first (all bugs are fixed before any tasks), then `REVIEWS.md`, then completes the current milestone. One milestone per cycle, then the planner expands the next backlog story.
- The **Reviewer** reviews each commit individually, plus a cross-cutting review when a milestone completes. Non-code issues ([doc]: stale docs, misleading comments) are fixed directly by the reviewer. Code-level issues ([code]) are filed to REVIEWS.md for the builder. Milestone reviews clean up stale/already-resolved review items.
- The **Tester** runs scoped tests when a milestone completes, focusing on changed files. It runs the test suite only — it does not start the app or test live endpoints. Exits when the builder finishes.
- The **Validator** builds the app in a Docker container after each milestone, starts it, and tests it against SPEC.md acceptance criteria. Persists deployment knowledge in DEPLOY.md. Exits when the builder finishes.
- Neither the Reviewer nor Tester duplicate items already in their respective files.
- All agents run `git pull --rebase` before pushing to avoid merge conflicts. If rebase fails with conflicts (e.g. two agents edited DEPLOY.md or BUGS.md concurrently), agents recover automatically: abort the rebase, stash local changes, pull fresh, pop the stash, and keep the local version for any conflicted files.
- `SPEC.md` is the source of truth for technical decisions. `BACKLOG.md` is the story queue. Edit either anytime to steer the project — run `plan` to adapt the task list.

---

## Iterative Development

`go` supports iterative sessions. You can build a project in phases:

1. **Session 1:** `go --directory my-app --spec-file api-spec.md --local` — bootstraps project, builds API
2. **Session 2:** `go --directory my-app --spec-file frontend-spec.md --local` — detects existing repo, clones agent directories, overwrites REQUIREMENTS.md with frontend spec, planner updates SPEC.md and creates new milestones, builder implements frontend
3. **Session 3:** `go --directory my-app --local` — continues where it left off (no new requirements)

`go` uses repo-first detection: it checks whether the repo already exists (locally via `remote.git/`, or on GitHub via `gh repo view`) rather than checking for local clone directories. This means:

- **Repo exists, agent dirs exist:** pulls all clones, plans, builds (standard resume)
- **Repo exists, agent dirs missing:** clones all agents from the repo, then continues (fresh-machine resume)
- **No repo:** bootstraps from scratch (requires `--spec-file` or `--description`)

Agent directories (`builder/`, `reviewer/`, `tester/`, `validator/`) are treated as disposable working copies — they can be recreated from the repo at any time. The repo (GitHub or `remote.git/`) and `logs/` directory (checkpoints) are the persistent state.

The `--spec-file` for session 2 can contain just new requirements ("Add a React frontend") or a complete updated requirements doc (old API spec + new frontend spec). The planner compares REQUIREMENTS.md against SPEC.md and the codebase to determine what's new.

---

## Legacy Commands

The original `reviewoncommit` and `testoncommit` commands still exist for manual/standalone use. They use the old `_watch_loop` polling mechanism and are not launched by `go`.

---

## Shutdown Protocol

The builder waits for all agents to finish before exiting:

1. **Builder completes all milestones:** After the last milestone, the builder enters a wait loop.
2. **Wait for agents to go idle:** The builder monitors `logs/reviewer.log`, `logs/tester.log`, and `logs/validator.log` modification times. When all logs haven't changed in 120+ seconds, agents are considered idle.
3. **Check work lists:** The builder pulls latest and checks `BUGS.md`, `REVIEWS.md`, and `TASKS.md` for unchecked items.
4. **Fix or exit:** If new work was filed (bugs from tester/validator, reviews from reviewer), the builder fixes it (up to 4 fix-only cycles) and loops back to step 2. If checklists are clean and agents are idle, the builder writes `logs/builder.done` and exits.
5. **Agents shut down:** The reviewer, tester, and validator see `logs/builder.done` on their next poll cycle. The reviewer completes any remaining milestone reviews before exiting. The tester and validator exit immediately.
6. **Crash fallback:** If `logs/builder.log` hasn't been modified in 30+ minutes, agents assume the builder crashed and shut down.
7. **Startup cleanup:** `go` clears any stale `builder.done` sentinel before launching agents.
8. **Timeout safety:** If agents don't go idle within 10 minutes, the builder writes `builder.done` and exits anyway.
