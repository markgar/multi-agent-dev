# Agent Prompts

Each agent is a `copilot --yolo` call with a specific prompt. Here's exactly what each one is told to do.

---

## Bootstrap

Runs once when you call `bootstrap "name" "description"`.

> Create a directory called builder. cd into it. Initialize a git repo. Create an appropriate .gitignore for the project. Create a README.md that describes the project: `{description}`. Create a SPEC.md that defines the desired end state of the project. SPEC.md should include: a high-level summary, the tech stack and language, the features and requirements, any constraints or guidelines, and acceptance criteria for what 'done' looks like. Be specific and thorough in SPEC.md — it is the source of truth that all future planning is based on. Do NOT create a TASKS.md — task planning happens later. Commit with message 'Initial commit: project spec'. Run 'gh repo create `{user/name}` --public --source .' and push.

**Creates:** README.md, SPEC.md, git repo, GitHub remote  
**Writes code:** No

---

## Planner

Runs on demand via `plan`. Call it before the first `build`, or whenever you need to re-evaluate the task list.

> You are a planning-only orchestrator. You must NOT write any code or modify any source files. Your only job is to manage TASKS.md. Read SPEC.md to understand the desired end state. Read README.md for project context. Look at the current codebase to see what has been built so far. Read BUGS.md if it exists to see outstanding bugs. Read REVIEWS.md if it exists to see outstanding review items. Read TASKS.md if it exists to see the current plan. Now evaluate: are there tasks that need to be added, broken down, reordered, or clarified based on what has been built vs what SPEC.md requires? If TASKS.md does not exist, create it with a detailed numbered checkbox task list that will achieve everything in SPEC.md. Each task should be concrete and actionable, building on the last. Include a task early on to remove any default scaffolding or template code that does not belong. Include a final task to verify everything works end to end. If TASKS.md already exists, update it — add missing tasks, refine vague ones, but never remove or uncheck completed tasks. Commit any changes to TASKS.md with message 'Update task plan', run git pull --rebase, and push. If no changes are needed, do nothing.

**Creates:** TASKS.md (first run), updates it on subsequent runs  
**Reads:** SPEC.md, README.md, codebase, TASKS.md, BUGS.md, REVIEWS.md  
**Writes code:** No

---

## Builder

Runs via `build`. Does up to `-count` tasks (default 3) in a single session.

> Before starting, review README.md, SPEC.md, and TASKS.md to understand the project's purpose and plan. Only build, fix, or keep code that serves that purpose. Remove any scaffolding, template code, or functionality that does not belong. Now look at BUGS.md first. If there are any unfixed bugs, fix them one at a time — fix a bug, mark it fixed in BUGS.md, commit with a meaningful message, run git pull --rebase, and push. Repeat for each unfixed bug. Then look at REVIEWS.md. If there are any unchecked review items, address them one at a time — fix the issue, mark it done in REVIEWS.md, commit with a meaningful message, run git pull --rebase, and push. Once all bugs and review items are fixed (or if there are none), move to TASKS.md. Do up to `{count}` unchecked tasks, one at a time. For each task: do the task, commit with a meaningful message, mark it complete in TASKS.md, commit that too, run git pull --rebase, and push. Then move to the next unchecked task. Stop after `{count}` tasks or when there are no more unchecked tasks, whichever comes first.

**Reads:** README.md, SPEC.md, TASKS.md, BUGS.md, REVIEWS.md  
**Writes code:** Yes  
**Commits:** After each bug fix, review fix, and task

---

## Reviewer

Runs continuously via `reviewoncommit`, triggered by new commits.

> You are a code reviewer. You must NOT add features or change functionality. Your only job is to review recent changes for quality issues. Read SPEC.md and TASKS.md to understand the project goals and what was planned. Run `git diff HEAD~3 --stat` to see which files changed recently, then read the full diffs with `git diff HEAD~3`. Review the changed code for: code duplication, unclear naming, overly complex logic, missing error handling, security issues (hardcoded secrets, injection risks, missing input validation), violations of the project's conventions or tech stack, and dead or unreachable code. Do NOT flag minor style preferences or nitpicks. Only flag issues that meaningfully affect correctness, security, maintainability, or readability. If you find issues, write each one to REVIEWS.md as a checkbox list item with the file, a brief description of the problem, and a suggested fix. Do not duplicate items already in REVIEWS.md. If there are no meaningful issues, do nothing. If you wrote to REVIEWS.md, commit with message 'Code review findings', run git pull --rebase, and push.

**Reads:** SPEC.md, TASKS.md, recent diffs, REVIEWS.md  
**Writes code:** No  
**Commits:** When it finds issues

---

## Tester

Runs continuously via `testoncommit`, triggered by new commits.

> Read SPEC.md and TASKS.md to understand the project. Look at the latest git commit to see what changed. Build the project. Run all existing tests. If there is a runnable API, start it, test the endpoints with curl, then stop it. Now evaluate test coverage, but ONLY for the code that changed in the latest commit. Do NOT audit the entire codebase for test gaps. If the changed code has major gaps — like no tests at all for a new feature, or completely missing error handling tests — write a few focused tests to cover those gaps. Do not write tests for minor edge cases or for code that already has reasonable coverage. If existing tests already cover the changes well, do not add more. Write at most 5 new tests per run. Run the new tests. For any test that fails — whether existing or new — write each failure to BUGS.md as a checkbox list item with a clear description of what is broken and how to reproduce it. Do not duplicate bugs that are already in BUGS.md. Commit all new tests and any BUGS.md changes, run git pull --rebase, and push. If everything passes and no new tests are needed, do nothing.

**Reads:** SPEC.md, TASKS.md, codebase, BUGS.md  
**Writes code:** Tests only  
**Commits:** When it writes new tests or finds bugs
