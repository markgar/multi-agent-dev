"""Tests for merge conflict prevention and recovery.

Covers:
- Builder prompt no longer instructs git pull --rebase on feature branches
- Orphaned milestone cleanup after build failure
- Builder continues claim loop after merge failure (not terminating)
- Copilot-assisted merge conflict resolution
"""

import os
import types

import pytest

from agentic_dev.builder import _cleanup_orphaned_milestones
from agentic_dev.git_helpers import (
    MERGE_CONFLICT_RESOLUTION_PROMPT,
    _resolve_merge_conflicts_with_copilot,
)
from agentic_dev.prompts import BUILDER_PROMPT, BUILDER_ISSUE_FIXING_SECTION


# ============================================
# Builder prompt: no git pull --rebase
# ============================================


def test_builder_prompt_does_not_contain_git_pull_rebase():
    """Regression: git pull --rebase on a feature branch can pull commits from
    main, contaminating the branch and causing merge conflicts."""
    rendered = BUILDER_PROMPT.format(
        milestone_file="milestones/milestone-01.md",
        issue_fixing_section=BUILDER_ISSUE_FIXING_SECTION,
    )
    # The prompt should not instruct the builder to run git pull --rebase.
    # The warning text ("Do NOT run 'git pull'") is allowed — it's a prohibition.
    assert "run git pull --rebase" not in rendered
    assert "run git pull" not in rendered.lower()


def test_builder_prompt_warns_against_git_pull():
    """The prompt should explicitly tell the LLM not to run git pull."""
    rendered = BUILDER_PROMPT.format(
        milestone_file="milestones/milestone-01.md",
        issue_fixing_section=BUILDER_ISSUE_FIXING_SECTION,
    )
    assert "Do NOT run 'git pull'" in rendered


def test_builder_prompt_instructs_git_push_after_commit():
    """After each commit, the builder should push without pulling first."""
    rendered = BUILDER_PROMPT.format(
        milestone_file="milestones/milestone-01.md",
        issue_fixing_section=BUILDER_ISSUE_FIXING_SECTION,
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


# ============================================
# Copilot-assisted merge conflict resolution
# ============================================


def test_conflict_resolution_prompt_has_placeholder():
    """The prompt template must contain the {conflicted_files} placeholder."""
    assert "{conflicted_files}" in MERGE_CONFLICT_RESOLUTION_PROMPT


def test_conflict_resolution_prompt_instructs_git_add():
    """The prompt must tell Copilot to git add resolved files."""
    assert "git add" in MERGE_CONFLICT_RESOLUTION_PROMPT


def test_conflict_resolution_prompt_checks_for_remaining_markers():
    """The prompt must instruct verification that no markers remain."""
    assert "<<<<<<< " in MERGE_CONFLICT_RESOLUTION_PROMPT


def test_conflict_resolution_prompt_does_not_commit():
    """The prompt must tell Copilot NOT to run git commit."""
    assert "Do NOT run git commit" in MERGE_CONFLICT_RESOLUTION_PROMPT


def test_resolve_returns_false_when_no_conflicted_files(monkeypatch):
    """When git reports no unmerged files, resolution should return False."""
    import agentic_dev.git_helpers as gh

    def fake_run_cmd(cmd, capture=False, quiet=False, cwd=None):
        result = types.SimpleNamespace()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr(gh, "run_cmd", fake_run_cmd)

    assert _resolve_merge_conflicts_with_copilot("test") is False


def test_resolve_returns_false_when_copilot_fails(monkeypatch):
    """When Copilot exits non-zero, resolution should return False."""
    import agentic_dev.git_helpers as gh

    call_log = []

    def fake_run_cmd(cmd, capture=False, quiet=False, cwd=None):
        call_log.append(cmd)
        result = types.SimpleNamespace()
        if cmd[:3] == ["git", "diff", "--name-only"]:
            result.returncode = 0
            result.stdout = "src/Program.cs\nsrc/Startup.cs"
        else:
            result.returncode = 0
            result.stdout = ""
        result.stderr = ""
        return result

    def fake_run_copilot(agent_name, prompt):
        return 1  # non-zero = failure

    monkeypatch.setattr(gh, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(gh, "run_copilot", fake_run_copilot)

    assert _resolve_merge_conflicts_with_copilot("test") is False


def test_resolve_returns_false_when_markers_remain(monkeypatch):
    """When conflict markers remain after Copilot runs, returns False."""
    import agentic_dev.git_helpers as gh

    def fake_run_cmd(cmd, capture=False, quiet=False, cwd=None):
        result = types.SimpleNamespace()
        result.stderr = ""
        if cmd[:3] == ["git", "diff", "--name-only"]:
            if "--diff-filter=U" in cmd:
                # First call: report conflicts; second call: report resolved
                result.returncode = 0
                result.stdout = "src/Program.cs"
            else:
                result.returncode = 0
                result.stdout = ""
        elif cmd[0] == "grep":
            # Conflict markers still found
            result.returncode = 0
            result.stdout = "src/Program.cs:<<<<<<< HEAD"
        else:
            result.returncode = 0
            result.stdout = ""
        return result

    def fake_run_copilot(agent_name, prompt):
        return 0  # Copilot "succeeded" but didn't actually resolve

    monkeypatch.setattr(gh, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(gh, "run_copilot", fake_run_copilot)

    assert _resolve_merge_conflicts_with_copilot("test") is False


def test_resolve_returns_true_when_all_conflicts_resolved(monkeypatch):
    """When Copilot resolves all conflicts and no markers remain, returns True."""
    import agentic_dev.git_helpers as gh

    diff_call_count = {"n": 0}

    def fake_run_cmd(cmd, capture=False, quiet=False, cwd=None):
        result = types.SimpleNamespace()
        result.stderr = ""
        if cmd[:3] == ["git", "diff", "--name-only"]:
            diff_call_count["n"] += 1
            if diff_call_count["n"] == 1:
                # First call: report conflicts
                result.returncode = 0
                result.stdout = "src/Program.cs"
            else:
                # Second call: no more unmerged files
                result.returncode = 0
                result.stdout = ""
        elif cmd[0] == "grep":
            # No conflict markers found (grep returns 1 = no match)
            result.returncode = 1
            result.stdout = ""
        else:
            result.returncode = 0
            result.stdout = ""
        return result

    def fake_run_copilot(agent_name, prompt):
        return 0

    monkeypatch.setattr(gh, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(gh, "run_copilot", fake_run_copilot)

    assert _resolve_merge_conflicts_with_copilot("test") is True
