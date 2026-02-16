"""Tests for validator milestone filtering, sentinel integration, and frontend detection."""

import os

from agentic_dev.validator import find_unvalidated_milestones, detect_has_frontend
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
