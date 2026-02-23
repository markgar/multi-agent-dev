# Agent Prompts

Each agent is a `copilot --yolo` call with a specific prompt. Here's exactly what each one is told to do.

---

## Bootstrap

Runs once internally when you call `go`. Do not run `bootstrap` directly — it is deprecated and will error.

> Create a directory called builder. cd into it. Initialize a git repo. Create an appropriate .gitignore for the project. Create a brief README.md (~15 lines) — what the project is, how to build and run it, and how to develop. Do not describe features in detail — REQUIREMENTS.md and SPEC.md cover that. A file called REQUIREMENTS.md already exists in this directory — it contains the original project requirements exactly as provided by the user. Do NOT modify or overwrite REQUIREMENTS.md. Use it as the primary input when writing SPEC.md. Create a SPEC.md that captures TECHNICAL DECISIONS only (~40-60 lines). SPEC.md should include: (1) a high-level summary, (2) the tech stack and language choices, (3) the architecture approach — layers, dependency rules, project structure, (4) cross-cutting concerns — authentication strategy, multi-tenancy approach, error handling conventions, (5) acceptance criteria at the feature level (e.g. 'members can be managed') not the field level. Do NOT include entity field definitions, API route tables, page layouts, or DTO shapes in SPEC.md — those details will be planned progressively as features are built. REQUIREMENTS.md is the authoritative source for feature details — SPEC.md captures the technical decisions for how to build them. Do NOT create a TASKS.md — task planning happens later. Commit with message '[bootstrap] Initial commit: project spec'. Run 'gh repo create `{user/name}` --public --source .' and push.

**Creates:** README.md, SPEC.md, REQUIREMENTS.md, reviews/, bugs/, git repo, GitHub remote  
**Writes code:** No

**Local mode (`--local`):** When `go` is called with `--local`, the bootstrap prompt replaces `gh repo create` with `git remote add origin {remote_path}` pointing to a local bare git repo. No GitHub CLI calls are made. The `--local` flag also skips the `gh` prerequisite checks and clones reviewer/tester/validator copies from the local bare repo instead of GitHub.

**Note:** Before Copilot runs, the CLI pre-creates `builder/REQUIREMENTS.md` containing the prompt or spec-file content verbatim, and creates `builder/reviews/` and `builder/bugs/` directories (with `.gitkeep` files so git tracks them). These are committed with the rest of the bootstrap. In later sessions, `go` may overwrite REQUIREMENTS.md with new requirements before re-planning.

---

## Planner

Runs on demand via `plan`. Called automatically by `go` before the first build cycle (as the **Backlog Planner**), and called again by the build loop between milestones (as the **Milestone Planner**) to expand the next backlog story.

The planner manages three files: **BACKLOG.md** (ordered story queue), **milestone files in `milestones/`** (one file per story), and **SPEC.md** (technical decisions). It plans **one milestone at a time** — never multiple milestones in a single run.

The planner uses different prompts depending on the project state:

### Backlog Planning (fresh project)

When no BACKLOG.md exists, the planner runs two focused Copilot calls:

1. **Backlog creation** — Reads REQUIREMENTS.md and SPEC.md, decomposes all requirements into an ordered story queue (BACKLOG.md) with dependency annotations, checks off the first story, and writes the first milestone file in `milestones/`.
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

- `[ ]` = in backlog (unclaimed), `[~]` = claimed by a builder (in progress), `[x]` = completed
- `<!-- depends: N -->` = HTML comment listing story numbers this depends on
- Dependencies require `[x]` (completed) — `[~]` (claimed) does NOT satisfy dependencies
- Dependencies must be **minimal** — only mark a dependency when the story cannot compile or function without the other story's code artifacts (imports, types, interfaces). Do NOT add dependencies for eventual integration — integration happens in whichever story is built second.
- The first story is always scaffolding (project structure, entry point, health endpoint)
- Stories are ordered so each builds on predecessors, preferring vertical feature slices — each story delivers one feature through all layers (entity → repository → service → API → frontend) rather than building one layer across all features.
- The builder claims stories via git-based optimistic locking: mark `[~]`, commit, push. If push fails (another builder claimed first), pull and try the next eligible story.

### Planning Rules

- **One milestone per run.** The planner writes exactly one new milestone file in `milestones/` each time it runs. It does not plan ahead or create multiple milestones at once.
- **Minimal dependencies for parallelism.** Multiple builders work concurrently — the dependency graph directly controls throughput. Only annotate a dependency when a story literally cannot compile without the other story's artifacts. Example: a Members API needs the Organization entity (import dependency) but does NOT need auth middleware — the controller can be built without auth, and auth is wired in when the auth story completes. The goal is the widest possible dependency graph.
- **Detail in task descriptions.** Instead of "Create Member entity", write "Create Member entity (Id, FirstName, LastName, Email, Role enum, IsActive, OrganizationId)". The builder should not need to cross-reference SPEC.md or REQUIREMENTS.md.
- **Task sizing.** Each task describes one logical change — one concept, one concern, one commit. If a task contains "and", "with", or a comma connecting distinct work, it is too big — split it.
- **Milestone sizing.** A well-sized milestone typically has 3-7 tasks. Under 3 suggests tasks might be too coarse. Over 8 suggests a natural split point exists.
- **Runnable after every milestone.** Each milestone must leave the app in a buildable, startable state.
- **No test or container stories/tasks.** Do not create backlog stories or milestone tasks for writing tests or containerization/deployment. The tester and validator agents handle those automatically.
- **Milestone acceptance context.** Each milestone file must contain a `> **Validates:**` blockquote describing what the validator should test — endpoint paths, HTTP methods, expected status codes, pages that should render, CLI commands. This is the validator's primary test plan.
- **Read the codebase first (cases B/C).** Match existing patterns — if a BaseRepository<T> exists, use it; if DTOs are records, make new DTOs records.

> **Backlog planning prompt:** You are a planning-only orchestrator. Your job is to decompose a project's requirements into a complete backlog of stories, then plan the first milestone. [...story decomposition rules, task sizing, milestone sizing, detail requirements, containerization/testing exclusions...]

> **Completeness check prompt:** You are a planning quality reviewer. Your ONLY job is to verify that BACKLOG.md completely covers REQUIREMENTS.md and SPEC.md. Walk through every ## and ### heading in REQUIREMENTS.md. For each section, verify at least one story covers it. Also check SPEC.md for technical decisions that require setup work. If gaps exist, add stories. [...gap identification, renumbering rules...]

> **Milestone planning prompt:** You are a planning-only orchestrator. Your job is to manage BACKLOG.md, SPEC.md, and the milestone files in `milestones/`. ASSESS THE PROJECT STATE. Determine: (B) Continuing — find next eligible story, expand into milestone. (C) Evolving — update SPEC.md, add new stories, then do Case B. [...task sizing, milestone sizing, detail requirements, codebase reading...]

**Post-plan enforcement (backlog_checker.py):** After the initial planner runs, the orchestrator runs a two-part quality gate implemented in `backlog_checker.py`:

1. **Deterministic structural checks (A1-A4)** — validates BACKLOG.md format (heading, checkbox syntax, sequential numbering, first story checked), dependency graph validity (valid references, no circular deps), prohibited content (no test-only or container-only stories, no pre-planned refactoring), and milestone proportionality (milestone size vs backlog size).
2. **LLM quality review (C1-C7)** — a single Copilot call evaluates story semantics: task sizing, detail level, milestone sizing, acceptance criteria, and coverage against REQUIREMENTS.md. Evaluation criteria are defined in `docs/backlog-planner-rubric.md`.

If structural checks fail, the initial planner is re-invoked. After re-plan, checks run again (non-blocking — results are logged).

3. **Story ordering check** — an LLM call verifies stories are ordered for maximum parallel builder throughput: stories on the critical path (longest dependency chain) are prioritized early, stories that unblock the most downstream work come before those that unblock fewer, and vertical feature slices are kept together (backend + frontend adjacent, not separated into backend-only and frontend-only blocks).

**Milestone size enforcement:** After every planner run (initial or between-milestone), `check_milestone_sizes()` checks for oversized milestones. If any uncompleted milestone exceeds 10 tasks, the planner is re-invoked with a targeted split prompt. If still oversized after one retry, a warning is logged and the build proceeds.

**Between-milestone re-planning:** After each milestone completes, the build loop calls the milestone planner again to expand the next backlog story. If no eligible story exists (all remaining stories have unmet dependencies), a dependency deadlock warning is logged. If the backlog is empty, the build is done.

**Creates:** BACKLOG.md (first run), first milestone file in `milestones/` (first run)  
**Updates:** BACKLOG.md (checks off stories), `milestones/` (writes new milestone files), SPEC.md (when new requirements are detected — case C)  
**Reads:** SPEC.md, REQUIREMENTS.md, BACKLOG.md, `milestones/`, codebase  
**Writes code:** No

---

## Copilot Instructions Generator

Runs once automatically after the first planner run. Skipped if `.github/copilot-instructions.md` already exists.

> You are a documentation generator. You must NOT write any application code or modify any source files other than .github/copilot-instructions.md. Read SPEC.md to understand the tech stack, language, and architecture. Read the milestone files in `milestones/` to understand the planned components and milestones. Read REQUIREMENTS.md for the original project intent. Now create the file .github/copilot-instructions.md (create the .github directory if it doesn't exist). Fill in the project-specific sections (Project structure, Key files, Architecture, Conventions) based on SPEC.md and the milestone files. Keep the coding guidelines and testing conventions sections exactly as provided in the template. Commit with message 'Add copilot instructions', run git pull --rebase, and push.

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

Runs via `build --loop --builder-id N`. Multiple builders can run in parallel, each in its own `builder-N/` clone directory. Each builder runs a claim loop:

1. **Claim a story:** Find the next eligible unclaimed (`[ ]`) story in BACKLOG.md where all dependencies are completed (`[x]`). Mark it `[~]` (claimed), commit, and push. If the push fails (another builder claimed it), pull and try again.
2. **Plan the milestone:** Call the milestone planner to expand the claimed story into a milestone file in `milestones/`.
3. **Build it:** Fix bugs and review findings first, then complete all tasks in the milestone.
4. **Complete the story:** Mark the story `[x]` in BACKLOG.md, commit, push.
5. **Loop:** Go back to step 1. If no eligible stories remain, write `logs/builder-N.done` and exit.

> Before starting, review README.md, SPEC.md, and the milestone files in `milestones/` to understand the project's purpose and plan. Read .github/copilot-instructions.md if it exists — follow its coding guidelines and conventions in all code you write. Read DEPLOY.md if it exists — it contains deployment configuration and lessons learned from the validator agent. If it mentions required env vars, ports, or startup requirements, ensure your code is compatible. Do NOT modify DEPLOY.md — only the validator agent manages that file. Only build, fix, or keep code that serves that purpose. Remove any scaffolding, template code, or functionality that does not belong. After any refactoring — including review fixes — check for dead code left behind and remove it. Before your first commit in each session, review .gitignore and ensure it covers the project's current tech stack; update it when you introduce a new framework or build tool. When completing a task that changes the project structure, key files, architecture, or conventions, update .github/copilot-instructions.md to reflect the change (it is a style guide — describe file roles and coding patterns, not implementation details). Now look at the `bugs/` directory first. List `bug-*.md` files without matching `fixed-*.md` files — these are open bugs. Fix ALL open bugs before anything else. Then look at the `reviews/` directory. List `finding-*.md` files without matching `resolved-*.md` files — these are open findings. Address them one at a time. Once all bugs and findings are resolved, move to the milestone file. Complete every task in the milestone, then STOP. For each task: write the code AND mark it complete in the milestone file, then commit BOTH together in a single commit with a meaningful message. After each commit, run git pull --rebase and push. When every task in the current milestone is checked, verify the application still builds and runs.

**Reads:** README.md, SPEC.md, `milestones/`, bugs/, reviews/, DEPLOY.md, REVIEW-THEMES.md, .github/copilot-instructions.md  
**Writes code:** Yes  
**Updates:** .github/copilot-instructions.md (when project structure changes), .gitignore (when tech stack changes)  
**Commits:** After each bug fix, review fix, and task (prefixed with `[builder]`)  
**Shutdown signal:** Writes `logs/builder-N.done` when no eligible stories remain

---

## Commit Watcher

Runs continuously via `commitwatch`, launched automatically by `go`. Polls for new commits and spawns a scoped reviewer for each one.

**Persistent checkpoint:** The last-reviewed commit SHA is saved to `logs/reviewer.checkpoint` after each commit is processed. On restart, the watcher resumes from the checkpoint — no commits are ever missed or re-reviewed.

**Filtering:** Merge commits and the reviewer's own commits (reviews/-only changes) are automatically skipped to avoid wasted work.

For each new commit detected, the watcher enumerates all commits since the last checkpoint (`git log {last_sha}..HEAD --format=%H --reverse`), filters out skippable commits (merges, reviewer-only, coordination-only), and reviews the remaining ones. If there is a single reviewable commit, it reviews that commit individually. If there are multiple reviewable commits (e.g. the builder pushed several commits while the reviewer was busy), it reviews them as a single batch using the combined diff — one Copilot call instead of N:

**Severity-based filing:** Per-commit and batch reviews use a split filing strategy. [bug] and [security] issues are filed as `finding-<timestamp>.md` so the builder sees and fixes them immediately. [cleanup] and [robustness] issues are filed as `note-<timestamp>.md` — per-commit observations that the builder does not act on directly. The milestone review later evaluates notes for recurring patterns and only promotes them to `finding-*.md` if the same class of issue appeared in 2+ locations. This reduces noise while ensuring critical issues reach the builder without delay.

**Single commit prompt:**

> ...reviews the diff... For [bug] and [security] issues, create `finding-<timestamp>.md` files in `reviews/`. For [cleanup] and [robustness] issues, create `note-<timestamp>.md` files instead — these are observations that the milestone review will evaluate for patterns. Commit with message 'Code review: {sha}', run git pull --rebase, and push.

**Batched commits prompt (2+ commits):**

> ...reviews the combined diff... Same severity-based filing: `finding-*.md` for [bug]/[security], `note-*.md` for [cleanup]/[robustness]. Commit with message 'Code review: {base_sha:.8}..{head_sha:.8}', run git pull --rebase, and push.

**Milestone reviews:** When the watcher detects that all tasks in a milestone file in `milestones/` are checked, it triggers a cross-cutting review of the entire milestone's diff. This catches issues that per-commit reviews miss: inconsistent patterns across files, API mismatches, duplicated logic introduced across separate commits, and architectural problems in how pieces fit together. Each milestone is only reviewed once (tracked in `logs/reviewer.milestone`). The milestone reviewer also cleans up stale findings — creating `resolved-*.md` files for issues already fixed in the code.

**Code analysis:** Before the milestone review prompt runs, the watcher invokes `run_milestone_analysis()` from `code_analysis.py` — a tree-sitter-based structural analysis of all files changed in the milestone. It checks for long functions, deeply nested code, large files, and other structural issues across Python, JS/TS, and C#. The analysis results are included in the milestone review prompt so the reviewer has both diff context and structural quality data.

**Milestone frequency filter:** The milestone review reads all `note-*.md` files from per-commit reviews and applies a frequency filter before filing findings for the builder:
- [bug] and [security]: Always filed as `finding-*.md` regardless of frequency
- [cleanup] and [robustness]: Only promoted to `finding-*.md` if the same class of problem appears in 2+ locations or files across the milestone. One-off issues stay as notes.
- When promoting a recurring pattern, the reviewer consolidates the notes into a single finding describing the pattern and all affected locations.

> ...reviews the full milestone diff... Reads `note-*.md` files for per-commit observations. Files `finding-*.md` for [bug]/[security] always, and for [cleanup]/[robustness] only when the pattern recurs in 2+ locations. Cleans up stale findings. Commit with message 'Milestone review: {milestone_name}', run git pull --rebase, and push.

**Trigger:** Polls every 10 seconds for new commits  
**Scope:** Per-commit diff for individual reviews; full milestone diff for milestone reviews  
**Checkpoint:** `logs/reviewer.checkpoint` (per-commit), `logs/reviewer.milestone` (per-milestone)  
**Skips:** Merge commits, coordination-only commits (milestone files only, or reviews/ and bugs/ only)  
**Runs from:** `reviewer/` clone  
**Shutdown:** Checks for `logs/builder.done` each cycle; completes any remaining milestone reviews before exiting  
**Writes code:** [doc] fixes only (comments, README). Never changes application logic or DEPLOY.md directly.  
**Updates:** REVIEW-THEMES.md (rolling summary of top recurring review patterns, replaced each milestone review)

---

## Tester

Milestone-triggered via `testloop`, launched automatically by `go`. Watches `logs/milestones.log` for newly completed milestones and runs scoped tests for each one.

For each newly completed milestone:

> Read SPEC.md and the milestone files in `milestones/` to understand the project. A milestone — '{milestone_name}' — has just been completed. Pull the latest code with `git pull --rebase`. Run `git diff {milestone_start_sha} {milestone_end_sha} --name-only` to see which files changed in this milestone. Build the project. Run all existing tests. Testing has two priorities: (1) test the new milestone's code — features with no tests, missing error handling, missing validation; (2) test integration with existing code — look for missing tests that span multiple components or layers (e.g. form → API service → backend endpoint → UI update), and review existing test files for cross-feature gaps that accumulated over prior milestones. The more milestones completed, the more important integration tests become. Prioritize integration tests over unit tests. Each test should verify a distinct user-facing behavior. Do not test internal implementation details, getters/setters, or trivially obvious code. Write at most 20 new tests per run. Do NOT start the application, start servers, or test live endpoints — a separate validator agent handles runtime testing in containers. Focus exclusively on running the test suite. For any test that fails, create a `bug-<timestamp>.md` file in `bugs/` with what failed, steps to reproduce, and which milestone. Do not edit or delete existing files in `bugs/`. Commit new tests and new bug files, run git pull --rebase, and push. If the push fails, run git pull --rebase and push again (retry up to 3 times). If everything passes and no new tests are needed, do nothing.

When the builder finishes, the tester sees `logs/builder.done` and exits.

**Trigger:** Polls `logs/milestones.log` every 10 seconds (configurable via `--interval`)  
**Scope:** New milestone's changed files + integration with existing code  
**Checkpoint:** `logs/tester.milestone` (set of milestones already tested)  
**Runs from:** `tester/` clone  
**Shutdown:** Checks for `logs/builder.done`; exits when builder is done  
**Writes code:** Tests only  
**Commits:** When it writes new tests or finds bugs

---

## Validator

Milestone-triggered via `validateloop`, launched automatically by `go`. Watches `logs/milestones.log` for newly completed milestones and validates the application in a Docker container.

For each newly completed milestone:

> You are a deployment validator. Your job is to build the application in a Docker container, run it, and verify it works against the acceptance criteria in SPEC.md. FIRST: Read DEPLOY.md if it exists — it contains everything previous runs learned about building and deploying this application. Follow its instructions for Dockerfile configuration, environment variables, port mappings, startup sequence, and known gotchas. Read SPEC.md for acceptance criteria. Read the milestone files in `milestones/` to see which milestones are complete — you should test all requirements that should be working up to and including milestone '{milestone_name}'. Set `COMPOSE_PROJECT_NAME` for container namespace isolation and use deterministic host ports derived from the project name. Stop and remove any running containers from this project's previous validation. If no Dockerfile exists, create one appropriate for the project's tech stack. Build the container. Start it. Wait for the app to be healthy. Test every SPEC.md requirement that should be working at this point — for milestone 1, just confirm the app starts and responds; for later milestones, test accumulated functionality. Leave containers running after testing so the app is browsable. Report failures by creating `bug-<timestamp>.md` files in `bugs/`. Update DEPLOY.md with everything learned about deploying this application. Commit and push.

**Port isolation:** Each project gets deterministic host ports computed from a SHA-256 hash of the project name (range 3000-8999). `COMPOSE_PROJECT_NAME` is set to the project name so Docker containers from different projects are namespaced and don't conflict. This allows multiple projects (or model comparisons) to run side-by-side on the same host.

**Persistent containers:** After successful validation, containers are left running so the application is accessible at `http://localhost:<port>` for browsing. Containers are cleaned up at the start of the *next* milestone's validation (not after testing). This means the latest validated milestone is always browsable.

**Milestone SHA checkout:** Before validating, the validator checks out the exact commit at the milestone's end SHA (`git checkout {end_sha}`). This ensures each milestone is tested against exactly the code that existed when it was completed, not code from later milestones. Copilot commits validation artifacts (Dockerfile, DEPLOY.md, bugs/) on the detached HEAD. After Copilot finishes, the Python orchestration collects those commits, returns to main, cherry-picks them onto main, and pushes. This avoids rebase conflicts that occur when pushing directly from a detached HEAD that diverged from main while validation was running.

**Persistent deployment knowledge:** The validator reads DEPLOY.md at the start of each run and updates it at the end. This creates a ratchet effect — each milestone's validation run gets more reliable because it inherits knowledge from all prior runs. DEPLOY.md captures: Dockerfile configuration, required environment variables, port mappings, docker-compose service setup, startup sequence, health check details, and known gotchas. The builder also reads DEPLOY.md to stay compatible with deployment requirements.

**Validation results log:** After each milestone, the validator writes `validation-results.txt` in the repo root (not committed). The Python orchestration copies it to `logs/validation-<milestone-name>.txt` for post-run analysis. Each line is `PASS` or `FAIL` with a description of what was tested (container build, startup, endpoints, error cases).

When the builder finishes, the validator sees `logs/builder.done` and exits.

**Trigger:** Polls `logs/milestones.log` every 10 seconds (configurable via `--interval`)  
**Scope:** All SPEC.md requirements that should work at the current milestone  
**Checkpoint:** `logs/validator.milestone` (set of milestones already validated)  
**Runs from:** `validator/` clone  
**Shutdown:** Checks for `logs/builder.done`; exits when builder is done  
**Writes code:** Dockerfile, docker-compose.yml (if needed), DEPLOY.md, Playwright tests (if frontend detected)  
**Commits:** When it creates/updates deployment files, finds bugs, or updates DEPLOY.md

**Playwright UI testing (automatic):** Before each validation run, the orchestration checks whether the repo contains a frontend (package.json, .tsx/.jsx/.vue/.svelte files, or frontend keywords in SPEC.md). When a frontend is detected, the validator prompt is extended with Playwright instructions that tell the Copilot agent to:
- Add a `playwright` sidecar service to docker-compose.yml using `mcr.microsoft.com/playwright:v1.52.0-noble`
- Write TypeScript tests in `e2e/` using `data-testid` selectors (with semantic selector fallbacks)
- Test page rendering, navigation, form submission, and interactive elements in a real headless browser
- Run tests via `docker compose run --rm playwright` and include `[UI]` results in `validation-results.txt`
- Report UI failures to `bugs/` by creating a `bug-<timestamp>.md` file with a `[UI]` prefix

For API-only projects, the Playwright section is omitted entirely — no extra prompt text, no browser overhead.

---

## Positive Feedback Loops

The multi-agent system is designed around cumulative knowledge. Several mechanisms create positive feedback loops where each milestone makes subsequent milestones more reliable:

### Deployment Knowledge Ratchet (DEPLOY.md)

The validator writes DEPLOY.md after each milestone — Dockerfile configuration, required env vars, port mappings, startup sequence, health check details, and known gotchas. The builder reads DEPLOY.md before every session to stay compatible with deployment requirements. Each milestone's validation run inherits all knowledge from prior runs, so container builds and runtime validation get progressively more reliable. What was a painful discovery in milestone 1 becomes a documented fact for milestone 2.

### Review Signal Filtering (notes → findings)

Per-commit reviews catch every issue but split them by urgency. [bug] and [security] issues are filed as `finding-*.md` so the builder sees and fixes them immediately — these are too important to wait. [cleanup] and [robustness] issues are filed as `note-*.md` — observational records that the builder does not act on directly. When a milestone completes, the milestone review reads all accumulated notes and applies a frequency filter: only patterns that recurred across 2+ locations or files get promoted to `finding-*.md` for the builder. One-off cleanup issues stay as notes. This means the builder spends fix cycles on systemic problems, not isolated nitpicks, and the signal-to-noise ratio of review feedback improves over time as the reviewer learns what patterns actually recur.

### Review Themes (REVIEW-THEMES.md)

The reviewer maintains REVIEW-THEMES.md — a cumulative knowledge base of recurring code quality patterns observed across milestone reviews. The builder reads it to avoid repeating the same class of mistake. Themes are never dropped — once a pattern is identified, it stays permanently so the builder always has the full history of lessons learned.

### Codebase-Aware Planning

The milestone planner reads the actual codebase before expanding the next backlog story. It discovers what patterns have emerged — base classes, naming conventions, dependency injection wiring, project structure — and writes tasks that match those patterns. This prevents the planner from fighting the codebase's natural direction and ensures each milestone's tasks build on what actually exists rather than what was originally imagined.

### Evolving Style Guide (.github/copilot-instructions.md)

The builder updates the project's copilot-instructions.md whenever project structure, key files, architecture, or conventions change. Future builder sessions (and all other Copilot-powered agents) read this file, so coding conventions stay consistent as the project grows. This is especially important across iterative development sessions where the builder agent is a fresh process with no memory of prior sessions.

---

## Agent Coordination Rules

- **Commit message tagging:** Every agent prefixes its commit messages with its name in brackets — `[builder]`, `[reviewer]`, `[tester]`, `[validator]`, `[planner]`, `[bootstrap]`. This makes it easy to see who did what in `git log`.
- The **Planner** runs on demand via `plan`. It assesses project state (fresh / continuing / evolving), manages BACKLOG.md (story queue with three-state tracking: `[ ]` unclaimed, `[~]` claimed, `[x]` completed), updates SPEC.md if new requirements are detected, then writes one milestone file per story in `milestones/`. It never writes application code.
- The **Builder** runs in a claim loop. Each builder claims a story from BACKLOG.md (`[~]`), calls the planner to expand it into a milestone, completes all tasks, marks the story done (`[x]`), and loops. When no eligible stories remain, writes `logs/builder-N.done`.
- The **Reviewer** reviews each commit individually, plus a cross-cutting review when a milestone completes. Non-code issues ([doc]: stale docs, misleading comments) are fixed directly by the reviewer (except DEPLOY.md — that gets filed as a finding). Code-level issues ([code]) are filed as `finding-*.md` files in `reviews/` for the builder. Milestone reviews clean up stale findings by creating `resolved-*.md` files.
- The **Tester** runs scoped tests when a milestone completes, focusing on changed files. It runs the test suite only — it does not start the app or test live endpoints. Files bugs in `bugs/`. Exits when the builder finishes.
- The **Validator** builds the app in a Docker container after each milestone, starts it, and tests it against SPEC.md acceptance criteria. Files bugs in `bugs/`. Persists deployment knowledge in DEPLOY.md. Exits when the builder finishes.
- Agents never edit or delete existing files in `reviews/` or `bugs/` — they only create new files. This eliminates merge conflicts on those directories.
- All agents run `git pull --rebase` before pushing to avoid merge conflicts. Since `reviews/` and `bugs/` are append-only directories (no file is ever edited), concurrent new-file creations never conflict.
- `SPEC.md` is the source of truth for technical decisions. `BACKLOG.md` is the story queue. Edit either anytime to steer the project — run `plan` to adapt.
- Each milestone file in `milestones/` is exclusively owned by one builder — no two builders edit the same file.
- `REVIEW-THEMES.md` is a cumulative knowledge base of recurring review patterns, owned by the reviewer. The reviewer updates it after each milestone review, adding new themes but never removing old ones. Themes persist forever as lessons learned. The builder reads it to avoid repeating patterns but never modifies it.

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

Agent directories (`builder-1/`, `builder-N/`, `reviewer/`, `tester/`, `validator/`) are treated as disposable working copies — they can be deleted and re-cloned from the repo at any time. The repo (GitHub or `remote.git/`) and `logs/` directory (checkpoints) are the persistent state.

The `--spec-file` for session 2 can contain just new requirements ("Add a React frontend") or a complete updated requirements doc (old API spec + new frontend spec). The planner compares REQUIREMENTS.md against SPEC.md and the codebase to determine what's new.

---

## Legacy Commands

The original `reviewoncommit` and `testoncommit` commands still exist for manual/standalone use. They use the old `_watch_loop` polling mechanism and are not launched by `go`.

---

## Shutdown Protocol

Multi-builder shutdown uses per-builder sentinel files:

1. **Builder completes all stories:** When a builder finds no eligible stories in BACKLOG.md (all are `[~]` or `[x]`), it waits for downstream agents to go idle, verifies checklists are clean, then writes `logs/builder-N.done`.
2. **Wait for agents to go idle:** Each builder monitors `logs/reviewer.log`, `logs/tester.log`, and `logs/validator.log` modification times. When all logs haven't changed in 120+ seconds, agents are considered idle.
3. **Check work lists:** The builder pulls latest and scans `bugs/` for open bugs (bug-* without fixed-*), `reviews/` for open findings (finding-* without resolved-*), and milestone files for unchecked items.
4. **Fix or exit:** If new work was filed, the builder fixes it (up to 4 fix-only cycles) and loops back to step 2. If checklists are clean and agents are idle, writes `logs/builder-N.done`.
5. **All builders done:** `is_builder_done()` discovers all `builder-*.done` files in `logs/` and returns True only when all expected builders have finished.
6. **Agents shut down:** The reviewer, tester, and validator see all builders done on their next poll cycle. The reviewer completes any remaining milestone reviews before exiting.
7. **Crash fallback:** If `logs/builder.log` hasn't been modified in 30+ minutes, agents assume the builder crashed and shut down.
8. **Startup cleanup:** `go` calls `clear_builder_done(num_builders)` to remove stale sentinel files before launching agents.
9. **Timeout safety:** If agents don't go idle within 10 minutes, the builder writes its sentinel and exits anyway.
