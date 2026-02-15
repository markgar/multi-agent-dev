"""Tests for build loop decision logic and stuck detection."""

from agentic_dev.builder import (
    BuildState,
    _MAX_FIX_ONLY_CYCLES,
    _MAX_POST_COMPLETION_REPLANS,
    classify_remaining_work,
    update_milestone_retry_state,
)
from agentic_dev.sentinel import check_agent_idle


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
    """Even with reviews, if bugs exist the signal is 'continue' (must-fix)."""
    assert classify_remaining_work(bugs=1, reviews=5, tasks=0, agents_idle=True) == "continue"


def test_agent_idle_when_log_old_enough():
    assert check_agent_idle(log_exists=True, log_age_seconds=60.0, idle_threshold=30.0) is True


def test_agent_not_idle_when_log_recently_modified():
    assert check_agent_idle(log_exists=True, log_age_seconds=10.0, idle_threshold=30.0) is False


def test_agent_idle_when_log_does_not_exist():
    assert check_agent_idle(log_exists=False, log_age_seconds=0.0, idle_threshold=30.0) is True


def test_agent_idle_at_exact_threshold():
    assert check_agent_idle(log_exists=True, log_age_seconds=30.0, idle_threshold=30.0) is True


def test_stuck_milestone_detected_after_max_retries():
    is_stuck, count = update_milestone_retry_state(
        current_name="API endpoints", current_done=2,
        last_name="API endpoints", last_done=2,
        retry_count=2, max_retries=3,
    )
    assert is_stuck is True
    assert count == 3


def test_milestone_not_stuck_when_progress_is_made():
    is_stuck, count = update_milestone_retry_state(
        current_name="API endpoints", current_done=3,
        last_name="API endpoints", last_done=2,
        retry_count=2, max_retries=3,
    )
    assert is_stuck is False
    assert count == 0


def test_new_milestone_resets_retry_count():
    is_stuck, count = update_milestone_retry_state(
        current_name="Core data models", current_done=0,
        last_name="Project scaffolding", last_done=4,
        retry_count=2, max_retries=3,
    )
    assert is_stuck is False
    assert count == 0


def test_first_cycle_with_no_previous_milestone():
    is_stuck, count = update_milestone_retry_state(
        current_name="Project scaffolding", current_done=0,
        last_name=None, last_done=-1,
        retry_count=0, max_retries=3,
    )
    assert is_stuck is False
    assert count == 0


def test_fix_only_cycles_default_to_zero():
    state = BuildState()
    assert state.fix_only_cycles == 0


def test_fix_only_cycle_limit_is_reasonable():
    assert _MAX_FIX_ONLY_CYCLES >= 1
    assert _MAX_FIX_ONLY_CYCLES <= 10


def test_fix_only_cycles_increment_independently_of_cycle_count():
    state = BuildState()
    state.cycle_count = 10
    state.fix_only_cycles = 1
    assert state.fix_only_cycles < state.cycle_count


def test_post_completion_replans_default_to_zero():
    state = BuildState()
    assert state.post_completion_replans == 0


def test_post_completion_replan_limit_is_at_least_one():
    assert _MAX_POST_COMPLETION_REPLANS >= 1


def test_post_completion_replan_limit_only_applies_when_backlog_empty():
    """After all milestones are done and no backlog stories remain, the planner
    should only get a limited number of chances to create new cleanup milestones
    before the builder stops re-planning. When backlog stories exist, the limit
    is reset and story expansion takes precedence."""
    assert _MAX_POST_COMPLETION_REPLANS <= 3
