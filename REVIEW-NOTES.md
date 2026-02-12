# System Strategy Review

## What works well

The **lifecycle flow** is sound: planner sizes work → builder executes one milestone → planner re-evaluates → repeat. The **reviewer** has clean per-commit scope with persistent checkpoint, and the **tester** provides independent validation on a timer. Separation of concerns is right.

## Work streams

### A. Milestone SHA infrastructure

*Consolidates original issues #1 (broken SHA range) and #7 (shared source of truth).*

**Problem:** The milestone review SHA range is broken — by the time a milestone is detected as complete, the reviewer checkpoint has already advanced past the milestone's commits, producing a tiny or empty diff. Additionally, multiple agents (reviewer, tester) need milestone SHA ranges but there's no shared source. The reviewer computes SHAs from its own checkpoint (broken), and the tester can't access them at all.

**Root cause:** There is no authoritative record of which commits belong to which milestone. Each agent tries to derive this independently.

**Solution:** The build loop (Python code, not prompts) records SHA boundaries to an append-only `logs/milestones.log` file. This is deterministic — can't be forgotten or malformatted by an LLM.

```
Project scaffolding|abc1234|def5678
API endpoints|def5678|789abcd
```

Each consuming agent independently tracks which milestones it has already processed:

- `logs/milestones.log` — append-only, one line per completed milestone. Permanent record. If the builder completes 3 milestones before the reviewer runs, all 3 entries are waiting.
- `logs/reviewer.milestone` — set of milestone names the reviewer has already reviewed.
- `logs/tester.milestone` — set of milestone names the tester has already tested.

Each agent reads `milestones.log`, subtracts its own checkpoint file, and processes any unseen milestones.

#### Proposed work

- Add `record_milestone_boundary(name, start_sha, end_sha)` and `load_milestone_boundaries()` helpers in `utils.py`.
- Add `get_last_milestone_end_sha()` helper — returns the most recently completed milestone's end SHA, falling back to the initial bootstrap commit (`git rev-list --max-parents=0 HEAD`).
- Update the build loop: capture HEAD before and after each builder session. After each session, compare completed milestones before vs. after. For any newly completed milestone, compute `start_sha = get_last_milestone_end_sha()` and `end_sha = current HEAD`, then call `record_milestone_boundary()`.
- Update `commitwatch` to read milestone boundaries from `logs/milestones.log` instead of computing them from the reviewer checkpoint.
- Remove the broken SHA computation from the current milestone review trigger.

**Files touched:** `utils.py`, `cli.py` (build loop, commitwatch).

**Priority:** 1 — This is the foundation. Work streams B and C depend on it.

---

### B. Milestone-scoped agents

*Consolidates original issues #3 (reviewer falls behind) and #6 (tester is blind to milestones). Depends on work stream A.*

**Problem:** The tester runs on a blind 5-minute timer and can test mid-milestone, finding "bugs" that are just incomplete work. The reviewer queues up sequential reviews and can fall arbitrarily far behind the builder, making its feedback a post-hoc audit rather than a real-time loop.

**Solution:** Both the tester and reviewer become milestone-aware using the infrastructure from work stream A. The tester switches from timer-based to milestone-triggered. The build loop adds a drain window so review findings land before the next milestone starts.

#### Proposed work

**Milestone-triggered tester:**
- Rewrite `testloop` to watch `logs/milestones.log` for newly completed milestones instead of running on a 5-minute timer.
- When a milestone completes, run `git diff {start_sha}..{end_sha} --name-only` to get changed files. Focus testing on those files and their related functionality.
- The tester also runs one final pass when `builder.done` appears, as it does today.
- The tester tracks processed milestones in `logs/tester.milestone`.
- Update the tester prompt to include: `"Run git diff {start_sha} {end_sha} --name-only to see which files changed in this milestone. Focus your testing on those files and the features they implement."`

**Reviewer drain window:**
- After the builder finishes a milestone, the build loop waits up to 2 minutes for the reviewer to catch up (polls `logs/reviewer.checkpoint` to see if it's reached the builder's last commit).
- If the reviewer still hasn't caught up after the drain window, proceed anyway — don't block indefinitely.
- Add a commit-count log metric: after each poll cycle, log `"Reviewed X / Y commits"` so the operator can see if the reviewer is keeping pace.

**Post-milestone sequencing:**
1. Builder finishes milestone → records boundary to `milestones.log`
2. Reviewer drain window + tester runs (can be parallel — they look at different things)
3. Planner re-evaluates
4. Builder starts next milestone

Steps 2-3 run in parallel. The builder waits for both before starting the next milestone, so new REVIEWS.md and BUGS.md items get addressed immediately.

**Files touched:** `cli.py` (build loop, testloop rewrite), `prompts.py` (tester prompt), `utils.py` (milestone log readers, reviewer checkpoint comparison helper).

**Priority:** 2 — Requires work stream A infrastructure.

---

### C. Build loop resilience

*Consolidates original issues #4 (large milestones) and #5 (partial milestone validation). These are complementary: #4 reduces the likelihood of the problem #5 handles.*

**Problem:** Large milestones can overwhelm a single LLM session (context window, token limits, quality degradation on later tasks). When the builder crashes or stops mid-milestone, the build loop re-invokes the planner unnecessarily, which might reorganize half-done work.

**Solution:** Enforce small milestones structurally (prevent the problem) and add partial-milestone retry logic (handle it gracefully when it happens anyway).

#### Proposed work

**Planner sizing rules:**
- Update the planner prompt with concrete structural rules:
  - Each task describes one logical change. If a task has "and" connecting two distinct pieces of work, split it.
  - If a task requires creating something new and integrating it elsewhere, make those separate tasks.
  - Keep milestones to at most 5 tasks.
  - If a feature area needs more, split into sequential milestones (e.g., 'User API: models and routes' then 'User API: validation and error handling').
- Add a post-plan size check in the build loop: after `plan()` runs, parse TASKS.md and count tasks per uncompleted milestone. If any milestone exceeds 5 tasks, re-invoke the planner with: `"Milestone '{name}' has {n} tasks. Split it into smaller milestones of at most 5 tasks each."` Retry once — if still oversized, log a warning and proceed.

**Partial milestone retry:**
- After the builder returns, check whether the *current* milestone is fully complete (all checkboxes checked) vs. partially complete.
- If partially complete: **do not re-plan**. Re-invoke the builder immediately with the same milestone. The builder prompt already says "find the first milestone with unchecked tasks" so it will resume where it left off. Only re-plan at actual milestone boundaries.
- Track a retry count per milestone. If the builder fails 3 times on the same milestone without making progress (no new checkboxes checked between attempts), log an error and write `builder.done` — something is fundamentally stuck.
- Add a `get_current_milestone_progress()` helper that returns the milestone name and task completion count (done vs. total).

**Files touched:** `prompts.py` (planner prompt), `cli.py` (build loop: post-plan check, partial milestone detection, retry logic), `utils.py` (task-count-per-milestone helper, milestone progress helper).

**Priority:** 3 — Independent of A and B. Improves reliability regardless.

---

### D. Merge conflict resilience

*Original issue #2. Standalone — no dependencies on other work streams.*

**Problem:** Three agents push to the same remote. Builder edits source code + TASKS.md + BUGS.md + REVIEWS.md. Reviewer edits REVIEWS.md. Tester edits BUGS.md + test files. Concurrent edits to the same files (especially REVIEWS.md and BUGS.md) cause rebase conflicts.

**Solution:** Retry-with-backoff on push failures + append-only discipline for non-builder agents.

#### Proposed work

- Add a `git_push_with_retry()` helper in `utils.py` that wraps `git pull --rebase && git push` in a retry loop (3 attempts, 5-second backoff). On rebase conflict, run `git rebase --abort`, `git pull --rebase`, and retry.
- Update `run_copilot` callers in `commitwatch` and `testloop` to call `git_push_with_retry()` after the agent finishes, as a safety net if the agent's own push failed.
- In the reviewer and tester prompts, explicitly instruct: "Only append new lines to REVIEWS.md / BUGS.md. Never edit or reorder existing lines." The builder is the only agent that modifies existing lines (checking boxes).

**Files touched:** `utils.py` (new helper), `prompts.py` (reviewer/tester prompts), `cli.py` (commitwatch/testloop).

**Priority:** 4 — Independent. Can be implemented at any time.

---

## Open considerations

### Builder prompt and git

The builder prompt tells the agent to commit and push but never mentions SHAs. That's correct — the builder shouldn't think about SHAs. The build loop (Python code) handles boundary tracking externally. No change needed.

### Post-milestone orchestration

With drain window (B) and milestone-triggered testing (B), the build loop needs to orchestrate the sequence explicitly. The reviewer and tester can run in parallel after a milestone completes, but the builder should wait for both before starting the next milestone so that new REVIEWS.md and BUGS.md items get addressed immediately. This is designed into work stream B above.

## Implementation order

| Order | Work stream | What it delivers |
|-------|------------|-----------------|
| 1 | **A: Milestone SHA infrastructure** | Fixes broken milestone reviews. Foundation for B. |
| 2 | **D: Merge conflict resilience** | Independent, low-risk, immediate value. |
| 3 | **B: Milestone-scoped agents** | Tester stops finding false bugs. Reviewer feedback lands before next milestone. |
| 4 | **C: Build loop resilience** | Smaller milestones + graceful crash recovery. |
