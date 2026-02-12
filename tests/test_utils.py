"""Tests for sentinel logic, unchecked item counting, path resolution, and commit filtering."""

from agent.sentinel import check_builder_done_status
from agent.utils import count_unchecked_items, find_project_root
from agent.git_helpers import is_reviewer_only_files


# --- sentinel ---

def test_builder_done_when_sentinel_exists():
    assert check_builder_done_status(
        sentinel_exists=True, log_exists=False, log_age_minutes=0, timeout_minutes=10
    ) is True


def test_builder_done_when_log_is_stale():
    assert check_builder_done_status(
        sentinel_exists=False, log_exists=True, log_age_minutes=15, timeout_minutes=10
    ) is True


def test_builder_not_done_when_log_is_fresh():
    assert check_builder_done_status(
        sentinel_exists=False, log_exists=True, log_age_minutes=5, timeout_minutes=10
    ) is False


def test_builder_not_done_when_nothing_exists():
    assert check_builder_done_status(
        sentinel_exists=False, log_exists=False, log_age_minutes=0, timeout_minutes=10
    ) is False


# --- unchecked items ---

def test_counts_unchecked_checkboxes_in_realistic_content():
    content = (
        "# Bugs\n"
        "- [x] Fixed: server crash on empty input\n"
        "- [ ] Open: timeout on large file upload\n"
        "- [ ] Open: missing error message for invalid email\n"
        "- [x] Fixed: broken CSS on mobile\n"
    )
    assert count_unchecked_items(content) == 2


def test_zero_unchecked_when_all_done():
    content = "- [x] Done\n- [x] Also done\n"
    assert count_unchecked_items(content) == 0


def test_zero_unchecked_for_empty_content():
    assert count_unchecked_items("") == 0


# --- project root ---

def test_builder_dir_resolves_to_parent():
    assert find_project_root("/home/user/myproject/builder") == "/home/user/myproject"


def test_reviewer_dir_resolves_to_parent():
    assert find_project_root("/home/user/myproject/reviewer") == "/home/user/myproject"


def test_non_agent_dir_returns_itself():
    assert find_project_root("/home/user/myproject") == "/home/user/myproject"


# --- reviewer commit filtering ---

def test_reviews_only_commit_is_skipped():
    assert is_reviewer_only_files(["REVIEWS.md"]) is True


def test_commit_touching_code_is_not_skipped():
    assert is_reviewer_only_files(["REVIEWS.md", "src/main.py"]) is False


def test_empty_file_list_is_not_skipped():
    assert is_reviewer_only_files([]) is False
