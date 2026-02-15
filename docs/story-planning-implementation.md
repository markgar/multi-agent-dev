# Story-Based Planning — Implementation Guide

Design rationale is in `story-planning-refactor.md`. This document is the build plan.

**Status: IMPLEMENTED.** All phases have been completed and verified.

---

## Design Summary

**Problem:** The planner generates all milestones upfront. The builder completes them all in one Copilot session before the orchestrator records any boundaries. Tester and validator never fire.

**Solution:** BACKLOG.md + single-sprint model. TASKS.md only ever contains one unstarted milestone. The builder physically cannot blow through multiple milestones because they don't exist yet.

### New file: BACKLOG.md

Planner-owned. Ordered story queue with checkboxes and dependency annotations.

```markdown
# Backlog

1. [x] Backend scaffolding — solution structure, health endpoint, EF Core setup
2. [ ] Members — CRUD, roles, search/filter, multi-tenant <!-- depends: 1 -->
3. [ ] Program years — seasons, project assignments, utilization <!-- depends: 1 -->
4. [ ] Events and attendance — scheduling, check-in, status tracking <!-- depends: 2 -->
5. [ ] Notifications — assignment and audition announcements <!-- depends: 2, 3 -->
6. [ ] Final verification — end-to-end acceptance testing <!-- depends: 1-5 -->
```

- `[ ]` = in backlog, `[x]` = planned into a sprint
- `<!-- depends: N -->` = HTML comment, invisible in rendered markdown
- Planner picks next eligible unchecked story top-down (all deps `[x]`)
- Builder never reads or writes BACKLOG.md

### TASKS.md changes

One unstarted milestone at a time. Completed milestones accumulate as a build log. The planner appends a new `## Milestone:` after each sprint completes.

### SPEC.md changes

Technical decisions only (~40-60 lines): stack, architecture, cross-cutting concerns, acceptance criteria. No entity fields, API routes, or page layouts.

### README.md changes

~15 lines: what the project is, how to build/run, how to develop.

---

## Prompt Locations

All prompts and key functions are in `src/agent/`. See the source files directly for current line numbers — they shift as prompts are edited.

| Constant / Function | File |
|----------|------|
| `BOOTSTRAP_PROMPT` | `prompts.py` |
| `LOCAL_BOOTSTRAP_PROMPT` | `prompts.py` |
| `PLANNER_PROMPT` | `prompts.py` |
| `PLANNER_SPLIT_PROMPT` | `prompts.py` |
| `BUILDER_PROMPT` | `prompts.py` |
| `COPILOT_INSTRUCTIONS_PROMPT` | `prompts.py` |
| `TESTER_MILESTONE_PROMPT` | `prompts.py` |
| `VALIDATOR_MILESTONE_PROMPT` | `prompts.py` |
| `_MAX_TASKS_PER_MILESTONE` | `builder.py` |
| `_MAX_POST_COMPLETION_REPLANS` | `builder.py` |
| `_detect_milestone_progress()` | `builder.py` |
| `_check_remaining_work()` | `builder.py` |
| `plan()` | `cli.py` |
| `status()` | `cli.py` |
| `_generate_copilot_instructions()` | `cli.py` |
| `_WORKSPACE_README` | `bootstrap.py` |
| `parse_backlog()` | `milestone.py` |
| `has_pending_backlog_stories()` | `milestone.py` |
| `get_next_eligible_story()` | `milestone.py` |

---

## Implementation Steps

### Phase 4 — Backlog Parsing Helpers (do first, zero risk)

**Files:** `src/agent/milestone.py`, `tests/test_milestone.py`

**4.1** Add to `milestone.py`:

- `parse_backlog(content: str) -> list[dict]` — regex: `r"^(\d+)\.\s+\[([ xX])\]\s+(.+?)(?:\s*<!--\s*depends:\s*([\d,\s]+)\s*-->)?$"`. Returns `[{"number": int, "name": str, "checked": bool, "depends": list[int]}]`.
- `has_pending_backlog_stories(content: str) -> bool` — any unchecked story.
- `get_next_eligible_story(content: str) -> dict | None` — first unchecked story whose deps are all checked. `None` = all done or deadlock.
- `has_pending_backlog_stories_in_file(path)` / `get_next_eligible_story_in_file(path)` — I/O wrappers (return `False`/`None` if file missing).
- `count_unstarted_milestones(content: str) -> int` — milestones where `done == 0`. Uses existing `parse_milestones_from_text()`. + I/O wrapper.

**4.2** Add tests to `test_milestone.py`:

```python
SAMPLE_BACKLOG = """\
# Backlog

1. [x] Project scaffolding and base configuration
2. [x] Books CRUD <!-- depends: 1 -->
3. [ ] Authors CRUD <!-- depends: 1 -->
4. [ ] Search <!-- depends: 2, 3 -->
5. [ ] Reviews <!-- depends: 2 -->
"""
```

Tests:
- `test_parse_backlog_basic` — 5 stories, correct fields and deps
- `test_parse_backlog_empty` — `""` and non-story content → `[]`
- `test_has_pending_backlog_stories_mixed` → `True`
- `test_has_pending_backlog_stories_all_done` → `False`
- `test_has_pending_backlog_stories_empty` → `False`
- `test_get_next_eligible_story_skips_unmet_deps` — picks story 3 (Authors), not story 4 (Search)
- `test_get_next_eligible_story_picks_first_eligible` — story 3 before story 5
- `test_get_next_eligible_story_all_done` → `None`
- `test_get_next_eligible_story_deadlock` — circular deps → `None`, but `has_pending` = `True`
- `test_count_unstarted_milestones_mixed` / `_all_done`

Existing `parse_milestones_from_text` tests must still pass unchanged.

**Verify:** `pytest tests/test_milestone.py`

---

### Phase 1 — Lean Bootstrap Prompts

**Files:** `src/agent/prompts.py` (lines 8–44)

**1.1** Rewrite `BOOTSTRAP_PROMPT`: SPEC.md instruction becomes "technical decisions document (~40-60 lines). Include: (1) high-level summary, (2) tech stack, (3) architecture — layers, dependency rules, project structure, (4) cross-cutting concerns — auth, multi-tenancy, error handling, (5) acceptance criteria at feature level. Do NOT include entity fields, API routes, page layouts, DTO shapes." README.md becomes "~15 lines — what it is, how to build/run, how to develop." Keep placeholders `{description}`, `{gh_user}`, `{name}`.

**1.2** Same changes to `LOCAL_BOOTSTRAP_PROMPT`. Keep placeholders `{description}`, `{remote_path}`.

---

### Phase 2 — Sprint-Based Planner Prompt

**Files:** `prompts.py` (46–164), `builder.py` (line 22), `cli.py` (198–204)

**2.1** Rewrite `PLANNER_PROMPT`. Three cases:

- **Case A (fresh — no TASKS.md, no BACKLOG.md):** Read REQUIREMENTS.md + SPEC.md → create BACKLOG.md (numbered stories, `[ ]`, `<!-- depends: N -->`) → check off first story → write one `## Milestone:` in TASKS.md. First story = scaffolding. Prefer vertical slices.
- **Case B (continuing — milestone complete):** Read codebase for patterns → check off completed story in BACKLOG.md → find next eligible story → check it off → append one `## Milestone:` to TASKS.md. Never touch completed milestones.
- **Case C (evolving — new requirements):** Update SPEC.md if new tech decisions → add new stories to BACKLOG.md → apply Case B logic.

Key phrases to include:
- "You MUST write exactly one new milestone. Do not plan ahead."
- "Put implementation detail in task descriptions — field names, types, enum values, relationships."
- "A well-sized milestone typically has 3-7 tasks." (not a hard cap)
- Include calibration example (Members feature: entity, repo, service, controller, list page, detail page = 6 tasks).
- No new format placeholders.

**2.2** Update `PLANNER_SPLIT_PROMPT`: Add "Do NOT modify any section other than the milestone being split." Change "at most 5 tasks each" → "at most 8 tasks each".

**2.3** Raise `_MAX_TASKS_PER_MILESTONE` from `5` to `10` in `builder.py` line 22.

**2.4** Update `requirements_changed` prefix in `cli.py` (198–204): Compare REQUIREMENTS.md against BACKLOG.md story list + SPEC.md technical decisions.

---

### Phase 3 — Lean Copilot Instructions

**Files:** `prompts.py` (640–666)

**3.1** Rewrite `COPILOT_INSTRUCTIONS_PROMPT`:
- Key files: "Only files that exist right now. Do not predict."
- Conventions: "Coding patterns only. No architectural decisions, no file predictions."
- Architecture: "3-5 sentences about how layers communicate."
- Placeholder `{template}` unchanged. Brace-escaping in `_generate_copilot_instructions()` unchanged.

---

### Phase 5 — Builder Re-Plan Trigger

**Files:** `builder.py` (170–260, ~394), `tests/test_builder.py`, `tests/test_prompts.py`

**5.1** Update `_detect_milestone_progress()`. When `not progress` (all milestones complete):

```
if has_pending_backlog_stories_in_file("BACKLOG.md"):
    next = get_next_eligible_story_in_file("BACKLOG.md")
    if next:
        reset post_completion_replans to 0
        plan()  →  check_milestone_sizes()
        if still no progress → warn and return False
    else:
        warn "dependency deadlock" → return False
else:
    apply existing tail-chasing guard (post_completion_replans limit)
```

After successful re-plan, check `count_unstarted_milestones()` — warn if >1.

**5.2** Update `_check_remaining_work()`: If `has_pending_backlog_stories` but no `[ ]` items in TASKS.md, log "planner may have failed to expand" (don't classify as "done").

**5.3** Rename test `test_post_completion_replan_limit_prevents_unlimited_cleanup_milestones` → `test_post_completion_replan_limit_only_applies_when_backlog_empty`.

**5.4** Verify `PROMPT_FORMAT_CASES` in `test_prompts.py` still passes with rewritten prompts.

**Verify:** `pytest tests/`

**Harness:** Run CLI calculator + bookstore spec. Confirm:
- BACKLOG.md created with stories and deps
- One milestone at a time in TASKS.md
- `milestones.log` records boundaries
- Tester/validator fire between milestones
- Clean shutdown when backlog empty

---

### Phase 6 — Documentation and Downstream Prompts

**Files:** `bootstrap.py`, `prompts.py`, `cli.py`, `AGENTS.md`

**6.1** `_WORKSPACE_README` in `bootstrap.py`: SPEC.md = "technical decisions". Add BACKLOG.md row. Update "How It Works" bullet.

**6.2** `VALIDATOR_MILESTONE_PROMPT`: Add "Read task descriptions from completed milestones in TASKS.md for entity fields, API routes, expected behaviors."

**6.3** `TESTER_MILESTONE_PROMPT`: Add "Read task descriptions in TASKS.md for feature-level detail when evaluating test coverage."

**6.4** `status()` in `cli.py`: Read BACKLOG.md if it exists, print "Backlog: N/M stories complete" + story list, then existing TASKS.md output.

**6.5** `AGENTS.md`: Update Bootstrap, Planner, Copilot Instructions Generator, Builder, and Agent Coordination Rules sections for BACKLOG.md model.

**Verify:** `pytest tests/` + full harness run.

---

## Ship-Together Constraint

Phases 1–5 must deploy together. If lean prompts ship without Phase 5 (builder re-plan from BACKLOG.md), the builder finishes one milestone and shuts down — the rest of the backlog never gets built.

**Order:** Phase 4 → Phases 1-3+5 → Phase 6.

---

## Progress

- [x] Phase 4.1 — Backlog parsing functions in `milestone.py`
- [x] Phase 4.2 — Tests in `test_milestone.py`
- [x] Phase 4 verify — `pytest tests/test_milestone.py`
- [x] Phase 1.1 — Rewrite `BOOTSTRAP_PROMPT`
- [x] Phase 1.2 — Rewrite `LOCAL_BOOTSTRAP_PROMPT`
- [x] Phase 2.1 — Rewrite `PLANNER_PROMPT`
- [x] Phase 2.2 — Update `PLANNER_SPLIT_PROMPT`
- [x] Phase 2.3 — Raise `_MAX_TASKS_PER_MILESTONE` to 10
- [x] Phase 2.4 — Update `requirements_changed` prefix
- [x] Phase 3.1 — Rewrite `COPILOT_INSTRUCTIONS_PROMPT`
- [x] Phase 5.1 — Update `_detect_milestone_progress()`
- [x] Phase 5.2 — Update `_check_remaining_work()`
- [x] Phase 5.3 — Update `test_builder.py`
- [x] Phase 5.4 — Verify `test_prompts.py`
- [x] Phases 1-5 verify — `pytest tests/`
- [x] Phases 1-5 harness — CLI calculator + bookstore
- [x] Phase 6.1 — `_WORKSPACE_README`
- [x] Phase 6.2 — `VALIDATOR_MILESTONE_PROMPT`
- [x] Phase 6.3 — `TESTER_MILESTONE_PROMPT`
- [x] Phase 6.4 — `status()` shows BACKLOG.md
- [x] Phase 6.5 — `AGENTS.md`
- [x] Phase 6 verify — `pytest tests/` + harness
