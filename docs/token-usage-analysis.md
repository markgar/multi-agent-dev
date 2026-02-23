# Token Usage Analysis

## Purpose

Each builder milestone runs as a single Copilot CLI session (`copilot --allow-all-tools -p <prompt>`). This analysis measures how input token consumption scales across milestones as the target codebase grows, identifies what drives the growth, and documents the fixes applied to control it.

## Baseline Run

**Run:** `tests/harness/runs/20260219-092624/stretto-claude-2`
- **Model:** claude-opus-4.6
- **Project:** Stretto (music organization management — .NET API + React frontend)
- **Stories completed:** 29 (single builder)
- **Final codebase:** 226 hand-written source files, ~15,000 lines (excluding node_modules, obj/, generated/)

## Token Usage Per Milestone Session

Copilot CLI prints token stats at the end of each session. These are cumulative for the session (all turns combined):

| Story | Feature | Type | Input | Output | Cached | Session Time |
|-------|---------|------|-------|--------|--------|-------------|
| 3 | OpenAPI & TS client | Infrastructure | 5.2M | 21.8k | 5.1M (98%) | 8m 52s |
| 5 | Error handling | Infrastructure | 2.2M | 12.7k | 2.1M (95%) | 5m 44s |
| 7 | Program Years FE | Vertical slice | 7.1M | 33.2k | 6.9M (97%) | 11m 43s |
| 9 | Members FE | Vertical slice | 6.8M | 29.7k | 6.6M (97%) | 9m 46s |
| 11 | Venues FE | Vertical slice | 3.2M | 21.5k | 3.1M (97%) | 6m 20s |
| 15 | Auditions BE | Vertical slice | 9.4M | 30.5k | 9.3M (99%) | 13m 10s |
| 17 | Notifications | Vertical slice | 14.9M | 59.8k | 14.7M (99%) | 17m 35s |
| 20 | Events FE | Vertical slice | 12.7M | 41.3k | 12.5M (98%) | 15m 2s |
| 28 | Dashboard | Aggregation | 21.1M | 85.2k | 20.6M (98%) | 25m 22s |

## Key Findings

### 1. Input tokens grow ~4x over the project lifecycle

Early milestones use 2-5M input tokens. Late milestones use 12-21M. This is a linear growth trend driven by the builder reading progressively more files as the codebase grows.

### 2. The growth is driven by file reads, not conversation length

Explicit file read operations per session:
- Story 3 (5.2M, early): **19 file reads**
- Story 17 (14.9M, mid-late): **54 file reads**
- Story 28 (21.1M, final): **~50 file reads**

The builder reads more files in later sessions because there are more files to explore. The conversation itself (output tokens) stays relatively modest — 20-85k across all sessions.

### 3. Vertical slices read unrelated features

The critical inefficiency: for story 17 (Notifications), the builder read ProgramYears pages, Members pages, Venues pages, and Auditions pages — all irrelevant to Notifications. A NotificationService follows the same structure as MemberService — reading 5 other services teaches nothing new.

Sample reads from story 17 (Notifications backend):
```
● Read src/Stretto.Web/src/pages/ProgramYearsPage.tsx
● Read src/Stretto.Web/src/pages/ProgramYearDetailPage.tsx
● Read src/Stretto.Web/src/pages/ProgramYearEditPage.tsx
● Read src/Stretto.Web/src/pages/ProgramYearCreatePage.tsx
● Read src/Stretto.Web/src/pages/MembersPage.tsx
● Read src/Stretto.Web/src/pages/VenuesPage.tsx
● Read src/Stretto.Web/src/pages/AuditionsPage.tsx
● Read src/Stretto.Web/src/pages/VenueCreatePage.tsx
● Read src/Stretto.Web/src/components/VenueForm.tsx
● Read src/Stretto.Web/src/pages/VenueEditPage.tsx
```

None of these are relevant to building a notification service.

### 4. Prompt caching is nearly 100%

Cached tokens consistently represent 95-99% of input tokens. The Copilot CLI heavily leverages prompt caching, so the marginal cost of repeated context is low in dollar terms — but it still consumes context window capacity and session time.

### 5. No mid-session summarization occurs

Zero evidence of context truncation, compression, or mid-session summarization across all 29 milestone sessions. Each session runs to natural completion. With 4-7 tasks per milestone, sessions stay well within the context window (sessions complete in 6-25 minutes).

### 6. Copilot CLI creates internal plans

Some sessions show `Create ~/.copilot/session-state/<uuid>/plan.md` — the Copilot CLI's own internal planning, not summarization. This is normal behavior.

## Theoretical Optimal Token Usage

A well-scoped vertical slice should need roughly the same input tokens regardless of when it's built:

| What the builder needs | Token cost | Growth? |
|----------------------|------------|---------|
| Prompt + instructions | ~50k | Fixed |
| SPEC.md, README.md, copilot-instructions.md | ~20k | Fixed |
| DEPLOY.md, REVIEW-THEMES.md | ~10k | Slow growth |
| Milestone file | ~5k | Fixed |
| ONE example per layer (controller, service, repo, entity, page) | ~15k | Fixed |
| Shared infrastructure (DI, DbContext, routing) | ~10k | Slow growth |
| Bugs + review findings | ~5-20k | Variable |
| Files being edited/created | ~10-30k | Fixed per feature |

**Theoretical steady-state:** ~150-200k per session, regardless of codebase size.

Compare to observed: 5M-21M — roughly **30-100x** higher than necessary.

The gap is mostly the Copilot CLI's workspace indexing (which we don't control) plus the builder's tendency to read files beyond what it needs.

## Fixes Applied

### Fix 1: Reference files in milestone files (planner-side)

**Commit:** `d4250d9`

The planner now adds a `> **Reference files:**` blockquote to each milestone file, listing ONE exemplar file per architectural layer plus shared infrastructure files:

```markdown
## Milestone: Notifications backend
> **Validates:** POST /api/notifications/assignments returns 200...
> **Reference files:** Follow the patterns in MemberController.cs (controller
> conventions, routing, Result mapping), MemberService.cs (service layer,
> validation, repository usage), MemberRepository.cs (EF Core data access).
> Also read Program.cs for DI registration pattern.
```

Rules for the planner:
- ONE file per layer (entity, repo, service, controller, page) — not all files of that type
- Pick files from the MOST SIMILAR completed feature
- Include shared infrastructure files the builder must modify (Program.cs, AppDbContext.cs, App.tsx)
- For first feature milestone, list only infrastructure files
- For frontend milestones, list ONE page component and ONE form component as exemplars

### Fix 2: Context scoping in builder prompt (builder-side)

**Commit:** `d4250d9`

The builder prompt now includes a CONTEXT SCOPING section:

> Your milestone file contains a `> **Reference files:**` section listing the specific files you should read to understand the project's patterns. Read THOSE files — they are exemplars chosen by the planner to show you the conventions for each architectural layer. After reading the reference files, you know the patterns. Apply them to the new code you write. Do NOT read every file in the project — reading one example controller teaches you the same conventions as reading ten.

The builder is told to only read beyond reference files for:
1. Shared infrastructure it needs to modify (DI, DbContext, routing)
2. Files mentioned in open bugs or review findings
3. Files it is directly editing or extending

## How to Run This Analysis

Extract token stats from a builder log:

```bash
RUN=tests/harness/runs/<timestamp>/<project>

# Token usage per session
awk '/Claimed story/{name=$0} /claude.*in,/{print name; print $0; print "---"}' \
  "$RUN/logs/builder-1.log"

# File read counts per session range (adjust line numbers)
sed -n '35,625p' "$RUN/logs/builder-1.log" | grep -c "● Read"

# What files each session reads
sed -n '35,625p' "$RUN/logs/builder-1.log" | grep "● Read"

# Session times
grep "Total session time" "$RUN/logs/builder-1.log"

# All token stats
grep "in,.*out,.*cached" "$RUN/logs/builder-1.log"
```

To find session boundaries (line ranges for each story), search for:
```bash
grep -n "Claimed story\|Total session time\|in,.*out,.*cached" "$RUN/logs/builder-1.log"
```

## Expected Impact

With reference files and context scoping, later milestones should show:
- **Flat or near-flat input token usage** across milestone sessions (not 4x growth)
- **Fewer file read operations** — target ~15-25 reads per session regardless of codebase size
- **Consistent session times** — 5-15 minutes rather than scaling to 25+ minutes

The Copilot CLI's own workspace indexing will still contribute some baseline token cost that grows with codebase size — this is outside our control. But the explicit file reads (which doubled the token count in later sessions) should be constrained by the reference file pattern.
