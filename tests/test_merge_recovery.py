"""Tests for merge conflict prevention and recovery.

Covers:
- Builder prompt no longer instructs git pull --rebase on feature branches
- Orphaned milestone cleanup after build failure
- Builder continues claim loop after merge failure (not terminating)
"""

import os

import pytest

from agentic_dev.builder import _cleanup_orphaned_milestones
from agentic_dev.prompts import BUILDER_PROMPT


# ============================================
# Builder prompt: no git pull --rebase
# ============================================


def test_builder_prompt_does_not_contain_git_pull_rebase():
    """Regression: git pull --rebase on a feature branch can pull commits from
    main, contaminating the branch and causing merge conflicts."""
    rendered = BUILDER_PROMPT.format(
        milestone_file="milestones/milestone-01.md",
    )
    # The prompt should not instruct the builder to run git pull --rebase.
    # The warning text ("Do NOT run 'git pull'") is allowed — it's a prohibition.
    assert "run git pull --rebase" not in rendered
    assert "run git pull" not in rendered.lower()


def test_builder_prompt_warns_against_git_pull():
    """The prompt should explicitly tell the LLM not to run git pull."""
    rendered = BUILDER_PROMPT.format(
        milestone_file="milestones/milestone-01.md",
    )
    assert "Do NOT run 'git pull'" in rendered


def test_builder_prompt_instructs_git_push_after_commit():
    """After each commit, the builder should push without pulling first."""
    rendered = BUILDER_PROMPT.format(
        milestone_file="milestones/milestone-01.md",
    )
    assert "After each commit, run git push." in rendered


# ============================================
# _cleanup_orphaned_milestones (filesystem)
# ============================================


def test_cleanup_removes_incomplete_milestones(tmp_path, monkeypatch):
    """Orphaned milestones (unchecked tasks) for the story are deleted."""
    ms_dir = tmp_path / "milestones"
    ms_dir.mkdir()

    # Completed milestone part — should NOT be deleted
    complete = ms_dir / "milestone-01a-backend.md"
    complete.write_text("## Milestone: Backend\n- [x] Create models\n- [x] Create API\n")

    # Incomplete milestone part — SHOULD be deleted (orphaned by failed builder)
    incomplete = ms_dir / "milestone-01b-frontend.md"
    incomplete.write_text("## Milestone: Frontend\n- [x] Create shell\n- [ ] Add routing\n")

    # Unrelated milestone — should NOT be deleted
    other = ms_dir / "milestone-02-auth.md"
    other.write_text("## Milestone: Auth\n- [ ] Add auth middleware\n")

    monkeypatch.chdir(tmp_path)

    # Stub out git commands (we only care about filesystem effects)
    import agentic_dev.builder as builder_mod
    monkeypatch.setattr(builder_mod, "run_cmd", lambda *a, **kw: None)
    monkeypatch.setattr(builder_mod, "git_push_with_retry", lambda *a, **kw: True)

    _cleanup_orphaned_milestones(1, "test-builder")

    assert complete.exists(), "Completed milestone should not be deleted"
    assert not incomplete.exists(), "Incomplete orphaned milestone should be deleted"
    assert other.exists(), "Milestones for other stories should not be deleted"


def test_cleanup_does_nothing_when_no_orphans(tmp_path, monkeypatch):
    """When all milestones for the story are complete, nothing is deleted."""
    ms_dir = tmp_path / "milestones"
    ms_dir.mkdir()

    complete = ms_dir / "milestone-03a-api.md"
    complete.write_text("## Milestone: API\n- [x] Create endpoints\n")

    monkeypatch.chdir(tmp_path)

    import agentic_dev.builder as builder_mod
    call_count = {"git": 0}
    original_run_cmd = builder_mod.run_cmd
    def counting_run_cmd(*a, **kw):
        call_count["git"] += 1
    monkeypatch.setattr(builder_mod, "run_cmd", counting_run_cmd)
    monkeypatch.setattr(builder_mod, "git_push_with_retry", lambda *a, **kw: True)

    _cleanup_orphaned_milestones(3, "test-builder")

    assert complete.exists()
    # No git commands should have been called (no orphans to commit)
    assert call_count["git"] == 0


def test_cleanup_handles_missing_milestones_dir(tmp_path, monkeypatch):
    """When milestones/ doesn't exist, cleanup does nothing without crashing."""
    monkeypatch.chdir(tmp_path)

    import agentic_dev.builder as builder_mod
    monkeypatch.setattr(builder_mod, "run_cmd", lambda *a, **kw: None)
    monkeypatch.setattr(builder_mod, "git_push_with_retry", lambda *a, **kw: True)

    # Should not raise
    _cleanup_orphaned_milestones(1, "test-builder")


def test_cleanup_removes_multiple_orphaned_parts(tmp_path, monkeypatch):
    """When a story was split into 3 parts and 2 are incomplete, both are removed."""
    ms_dir = tmp_path / "milestones"
    ms_dir.mkdir()

    part_a = ms_dir / "milestone-05a-models.md"
    part_a.write_text("## Milestone: Models\n- [x] Create entity\n")

    part_b = ms_dir / "milestone-05b-api.md"
    part_b.write_text("## Milestone: API\n- [ ] Create endpoints\n")

    part_c = ms_dir / "milestone-05c-frontend.md"
    part_c.write_text("## Milestone: Frontend\n- [ ] Add pages\n")

    monkeypatch.chdir(tmp_path)

    import agentic_dev.builder as builder_mod
    monkeypatch.setattr(builder_mod, "run_cmd", lambda *a, **kw: None)
    monkeypatch.setattr(builder_mod, "git_push_with_retry", lambda *a, **kw: True)

    _cleanup_orphaned_milestones(5, "test-builder")

    assert part_a.exists(), "Completed part should not be deleted"
    assert not part_b.exists(), "Incomplete part b should be deleted"
    assert not part_c.exists(), "Incomplete part c should be deleted"
