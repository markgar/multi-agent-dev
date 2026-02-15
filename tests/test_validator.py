"""Tests for validator milestone filtering and sentinel integration."""

from agentic_dev.validator import find_unvalidated_milestones
from agentic_dev.sentinel import check_agent_idle
from agentic_dev.utils import find_project_root


# --- validator milestone filtering ---

def test_find_unvalidated_milestones_excludes_already_validated():
    boundaries = [
        {"name": "Scaffolding", "start_sha": "aaa", "end_sha": "bbb"},
        {"name": "API Endpoints", "start_sha": "bbb", "end_sha": "ccc"},
        {"name": "Auth", "start_sha": "ccc", "end_sha": "ddd"},
    ]
    validated = {"Scaffolding", "API Endpoints"}
    result = find_unvalidated_milestones(boundaries, validated)
    assert len(result) == 1
    assert result[0]["name"] == "Auth"


def test_find_unvalidated_milestones_returns_all_when_none_validated():
    boundaries = [
        {"name": "Scaffolding", "start_sha": "aaa", "end_sha": "bbb"},
        {"name": "API Endpoints", "start_sha": "bbb", "end_sha": "ccc"},
    ]
    validated = set()
    result = find_unvalidated_milestones(boundaries, validated)
    assert len(result) == 2
    assert result[0]["name"] == "Scaffolding"
    assert result[1]["name"] == "API Endpoints"


def test_find_unvalidated_milestones_returns_empty_when_all_validated():
    boundaries = [
        {"name": "Scaffolding", "start_sha": "aaa", "end_sha": "bbb"},
    ]
    validated = {"Scaffolding"}
    result = find_unvalidated_milestones(boundaries, validated)
    assert len(result) == 0


def test_find_unvalidated_milestones_handles_empty_boundaries():
    result = find_unvalidated_milestones([], {"Scaffolding"})
    assert len(result) == 0


# --- validator dir resolves to project root ---

def test_validator_dir_resolves_to_parent():
    assert find_project_root("/home/user/myproject/validator") == "/home/user/myproject"


# --- agent idle check works for validator log ---

def test_validator_log_idle_when_old():
    assert check_agent_idle(log_exists=True, log_age_seconds=60, idle_threshold=30) is True


def test_validator_log_not_idle_when_fresh():
    assert check_agent_idle(log_exists=True, log_age_seconds=10, idle_threshold=30) is False


def test_validator_log_idle_when_missing():
    assert check_agent_idle(log_exists=False, log_age_seconds=0, idle_threshold=30) is True
