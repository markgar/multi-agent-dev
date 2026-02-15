# Planner Quality Rubric

A measuring stick for evaluating planner output. Use this to grade TASKS.md, SPEC.md, and related documents produced by a planning run. Each criterion is scored Pass / Partial / Fail with concrete indicators.

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
| **No cleanup-only tasks** | Cleanup items from REVIEWS.md are folded into the next feature milestone | Minor cleanup milestone with 1-2 items | Standalone "refactor" or "cleanup" milestone with no feature work |

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
| **Vertical slice** | Milestone delivers a testable feature through multiple layers (entity → repo → service → API → frontend) | Milestone covers 2-3 layers of one feature (e.g. backend only, frontend follows) | Milestone covers one layer across many features ("All entities", "All repositories") |
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
| **Reasonable count** | 5-12 stories for a medium project; 3-5 for a small one | 13-15 stories (slightly over-split) or 2 stories (under-split) | 20+ stories or a single monolithic story |
| **Stable across re-plans** | Completed stories stay struck through; unstarted stories can be reordered but aren't duplicated or dropped | Minor rewording of unstarted stories | Completed stories get lost or unchecked; stories appear and disappear between re-plans |
| **Only 2 unstarted milestones detailed** | Exactly 2 unstarted `## Milestone:` headings exist below the roadmap | 3 unstarted milestones detailed | All stories are expanded into milestones upfront (defeats progressive planning) |

### Anti-patterns to flag

- **All-upfront expansion:** Every roadmap story has corresponding milestones already detailed. This is the old behavior — no progressive benefit.
- **Fine-grained stories:** 15+ stories where each is a single CRUD feature. Stories should group related capabilities (e.g. "Events and attendance" not "Events" + "Attendance" as separate stories).
- **Missing stories:** Features in REQUIREMENTS.md that have no corresponding story in the roadmap.

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

---

## Applying This Rubric: Stretto Example

Quick-check against the Stretto run (32 milestones, 593-line SPEC.md):

| Quick check | Result |
|------------|--------|
| Can the validator test a real feature after milestone 2? | **No.** Milestones 2-6 are all entities and EF config. First testable API is milestone 18. |
| Would you need SPEC.md to understand a task? | **Yes.** Tasks like "Create Member entity with IsActive and NotificationsEnabled fields" omit most fields — you need SPEC.md section 4 for the rest. |
| Are all milestones the same size? | **Nearly.** 28 of 32 milestones have exactly 3-5 tasks. The planner packed tasks to hit 5. |
| Does SPEC.md have entity field tables? | **Yes.** 13 entity tables with every field defined. |
| Does copilot-instructions.md list files that don't exist? | **Yes.** 35 predicted files at generation time, 0 of which existed. |

**Score: Needs work** across all 6 sections. This is the baseline the refactored planner must beat.
