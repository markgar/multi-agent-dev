# Backlog Planner Rubric

Evaluation criteria for the output of the **backlog planner**: the initial planner run that creates BACKLOG.md and the first milestone file in `milestones/`. This is the quality gate that runs after `PLANNER_INITIAL_PROMPT` (and optionally after `PLANNER_COMPLETENESS_PROMPT`), before the build starts.

Not a rubric for humans — this is a specification for an automated checker.

---

## Inputs

The checker reads three files from the builder directory:

- **BACKLOG.md** — the story queue
- **`milestones/`** — containing the first milestone file
- **REQUIREMENTS.md** — the original spec (for proportionality and coverage checks)

---

## Check Categories

### A. Structural Checks (Deterministic — Python)

These are fast, pattern-based checks that don't need an LLM call. Each returns pass/fail with a specific reason.

#### A1. Backlog file format

| Check | Pass | Fail | Action on fail |
|---|---|---|---|
| File starts with `# Backlog` heading | Heading present | No heading or wrong heading | **Warn** — cosmetic, proceed |
| Every story matches format: `N. [x] ... <!-- depends: ... -->` or `N. [ ] ... <!-- depends: ... -->` | All lines match | Any story missing checkbox or depends annotation | **Re-plan** — dependency graph is broken |
| Story numbers are sequential (1, 2, 3...) | Sequential, no gaps | Gaps, duplicates, or out-of-order numbers | **Warn** — cosmetic, proceed |
| First story is checked (`[x]`) | Checked | Unchecked | **Re-plan** — first milestone won't be planned |

#### A2. Dependency graph validity

| Check | Pass | Fail | Action on fail |
|---|---|---|---|
| All `<!-- depends: N -->` reference existing story numbers | All refs valid | Any ref to non-existent story | **Re-plan** — dependency graph is invalid |
| No circular dependencies | Acyclic graph | Cycle detected (A→B→A) | **Re-plan** — will cause deadlock |
| Story #1 has `<!-- depends: none -->` | No deps | Depends on something | **Warn** — scaffolding shouldn't depend on anything |

#### A3. Prohibited content

| Check | Pass | Fail | Action on fail |
|---|---|---|---|
| No stories mentioning tests (unit test, integration test, e2e test, test suite, test coverage) | Clean | Test story found | **Fix** — remove the story, renumber, fix deps |
| No stories mentioning containerization (Dockerfile, docker-compose, Docker, container, deployment, CI/CD) | Clean | Container story found | **Fix** — remove the story, renumber, fix deps |
| No stories mentioning cleanup/refactoring of code that doesn't exist yet | Clean | Pre-planned refactoring story found | **Fix** — remove the story |

Detection: scan story text for keywords `test`, `dockerfile`, `docker-compose`, `container`, `deployment`, `ci/cd`, `pipeline`, `refactor`, `cleanup`, `code quality`. Flag stories where these are the primary activity, not incidental mentions (e.g. "Create health endpoint" mentioning "test" in "…so the validator can test it" is fine).

#### A4. First milestone structure

| Check | Pass | Fail | Action on fail |
|---|---|---|---|
| The first milestone file in `milestones/` exists | File present | No milestone file | **Re-plan** — should plan exactly one milestone |
| There is exactly one milestone file in `milestones/` | One file | Zero or 2+ files | **Re-plan** — should plan exactly one milestone |
| Milestone has `> **Validates:**` block immediately after heading | Block present | Missing | **Re-plan** — validator needs acceptance criteria |
| Milestone has 3-7 tasks | In range | Out of range | **Re-plan** if 0 or 10+; **Warn** if 1-2 or 8-9 |
| All tasks have `- [ ]` checkbox format | All match | Missing checkboxes | **Warn** — builder tracks completion via checkboxes |

---

### B. Proportionality Check (Deterministic — Python)

This check evaluates whether the story count is reasonable for the app's size.

**Method:**

1. Count stories in BACKLOG.md (total lines matching `N. [`)
2. Estimate app complexity from REQUIREMENTS.md:
   - Count `##` and `###` headings as a rough feature proxy
   - Count keywords indicating distinct features: entity names (capitalized nouns after "Create"/"Add"), endpoint paths (`/api/...`), page references
3. Compute ratio: `stories / estimated_features`

| Ratio | Assessment | Action |
|---|---|---|
| 1.0–3.0 | **Pass** — reasonable proportionality | Proceed |
| 0.5–0.99 | **Warn** — stories may be too coarse, features could be under-decomposed | Log warning, proceed |
| 3.1–4.0 | **Warn** — stories may be over-split | Log warning, proceed |
| < 0.5 or > 4.0 | **Fail** — wildly disproportionate | **Re-plan** |

---

### C. Story Quality Checks (LLM-Evaluated)

These require an LLM call because they evaluate semantics. Run as a single focused Copilot call after the deterministic checks pass.

The LLM checker prompt should evaluate each criterion and output a structured verdict per check (PASS/FAIL + reason).

#### C1. Scaffolding-first ordering

Story #1 must be project scaffolding — creating the project structure, entry point, and a health/hello endpoint. If story #1 is a feature story, fail.

**Pass:** "Scaffolding — .NET solution structure, health endpoint, React app with Vite"
**Fail:** "Members — Create member entity and CRUD endpoints"

#### C2. Vertical slice orientation

Stories should represent user-facing features delivered through multiple layers, not single layers across multiple features.

**Pass:** "Members — backend API" (one feature, backend layers)
**Pass:** "Members — admin pages" (one feature, frontend layer)
**Fail:** "All domain entities" (one layer, all features)
**Fail:** "All repositories" (one layer, all features)

Evaluate: Do 80%+ of stories name a feature? Do any stories name only a layer without a feature? If more than 2 stories are layer-only, fail.

#### C3. Description specificity

Story descriptions should contain enough detail to understand scope without reading REQUIREMENTS.md.

**Pass:** "Members — backend API — CRUD endpoints: GET /api/members (list with search), GET /api/members/:id, POST /api/members, PUT /api/members/:id, PATCH /api/members/:id/deactivate"
**Fail:** "Members — implement member functionality"

Evaluate: Sample 5 stories (or all if <10). Does each story mention at least one concrete artifact — an entity name with fields, an endpoint path, a page name, a specific behavior? If 2+ sampled stories have zero concrete artifacts, fail.

#### C4. Feature coverage

Every `##` section in REQUIREMENTS.md should map to at least one story in BACKLOG.md.

Note: this overlaps with the existing completeness check (`PLANNER_COMPLETENESS_PROMPT`). If the completeness check already ran, this can be skipped. If the checker replaces the completeness check, include this.

#### C5. Over-splitting detection

A single CRUD feature (one entity with list/create/read/update/delete) should not be split into more than 2 stories (typically backend + frontend). If the same entity appears in 3+ stories, flag it.

**Pass:** "Books — backend API" + "Books — storefront page" (2 stories, 1 feature)
**Fail:** "Books — list endpoint" + "Books — create endpoint" + "Books — update/delete endpoints" (3 stories, 1 feature's CRUD operations split unnecessarily)

#### C6. First milestone task quality

For each task in the first milestone:

1. **Self-contained description** — does the task include enough detail (file paths, config keys, field names) that the builder can implement it without reading other docs?
2. **Single concern** — does the task describe one logical change, or does it have "and"/"with" connecting distinct work?
3. **No stuffing** — does the task create 3 or fewer files/endpoints/entities?

Sample all tasks in the first milestone. If 2+ tasks fail on any criterion, fail the check.

#### C7. Validates block quality

The `> **Validates:**` block must contain at least 3 specific, testable assertions. Each assertion should reference a concrete command, endpoint path with HTTP method and expected status code, page URL, or CLI command with expected output.

**Pass:** "GET /api/health returns 200 with JSON body containing `status: healthy`. `dotnet build` succeeds. `npm run build` succeeds."
**Fail:** "The application should work and be testable."

---

## Evaluation Flow

```
1. Run deterministic checks (A1-A4, B)
   ├── Any "Re-plan" failures? → trigger re-plan, stop
   ├── Any "Fix" failures? → fix and re-check
   └── All pass/warn? → continue

2. Run LLM quality check (C1-C7) as single Copilot call
   ├── 2+ failures? → trigger re-plan with specific feedback
   ├── 1 failure? → warn and proceed
   └── All pass? → proceed to build
```

---

## Re-plan Feedback

When the checker triggers a re-plan, the feedback must be specific. Don't say "improve quality" — say exactly what's wrong:

```
The following issues were found in the backlog:
- Story 12 ("Frontend orchestration cleanup slice") is a pre-planned refactoring story. Remove it — cleanup is handled reactively via review findings.
- Stories 3, 4, 5 split Book CRUD into three stories (list/create/update-delete). Consolidate into at most 2 stories (backend API + frontend pages).
- Story 11 description "Code formatting enforcement setup" is too vague. Specify which tools (ESLint, Prettier, dotnet format) and what configuration.
```

The checker should produce a concrete, actionable list that can be appended to the re-plan prompt.

---

## What This Checker Does NOT Evaluate

These are out of scope — they either happen at different phases or are covered by other agents:

- **SPEC.md quality** — evaluated during bootstrap, not the backlog planner
- **README.md quality** — evaluated during bootstrap
- **copilot-instructions.md quality** — evaluated after generation, separate phase
- **Milestone task quality for milestones 2+** — evaluated by the milestone planner checker (future)
- **Code quality** — handled by the reviewer agent
- **Test coverage** — handled by the tester agent
- **Deployment readiness** — handled by the validator agent

---

## Calibration Data

Tested against three builds:

| Build | Stories | Expected | Proportionality | Structural | Story Quality | Overall |
|---|---|---|---|---|---|---|
| Stretto-Claude (new) | 31 | Large/Complex (16+ features) | Pass (ratio ~2.0) | Pass (all clean) | Pass (vertical, detailed) | **Pass** |
| Bookstore-Claude | 8 | Small (3 features) | Pass (ratio ~2.7) | Pass (all clean) | Pass (vertical, detailed) | **Pass** |
| Bookstore-Codex | 12 | Small (3 features) | Fail (ratio ~4.0) | Fail (no heading) | Fail (2 non-feature stories, over-split CRUD) | **Fail — re-plan** |
