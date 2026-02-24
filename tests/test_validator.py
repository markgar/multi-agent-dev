"""Tests for validator milestone filtering, sentinel integration, frontend detection, and port isolation."""

import os

from agentic_dev.validator import (
    find_unvalidated_milestones,
    detect_has_frontend,
    compute_project_ports,
    _print_validation_summary,
    _copy_playwright_traces,
)
from agentic_dev.sentinel import check_agent_idle
from agentic_dev.utils import find_project_root


# --- port isolation ---

def test_compute_project_ports_returns_two_integers():
    app_port, secondary_port = compute_project_ports("my-project")
    assert isinstance(app_port, int)
    assert isinstance(secondary_port, int)


def test_compute_project_ports_in_valid_range():
    app_port, secondary_port = compute_project_ports("bookstore-fullstack-claude")
    assert 3000 <= app_port <= 8999
    assert 3001 <= secondary_port <= 9000


def test_compute_project_ports_deterministic():
    ports1 = compute_project_ports("test-project")
    ports2 = compute_project_ports("test-project")
    assert ports1 == ports2


def test_compute_project_ports_different_names_usually_differ():
    ports_a = compute_project_ports("bookstore-fullstack-claude")
    ports_b = compute_project_ports("bookstore-fullstack-codex")
    # Hash collisions are theoretically possible but extremely unlikely
    assert ports_a != ports_b


def test_compute_project_ports_secondary_is_one_more():
    app_port, secondary_port = compute_project_ports("anything")
    assert secondary_port == app_port + 1


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


# --- frontend detection ---

def test_detect_has_frontend_true_when_package_json_at_root(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "app"}')
    assert detect_has_frontend(str(tmp_path)) is True


def test_detect_has_frontend_true_when_package_json_one_level_deep(tmp_path):
    sub = tmp_path / "frontend"
    sub.mkdir()
    (sub / "package.json").write_text('{"name": "frontend"}')
    assert detect_has_frontend(str(tmp_path)) is True


def test_detect_has_frontend_true_when_tsx_files_exist(tmp_path):
    src = tmp_path / "src" / "components"
    src.mkdir(parents=True)
    (src / "App.tsx").write_text("export default function App() {}")
    assert detect_has_frontend(str(tmp_path)) is True


def test_detect_has_frontend_true_when_vue_files_exist(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.vue").write_text("<template><div/></template>")
    assert detect_has_frontend(str(tmp_path)) is True


def test_detect_has_frontend_true_when_spec_mentions_react(tmp_path):
    (tmp_path / "SPEC.md").write_text("## Tech Stack\n- React frontend with TypeScript\n")
    assert detect_has_frontend(str(tmp_path)) is True


def test_detect_has_frontend_true_when_spec_mentions_frontend(tmp_path):
    (tmp_path / "SPEC.md").write_text("## Architecture\nThe frontend serves a dashboard.\n")
    assert detect_has_frontend(str(tmp_path)) is True


def test_detect_has_frontend_false_for_api_only_project(tmp_path):
    (tmp_path / "app.py").write_text("from flask import Flask")
    (tmp_path / "SPEC.md").write_text("## Tech Stack\n- Python Flask REST API\n- PostgreSQL database\n")
    assert detect_has_frontend(str(tmp_path)) is False


def test_detect_has_frontend_false_for_empty_directory(tmp_path):
    assert detect_has_frontend(str(tmp_path)) is False


def test_detect_has_frontend_false_when_no_spec(tmp_path):
    (tmp_path / "Program.cs").write_text("Console.WriteLine();")
    assert detect_has_frontend(str(tmp_path)) is False


# --- validation summary ---

def test_print_validation_summary_counts_categories(tmp_path, monkeypatch):
    """_print_validation_summary parses result lines and doesn't crash."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    results = logs_dir / "validation-auth-api.txt"
    results.write_text(
        "PASS [A] Container builds successfully\n"
        "PASS [A] Health endpoint returns 200\n"
        "FAIL [A] Login endpoint returns 401 for bad creds\n"
        "PASS [B] Members API requirement covered\n"
        "FAIL [C] Fixed bug #42 still failing\n"
        "PASS [UI] Landing page renders\n"
        "FAIL [UI] Navigation menu broken\n"
        "PASS Misc check\n"
    )
    monkeypatch.setattr("agentic_dev.validator.resolve_logs_dir", lambda: str(logs_dir))
    # Should not raise
    _print_validation_summary("Auth API")


def test_print_validation_summary_handles_missing_file(tmp_path, monkeypatch):
    """_print_validation_summary handles a missing results file gracefully."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    monkeypatch.setattr("agentic_dev.validator.resolve_logs_dir", lambda: str(logs_dir))
    # Should not raise
    _print_validation_summary("nonexistent-milestone")


def test_print_validation_summary_handles_empty_file(tmp_path, monkeypatch):
    """_print_validation_summary handles an empty results file gracefully."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    results = logs_dir / "validation-empty.txt"
    results.write_text("")
    monkeypatch.setattr("agentic_dev.validator.resolve_logs_dir", lambda: str(logs_dir))
    _print_validation_summary("empty")


# --- playwright trace copying ---

def test_copy_playwright_traces_copies_existing_dirs(tmp_path, monkeypatch):
    """_copy_playwright_traces copies report and traces when dirs exist."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    monkeypatch.setattr("agentic_dev.validator.resolve_logs_dir", lambda: str(logs_dir))
    monkeypatch.chdir(tmp_path)

    report_dir = tmp_path / "e2e" / "playwright-report"
    report_dir.mkdir(parents=True)
    (report_dir / "index.html").write_text("<html/>")

    traces_dir = tmp_path / "e2e" / "test-results"
    traces_dir.mkdir(parents=True)
    (traces_dir / "trace.zip").write_text("data")

    _copy_playwright_traces("UI Shell")

    dest = logs_dir / "playwright-ui-shell"
    assert (dest / "report" / "index.html").exists()
    assert (dest / "traces" / "trace.zip").exists()


def test_copy_playwright_traces_handles_missing_dirs(tmp_path, monkeypatch):
    """_copy_playwright_traces does nothing when source dirs don't exist."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    monkeypatch.setattr("agentic_dev.validator.resolve_logs_dir", lambda: str(logs_dir))
    monkeypatch.chdir(tmp_path)
    # Should not raise
    _copy_playwright_traces("no-frontend")
