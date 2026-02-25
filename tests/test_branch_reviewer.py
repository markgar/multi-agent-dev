"""Tests for branch-attached reviewer infrastructure.

Covers: sentinel per-builder checkpoints, branch-review-head signals,
git_helpers branch detection, utils reviewer-N dir recognition,
builder merge gate, and watcher branch-mode routing.
"""

import os
import tempfile

import pytest

from agentic_dev.git_helpers import parse_ls_remote_output
from agentic_dev.sentinel import (
    check_agent_idle,
    clear_branch_review_head,
    load_branch_review_head,
    load_reviewer_checkpoint,
    save_branch_review_head,
    save_reviewer_checkpoint,
)
from agentic_dev.utils import find_project_root


# ============================================
# sentinel: per-builder reviewer checkpoints
# ============================================


def test_save_load_reviewer_checkpoint_per_builder(tmp_path, monkeypatch):
    """Per-builder mode uses reviewer-N.branch-checkpoint."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    save_reviewer_checkpoint("def456", builder_id=1)
    save_reviewer_checkpoint("ghi789", builder_id=2)
    assert load_reviewer_checkpoint(builder_id=1) == "def456"
    assert load_reviewer_checkpoint(builder_id=2) == "ghi789"
    # Correct filenames
    assert os.path.exists(tmp_path / "reviewer-1.branch-checkpoint")
    assert os.path.exists(tmp_path / "reviewer-2.branch-checkpoint")


def test_save_load_reviewer_checkpoint_default_is_builder_1(tmp_path, monkeypatch):
    """Default argument (no builder_id) uses builder 1."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    save_reviewer_checkpoint("aaa111")
    assert load_reviewer_checkpoint() == "aaa111"
    assert os.path.exists(tmp_path / "reviewer-1.branch-checkpoint")


def test_load_reviewer_checkpoint_missing_file(tmp_path, monkeypatch):
    """Returns empty string when no checkpoint file exists."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    assert load_reviewer_checkpoint(builder_id=5) == ""


# ============================================
# sentinel: branch-review-head signals
# ============================================


def test_save_load_branch_review_head(tmp_path, monkeypatch):
    """Round-trip write/read of branch-review-head signal."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    save_branch_review_head(1, "builder-1/milestone-01", "abc123")
    branch, sha = load_branch_review_head(1)
    assert branch == "builder-1/milestone-01"
    assert sha == "abc123"


def test_load_branch_review_head_missing(tmp_path, monkeypatch):
    """Returns empty tuple when no signal file exists."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    branch, sha = load_branch_review_head(99)
    assert branch == ""
    assert sha == ""


def test_clear_branch_review_head(tmp_path, monkeypatch):
    """Clearing removes the signal file."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    save_branch_review_head(1, "builder-1/milestone-01", "abc123")
    assert os.path.exists(tmp_path / "reviewer-1.branch-head")
    clear_branch_review_head(1)
    assert not os.path.exists(tmp_path / "reviewer-1.branch-head")
    branch, sha = load_branch_review_head(1)
    assert branch == ""
    assert sha == ""


def test_clear_branch_review_head_no_file(tmp_path, monkeypatch):
    """Clearing when no file exists does not raise."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    clear_branch_review_head(1)  # should not raise


def test_branch_review_head_per_builder_isolation(tmp_path, monkeypatch):
    """Each builder has its own independent signal file."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    save_branch_review_head(1, "builder-1/milestone-01", "sha1")
    save_branch_review_head(2, "builder-2/milestone-02", "sha2")
    b1_branch, b1_sha = load_branch_review_head(1)
    b2_branch, b2_sha = load_branch_review_head(2)
    assert b1_branch == "builder-1/milestone-01"
    assert b1_sha == "sha1"
    assert b2_branch == "builder-2/milestone-02"
    assert b2_sha == "sha2"


# ============================================
# git_helpers: parse_ls_remote_output
# ============================================


def test_parse_ls_remote_output_single_branch():
    output = "abc123\trefs/heads/builder-1/milestone-01\n"
    assert parse_ls_remote_output(output) == ["builder-1/milestone-01"]


def test_parse_ls_remote_output_multiple_branches():
    output = (
        "abc123\trefs/heads/builder-1/milestone-02\n"
        "def456\trefs/heads/builder-1/milestone-01\n"
    )
    # Should be sorted
    assert parse_ls_remote_output(output) == [
        "builder-1/milestone-01",
        "builder-1/milestone-02",
    ]


def test_parse_ls_remote_output_empty():
    assert parse_ls_remote_output("") == []
    assert parse_ls_remote_output("\n") == []


def test_parse_ls_remote_output_malformed_lines():
    output = "not-a-valid-line\nabc123\trefs/heads/builder-1/milestone-01\n"
    assert parse_ls_remote_output(output) == ["builder-1/milestone-01"]


def test_parse_ls_remote_output_non_heads_ref():
    output = "abc123\trefs/tags/v1.0\n"
    assert parse_ls_remote_output(output) == []


# ============================================
# utils: find_project_root recognizes reviewer-N
# ============================================


def test_find_project_root_recognizes_reviewer_numbered_dirs():
    assert find_project_root("/home/user/project/reviewer-1") == "/home/user/project"
    assert find_project_root("/home/user/project/reviewer-2") == "/home/user/project"
    assert find_project_root("/home/user/project/reviewer-10") == "/home/user/project"


def test_find_project_root_ignores_non_matching_reviewer_dirs():
    assert find_project_root("/home/user/project/reviewer-") == "/home/user/project/reviewer-"
    assert find_project_root("/home/user/project/reviewer-abc") == "/home/user/project/reviewer-abc"
    assert find_project_root("/home/user/project/reviewer1") == "/home/user/project/reviewer1"


# ============================================
# sentinel: are_agents_idle with reviewer-N logs
# ============================================


def test_are_agents_idle_with_reviewer_numbered_logs(tmp_path, monkeypatch):
    """Discovery-based idle check finds reviewer-N.log files."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))

    # Create reviewer-1.log and reviewer-2.log with old mtimes
    import time
    for name in ["reviewer-1.log", "reviewer-2.log", "milestone-reviewer.log", "tester.log", "validator.log"]:
        path = tmp_path / name
        path.write_text("log content")
        # Set mtime to 200 seconds ago (idle threshold is 120s)
        old_time = time.time() - 200
        os.utime(path, (old_time, old_time))

    from agentic_dev.sentinel import are_agents_idle
    assert are_agents_idle() is True


def test_are_agents_idle_false_when_reviewer_log_fresh(tmp_path, monkeypatch):
    """Should return False when a reviewer-N.log is fresh."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))

    import time
    # reviewer-1.log is old
    path1 = tmp_path / "reviewer-1.log"
    path1.write_text("log content")
    old_time = time.time() - 200
    os.utime(path1, (old_time, old_time))

    # reviewer-2.log is fresh (just created)
    path2 = tmp_path / "reviewer-2.log"
    path2.write_text("log content")

    # Other logs are old
    for name in ["milestone-reviewer.log", "tester.log", "validator.log"]:
        path = tmp_path / name
        path.write_text("log content")
        os.utime(path, (old_time, old_time))

    from agentic_dev.sentinel import are_agents_idle
    assert are_agents_idle() is False


# ============================================
# builder: _wait_for_reviewer (pure logic test)
# ============================================


def test_wait_for_reviewer_returns_true_when_caught_up(tmp_path, monkeypatch):
    """Merge gate passes immediately when reviewer has reviewed all commits."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    # Simulate reviewer has caught up
    save_branch_review_head(1, "builder-1/milestone-01", "deadbeef")

    # Mock run_cmd to return the branch HEAD
    from unittest.mock import MagicMock
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "deadbeef\n"
    monkeypatch.setattr("agentic_dev.builder.run_cmd", lambda *args, **kwargs: mock_result)
    monkeypatch.setattr("agentic_dev.builder.log", lambda *args, **kwargs: None)

    from agentic_dev.builder import _wait_for_reviewer
    result = _wait_for_reviewer(1, "builder-1/milestone-01", "builder-1", timeout=5)
    assert result is True


def test_wait_for_reviewer_returns_false_on_timeout(tmp_path, monkeypatch):
    """Merge gate times out when reviewer hasn't caught up."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    # Reviewer's signal is for a different SHA
    save_branch_review_head(1, "builder-1/milestone-01", "oldsha")

    from unittest.mock import MagicMock
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "newsha\n"
    monkeypatch.setattr("agentic_dev.builder.run_cmd", lambda *args, **kwargs: mock_result)
    monkeypatch.setattr("agentic_dev.builder.log", lambda *args, **kwargs: None)
    monkeypatch.setattr("agentic_dev.builder._REVIEWER_MERGE_POLL_INTERVAL", 0.1)

    from agentic_dev.builder import _wait_for_reviewer
    result = _wait_for_reviewer(1, "builder-1/milestone-01", "builder-1", timeout=0.5)
    assert result is False


def test_wait_for_reviewer_skips_when_head_unknown(tmp_path, monkeypatch):
    """Merge gate passes when HEAD can't be determined."""
    from unittest.mock import MagicMock
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    monkeypatch.setattr("agentic_dev.builder.run_cmd", lambda *args, **kwargs: mock_result)
    monkeypatch.setattr("agentic_dev.builder.log", lambda *args, **kwargs: None)

    from agentic_dev.builder import _wait_for_reviewer
    result = _wait_for_reviewer(1, "builder-1/milestone-01", "builder-1")
    assert result is True


def test_wait_for_reviewer_wrong_branch_does_not_match(tmp_path, monkeypatch):
    """Merge gate does not match if reviewer signal is for a different branch."""
    monkeypatch.setattr("agentic_dev.sentinel.resolve_logs_dir", lambda: str(tmp_path))
    save_branch_review_head(1, "builder-1/milestone-00", "deadbeef")

    from unittest.mock import MagicMock
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "deadbeef\n"
    monkeypatch.setattr("agentic_dev.builder.run_cmd", lambda *args, **kwargs: mock_result)
    monkeypatch.setattr("agentic_dev.builder.log", lambda *args, **kwargs: None)
    monkeypatch.setattr("agentic_dev.builder._REVIEWER_MERGE_POLL_INTERVAL", 0.1)

    from agentic_dev.builder import _wait_for_reviewer
    result = _wait_for_reviewer(1, "builder-1/milestone-01", "builder-1", timeout=0.5)
    assert result is False


# ============================================
# prompts: branch-attached prompts exist and have correct placeholders
# ============================================


def test_branch_commit_prompt_has_branch_name_placeholder():
    from agentic_dev.prompts import REVIEWER_BRANCH_COMMIT_PROMPT
    assert "{branch_name}" in REVIEWER_BRANCH_COMMIT_PROMPT
    assert "{commit_sha}" in REVIEWER_BRANCH_COMMIT_PROMPT
    assert "{prev_sha}" in REVIEWER_BRANCH_COMMIT_PROMPT


def test_branch_batch_prompt_has_branch_name_placeholder():
    from agentic_dev.prompts import REVIEWER_BRANCH_BATCH_PROMPT
    assert "{branch_name}" in REVIEWER_BRANCH_BATCH_PROMPT
    assert "{base_sha}" in REVIEWER_BRANCH_BATCH_PROMPT
    assert "{head_sha}" in REVIEWER_BRANCH_BATCH_PROMPT
    assert "{commit_count}" in REVIEWER_BRANCH_BATCH_PROMPT


def test_branch_prompts_can_be_formatted():
    """Ensure the branch prompts accept .format() without KeyError."""
    from agentic_dev.prompts import REVIEWER_BRANCH_COMMIT_PROMPT, REVIEWER_BRANCH_BATCH_PROMPT
    result = REVIEWER_BRANCH_COMMIT_PROMPT.format(
        branch_name="builder-1/milestone-01",
        prev_sha="abc12345",
        commit_sha="def67890",
    )
    assert "builder-1/milestone-01" in result
    assert "abc12345" in result

    result = REVIEWER_BRANCH_BATCH_PROMPT.format(
        branch_name="builder-2/milestone-03",
        base_sha="aaa11111",
        head_sha="bbb22222",
        commit_count=5,
    )
    assert "builder-2/milestone-03" in result
    assert "5" in result


# ============================================
# terminal: build_agent_script with reviewer commands
# ============================================


def test_build_agent_script_reviewer_command():
    """Terminal script propagates the commitwatch --builder-id command."""
    from agentic_dev.terminal import build_agent_script
    script = build_agent_script("/path/to/reviewer-1", "commitwatch --builder-id 1", "macos")
    assert "commitwatch --builder-id 1" in script
    assert "reviewer-1" in script
