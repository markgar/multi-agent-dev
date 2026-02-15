"""Tests for CLI directory resolution logic."""

import os

from agent.orchestrator import _resolve_directory


# --- _resolve_directory ---

def test_resolve_directory_returns_absolute_path():
    """Relative path is resolved to absolute."""
    result = _resolve_directory("my-project")
    expected = os.path.join(os.getcwd(), "my-project")
    assert result == expected


def test_resolve_directory_expands_home():
    """Tilde is expanded to the home directory."""
    result = _resolve_directory("~/my-project")
    assert result.startswith(os.path.expanduser("~"))
    assert result.endswith("my-project")
    assert "~" not in result


def test_resolve_directory_preserves_absolute_path(tmp_path):
    """Absolute path is returned as-is (normalized)."""
    result = _resolve_directory(str(tmp_path / "my-project"))
    assert result == str(tmp_path / "my-project")


def test_resolve_directory_normalizes_path():
    """Paths with .. and . are normalized."""
    result = _resolve_directory("./foo/../bar")
    assert ".." not in result
    assert result.endswith("bar")
