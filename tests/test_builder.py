"""Tests for builder claim loop, text manipulation, and decision logic."""

from agentic_dev.builder import (
    BuildState,
    _MAX_FIX_ONLY_CYCLES,
    _build_partition_filter,
    _format_issue_list,
    classify_remaining_work,
    mark_story_claimed,
    mark_story_completed_text,
    mark_story_unclaimed_text,
    find_milestone_file_for_story,
)
from agentic_dev.sentinel import check_agent_idle


# ============================================
# classify_remaining_work (pure function)
# ============================================


def test_all_work_done_when_agents_idle():
    assert classify_remaining_work(bugs=0, reviews=0, tasks=0, agents_idle=True) == "done"


def test_no_work_but_agents_active_returns_waiting():
    assert classify_remaining_work(bugs=0, reviews=0, tasks=0, agents_idle=False) == "waiting"


def test_bugs_or_tasks_return_continue():
    assert classify_remaining_work(bugs=1, reviews=0, tasks=0, agents_idle=False) == "continue"
    assert classify_remaining_work(bugs=0, reviews=0, tasks=5, agents_idle=False) == "continue"
    assert classify_remaining_work(bugs=2, reviews=1, tasks=3, agents_idle=False) == "continue"


def test_bugs_return_continue_even_when_agents_idle():
    assert classify_remaining_work(bugs=1, reviews=0, tasks=0, agents_idle=True) == "continue"


def test_reviews_only_with_agents_idle_returns_reviews_only():
    assert classify_remaining_work(bugs=0, reviews=3, tasks=0, agents_idle=True) == "reviews-only"


def test_reviews_only_with_agents_active_returns_reviews_only():
    """Reviews should be acted on immediately, not gated by agent idle status."""
    assert classify_remaining_work(bugs=0, reviews=3, tasks=0, agents_idle=False) == "reviews-only"


def test_bugs_take_priority_over_reviews_only():
    """Even with reviews, if bugs exist the signal is continue (must-fix)."""
    assert classify_remaining_work(bugs=1, reviews=5, tasks=0, agents_idle=True) == "continue"


# ============================================
# check_agent_idle (pure function from sentinel)
# ============================================


def test_agent_idle_when_log_old_enough():
    assert check_agent_idle(log_exists=True, log_age_seconds=60.0, idle_threshold=30.0) is True


def test_agent_not_idle_when_log_recently_modified():
    assert check_agent_idle(log_exists=True, log_age_seconds=10.0, idle_threshold=30.0) is False


def test_agent_idle_when_log_does_not_exist():
    assert check_agent_idle(log_exists=False, log_age_seconds=0.0, idle_threshold=30.0) is True


def test_agent_idle_at_exact_threshold():
    assert check_agent_idle(log_exists=True, log_age_seconds=30.0, idle_threshold=30.0) is True


# ============================================
# mark_story_claimed (pure function)
# ============================================

_SAMPLE_BACKLOG = """# Backlog

1. [x] Project scaffolding <!-- depends: -->
2. [ ] Members backend <!-- depends: 1 -->
3. [ ] Members frontend <!-- depends: 2 -->
4. [2] Events backend <!-- depends: 1 -->
5. [ ] Events frontend <!-- depends: 4 -->
"""


def test_mark_story_claimed_marks_correct_story():
    result = mark_story_claimed(_SAMPLE_BACKLOG, 2, builder_id=3)
    assert "2. [3] Members backend" in result
    # Other stories unchanged
    assert "1. [x] Project scaffolding" in result
    assert "3. [ ] Members frontend" in result
    assert "4. [2] Events backend" in result


def test_mark_story_claimed_does_not_modify_already_claimed():
    result = mark_story_claimed(_SAMPLE_BACKLOG, 4, builder_id=3)
    # Story 4 is already [2], should not change
    assert result == _SAMPLE_BACKLOG


def test_mark_story_claimed_does_not_modify_completed():
    result = mark_story_claimed(_SAMPLE_BACKLOG, 1, builder_id=2)
    # Story 1 is already [x], should not change
    assert result == _SAMPLE_BACKLOG


def test_mark_story_claimed_handles_no_match():
    result = mark_story_claimed(_SAMPLE_BACKLOG, 99, builder_id=1)
    assert result == _SAMPLE_BACKLOG


def test_mark_story_claimed_handles_story_with_dependencies():
    content = "1. [ ] Setup\n2. [ ] Feature A <!-- depends: 1 -->\n"
    result = mark_story_claimed(content, 2, builder_id=1)
    assert "2. [1] Feature A <!-- depends: 1 -->" in result
    assert "1. [ ] Setup" in result


def test_mark_story_claimed_handles_story_at_end_without_trailing_newline():
    content = "1. [ ] Setup\n2. [ ] Feature A"
    result = mark_story_claimed(content, 2, builder_id=4)
    assert "2. [4] Feature A" in result


def test_mark_story_claimed_different_builders_produce_different_text():
    content = "1. [ ] Setup\n2. [ ] Feature A\n"
    result_b1 = mark_story_claimed(content, 1, builder_id=1)
    result_b2 = mark_story_claimed(content, 1, builder_id=2)
    assert "1. [1] Setup" in result_b1
    assert "1. [2] Setup" in result_b2
    assert result_b1 != result_b2


# ============================================
# mark_story_completed_text (pure function)
# ============================================


def test_mark_story_completed_changes_claimed_to_x():
    result = mark_story_completed_text(_SAMPLE_BACKLOG, 4)
    assert "4. [x] Events backend" in result
    # Other stories unchanged
    assert "1. [x] Project scaffolding" in result
    assert "2. [ ] Members backend" in result


def test_mark_story_completed_does_not_modify_unclaimed():
    result = mark_story_completed_text(_SAMPLE_BACKLOG, 2)
    # Story 2 is [ ], should not change
    assert result == _SAMPLE_BACKLOG


def test_mark_story_completed_does_not_modify_already_completed():
    result = mark_story_completed_text(_SAMPLE_BACKLOG, 1)
    # Story 1 is already [x], should not change
    assert result == _SAMPLE_BACKLOG


def test_mark_story_completed_handles_no_match():
    result = mark_story_completed_text(_SAMPLE_BACKLOG, 99)
    assert result == _SAMPLE_BACKLOG


def test_mark_story_completed_handles_dependencies():
    content = "1. [3] Setup <!-- depends: -->\n2. [ ] Feature A <!-- depends: 1 -->\n"
    result = mark_story_completed_text(content, 1)
    assert "1. [x] Setup <!-- depends: -->" in result
    assert "2. [ ] Feature A <!-- depends: 1 -->" in result


# ============================================
# mark_story_unclaimed_text (pure function)
# ============================================


def test_unclaim_reverts_claimed_to_unclaimed():
    result = mark_story_unclaimed_text(_SAMPLE_BACKLOG, 4)
    assert "4. [ ] Events backend" in result
    # Other stories unchanged
    assert "1. [x] Project scaffolding" in result
    assert "2. [ ] Members backend" in result


def test_unclaim_handles_different_builder_ids():
    content = "1. [3] Setup\n2. [1] Feature A\n"
    result = mark_story_unclaimed_text(content, 1)
    assert "1. [ ] Setup" in result
    assert "2. [1] Feature A" in result  # story 2 unchanged


def test_unclaim_does_not_modify_unclaimed():
    result = mark_story_unclaimed_text(_SAMPLE_BACKLOG, 2)
    # Story 2 is already [ ], should not change
    assert result == _SAMPLE_BACKLOG


def test_unclaim_does_not_modify_completed():
    result = mark_story_unclaimed_text(_SAMPLE_BACKLOG, 1)
    # Story 1 is [x], should not change
    assert result == _SAMPLE_BACKLOG


def test_unclaim_handles_no_match():
    result = mark_story_unclaimed_text(_SAMPLE_BACKLOG, 99)
    assert result == _SAMPLE_BACKLOG


def test_unclaim_handles_dependencies():
    content = "1. [4] Setup <!-- depends: -->\n2. [ ] Feature A <!-- depends: 1 -->\n"
    result = mark_story_unclaimed_text(content, 1)
    assert "1. [ ] Setup <!-- depends: -->" in result
    assert "2. [ ] Feature A <!-- depends: 1 -->" in result


# ============================================
# BuildState defaults
# ============================================


def test_build_state_defaults():
    state = BuildState()
    assert state.cycle_count == 0
    assert state.fix_only_cycles == 0


def test_fix_only_cycle_limit_is_reasonable():
    assert _MAX_FIX_ONLY_CYCLES >= 1
    assert _MAX_FIX_ONLY_CYCLES <= 10


# ============================================
# find_milestone_file_for_story
# ============================================


def test_find_milestone_file_returns_incomplete(tmp_path):
    ms_dir = tmp_path / "milestones"
    ms_dir.mkdir()

    complete = ms_dir / "milestone-01-setup.md"
    complete.write_text("## Milestone: Setup\n- [x] Init project\n- [x] Add readme\n")

    incomplete = ms_dir / "milestone-02-api.md"
    incomplete.write_text("## Milestone: API\n- [x] Add models\n- [ ] Add endpoints\n")

    result = find_milestone_file_for_story(str(ms_dir))
    assert result == str(incomplete)


def test_find_milestone_file_returns_none_when_all_complete(tmp_path):
    ms_dir = tmp_path / "milestones"
    ms_dir.mkdir()

    complete = ms_dir / "milestone-01-setup.md"
    complete.write_text("## Milestone: Setup\n- [x] Init project\n")

    result = find_milestone_file_for_story(str(ms_dir))
    assert result is None


def test_find_milestone_file_returns_none_when_dir_missing(tmp_path):
    result = find_milestone_file_for_story(str(tmp_path / "nonexistent"))
    assert result is None


# ============================================
# _build_partition_filter (pure function — always returns empty)
# ============================================


def test_partition_filter_single_builder_returns_empty():
    assert _build_partition_filter(1, 1) == ""


def test_partition_filter_multiple_builders_returns_empty():
    """Partitioning is removed — builders race to fix issues."""
    assert _build_partition_filter(1, 2) == ""
    assert _build_partition_filter(2, 2) == ""
    assert _build_partition_filter(1, 3) == ""
    assert _build_partition_filter(2, 3) == ""
    assert _build_partition_filter(3, 3) == ""


# ============================================
# _format_issue_list (pure function)
# ============================================


def test_format_issue_list_renders_number_and_title():
    issues = [
        {"number": 1, "title": "Server crash on empty input"},
        {"number": 5, "title": "Missing validation on email field"},
    ]
    result = _format_issue_list(issues)
    assert "#1: Server crash on empty input" in result
    assert "#5: Missing validation on email field" in result


def test_format_issue_list_empty_input():
    assert _format_issue_list([]) == ""


def test_format_issue_list_handles_missing_fields():
    issues = [{"number": 3}, {"title": "No number"}]
    result = _format_issue_list(issues)
    assert "#3:" in result
    assert "#?:" in result
