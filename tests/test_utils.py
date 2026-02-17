"""Tests for sentinel logic, unchecked item counting, path resolution, and commit filtering."""

import pytest

from agentic_dev.sentinel import check_builder_done_status
from agentic_dev.utils import (
    count_unchecked_items,
    find_project_root,
    validate_model,
    ALLOWED_MODELS,
    _AUTH_ERROR_MARKERS,
    _detect_auth_failure,
)
from agentic_dev.git_helpers import is_reviewer_only_files, is_coordination_only_files
from agentic_dev.terminal import build_agent_script
from agentic_dev.utils import count_open_items_in_dir, _extract_item_ids
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
    assert is_reviewer_only_files(["reviews/finding-20260215-120000.md"]) is True


def test_reviews_multiple_files_is_skipped():
    assert is_reviewer_only_files(["reviews/finding-20260215-120000.md", "reviews/resolved-20260215-110000.md"]) is True


def test_commit_touching_code_is_not_skipped():
    assert is_reviewer_only_files(["reviews/finding-20260215-120000.md", "src/main.py"]) is False


def test_empty_file_list_is_not_skipped():
    assert is_reviewer_only_files([]) is False


# --- coordination-only commit filtering ---

def test_tasks_only_commit_is_skipped():
    assert is_coordination_only_files(["TASKS.md"]) is True


def test_reviews_only_is_coordination_only():
    assert is_coordination_only_files(["reviews/finding-20260215-120000.md"]) is True


def test_bugs_only_commit_is_skipped():
    assert is_coordination_only_files(["bugs/bug-20260215-120000.md"]) is True


def test_mixed_coordination_files_are_skipped():
    assert is_coordination_only_files(["TASKS.md", "reviews/finding-20260215-120000.md"]) is True


def test_bugs_and_reviews_coordination_only():
    assert is_coordination_only_files(["bugs/fixed-20260215-120000.md", "reviews/resolved-20260215-110000.md"]) is True


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


def test_agent_script_propagates_copilot_model(monkeypatch):
    monkeypatch.setenv("COPILOT_MODEL", "gpt-5.3-codex")
    script = build_agent_script("/path/to/reviewer", "commitwatch", "macos")
    assert "export COPILOT_MODEL='gpt-5.3-codex'" in script


def test_agent_script_omits_model_when_unset(monkeypatch):
    monkeypatch.delenv("COPILOT_MODEL", raising=False)
    script = build_agent_script("/path/to/reviewer", "commitwatch", "macos")
    assert "COPILOT_MODEL" not in script


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


# --- auth failure detection ---

def test_detect_auth_failure_recognizes_expired_token(tmp_path):
    log_file = tmp_path / "builder.log"
    log_file.write_text(
        "========== [2026-02-16 17:10:06] builder ==========\n"
        "Model: gpt-5.3-codex\n"
        "Prompt: Before starting...\n"
        "--- output ---\n"
        "Error: No authentication information found.\n"
        "\n"
        "Copilot can be authenticated with GitHub using an OAuth Token "
        "or a Fine-Grained Personal Access Token.\n"
        "\n"
        "To authenticate, you can use any of the following methods:\n"
        "  • Start 'copilot' and run the '/login' command\n"
        "  • Set the COPILOT_GITHUB_TOKEN, GH_TOKEN, or GITHUB_TOKEN "
        "environment variable\n"
        "  • Run 'gh auth login' to authenticate with the GitHub CLI\n"
        "--- end (exit: 1) ---\n"
    )
    assert _detect_auth_failure(str(log_file)) is True


def test_detect_auth_failure_ignores_normal_errors(tmp_path):
    log_file = tmp_path / "builder.log"
    log_file.write_text(
        "--- output ---\n"
        "Error: something went wrong with the build\n"
        "--- end (exit: 1) ---\n"
    )
    assert _detect_auth_failure(str(log_file)) is False


def test_detect_auth_failure_handles_missing_file():
    assert _detect_auth_failure("/nonexistent/path/builder.log") is False


def test_detect_auth_failure_handles_empty_file(tmp_path):
    log_file = tmp_path / "builder.log"
    log_file.write_text("")
    assert _detect_auth_failure(str(log_file)) is False


# --- _extract_item_ids ---

def test_extract_item_ids_strips_prefix_and_suffix():
    filenames = ["finding-20260215-120000.md", "finding-20260215-130000.md"]
    assert _extract_item_ids(filenames, "finding-") == {"20260215-120000", "20260215-130000"}


def test_extract_item_ids_ignores_non_matching_files():
    filenames = ["finding-20260215-120000.md", "resolved-20260215-110000.md", "README.md"]
    assert _extract_item_ids(filenames, "finding-") == {"20260215-120000"}


def test_extract_item_ids_empty_list():
    assert _extract_item_ids([], "bug-") == set()


# --- count_open_items_in_dir ---

def test_count_open_items_no_closed(tmp_path):
    d = tmp_path / "reviews"
    d.mkdir()
    (d / "finding-20260215-120000.md").write_text("issue 1")
    (d / "finding-20260215-130000.md").write_text("issue 2")
    assert count_open_items_in_dir(str(d), "finding-", "resolved-") == 2


def test_count_open_items_some_resolved(tmp_path):
    d = tmp_path / "reviews"
    d.mkdir()
    (d / "finding-20260215-120000.md").write_text("issue 1")
    (d / "finding-20260215-130000.md").write_text("issue 2")
    (d / "resolved-20260215-120000.md").write_text("fixed")
    assert count_open_items_in_dir(str(d), "finding-", "resolved-") == 1


def test_count_open_items_all_resolved(tmp_path):
    d = tmp_path / "reviews"
    d.mkdir()
    (d / "finding-20260215-120000.md").write_text("issue 1")
    (d / "resolved-20260215-120000.md").write_text("fixed")
    assert count_open_items_in_dir(str(d), "finding-", "resolved-") == 0


def test_count_open_items_empty_directory(tmp_path):
    d = tmp_path / "bugs"
    d.mkdir()
    assert count_open_items_in_dir(str(d), "bug-", "fixed-") == 0


def test_count_open_items_missing_directory(tmp_path):
    assert count_open_items_in_dir(str(tmp_path / "nonexistent"), "bug-", "fixed-") == 0


def test_count_open_bugs(tmp_path):
    d = tmp_path / "bugs"
    d.mkdir()
    (d / "bug-20260215-120000.md").write_text("crash")
    (d / "bug-20260215-130000.md").write_text("error")
    (d / "fixed-20260215-120000.md").write_text("patched")
    (d / ".gitkeep").write_text("")
    assert count_open_items_in_dir(str(d), "bug-", "fixed-") == 1
