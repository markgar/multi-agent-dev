"""Tests for sentinel logic, unchecked item counting, path resolution, and commit filtering."""

import pytest

from agentic_dev.sentinel import check_builder_done_status
from agentic_dev.utils import count_unchecked_items, find_project_root, validate_model, ALLOWED_MODELS
from agentic_dev.git_helpers import is_reviewer_only_files, is_coordination_only_files
from agentic_dev.terminal import build_agent_script
from agentic_dev.watcher import find_unreviewed_milestones
from agentic_dev.tester import find_untested_milestones


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


# --- coordination-only commit filtering ---

def test_tasks_only_commit_is_skipped():
    assert is_coordination_only_files(["TASKS.md"]) is True


def test_reviews_only_is_coordination_only():
    assert is_coordination_only_files(["REVIEWS.md"]) is True


def test_bugs_only_commit_is_skipped():
    assert is_coordination_only_files(["BUGS.md"]) is True


def test_mixed_coordination_files_are_skipped():
    assert is_coordination_only_files(["TASKS.md", "REVIEWS.md"]) is True


def test_coordination_with_code_is_not_skipped():
    assert is_coordination_only_files(["TASKS.md", "src/app.js"]) is False


def test_empty_list_is_not_coordination_only():
    assert is_coordination_only_files([]) is False


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


# --- model validation ---

def test_validate_model_accepts_codex_friendly_name():
    assert validate_model("GPT-5.3-Codex") == "gpt-5.3-codex"


def test_validate_model_accepts_codex_cli_name():
    assert validate_model("gpt-5.3-codex") == "gpt-5.3-codex"


def test_validate_model_accepts_opus_friendly_name():
    assert validate_model("Claude Opus 4.6") == "claude-opus-4.6"


def test_validate_model_accepts_opus_cli_name():
    assert validate_model("claude-opus-4.6") == "claude-opus-4.6"


def test_validate_model_rejects_unknown_model():
    with pytest.raises(SystemExit) as exc_info:
        validate_model("GPT-4.1")
    assert "Invalid model" in str(exc_info.value)


def test_allowed_models_accepts_both_formats():
    assert "GPT-5.3-Codex" in ALLOWED_MODELS
    assert "gpt-5.3-codex" in ALLOWED_MODELS
    assert "Claude Opus 4.6" in ALLOWED_MODELS
    assert "claude-opus-4.6" in ALLOWED_MODELS
