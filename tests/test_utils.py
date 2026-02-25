"""Tests for sentinel logic, unchecked item counting, path resolution, and commit filtering."""

import pytest

from agentic_dev.sentinel import check_all_builders_done_status
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
from agentic_dev.utils import count_open_items_in_dir, count_partitioned_open_items, _extract_item_ids
from agentic_dev.utils import _parse_gh_issue_numbers
from agentic_dev.milestone_reviewer import find_unreviewed_milestones
from agentic_dev.tester import find_untested_milestones


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


def test_reviewer_numbered_dir_resolves_to_parent():
    assert find_project_root("/home/user/myproject/reviewer-1") == "/home/user/myproject"


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


def test_bugs_commit_is_no_longer_coordination_only():
    """bugs/ is not a coordination dir now that bugs use GH Issues."""
    assert is_coordination_only_files(["bugs/bug-20260215-120000.md"]) is False


def test_mixed_coordination_files_are_skipped():
    assert is_coordination_only_files(["TASKS.md", "reviews/finding-20260215-120000.md"]) is True


def test_bugs_and_reviews_mixed_not_coordination_only():
    """bugs/ files are no longer coordination-only; reviews/ still are."""
    assert is_coordination_only_files(["bugs/fixed-20260215-120000.md", "reviews/resolved-20260215-110000.md"]) is False


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


def test_agent_script_uses_explicit_model_over_env(monkeypatch):
    """When model param is provided, it overrides the env var."""
    monkeypatch.setenv("COPILOT_MODEL", "gpt-5.3-codex")
    script = build_agent_script("/path/to/reviewer", "commitwatch", "macos", model="claude-sonnet-4.6")
    assert "export COPILOT_MODEL='claude-sonnet-4.6'" in script
    assert "gpt-5.3-codex" not in script


def test_agent_script_explicit_model_when_env_unset(monkeypatch):
    """Explicit model works even when COPILOT_MODEL is not in env."""
    monkeypatch.delenv("COPILOT_MODEL", raising=False)
    script = build_agent_script("/path/to/reviewer", "commitwatch", "macos", model="claude-opus-4.6")
    assert "export COPILOT_MODEL='claude-opus-4.6'" in script


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


def test_validate_model_accepts_opus_fast_friendly_name():
    assert validate_model("Claude Opus 4.6 Fast") == "claude-opus-4.6-fast"


def test_validate_model_accepts_opus_fast_cli_name():
    assert validate_model("claude-opus-4.6-fast") == "claude-opus-4.6-fast"


def test_validate_model_accepts_sonnet_friendly_name():
    assert validate_model("Claude Sonnet 4.6") == "claude-sonnet-4.6"


def test_validate_model_accepts_sonnet_cli_name():
    assert validate_model("claude-sonnet-4.6") == "claude-sonnet-4.6"


def test_validate_model_rejects_unknown_model():
    with pytest.raises(SystemExit) as exc_info:
        validate_model("GPT-4.1")
    assert "Invalid model" in str(exc_info.value)


def test_allowed_models_accepts_both_formats():
    assert "GPT-5.3-Codex" in ALLOWED_MODELS
    assert "gpt-5.3-codex" in ALLOWED_MODELS
    assert "Claude Opus 4.6" in ALLOWED_MODELS
    assert "claude-opus-4.6" in ALLOWED_MODELS
    assert "Claude Opus 4.6 Fast" in ALLOWED_MODELS
    assert "claude-opus-4.6-fast" in ALLOWED_MODELS
    assert "Claude Sonnet 4.6" in ALLOWED_MODELS
    assert "claude-sonnet-4.6" in ALLOWED_MODELS


# --- resolve_agent_models ---

from agentic_dev.orchestrator import resolve_agent_models


def test_resolve_agent_models_all_default():
    """When no overrides given, every role gets the default model."""
    result = resolve_agent_models("claude-opus-4.6")
    assert result["builder"] == "claude-opus-4.6"
    assert result["reviewer"] == "claude-opus-4.6"
    assert result["milestone_reviewer"] == "claude-opus-4.6"
    assert result["tester"] == "claude-opus-4.6"
    assert result["validator"] == "claude-opus-4.6"
    assert result["planner"] == "claude-opus-4.6"


def test_resolve_agent_models_with_reviewer_override():
    """Reviewer override is applied; other roles get default."""
    result = resolve_agent_models("claude-opus-4.6", reviewer_model="claude-sonnet-4.6")
    assert result["reviewer"] == "claude-sonnet-4.6"
    assert result["builder"] == "claude-opus-4.6"
    assert result["planner"] == "claude-opus-4.6"


def test_resolve_agent_models_validates_overrides():
    """Invalid override model raises SystemExit."""
    with pytest.raises(SystemExit):
        resolve_agent_models("claude-opus-4.6", builder_model="invalid-model")


def test_resolve_agent_models_accepts_friendly_name_override():
    """Friendly names in overrides are normalized to CLI names."""
    result = resolve_agent_models("claude-opus-4.6", tester_model="Claude Sonnet 4.6")
    assert result["tester"] == "claude-sonnet-4.6"


def test_resolve_agent_models_multiple_overrides():
    """Multiple per-agent overrides work independently."""
    result = resolve_agent_models(
        "gpt-5.3-codex",
        reviewer_model="claude-sonnet-4.6",
        milestone_reviewer_model="claude-opus-4.6",
        validator_model="claude-sonnet-4.6",
    )
    assert result["builder"] == "gpt-5.3-codex"
    assert result["reviewer"] == "claude-sonnet-4.6"
    assert result["milestone_reviewer"] == "claude-opus-4.6"
    assert result["tester"] == "gpt-5.3-codex"
    assert result["validator"] == "claude-sonnet-4.6"
    assert result["planner"] == "gpt-5.3-codex"


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


# --- count_partitioned_open_items ---

def test_partitioned_count_single_builder_returns_all(tmp_path):
    d = tmp_path / "reviews"
    d.mkdir()
    (d / "finding-20260223-165300.md").touch()  # ends in 0
    (d / "finding-20260223-165301.md").touch()  # ends in 1
    assert count_partitioned_open_items(str(d), "finding-", "resolved-", 1, 1) == 2


def test_partitioned_count_two_builders_splits_evenly(tmp_path):
    d = tmp_path / "bugs"
    d.mkdir()
    (d / "bug-20260223-165300.md").touch()  # ends in 0 -> builder-1
    (d / "bug-20260223-165301.md").touch()  # ends in 1 -> builder-2
    (d / "bug-20260223-165302.md").touch()  # ends in 2 -> builder-1
    (d / "bug-20260223-165303.md").touch()  # ends in 3 -> builder-2
    assert count_partitioned_open_items(str(d), "bug-", "fixed-", 1, 2) == 2
    assert count_partitioned_open_items(str(d), "bug-", "fixed-", 2, 2) == 2


def test_partitioned_count_excludes_closed_items(tmp_path):
    d = tmp_path / "bugs"
    d.mkdir()
    (d / "bug-20260223-165300.md").touch()  # ends in 0 -> builder-1
    (d / "fixed-20260223-165300.md").touch()  # closes it
    (d / "bug-20260223-165302.md").touch()  # ends in 2 -> builder-1
    assert count_partitioned_open_items(str(d), "bug-", "fixed-", 1, 2) == 1


def test_partitioned_count_nonexistent_dir():
    assert count_partitioned_open_items("/nonexistent", "bug-", "fixed-", 1, 2) == 0


def test_partitioned_count_three_builders(tmp_path):
    d = tmp_path / "reviews"
    d.mkdir()
    for i in range(10):
        (d / f"finding-20260223-16530{i}.md").touch()
    # builder-1 gets 0,3,6,9 = 4 items
    assert count_partitioned_open_items(str(d), "finding-", "resolved-", 1, 3) == 4
    # builder-2 gets 1,4,7 = 3 items
    assert count_partitioned_open_items(str(d), "finding-", "resolved-", 2, 3) == 3
    # builder-3 gets 2,5,8 = 3 items
    assert count_partitioned_open_items(str(d), "finding-", "resolved-", 3, 3) == 3


# --- builder-N directory recognition ---

def test_find_project_root_recognizes_builder_numbered_dirs():
    assert find_project_root("/home/user/project/builder-1") == "/home/user/project"
    assert find_project_root("/home/user/project/builder-2") == "/home/user/project"
    assert find_project_root("/home/user/project/builder-10") == "/home/user/project"


def test_find_project_root_recognizes_milestone_reviewer():
    assert find_project_root("/home/user/project/milestone-reviewer") == "/home/user/project"


def test_find_project_root_ignores_non_matching_builder_dirs():
    # These should NOT be treated as agent directories
    assert find_project_root("/home/user/project/builder-") == "/home/user/project/builder-"
    assert find_project_root("/home/user/project/builder-abc") == "/home/user/project/builder-abc"
    assert find_project_root("/home/user/project/builder1") == "/home/user/project/builder1"


# --- coordination-only with milestones/ and BACKLOG.md ---

def test_backlog_only_commit_is_coordination_only():
    assert is_coordination_only_files(["BACKLOG.md"]) is True


def test_milestones_md_is_coordination_only():
    assert is_coordination_only_files(["milestones/milestone-01-setup.md"]) is True


def test_milestones_and_tasks_are_coordination_only():
    assert is_coordination_only_files(["TASKS.md", "milestones/milestone-02-api.md", "BACKLOG.md"]) is True


def test_milestones_with_code_is_not_coordination_only():
    assert is_coordination_only_files(["milestones/milestone-01-setup.md", "src/main.py"]) is False


def test_milestones_non_md_is_not_coordination_only():
    assert is_coordination_only_files(["milestones/data.json"]) is False


# --- check_all_builders_done_status (multi-builder sentinel) ---

def test_all_builders_done_when_all_have_sentinels():
    assert check_all_builders_done_status(
        builder_logs=["builder-1.log", "builder-2.log"],
        builder_dones={"builder-1.done", "builder-2.done"},
        log_ages={"builder-1.log": 5.0, "builder-2.log": 3.0},
        timeout_minutes=30.0,
    ) is True


def test_not_done_when_one_builder_missing_sentinel():
    assert check_all_builders_done_status(
        builder_logs=["builder-1.log", "builder-2.log"],
        builder_dones={"builder-1.done"},
        log_ages={"builder-1.log": 5.0, "builder-2.log": 3.0},
        timeout_minutes=30.0,
    ) is False


def test_done_when_missing_sentinel_but_log_is_stale():
    assert check_all_builders_done_status(
        builder_logs=["builder-1.log", "builder-2.log"],
        builder_dones={"builder-1.done"},
        log_ages={"builder-1.log": 5.0, "builder-2.log": 35.0},
        timeout_minutes=30.0,
    ) is True


def test_not_done_when_no_builder_logs_exist():
    assert check_all_builders_done_status(
        builder_logs=[],
        builder_dones=set(),
        log_ages={},
        timeout_minutes=30.0,
    ) is False


def test_single_builder_done_status():
    assert check_all_builders_done_status(
        builder_logs=["builder-1.log"],
        builder_dones={"builder-1.done"},
        log_ages={"builder-1.log": 2.0},
        timeout_minutes=30.0,
    ) is True


# --- _parse_gh_issue_numbers (pure function) ---


def test_parse_gh_issue_numbers_empty_json():
    assert _parse_gh_issue_numbers("[]") == []


def test_parse_gh_issue_numbers_valid():
    assert _parse_gh_issue_numbers('[{"number":1},{"number":5},{"number":12}]') == [1, 5, 12]


def test_parse_gh_issue_numbers_invalid_json():
    assert _parse_gh_issue_numbers("not json") == []


def test_parse_gh_issue_numbers_empty_string():
    assert _parse_gh_issue_numbers("") == []


def test_parse_gh_issue_numbers_missing_number_key():
    assert _parse_gh_issue_numbers('[{"title":"bug"}]') == []


def test_parse_gh_issue_numbers_mixed_entries():
    """Entries without a 'number' key are skipped."""
    result = _parse_gh_issue_numbers('[{"number":3},{"title":"oops"},{"number":7}]')
    assert result == [3, 7]
