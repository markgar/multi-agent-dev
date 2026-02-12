"""Tests for build loop decision logic and stuck detection."""

from agent.builder import classify_remaining_work, update_milestone_retry_state


def test_all_work_done_after_three_confirmations():
    assert classify_remaining_work(bugs=0, reviews=0, tasks=0, no_work_count=3) == "done"
    assert classify_remaining_work(bugs=0, reviews=0, tasks=0, no_work_count=5) == "done"


def test_no_work_but_not_yet_confirmed_returns_idle():
    assert classify_remaining_work(bugs=0, reviews=0, tasks=0, no_work_count=1) == "idle"
    assert classify_remaining_work(bugs=0, reviews=0, tasks=0, no_work_count=2) == "idle"


def test_any_remaining_work_returns_continue():
    assert classify_remaining_work(bugs=1, reviews=0, tasks=0, no_work_count=0) == "continue"
    assert classify_remaining_work(bugs=0, reviews=3, tasks=0, no_work_count=0) == "continue"
    assert classify_remaining_work(bugs=0, reviews=0, tasks=5, no_work_count=0) == "continue"
    assert classify_remaining_work(bugs=2, reviews=1, tasks=3, no_work_count=0) == "continue"


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
