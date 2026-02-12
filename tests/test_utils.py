"""Tests for sentinel logic, unchecked item counting, path resolution, and commit filtering."""

from agent.sentinel import check_builder_done_status
from agent.utils import count_unchecked_items, find_project_root
from agent.git_helpers import is_reviewer_only_files
from agent.terminal import build_agent_script
from agent.watcher import find_unreviewed_milestones
from agent.tester import find_untested_milestones


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


# --- agent script generation ---

def test_macos_script_has_cd_and_command():
    script = build_agent_script("/path/to/reviewer", "commitwatch", "macos")
    assert "cd '/path/to/reviewer'" in script
    assert "agentic-dev commitwatch" in script
    assert "exec bash" not in script


def test_linux_script_includes_exec_bash():
    script = build_agent_script("/path/to/tester", "testloop", "linux")
    assert "cd '/path/to/tester'" in script
    assert "agentic-dev testloop" in script
    assert "exec bash" in script


def test_windows_script_still_generates_valid_content():
    script = build_agent_script("C:\\Users\\dev\\reviewer", "commitwatch", "windows")
    assert "agentic-dev commitwatch" in script


# --- milestone filtering ---

def test_find_unreviewed_milestones_excludes_already_reviewed():
    boundaries = [
        {"name": "Scaffolding", "start_sha": "aaa", "end_sha": "bbb"},
        {"name": "API", "start_sha": "bbb", "end_sha": "ccc"},
        {"name": "Auth", "start_sha": "ccc", "end_sha": "ddd"},
    ]
    reviewed = {"Scaffolding", "API"}
    result = find_unreviewed_milestones(boundaries, reviewed)
    assert len(result) == 1
    assert result[0]["name"] == "Auth"


def test_find_untested_milestones_excludes_already_tested():
    boundaries = [
        {"name": "Scaffolding", "start_sha": "aaa", "end_sha": "bbb"},
        {"name": "API", "start_sha": "bbb", "end_sha": "ccc"},
    ]
    tested = {"Scaffolding"}
    result = find_untested_milestones(boundaries, tested)
    assert len(result) == 1
    assert result[0]["name"] == "API"
