# Agent Prompts

Each agent is a `copilot --yolo` call with a specific prompt. Here's exactly what each one is told to do.

---

## Orchestrator

The `go` command is the single entry point. It detects project state, bootstraps or resumes, and launches all agents. Users never call individual agent commands directly — `go` handles everything.

### New project flow

When no repo exists (requires `--spec-file` or `--description`):

1. **Bootstrap** — runs Copilot to create the repo (README.md, SPEC.md, REQUIREMENTS.md)
2. **Migrate builder** — renames `builder/` to `builder-1/` for multi-builder consistency
3. **Clone additional builders** — if `--builders N` with N > 1, clones `builder-2/` through `builder-N/`
4. **Launch agents and build** — see launch sequence below

### Existing project flow

When the repo already exists (detected via `remote.git/` locally or `gh repo view` on GitHub):

1. **Migrate legacy builder** — renames `builder/` to `builder-1/` if needed
2. **Clone all agents** — creates any missing agent directories (`builder-N/`, `reviewer/`, `milestone-reviewer/`, `tester/`, `validator/`) from the repo
3. **Pull all clones** — `git pull --rebase` on every agent directory
4. **Update requirements** — if `--spec-file` or `--description` provided, overwrites `REQUIREMENTS.md`, commits, and pushes
5. **Launch agents and build** — see launch sequence below

### Launch sequence

`_launch_agents_and_build()` runs the following steps in order:

1. **Clear sentinels** — removes stale `logs/builder-N.done` files from previous runs
2. **Run backlog planner** — creates `BACKLOG.md` (fresh project) or plans the next milestone (continuing project). If planning fails, aborts.
3. **Check milestone sizes** — splits any milestone exceeding 8 tasks
4. **Generate copilot-instructions** — creates `.github/copilot-instructions.md` if it doesn't exist (skipped on resume)
5. **Spawn agents in terminal windows** — one terminal per agent, in this order:
   - Reviewer-1 through Reviewer-N (`reviewer-N/` clone → `commitwatch --builder-id N`) — one branch-attached reviewer per builder
   - Milestone reviewer (`milestone-reviewer/` clone → `milestonewatch`)
   - Tester (`tester/` clone → `testloop`)
   - Validator (`validator/` clone → `validateloop --project-name <name>`)
   - Builder-1 through Builder-N (`builder-N/` clone → `build --loop --builder-id N`)
6. **Stagger builders** — 30-second delay between each builder launch so builder-1 reliably claims story #1 before builder-2 starts
7. **Wait for completion** — polls `is_builder_done()` every 15 seconds until all builders have written their sentinel files

### Model and environment

The `--model` flag is validated against allowed models (`gpt-5.3-codex`, `claude-opus-4.6`, `claude-opus-4.6-fast`) and exported as `COPILOT_MODEL` for all agent subprocesses to use.

**Implements:** `src/agentic_dev/orchestrator.py`  
**Delegates to:** `bootstrap.py`, `planner.py`, `sentinel.py`, `terminal.py`  
**Writes code:** No

---

## Bootstrap

Runs once internally when you call `go`. Do not run `bootstrap` directly — it is deprecated and will error.

> Create a directory called builder. cd into it. Initialize a git repo. Create an appropriate .gitignore for the project. Create a brief README.md (~15 lines) — what the project is, how to build and run it, and how to develop. Do not describe features in detail — REQUIREMENTS.md and SPEC.md cover that. A file called REQUIREMENTS.md already exists in this directory — it contains the original project requirements exactly as provided by the user. Do NOT modify or overwrite REQUIREMENTS.md. Use it as the primary input when writing SPEC.md. Create a SPEC.md that captures TECHNICAL DECISIONS only (~40-60 lines). SPEC.md should include: (1) a high-level summary, (2) the tech stack and language choices, (3) the architecture approach — layers, dependency rules, project structure, (4) cross-cutting concerns — authentication strategy, multi-tenancy approach, error handling conventions, (5) acceptance criteria at the feature level (e.g. 'members can be managed') not the field level. Do NOT include entity field definitions, API route tables, page layouts, or DTO shapes in SPEC.md — those details will be planned progressively as features are built. REQUIREMENTS.md is the authoritative source for feature details — SPEC.md captures the technical decisions for how to build them. Do NOT create a TASKS.md — task planning happens later. Commit with message '[bootstrap] Initial commit: project spec'. Run 'gh repo create `{user/name}` --public --source .' and push.

**Creates:** README.md, SPEC.md, REQUIREMENTS.md, git repo, GitHub remote  
**Writes code:** No

**Local mode (`--local`):** When `go` is called with `--local`, the bootstrap prompt replaces `gh repo create` with `git remote add origin {remote_path}` pointing to a local bare git repo. No GitHub CLI calls are made. The `--local` flag also skips the `gh` prerequisite checks and clones reviewer/tester/validator copies from the local bare repo instead of GitHub.

**Note:** Before Copilot runs, the CLI pre-creates `builder/REQUIREMENTS.md` containing the prompt or spec-file content verbatim. This is committed with the rest of the bootstrap. In later sessions, `go` may overwrite REQUIREMENTS.md with new requirements before re-planning.

---

## Planner

Runs on demand via `plan`. Called automatically by `go` before the first build cycle (as the **Backlog Planner**), and called again by the build loop between milestones (as the **Milestone Planner**) to expand the next backlog story.

The planner manages three files: **BACKLOG.md** (ordered story queue), **milestone files in `milestones/`** (one file per story), and **SPEC.md** (technical decisions). It plans **one milestone at a time** — never multiple milestones in a single run.

The planner uses different prompts depending on the project state:

### Backlog Planning (fresh project)

When no BACKLOG.md exists, the planner runs two focused Copilot calls:

1. **Backlog creation** — Reads REQUIREMENTS.md and SPEC.md, decomposes all requirements into an ordered story queue (BACKLOG.md) with dependency annotations. No stories are checked off and no milestone files are created — builders claim and plan stories themselves.
2. **Completeness check** — A separate Copilot call reviews the backlog against REQUIREMENTS.md and SPEC.md. It walks through every section and subsection to verify coverage. Any gaps (missing feature stories, uncovered technical concerns like API client generation, seed data, navigation structure) are added as new stories.

This two-step approach prevents the LLM from self-validating — the completeness pass reviews with fresh eyes.

### Milestone Planning (between milestones)

When BACKLOG.md already exists, the planner determines which situation applies:

- **(B) Continuing project** — a milestone was just completed. BACKLOG.md and milestone files exist. Reads the codebase to understand what patterns emerged (base classes, naming conventions, dependency injection wiring). Finds the next eligible unchecked story in BACKLOG.md (all dependencies completed), checks it off, and writes a new milestone file in `milestones/`.
- **(C) Evolving project** — REQUIREMENTS.md contains features or requirements not reflected in BACKLOG.md stories or SPEC.md technical decisions. This means new requirements have been added. Updates SPEC.md to incorporate any new technical decisions. Adds new stories to BACKLOG.md for the new features. The default is additive — existing features stay in SPEC.md unless REQUIREMENTS.md explicitly asks to remove or replace them. Silence about an existing feature is not a removal request. Then proceeds to Case B logic.

In both cases, the planner looks at the actual codebase to understand what is already built — it does not rely only on checked tasks.

### BACKLOG.md

BACKLOG.md is a planner-owned, numbered, ordered story queue. Each entry:

```
N. [x] Story name <!-- depends: 1, 2 -->
```

- `[ ]` = in backlog (unclaimed), `[N]` = claimed by builder N (in progress), `[x]` = completed
- `<!-- depends: N -->` = HTML comment listing story numbers this depends on
- Dependencies require `[x]` (completed) — `[N]` (claimed) does NOT satisfy dependencies
- Dependencies must be **minimal** — only mark a dependency when the story cannot compile or function without the other story's code artifacts (imports, types, interfaces). Do NOT add dependencies for eventual integration — integration happens in whichever story is built second.
- The first story is always scaffolding (project structure, entry point, health endpoint)
- Stories are ordered so each builds on predecessors, preferring vertical feature slices — each story delivers one feature through all layers (entity → repository → service → API → frontend) rather than building one layer across all features.
- The builder claims stories via git-based optimistic locking: mark `[N]` (where N is the builder number), commit, push. If push fails (another builder claimed first), pull and try the next eligible story. Using the builder number instead of a generic marker ensures concurrent claims produce different text on the same line, causing a git merge conflict that prevents double-claims.

### Planning Rules

- **One milestone per run.** The planner writes exactly one new milestone file in `milestones/` each time it runs. It does not plan ahead or create multiple milestones at once.
- **Minimal dependencies for parallelism.** Multiple builders work concurrently — the dependency graph directly controls throughput. Only annotate a dependency when a story literally cannot compile without the other story's artifacts. Example: a Members API needs the Organization entity (import dependency) but does NOT need auth middleware — the controller can be built without auth, and auth is wired in when the auth story completes. The goal is the widest possible dependency graph.
- **Detail in task descriptions.** Instead of "Create Member entity", write "Create Member entity (Id, FirstName, LastName, Email, Role enum, IsActive, OrganizationId)". The builder should not need to cross-reference SPEC.md or REQUIREMENTS.md.
- **Story sizing = session sizing.** One story = one milestone = one Copilot CLI session. Size stories so a single session can complete one without losing focus. A story is too small if it's just a config change or a single file edit — merge it into its natural neighbor. A story is too big if completing it requires switching between unrelated concerns. Keep backend and frontend together when tightly coupled; split them when either half is substantial enough to be its own session. When in doubt, prefer smaller stories.
- **Task sizing.** Each task describes one logical change — one concept, one concern, one commit. If a task contains "and", "with", or a comma connecting distinct work, it is too big — split it.
- **Milestone sizing.** A well-sized milestone is a focused batch of work completable in one session. If you're packing unrelated concerns into one milestone, split it. The orchestrator enforces a hard ceiling programmatically — the planner should focus on natural groupings, not hitting a number.
- **Runnable after every milestone.** Each milestone must leave the app in a buildable, startable state.
- **No test or container stories/tasks.** Do not create backlog stories or milestone tasks for writing tests or containerization/deployment. The tester and validator agents handle those automatically.
- **Milestone acceptance context.** Each milestone file must contain a `> **Validates:**` blockquote describing what the validator should test — endpoint paths, HTTP methods, expected status codes, pages that should render, CLI commands. This is the validator's primary test plan.
- **Reference files for context scoping.** Each milestone file must contain a `> **Reference files:**` blockquote listing ONE exemplar file per architectural layer (entity, repository, service, controller, page) plus shared infrastructure files. The builder reads these files to learn the project's patterns and then applies them — avoiding the need to read the entire codebase. Pick files from the most similar completed feature.
- **Read the codebase first (cases B/C).** Match existing patterns — if a BaseRepository<T> exists, use it; if DTOs are records, make new DTOs records.

> **Backlog planning prompt:** You are a planning-only orchestrator. Your job is to decompose a project's requirements into a complete backlog of stories. [...story decomposition rules, task sizing, milestone sizing, detail requirements, containerization/testing exclusions...]

> **Completeness check prompt:** You are a planning quality reviewer. Your ONLY job is to verify that BACKLOG.md completely covers REQUIREMENTS.md and SPEC.md. Walk through every ## and ### heading in REQUIREMENTS.md. For each section, verify at least one story covers it. Also check SPEC.md for technical decisions that require setup work. If gaps exist, add stories. [...gap identification, renumbering rules...]

> **Milestone planning prompt:** You are a planning-only orchestrator. Your job is to manage BACKLOG.md, SPEC.md, and the milestone files in `milestones/`. ASSESS THE PROJECT STATE. Determine: (B) Continuing — find next eligible story, expand into milestone. (C) Evolving — update SPEC.md, add new stories, then do Case B. [...task sizing, milestone sizing, detail requirements, codebase reading...]

**Post-plan enforcement (backlog_checker.py):** After the initial planner runs, the orchestrator runs a two-part quality gate implemented in `backlog_checker.py`:

1. **Deterministic structural checks (A1-A4)** — validates BACKLOG.md format (heading, checkbox syntax, sequential numbering), dependency graph validity (valid references, no circular deps), prohibited content (no test-only or container-only stories, no pre-planned refactoring), and milestone proportionality (milestone size vs backlog size).
2. **LLM quality review (C1-C7)** — a single Copilot call evaluates story semantics: task sizing, detail level, milestone sizing, acceptance criteria, and coverage against REQUIREMENTS.md. Evaluation criteria are defined in `docs/backlog-planner-rubric.md`.

If structural checks fail, the initial planner is re-invoked. After re-plan, checks run again (non-blocking — results are logged).

3. **Story ordering check** — an LLM call verifies stories are ordered for maximum parallel builder throughput: stories on the critical path (longest dependency chain) are prioritized early, stories that unblock the most downstream work come before those that unblock fewer, and vertical feature slices are kept together (backend + frontend adjacent, not separated into backend-only and frontend-only blocks).

**Milestone size enforcement:** After every planner run (initial or between-milestone), `check_milestone_sizes()` checks for oversized milestones. If any uncompleted milestone exceeds 8 tasks, the planner is re-invoked with a targeted split prompt. If still oversized after one retry, a warning is logged and the build proceeds.

**Split milestone handling:** When `check_milestone_sizes()` splits a milestone into parts (e.g., `milestone-08a` and `milestone-08b`), the builder detects all newly created milestone files by comparing the set of incomplete milestones before and after planning. It builds each part sequentially, recording each as a completed milestone boundary. The story is only marked complete (`[x]`) after all parts succeed. If any part fails, the builder stops — remaining parts are not attempted.

**Between-milestone re-planning:** After each milestone completes, the build loop calls the milestone planner again to expand the next backlog story. If no eligible story exists (all remaining stories have unmet dependencies), a dependency deadlock warning is logged. If the backlog is empty, the build is done.

**Creates:** BACKLOG.md (first run)  
**Updates:** BACKLOG.md (checks off stories), `milestones/` (writes new milestone files), SPEC.md (when new requirements are detected — case C)  
**Reads:** SPEC.md, REQUIREMENTS.md, BACKLOG.md, `milestones/`, codebase  
**Writes code:** No

---

## Copilot Instructions Generator

Runs once automatically after the first planner run. Skipped if `.github/copilot-instructions.md` already exists.

> You are a documentation generator. You must NOT write any application code or modify any source files other than .github/copilot-instructions.md. Read SPEC.md to understand the tech stack, language, and architecture. Read the milestone files in `milestones/` to understand the planned components and milestones. Read REQUIREMENTS.md for the original project intent. Now create the file .github/copilot-instructions.md (create the .github directory if it doesn't exist). Fill in the project-specific sections (Project structure, Key files, Architecture, Conventions) based on SPEC.md and the milestone files. Keep the coding guidelines and testing conventions sections exactly as provided in the template. Commit with message '[planner] Add copilot instructions', run git pull --rebase, and push.

The generated file includes:
- **LLM-friendly coding guidelines** — universal rules for flat control flow, small functions, descriptive naming, no magic, etc.
- **Documentation maintenance rule** — instructs the builder to keep the instructions file updated as the project evolves.
- **Project-specific sections** — structure, key files, architecture, and conventions inferred from the plan.
- **Testing conventions** — universal rules for behavioral test naming, realistic inputs, regression tests, no mocking.

**Creates:** `.github/copilot-instructions.md`  
**Reads:** SPEC.md, `milestones/`, REQUIREMENTS.md  
**Writes code:** No

---

## Builder

Runs via `build --loop --builder-id N --num-builders M`. Multiple builders can run in parallel, each in its own `builder-N/` clone directory. Each builder runs a claim loop:

1. **Claim a story:** Find the next eligible unclaimed (`[ ]`) story in BACKLOG.md where all dependencies are completed (`[x]`). Mark it `[N]` (where N is the builder number), commit, and push. If the push fails (another builder claimed it), pull and try again.
2. **Plan the milestone:** Call the milestone planner to expand the claimed story into a milestone file in `milestones/`.
3. **Build it:** Create a feature branch (`builder-N/milestone-NN`), fix bugs and review findings first, then complete all tasks in the milestone. All per-task commits go to the feature branch.
4. **Merge to main:** Merge the feature branch to main with `--no-ff`, tag the merge commit `milestone-NN`, and delete the branch.
5. **Complete the story:** Mark the story `[x]` in BACKLOG.md, commit, push.
6. **Loop:** Go back to step 1. If no eligible stories remain, write `logs/builder-N.done` and exit.

**Branch isolation:** Each milestone is built on a feature branch (`builder-N/milestone-NN`). The builder creates the branch after planning (so milestone files land on main where all agents see them), pushes per-task commits to the branch, and merges to main with `--no-ff` when complete. The merge commit is tagged `milestone-NN` and recorded in `logs/milestones.log`. All other agents only see main, which contains only completed milestones. This eliminates dirty-main problems where downstream agents (validator, tester) see half-built milestones.

**Bug/finding partitioning (multi-builder):** When multiple builders run in parallel (`--num-builders M` with M > 1), bugs and findings are partitioned by issue number. Each builder only fixes items where `issue_number % num_builders == (builder_id - 1)`. For example, with 2 builders: builder-1 fixes even-numbered issues; builder-2 fixes odd-numbered issues. This prevents two builders from racing to fix the same bug or finding. With a single builder, no filtering is applied. The partitioning is enforced both in the builder's LLM prompt and in the Python shutdown logic that counts remaining work.

> Before starting, read the milestone file to understand the tasks and reference files. Read README.md, SPEC.md, and .github/copilot-instructions.md for project context and coding conventions. Read ONLY the files listed in the milestone's `> **Reference files:**` section to learn the project's patterns — do NOT read every file in the project. One example controller teaches the same conventions as ten. Beyond reference files, only read files you are directly editing, shared infrastructure you must modify (DI, DbContext, routing), and files mentioned in bugs or review findings. Read DEPLOY.md if it exists — it contains deployment configuration and lessons learned from the validator agent. If it mentions required env vars, ports, or startup requirements, ensure your code is compatible. Do NOT modify DEPLOY.md — only the validator agent manages that file. Only build, fix, or keep code that serves that purpose. Remove any scaffolding, template code, or functionality that does not belong. After any refactoring — including review fixes — check for dead code left behind and remove it. Before your first commit in each session, review .gitignore and ensure it covers the project's current tech stack; update it when you introduce a new framework or build tool. When completing a task that changes the project structure, key files, architecture, or conventions, update .github/copilot-instructions.md to reflect the change (it is a style guide — describe file roles and coding patterns, not implementation details). Check GitHub Issues for open bugs and findings: run `gh issue list --label bug --state open` and `gh issue list --label finding --state open` to see actionable items. Fix ALL open bugs before anything else, then address findings one at a time, closing each issue when fixed. Once all bugs and findings are resolved, move to the milestone file. Complete every task in the milestone, then STOP. For each task: write the code AND mark it complete in the milestone file, then commit BOTH together in a single commit with a meaningful message. After each commit, run git pull --rebase and push. When every task in the current milestone is checked, verify the application still builds and runs.

**Reads:** README.md, SPEC.md, `milestones/`, GitHub Issues (bugs, findings), DEPLOY.md, REVIEW-THEMES.md, .github/copilot-instructions.md  
**Writes code:** Yes  
**Updates:** .github/copilot-instructions.md (when project structure changes), .gitignore (when tech stack changes)  
**Commits:** After each bug fix, review fix, and task (prefixed with `[builder]`)  
**Shutdown signal:** Writes `logs/builder-N.done` when no eligible stories remain

---

## Commit Watcher (Branch-Attached Reviewer)

Runs continuously via `commitwatch --builder-id N`, launched automatically by `go`. Each builder gets a dedicated reviewer (`reviewer-N/`) that watches the builder's feature branch and reviews commits **before they merge to main**.

### Branch-attached mode (default, builder-id > 0)

The reviewer polls for active feature branches matching its builder (`builder-N/*` via `git ls-remote`). When a branch appears:

1. **Checkout branch** — `git fetch origin && git checkout {branch_name}`
2. **Review commits** — enumerates new commits since the last checkpoint, reviews them individually or as a batch (same severity-based filing as legacy mode)
3. **Signal merge readiness** — writes the reviewed HEAD SHA to `logs/reviewer-N.branch-head` so the builder's merge gate knows the review is complete
4. **Branch disappears** — when the builder merges and deletes the branch, the reviewer returns to main and waits for the next branch

**Merge gate:** The builder waits (soft timeout, 5 minutes) for the reviewer to catch up before merging a milestone branch. The builder reads `logs/reviewer-N.branch-head` and compares its `(branch_name, sha)` tuple against the branch HEAD. If the reviewer has reviewed all commits, the merge proceeds immediately. On timeout, the merge proceeds anyway — the gate is advisory, not blocking.

**Persistent checkpoint:** Per-builder checkpoints are saved to `logs/reviewer-N.branch-checkpoint`. On restart, the reviewer resumes from the checkpoint.

### Legacy mode (builder-id = 0)

When `commitwatch` is called without `--builder-id` (or with `--builder-id 0`), the original main-polling behavior is preserved. The legacy reviewer watches main for new commits and reviews them post-merge. This mode uses `logs/reviewer.checkpoint`.

### Shared behavior (both modes)

**Filtering:** Merge commits (except milestone merges) and the reviewer's own commits are automatically skipped.

**Severity-based filing:** [bug] and [security] issues are filed as GitHub Issues with the `finding` label so the builder sees and fixes them immediately. [cleanup] and [robustness] issues are filed as GitHub Issues with the `note` label — per-commit observations that the milestone reviewer later evaluates for recurring patterns.

**Single commit prompt:**

> ...reviews the diff on the feature branch... For [bug] and [security] issues, create GitHub Issues with `--label finding`. For [cleanup] and [robustness] issues, create GitHub Issues with `--label note` instead — these are observations that the milestone review will evaluate for patterns. Only commit if there are [doc] fixes; issue creation does not require commits.

**Batched commits prompt (2+ commits):**

> ...reviews the combined diff... Same severity-based filing: GitHub Issues with `--label finding` for [bug]/[security], `--label note` for [cleanup]/[robustness]. Only commit if there are [doc] fixes.

**Trigger:** Polls every 10 seconds for new branch activity (branch mode) or new commits on main (legacy mode)  
**Scope:** Per-commit diff for individual reviews; combined diff for batched reviews  
**Checkpoint:** `logs/reviewer-N.branch-checkpoint` (branch mode) or `logs/reviewer.checkpoint` (legacy mode)  
**Signal file:** `logs/reviewer-N.branch-head` — `branch_name sha` tuple read by the builder merge gate  
**Skips:** Non-milestone merge commits, coordination-only commits (milestone files only)  
**Runs from:** `reviewer-N/` clone (one per builder)  
**Shutdown:** Checks for `logs/builder.done` each cycle; exits when builder is done  
**Writes code:** [doc] fixes only (comments, README). Never changes application logic or DEPLOY.md directly.

---

## Milestone Reviewer

Runs continuously via `milestonewatch`, launched automatically by `go` in a separate terminal window. Watches for completed milestones and runs cross-cutting reviews of the entire milestone's diff. This is a **separate agent** from the commit watcher, running in its own `milestone-reviewer/` git clone.

When a milestone completes (all tasks checked in the milestone file), the milestone reviewer triggers a cross-cutting review that catches issues per-commit reviews miss: inconsistent patterns across files, API mismatches, duplicated logic introduced across separate commits, and architectural problems in how pieces fit together. Each milestone is only reviewed once (tracked in `logs/reviewer.milestone`).

**Code analysis:** Before the milestone review prompt runs, the milestone reviewer invokes `run_milestone_analysis()` from `code_analysis.py` — a tree-sitter-based structural analysis of all files changed in the milestone. It checks for long functions, deeply nested code, large files, and other structural issues across Python, JS/TS, and C#. The analysis results are included in the milestone review prompt so the reviewer has both diff context and structural quality data.

**Frequency filter:** The milestone review reads all open GitHub Issues with the `note` label from per-commit reviews and applies a frequency filter before filing findings for the builder:
- [bug] and [security]: Always filed as GitHub Issues with `--label finding` regardless of frequency
- [cleanup] and [robustness]: Only promoted from `note` to `finding` (via `gh issue edit --remove-label note --add-label finding`) if the same class of problem appears in 2+ locations or files across the milestone. One-off issues stay as notes.
- When promoting a recurring pattern, the reviewer consolidates the notes into a single finding issue describing the pattern and all affected locations, and closes the original note issues.

**Stale finding cleanup:** The milestone reviewer closes finding issues that have already been fixed in the code (via `gh issue close` with a comment), keeping the builder's work list clean.

> ...reviews the full milestone diff... Reads open `note`-labeled GitHub Issues for per-commit observations. Files new GitHub Issues with `--label finding` for [bug]/[security] always, and promotes `note` issues to `finding` only when the pattern recurs in 2+ locations. Closes stale finding issues. Commit with message 'Milestone review: {milestone_name}', run git pull --rebase, and push.

**Trigger:** Polls `logs/milestones.log` every 10 seconds (configurable via `--interval`) for newly completed milestones  
**Scope:** Full milestone diff (`milestone_start_sha..milestone_end_sha`)  
**Checkpoint:** `logs/reviewer.milestone` (set of milestones already reviewed)  
**Runs from:** `milestone-reviewer/` clone  
**Shutdown:** Checks for `logs/builder.done` each cycle; drains remaining milestone reviews before exiting  
**Writes code:** [doc] fixes only (comments, README). Never changes application logic or DEPLOY.md directly.  
**Updates:** REVIEW-THEMES.md (rolling summary of top recurring review patterns, replaced each milestone review)

---

## Tester

Milestone-triggered via `testloop`, launched automatically by `go`. Watches `logs/milestones.log` for newly completed milestones and runs scoped tests for each one.

For each newly completed milestone:

> Read SPEC.md and the milestone files in `milestones/` to understand the project. A milestone — '{milestone_name}' — has just been completed. Pull the latest code with `git pull --rebase`. Run `git diff {milestone_start_sha} {milestone_end_sha} --name-only` to see which files changed in this milestone. Build the project. Run all existing tests. Testing has two priorities: (1) test the new milestone's code — features with no tests, missing error handling, missing validation; (2) test integration with existing code — look for missing tests that span multiple components or layers (e.g. form → API service → backend endpoint → UI update), and review existing test files for cross-feature gaps that accumulated over prior milestones. The more milestones completed, the more important integration tests become. Prioritize integration tests over unit tests. Each test should verify a distinct user-facing behavior. Do not test internal implementation details, getters/setters, or trivially obvious code. Write at most 20 new tests per run. Do NOT start the application, start servers, or test live endpoints — a separate validator agent handles runtime testing in containers. Focus exclusively on running the test suite. For any test that fails, create a GitHub Issue with `--label bug` describing what failed, steps to reproduce, and which milestone. Commit new tests, run git pull --rebase, and push. If the push fails, run git pull --rebase and push again (retry up to 3 times). If everything passes and no new tests are needed, do nothing.

When the builder finishes, the tester sees `logs/builder.done`, drains any remaining untested milestones, and exits.

**Trigger:** Polls `logs/milestones.log` every 10 seconds (configurable via `--interval`)  
**Scope:** New milestone's changed files + integration with existing code  
**Checkpoint:** `logs/tester.milestone` (set of milestones already tested)  
**Runs from:** `tester/` clone  
**Shutdown:** Checks for `logs/builder.done`; drains remaining milestones before exiting  
**Writes code:** Tests only  
**Commits:** When it writes new tests or finds bugs

---

## Validator

Milestone-triggered via `validateloop`, launched automatically by `go`. Watches `logs/milestones.log` for newly completed milestones and validates the application in a Docker container.

For each newly completed milestone:

> You are a deployment validator. Your job is to build the application in a Docker container, run it, and verify it works. FIRST: Read DEPLOY.md if it exists — it contains everything previous runs learned about building and deploying this application. Follow its instructions for Dockerfile configuration, environment variables, port mappings, startup sequence, and known gotchas. Read SPEC.md for acceptance criteria. Read only the current milestone file for milestone '{milestone_name}' — test only the functionality added by this milestone, not previous milestones. Set `COMPOSE_PROJECT_NAME` for container namespace isolation and use deterministic host ports derived from the project name. Stop and remove any running containers from this project's previous validation. If no Dockerfile exists, create one appropriate for the project's tech stack. Build the container. Start it. Wait for the app to be healthy. Then perform three checks: (A) Current milestone validation — test endpoints, pages, and behaviors listed in the milestone's `> **Validates:**` block. (B) Requirements coverage — read REQUIREMENTS.md and BACKLOG.md to identify which requirements align with this milestone's story; verify each is working; file a GitHub Issue with `--label bug` and a [missing-requirement] prefix for any gap. (C) Fixed bug verification — check GitHub Issues with `--label bug --state closed` for recently fixed bugs; re-test each fix; if the issue persists, reopen the issue or file a new one describing the regression. Leave containers running after testing so the app is browsable. Update DEPLOY.md with everything learned about deploying this application. Commit and push.

**Port isolation:** Each project gets deterministic host ports computed from a SHA-256 hash of the project name (range 3000-8999). `COMPOSE_PROJECT_NAME` is set to the project name so Docker containers from different projects are namespaced and don't conflict. This allows multiple projects (or model comparisons) to run side-by-side on the same host.

**Persistent containers:** After successful validation, containers are left running so the application is accessible at `http://localhost:<port>` for browsing. Containers are cleaned up at the start of the *next* milestone's validation (not after testing). This means the latest validated milestone is always browsable.

**Milestone SHA checkout:** Before validating, the validator checks out the exact commit at the milestone's end SHA (`git checkout {end_sha}`). This ensures each milestone is tested against exactly the code that existed when it was completed, not code from later milestones. Copilot commits validation artifacts (Dockerfile, DEPLOY.md) on the detached HEAD. After Copilot finishes, the Python orchestration collects those commits, returns to main, cherry-picks them onto main, and pushes. This avoids rebase conflicts that occur when pushing directly from a detached HEAD that diverged from main while validation was running.

**Persistent deployment knowledge:** The validator reads DEPLOY.md at the start of each run and updates it at the end. This creates a ratchet effect — each milestone's validation run gets more reliable because it inherits knowledge from all prior runs. DEPLOY.md captures: Dockerfile configuration, required environment variables, port mappings, docker-compose service setup, startup sequence, health check details, and known gotchas. The builder also reads DEPLOY.md to stay compatible with deployment requirements.

**Validation results log:** After each milestone, the validator writes `validation-results.txt` in the repo root (not committed). The Python orchestration copies it to `logs/validation-<milestone-name>.txt` for post-run analysis. Each line is `PASS` or `FAIL` with a description of what was tested (container build, startup, endpoints, error cases).

**Validation summary:** After copying the results file, the orchestration always prints a pass/fail summary to the terminal log. The summary counts PASS and FAIL lines per category tag — `[A]` milestone tests, `[B]` requirements coverage, `[C]` fixed bug verification, `[UI]` Playwright — and logs up to 10 individual failure lines. This runs unconditionally so operators always see validation outcomes without opening log files.

**Playwright trace saving (`--save-traces`):** When `validateloop` is called with `--save-traces`, the orchestration appends extra instructions to the Playwright prompt telling Copilot to run tests with `--trace on` and `--reporter=html`. After the Copilot run, it copies `e2e/playwright-report/` and `e2e/test-results/` to `logs/playwright-<milestone>/report/` and `logs/playwright-<milestone>/traces/` respectively. These artifacts are not committed to the repo. Without `--save-traces`, no extra prompt text is added and no artifacts are copied — the default keeps `logs/` lean.

When the builder finishes, the validator sees `logs/builder.done`, drains any remaining unvalidated milestones, and exits.

**Trigger:** Polls `logs/milestones.log` every 10 seconds (configurable via `--interval`)  
**Scope:** Three checks per milestone: (A) current milestone validation against its `> **Validates:**` block, (B) requirements coverage by cross-referencing REQUIREMENTS.md and BACKLOG.md against the running app, (C) fixed bug verification by re-testing recently closed GitHub Issues with `--label bug`  
**Reads:** SPEC.md, DEPLOY.md, REQUIREMENTS.md, BACKLOG.md, `milestones/` (current only), GitHub Issues (for fixed bug verification)  
**Bug prefixes:** `[missing-requirement]` for requirements gaps; `[UI]` for Playwright failures  
**Checkpoint:** `logs/validator.milestone` (set of milestones already validated)  
**Runs from:** `validator/` clone  
**Shutdown:** Checks for `logs/builder.done`; drains remaining milestones before exiting  
**Writes code:** Dockerfile, docker-compose.yml (if needed), DEPLOY.md, Playwright tests (if frontend detected)  
**Commits:** When it creates/updates deployment files, finds bugs, or updates DEPLOY.md

**Playwright UI testing (automatic):** Before each validation run, the orchestration checks whether the repo contains a frontend (package.json, .tsx/.jsx/.vue/.svelte files, or frontend keywords in SPEC.md). When a frontend is detected, the validator prompt is extended with Playwright instructions that tell the Copilot agent to:
- Add a `playwright` sidecar service to docker-compose.yml using `mcr.microsoft.com/playwright:v1.52.0-noble`
- Write TypeScript tests in `e2e/` using `data-testid` selectors (with semantic selector fallbacks)
- Test page rendering, navigation, form submission, and interactive elements in a real headless browser
- Run tests via `docker compose run --rm playwright` and include `[UI]` results in `validation-results.txt`
- Report UI failures by creating a GitHub Issue with `--label bug` and a `[UI]` prefix in the title

For API-only projects, the Playwright section is omitted entirely — no extra prompt text, no browser overhead.

---

## Positive Feedback Loops

The multi-agent system is designed around cumulative knowledge. Several mechanisms create positive feedback loops where each milestone makes subsequent milestones more reliable:

### Deployment Knowledge Ratchet (DEPLOY.md)

The validator writes DEPLOY.md after each milestone — Dockerfile configuration, required env vars, port mappings, startup sequence, health check details, and known gotchas. The builder reads DEPLOY.md before every session to stay compatible with deployment requirements. Each milestone's validation run inherits all knowledge from prior runs, so container builds and runtime validation get progressively more reliable. What was a painful discovery in milestone 1 becomes a documented fact for milestone 2.

### Review Signal Filtering (notes → findings)

Per-commit reviews catch every issue but split them by urgency. [bug] and [security] issues are filed as GitHub Issues with the `finding` label so the builder sees and fixes them immediately — these are too important to wait. [cleanup] and [robustness] issues are filed as GitHub Issues with the `note` label — observational records that the builder does not act on directly. When a milestone completes, the milestone review reads all accumulated notes and applies a frequency filter: only patterns that recurred across 2+ locations or files get promoted to `finding` (via relabeling) for the builder. One-off cleanup issues stay as notes. This means the builder spends fix cycles on systemic problems, not isolated nitpicks, and the signal-to-noise ratio of review feedback improves over time as the reviewer learns what patterns actually recur.

### Review Themes (REVIEW-THEMES.md)

The reviewer maintains REVIEW-THEMES.md — a cumulative knowledge base of recurring code quality patterns observed across milestone reviews. The builder reads it to avoid repeating the same class of mistake. Themes are never dropped — once a pattern is identified, it stays permanently so the builder always has the full history of lessons learned.

### Codebase-Aware Planning

The milestone planner reads the actual codebase before expanding the next backlog story. It discovers what patterns have emerged — base classes, naming conventions, dependency injection wiring, project structure — and writes tasks that match those patterns. This prevents the planner from fighting the codebase's natural direction and ensures each milestone's tasks build on what actually exists rather than what was originally imagined.

### Evolving Style Guide (.github/copilot-instructions.md)

The builder updates the project's copilot-instructions.md whenever project structure, key files, architecture, or conventions change. Future builder sessions (and all other Copilot-powered agents) read this file, so coding conventions stay consistent as the project grows. This is especially important across iterative development sessions where the builder agent is a fresh process with no memory of prior sessions.

---

## Agent Coordination Rules

- **Commit message tagging:** Every agent prefixes its commit messages with its name in brackets — `[builder]`, `[reviewer]`, `[tester]`, `[validator]`, `[planner]`, `[bootstrap]`. This makes it easy to see who did what in `git log`.
- The **Planner** runs on demand via `plan`. It assesses project state (fresh / continuing / evolving), manages BACKLOG.md (story queue with three-state tracking: `[ ]` unclaimed, `[N]` claimed by builder N, `[x]` completed), updates SPEC.md if new requirements are detected, then writes one milestone file per story in `milestones/`. It never writes application code.
- The **Builder** runs in a claim loop. Each builder claims a story from BACKLOG.md (`[N]`), calls the planner to expand it into a milestone, completes all tasks, marks the story done (`[x]`), and loops. When no eligible stories remain, writes `logs/builder-N.done`.
- The **Branch-Attached Reviewer** (one per builder, `reviewer-N/`) watches the builder's feature branch and reviews commits before they merge. The builder has a soft merge gate that waits for the reviewer to catch up. [bug]/[security] issues are filed as GitHub Issues with `--label finding` for the builder; [cleanup]/[robustness] issues are filed as GitHub Issues with `--label note` for the milestone reviewer to evaluate. Non-code issues ([doc]: stale docs, misleading comments) are fixed directly (except DEPLOY.md — that gets filed as a finding).
- The **Milestone Reviewer** runs cross-cutting reviews when a milestone completes. It reads accumulated `note`-labeled GitHub Issues, promotes recurring patterns to `finding` (via `gh issue edit --remove-label note --add-label finding`), and closes stale finding issues. It also updates REVIEW-THEMES.md.
- The **Tester** runs scoped tests when a milestone completes, focusing on changed files. It runs the test suite only — it does not start the app or test live endpoints. Files bugs as GitHub Issues with `--label bug`. Exits when the builder finishes.
- The **Validator** builds the app in a Docker container after each milestone, starts it, and tests it against SPEC.md acceptance criteria. Files bugs as GitHub Issues with `--label bug`. Persists deployment knowledge in DEPLOY.md. Exits when the builder finishes.
- **Bug/finding partitioning:** When multiple builders run concurrently, each builder is assigned a subset of bugs and findings based on issue number. The rule is `issue_number % num_builders == (builder_id - 1)`. This partitioning is enforced both in the builder's LLM prompt (which tells Copilot which items to fix) and in the Python shutdown logic (which counts only assigned items as remaining work). This eliminates races where two builders attempt to fix the same bug or review finding simultaneously.
- **Branch model:** Builders push code to per-milestone feature branches (`builder-N/milestone-NN`), never directly to main. Coordination artifacts (BACKLOG.md claims/completions, milestone files from the planner) are committed on main before branching. Main receives completed milestones via `--no-ff` merge commits, each tagged `milestone-NN`. Each builder's branch-attached reviewer (`reviewer-N/`) reviews commits on the feature branch before the merge.
- All agents run `git pull --rebase` before pushing to avoid merge conflicts.
- `SPEC.md` is the source of truth for technical decisions. `BACKLOG.md` is the story queue. Edit either anytime to steer the project — run `plan` to adapt.
- Each milestone file in `milestones/` is exclusively owned by one builder — no two builders edit the same file.
- `REVIEW-THEMES.md` is a cumulative knowledge base of recurring review patterns, owned by the milestone reviewer. The milestone reviewer updates it after each milestone review, adding new themes but never removing old ones. Themes persist forever as lessons learned. The builder reads it to avoid repeating patterns but never modifies it.

---

## Iterative Development

`go` supports iterative sessions. You can build a project in phases:

1. **Session 1:** `go --directory my-app --model gpt-5.3-codex --spec-file api-spec.md --local` — bootstraps project, builds API
2. **Session 2:** `go --directory my-app --model gpt-5.3-codex --spec-file frontend-spec.md --local` — detects existing repo, clones agent directories, overwrites REQUIREMENTS.md with frontend spec, planner updates SPEC.md and creates new milestones, builder implements frontend
3. **Session 3:** `go --directory my-app --model gpt-5.3-codex --local` — continues where it left off (no new requirements)
4. **Parallel build:** `go --directory my-app --model gpt-5.3-codex --builders 3 --local` — launches 3 builders that claim and build stories in parallel

`go` uses repo-first detection: it checks whether the repo already exists (locally via `remote.git/`, or on GitHub via `gh repo view`) rather than checking for local clone directories. This means:

- **Repo exists, agent dirs exist:** pulls all clones, plans, builds (standard resume)
- **Repo exists, agent dirs missing:** clones all agents from the repo, then continues (fresh-machine resume)
- **No repo:** bootstraps from scratch (requires `--spec-file` or `--description`)
- **Legacy `builder/` directory:** automatically migrated to `builder-1/` on resume

Agent directories (`builder-1/`, `builder-N/`, `reviewer-1/`, `reviewer-N/`, `milestone-reviewer/`, `tester/`, `validator/`) are treated as disposable working copies — they can be deleted and re-cloned from the repo at any time. The repo (GitHub or `remote.git/`) and `logs/` directory (checkpoints) are the persistent state.

- **Legacy `reviewer/` directory:** automatically migrated to `reviewer-1/` on resume

The `--spec-file` for session 2 can contain just new requirements ("Add a React frontend") or a complete updated requirements doc (old API spec + new frontend spec). The planner compares REQUIREMENTS.md against SPEC.md and the codebase to determine what's new.

---

## Legacy Commands

The original `reviewoncommit` and `testoncommit` commands still exist for manual/standalone use. They use the old `_watch_loop` polling mechanism and are not launched by `go`.

---

## Shutdown Protocol

Multi-builder shutdown uses per-builder sentinel files:

1. **Builder completes all stories:** When a builder finds no eligible stories in BACKLOG.md (all are `[N]` or `[x]`), it waits for downstream agents to go idle, verifies checklists are clean, then writes `logs/builder-N.done`.
2. **Wait for agents to go idle:** Each builder monitors agent log files using discovery-based detection — it finds all `logs/reviewer-*.log` files (matching `reviewer-\d+`) plus `logs/milestone-reviewer.log`, `logs/tester.log`, and `logs/validator.log`. When all discovered logs haven't changed in 120+ seconds, agents are considered idle.
3. **Check work lists:** The builder pulls latest, checks GitHub Issues for open bugs (`gh issue list --label bug --state open`) and open findings (`gh issue list --label finding --state open`), and scans milestone files for unchecked items.
4. **Fix or exit:** If new work was filed, the builder fixes it (up to 4 fix-only cycles) and loops back to step 2. If checklists are clean and agents are idle, writes `logs/builder-N.done`.
5. **All builders done:** `is_builder_done()` discovers all `builder-*.done` files in `logs/` and returns True only when all expected builders have finished.
6. **Agents shut down:** The branch-attached reviewers, milestone reviewer, tester, and validator see all builders done on their next poll cycle. The milestone reviewer, tester, and validator each drain any remaining milestones before exiting.
7. **Crash fallback:** If `logs/builder.log` hasn't been modified in 30+ minutes, agents assume the builder crashed and shut down.
8. **Startup cleanup:** `go` calls `clear_builder_done(num_builders)` to remove stale sentinel files before launching agents.
9. **Timeout safety:** If agents don't go idle within 10 minutes, the builder writes its sentinel and exits anyway.
