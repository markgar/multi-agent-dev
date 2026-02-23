# Planner Quality Rubric

A measuring stick for evaluating planner output. Use this to grade milestone files in `milestones/`, SPEC.md, and related documents produced by a planning run. Each criterion is scored Pass / Partial / Fail with concrete indicators.

This rubric describes what good planner output looks like — not how to build the planner.

---

## 1. Task Quality

A task is the atomic unit of work: one commit, one focused coding session.

| Criterion | Pass | Partial | Fail |
|-----------|------|---------|------|
| **Single concern** | Task describes one logical change — one file or one tightly coupled pair | Task has a mild "and" connecting related work (e.g. "Create entity and add to DbContext") | Task contains distinct unrelated concerns joined by "and", "with", or commas |
| **Right-sized** | Builder can understand, code, and commit the task in one pass without context overflow | Task is slightly large but still completable (e.g. 2-3 closely related files) | Task packs 4+ endpoints, 4+ entities, or 4+ pages into one line |
| **Self-contained description** | Task includes all detail the builder needs: field names, types, enum values, relationships, endpoint paths | Task names the thing to create but omits some detail (e.g. "Create Member entity" with only half the fields listed) | Task is a vague stub ("Create member functionality") that requires cross-referencing other docs |
| **No test or container tasks** | Milestone contains zero tasks for writing tests, Dockerfiles, or docker-compose | One task mixes a small test with feature work | Standalone testing or containerization milestones exist |
| **No cleanup-only tasks** | Cleanup items from `reviews/` are folded into the next feature milestone | Minor cleanup milestone with 1-2 items | Standalone "refactor" or "cleanup" milestone with no feature work |

### Anti-patterns to flag

- **Endpoint stuffing:** "Create MembersController with GET list, GET by id, POST, PUT, DELETE/deactivate" — this is 5+ endpoints in one task.
- **Entity batching:** "Create Organization, Member, ProgramYear, and Project entities" — this is 4 entities in one task.
- **Layer cramming:** "Create Member entity, repository, service, and controller" — this is 4 layers in one task.
- **Configuration overload:** "Add .editorconfig, configure Program.cs with health endpoint, add Swagger, and register DI" — this is 4 distinct setup steps crammed together.

### Calibration: what a good task looks like

```
- Create Member entity (Id, FirstName, LastName, Email, Role enum, IsActive, OrganizationId)
- Create MemberRepository implementing BaseRepository<Member>
- Create MembersController with GET /members and GET /members/:id endpoints
- Create MembersController POST and PUT endpoints with request validation
- Create Members list page with search and add-member form
```

Each task is one file (or a tightly coupled pair), with enough detail that the builder doesn't need to look anything up.

---

## 2. Milestone Quality

A milestone is a coherent batch of related tasks that leaves the app runnable.

| Criterion | Pass | Partial | Fail |
|-----------|------|---------|------|
| **Size range** | 3-7 tasks | 2 tasks or 8-9 tasks | 1 task or 10+ tasks |
| **Cohesion** | All tasks in the milestone serve a single feature or concern | Most tasks are related with 1 outlier | Tasks span unrelated features |
| **Vertical slice** | Milestone delivers a testable feature through one or more layers. Paired backend+frontend milestones for one feature count as vertical slices. | Milestone covers 2-3 layers of one feature with a minor outlier task | Milestone covers one layer across many features ("All entities", "All repositories") |
| **Runnable after completion** | App builds, starts, and responds to at least one request after the milestone | App builds but might not respond meaningfully | Milestone leaves the app in a broken or un-startable state |
| **Natural naming** | Milestone name describes the delivered feature ("Members — backend", "Auth flow") | Name describes the layer but hints at feature ("API controllers — auth") | Name describes only the layer ("Domain entities — batch 2") |

### Anti-patterns to flag

- **Horizontal layering:** Milestones organized as "All entities" → "All configurations" → "All repositories" → "All services" → "All controllers". The validator can't test anything until the controller milestones.
- **Uniform sizing:** Every milestone has exactly the same number of tasks (e.g. all 5). This suggests the planner is optimizing for a count rather than natural groupings.
- **Feature split across 4+ milestones:** A single feature (e.g. Members) requiring entity + repo + service + API + frontend shouldn't be spread across 5 separate single-layer milestones. 1-2 milestones for one feature is right.
- **Micro-milestones:** A milestone with 1-2 trivial tasks (e.g. "Add ESLint config") that could be part of a larger scaffolding milestone.

### Calibration: what a good milestone looks like

```
## Milestone: Members feature
- Create Member entity (Id, FirstName, LastName, Email, Role enum, IsActive, OrganizationId)
- Create MemberRepository implementing BaseRepository<Member>
- Add Fluent API configuration for Member and seed data
- Create MemberService with list, get-by-id, create, update, and deactivate operations
- Create MembersController with GET /members, GET /members/:id, POST, PUT, DELETE endpoints
- Create Members list page with search and add-member form
- Create Member detail page with edit form and deactivate button
```

7 tasks. Each is one file or a tightly coupled pair. The milestone delivers one complete user-facing feature. After completion, the validator can test member CRUD end-to-end.

---

## 3. Roadmap Quality (Progressive Planning)

The roadmap is the high-level story list that guides progressive expansion.

| Criterion | Pass | Partial | Fail |
|-----------|------|---------|------|
| **Feature-oriented stories** | Each story is a user-facing feature ("Members", "Events and attendance", "Auditions") | Stories are mostly features with a few layer-oriented items | Stories are layers ("All entities", "All services") |
| **Scaffolding first** | Story #1 is always project scaffolding (runnable app with health endpoint) | Scaffolding is early but not first | No scaffolding story; features assume infrastructure exists |
| **Dependency ordering** | Stories are ordered so dependent features come after prerequisites (e.g. Members before Attendance) | Mostly ordered with 1-2 out-of-order items | No clear ordering; features appear randomly |
| **Proportional count** | Story count is proportional to app complexity (see sizing guide below) | Count is slightly over or under for the app's tier | Count is wildly mismatched — trivial app with 20+ stories, or complex app with 3 stories |
| **Stable across re-plans** | Completed stories stay struck through; unstarted stories can be reordered but aren't duplicated or dropped | Minor rewording of unstarted stories | Completed stories get lost or unchecked; stories appear and disappear between re-plans |
| **Progressive expansion** | Only 1-2 unstarted milestones exist in `milestones/` — the rest are backlog stories expanded on demand | 3 unstarted milestones detailed | All stories are expanded into milestones upfront (defeats progressive planning) |

### App sizing guide

Classify the app by counting distinct user-facing features in REQUIREMENTS.md (CRUD entities, auth flows, dashboards, integrations, file uploads, calendars, etc.). Each feature that requires its own backend+frontend work counts as one.

| App tier | Feature count | Expected stories | Examples |
|----------|--------------|-----------------|----------|
| **Small** | 1-3 features | 3-5 stories | CLI calculator, bookstore CRUD, todo app |
| **Medium** | 4-8 features | 6-15 stories | Blog with auth, project tracker, simple SaaS |
| **Large** | 9-15 features | 12-25 stories | Multi-entity CRUD app, e-commerce site |
| **Complex** | 16+ features | 20-40 stories | Multi-tenant SaaS (Stretto), ERP, LMS |

When a feature spans backend + frontend as separate stories (e.g. "Members — backend API" + "Members — admin pages"), count the pair as one feature but two stories. This is the expected pattern for full-stack apps — it keeps milestones focused while delivering vertical slices.

**Ratio check:** Divide story count by feature count. A ratio of 1.5-2.5 is typical for full-stack apps (backend + frontend stories per feature, plus scaffolding). Below 1.0 suggests stories are too coarse. Above 3.0 suggests over-splitting.

### Anti-patterns to flag

- **All-upfront expansion:** Every roadmap story has corresponding milestones already detailed. This is the old behavior — no progressive benefit.
- **Fine-grained stories:** Stories where each is a single CRUD operation rather than a feature. Stories should group related capabilities (e.g. "Events and attendance" not "Create event" + "List events" + "Delete event").
- **Missing stories:** Features in REQUIREMENTS.md that have no corresponding story in the roadmap.
- **Fixed-count thinking:** Applying a fixed story count regardless of app complexity (e.g. always targeting 10 stories).

---

## 4. SPEC.md Quality

SPEC.md captures technical decisions, not feature exhaustiveness.

| Criterion | Pass | Partial | Fail |
|-----------|------|---------|------|
| **Size** | 40-60 lines | 61-100 lines | 100+ lines (or under 20 lines, missing key decisions) |
| **Contains: tech stack** | Languages, frameworks, libraries, and versions listed | Most listed, some missing | No tech stack section |
| **Contains: architecture** | Layer names, dependency rules, project structure | Architecture mentioned but not the dependency rules | No architecture section |
| **Contains: cross-cutting concerns** | Auth strategy, multi-tenancy approach, error handling, file storage approach | Some cross-cutting concerns mentioned | No cross-cutting concerns |
| **Contains: acceptance criteria** | Feature-level criteria ("members can be managed", "attendance can be tracked") | Criteria exist but are field-level ("Member has FirstName, LastName, Email") | No acceptance criteria |
| **Does NOT contain: entity fields** | No field-by-field entity definitions | A few entities have fields listed | Full entity field tables |
| **Does NOT contain: API routes** | No endpoint-by-endpoint route table | A few key routes listed | Full API route table |
| **Does NOT contain: page layouts** | No page-by-page UI specification | A few key pages described | Full page layout descriptions |
| **No overlap with other docs** | SPEC.md content is not repeated in README.md or copilot-instructions.md | Minor overlap (e.g. tech stack appears in README too) | Major content duplicated across 2+ documents |

---

## 5. README.md Quality

| Criterion | Pass | Partial | Fail |
|-----------|------|---------|------|
| **Size** | ~15 lines | 16-50 lines | 50+ lines |
| **Says what it is** | 1-2 sentence project description | Description exists but is verbose | No description |
| **Says how to run** | Build and run commands for the specific stack | Commands exist but are generic | No run instructions |
| **No feature catalog** | Does not list entities, endpoints, or pages | Brief feature mentions | Full feature descriptions mirroring SPEC.md |

---

## 6. copilot-instructions.md Quality

| Criterion | Pass | Partial | Fail |
|-----------|------|---------|------|
| **Key files: only existing files** | Lists only files that exist in the repo right now | Lists mostly existing files with a few predicted | Lists 20+ files that don't exist yet |
| **Conventions: coding patterns only** | "Thin controllers", "consistent error envelope", "Fluent API for EF config" | Mix of patterns and architectural decisions | Architectural decisions dominate ("cookie-based auth", "auto-generated API client") |
| **Architecture: brief** | 3-5 sentences about how layers communicate | 6-10 sentences | Full architecture section repeating SPEC.md |
| **No SPEC.md overlap** | Content is complementary to SPEC.md (how to code vs. what to build) | Minor overlap | Large sections duplicated from SPEC.md |

---

## Scoring a Planning Run

For each of the 6 sections above, tally Pass / Partial / Fail counts across all criteria. A planning run is:

- **Good:** All sections have majority Pass, zero Fail in sections 1-3 (tasks, milestones, roadmap).
- **Acceptable:** All sections have majority Pass or Partial, at most 2 Fail total.
- **Needs work:** Any section has majority Fail, or sections 1-3 have 3+ Fails.

### Quick-check questions

These are fast binary checks to run before detailed scoring:

1. **Can the validator test a real feature after milestone 2?** If the first non-scaffolding milestone is a horizontal layer (e.g. "All entities"), the answer is no → Fail roadmap + milestone quality.
2. **Would you need to read SPEC.md to understand any task?** Pick 5 random tasks. If any requires cross-referencing SPEC.md for field names or endpoint paths → Fail task quality.
3. **Are all milestones the same size?** If every milestone has exactly N tasks → likely Fail milestone quality (planner optimizing for count, not cohesion).
4. **Does SPEC.md have entity field tables?** If yes → Fail SPEC.md quality.
5. **Does copilot-instructions.md list files that don't exist?** Run `ls` on the repo and compare → Fail copilot-instructions quality if >3 predicted files.
6. **Is the story count proportional to the app?** Count features in REQUIREMENTS.md, classify the app tier, and check whether the story count falls in the expected range. A CLI calculator with 20 stories fails; Stretto with 31 stories passes.

---

## Applying This Rubric: Examples

### Old Stretto run (pre-backlog planner, Feb 15 2026)

Baseline — the planner that this rubric was written to improve. 32 milestones all planned upfront, 593-line SPEC.md.

| Quick check | Result |
|------------|--------|
| Can the validator test a real feature after milestone 2? | **No.** Milestones 2-6 are all entities and EF config. First testable API is milestone 18. |
| Would you need SPEC.md to understand a task? | **Yes.** Tasks like "Create Member entity with IsActive and NotificationsEnabled fields" omit most fields. |
| Are all milestones the same size? | **Nearly.** 28 of 32 milestones have exactly 3-5 tasks. |
| Does SPEC.md have entity field tables? | **Yes.** 13 entity tables with every field defined. |
| Is the story count proportional? | N/A — no backlog existed. All milestones planned upfront. |

**Score: Needs work.** This is the baseline.

### New Stretto run (backlog planner, Feb 18 2026)

31 stories in BACKLOG.md, progressive planning (1 milestone at a time).

| Quick check | Result |
|------------|--------|
| Can the validator test a real feature after milestone 2? | **Yes.** Milestone 2 is API client generation, milestone 3+ are vertical feature slices. |
| Would you need SPEC.md to understand a task? | **No.** Tasks include field names, types, enums, endpoint paths inline. |
| Are all milestones the same size? | **TBD** — only 2 milestones exist so far (7 and 5 tasks). |
| Does SPEC.md have entity field tables? | **TBD.** |
| Is the story count proportional? | **Yes.** 31 stories for 16+ features. Ratio ~2.0 (Pass). |

**Score: Good** on available criteria. Significant improvement over baseline.
